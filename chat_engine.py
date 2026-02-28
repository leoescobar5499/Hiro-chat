# ═══════════════════════════════════════════════════════════════════════════
# CHAT_ENGINE.PY — Motor del chat
# _procesar_mensaje, _procesar_continuar, verificar_eventos_automaticos
# El archivo que tocás cuando querés cambiar cómo responde el personaje.
# ═══════════════════════════════════════════════════════════════════════════

import json
import threading

from utils import (
    now_argentina,
    llamada_mistral_segura,
    paths, get_personaje_activo_id,
    _get_conn,
    buscar_en_internet,
)
from memoria import (
    obtener_contexto, obtener_system_prompt, actualizar_fase,
    extraer_informacion_con_ia, guardar_memoria_permanente,
    agregar_embedding, _enriquecer_episodio,
    _debe_regenerar_sintesis, _ejecutar_sintesis,
    get_faiss_ntotal,
    extraer_menciones_casuales, _detectar_y_cerrar_hilos,
    detectar_emocion,
    generar_backstory_automatico,
    generar_diario_automatico,
    actualizar_evolucion_automatica,
    _get_modo_memoria,
)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER: RECORTE DE PALABRAS (compartido entre _procesar_mensaje y _procesar_continuar)
# ─────────────────────────────────────────────────────────────────────────────


def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-small-latest'
    except Exception:
        return 'mistral-small-latest'


def _recortar_respuesta(respuesta, limite=None):
    """
    Corta la respuesta según el modo activo:
      - compañero: 120 palabras (conversación fluida)
      - roleplay:  220 palabras (escenas narrativas necesitan más espacio)
    Si se pasa limite explícito, lo usa directamente.
    """
    if limite is None:
        try:
            modo = _get_modo_memoria()
            limite = 220 if modo == 'roleplay' else 120
        except Exception:
            limite = 120

    palabras = respuesta.split()
    if len(palabras) <= limite:
        return respuesta
    # Cortar en la última oración completa antes del límite
    oraciones = respuesta.split('. ')
    resultado, total = [], 0
    for o in oraciones:
        cant = len(o.split())
        if total + cant > limite:
            break
        resultado.append(o)
        total += cant
    if resultado:
        texto = '. '.join(resultado)
        if not texto.endswith('.'):
            texto += '.'
        return texto
    return ' '.join(palabras[:limite]) + '...'


def _get_escenario_id_actual():
    """Devuelve el id del escenario activo, o None."""
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM escenarios WHERE activo=1 LIMIT 1')
            r = cursor.fetchone()
            return r[0] if r else None
    except Exception:
        return None


def _detectar_query_busqueda(mensaje):
    """
    Mini-llamada rápida con mistral-small para decidir si el mensaje necesita
    una búsqueda en internet. Solo activa en modo compañero y si hay al menos
    una key de búsqueda configurada.
    Devuelve la query a buscar (str) o None si no hace falta.
    """
    try:
        # Solo en modo compañero
        if _get_modo_memoria() != 'compañero':
            return None

        # Solo si hay alguna key configurada y búsqueda habilitada
        from utils import cargar_config_apis
        cfg    = cargar_config_apis()
        search = cfg.get('search', {})
        if not search.get('enabled', False):
            return None
        if not any([
            search.get('serpapi_key', '').strip(),
            search.get('brave_key', '').strip(),
            search.get('tavily_key', '').strip(),
        ]):
            return None

        # Usar el modelo de extracción configurado (respeta el proveedor activo)
        modelo_extraccion = _get_modelo('extraction')
        resp = llamada_mistral_segura(
            model=modelo_extraccion,
            messages=[{
                'role': 'user',
                'content': (
                    f'¿Este mensaje requiere buscar datos concretos en internet para responder bien?\n'
                    f'Mensaje: "{mensaje}"\n\n'
                    f'Responde SOLO con JSON sin markdown:\n'
                    f'{{"necesita_busqueda": true/false, "query": "qué buscarías (máx 8 palabras)"}}\n\n'
                    f'BUSCAR SÍ: series, películas, canciones, artistas, libros, videojuegos, eventos, noticias, datos concretos, temporadas, elenco, fechas de lanzamiento, letras de canciones.\n'
                    f'BUSCAR NO: conversación cotidiana, emociones, opiniones, roleplay, saludos, preguntas sobre el personaje.'
                )
            }],
            max_tokens=80
        )
        from memoria._helpers import _limpiar_json
        datos = _limpiar_json(resp.choices[0].message.content.strip(), esperar_array=False)
        if datos and datos.get('necesita_busqueda') and datos.get('query', '').strip():
            return datos['query'].strip()
    except Exception as e:
        print(f"⚠️ Error detector búsqueda: {e}")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 7: PROCESAMIENTO DE MENSAJES
# ─────────────────────────────────────────────────────────────────────────────

def _procesar_mensaje(mensaje):
    """Núcleo del chat: guarda, llama a Mistral, guarda respuesta, actualiza memoria."""
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO mensajes (rol, contenido, timestamp) VALUES (?, ?, ?)',
                       ('user', mensaje, now_argentina().isoformat()))
        cursor.execute('UPDATE relacion SET ultimo_mensaje = ? WHERE id = 1',
                       (now_argentina().isoformat(),))
        # Roleplay necesita más contexto de sesión para mantener coherencia narrativa.
        # Compañero con 10 mensajes está bien; roleplay sube a 20.
        historial_limite = 20 if _get_modo_memoria() == 'roleplay' else 10
        cursor.execute('SELECT rol, contenido FROM mensajes ORDER BY id DESC LIMIT ?', (historial_limite,))
        historial = list(reversed(cursor.fetchall()))

    contexto      = obtener_contexto(mensaje)
    system_prompt = obtener_system_prompt(mensaje)  # ← pasa el mensaje actual

    # ── Búsqueda en internet (modo compañero + búsqueda habilitada) ───────────
    snippet_web = None
    query_busqueda = _detectar_query_busqueda(mensaje)
    if query_busqueda:
        print(f"🔍 Buscando: '{query_busqueda}'")
        snippet_web = buscar_en_internet(query_busqueda)
        if snippet_web:
            system_prompt += (
                f"\n\n───────────────────────────────\n"
                f"INFORMACIÓN ENCONTRADA EN INTERNET (usala naturalmente, como si ya lo supieras, sin mencionar que buscaste):\n"
                f"{snippet_web}\n"
                f"───────────────────────────────"
            )

    messages = [
        {'role': 'system', 'content': system_prompt + (f"\n\n{contexto}" if contexto else "")},
    ]
    for rol, contenido in historial[:-1]:
        messages.append({'role': 'assistant' if rol == 'assistant' else 'user', 'content': contenido})
    messages.append({'role': 'user', 'content': mensaje})

    response  = llamada_mistral_segura(model=_get_modelo("chat"), messages=messages, max_tokens=600, temperature=0.88)
    respuesta = _recortar_respuesta(response.choices[0].message.content.strip())

    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO mensajes (rol, contenido, timestamp) VALUES (?, ?, ?)',
                       ('assistant', respuesta, now_argentina().isoformat()))

    # ── Todo el post-proceso en background — el usuario ya tiene su respuesta ──
    def _post_proceso(mensaje, respuesta, escenario_id_actual):
        try:
            _detectar_y_cerrar_hilos(mensaje)
        except Exception as e:
            print(f"⚠️ Error cerrando hilos: {e}")

        try:
            datos = extraer_informacion_con_ia(mensaje, respuesta)
            if datos:
                guardar_memoria_permanente(datos)
        except Exception as e:
            print(f"⚠️ Error extracción: {e}")

        try:
            extraer_menciones_casuales(mensaje, respuesta)
        except Exception as e:
            print(f"⚠️ Error menciones casuales: {e}")

        try:
            embedding_id = agregar_embedding(f"Usuario: {mensaje}\nPersonaje: {respuesta}", 'episodio')
            with _get_conn(paths()['db']) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT COUNT(*) FROM memoria_episodica
                       WHERE contenido_usuario = ?
                       AND datetime(fecha) >= datetime('now', '-60 seconds')""",
                    (mensaje,)
                )
                if cursor.fetchone()[0] == 0:
                    cursor.execute('''INSERT OR IGNORE INTO memoria_episodica
                        (contenido_usuario, contenido_hiro, fecha, embedding_id, escenario_id)
                        VALUES (?, ?, ?, ?, ?)''',
                        (mensaje, respuesta, now_argentina().isoformat(),
                         embedding_id, escenario_id_actual))
                    episodio_id_nuevo = cursor.lastrowid
                else:
                    episodio_id_nuevo = None
            if episodio_id_nuevo:
                try:
                    _enriquecer_episodio(episodio_id_nuevo, mensaje, respuesta)
                except Exception as e:
                    print(f"⚠️ Error enriquecimiento episódico: {e}")
        except Exception as e:
            print(f"⚠️ Error episodio: {e}")

        try:
            detectar_emocion(mensaje)
        except Exception as e:
            print(f"⚠️ Error emoción: {e}")

        # ── Conteo de mensajes del usuario (base para todos los triggers) ──
        try:
            with _get_conn(paths()['db']) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM mensajes WHERE rol='user'")
                msg_count = cursor.fetchone()[0]
        except Exception as e:
            print(f"⚠️ Error contando mensajes: {e}")
            msg_count = 0

        # ── Backstory cada 50 mensajes ─────────────────────────────────────
        try:
            if msg_count > 0 and msg_count % 50 == 0:
                generar_backstory_automatico()
        except Exception as e:
            print(f"⚠️ Error backstory: {e}")

        # ── Diario automático: nueva sesión (gap > 3hs) o cada 25 mensajes ─
        try:
            _disparar_diario = False

            # Trigger 1: nueva sesión (gap > 3hs desde el penúltimo mensaje)
            with _get_conn(paths()['db']) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT timestamp FROM mensajes WHERE rol='user' ORDER BY id DESC LIMIT 2"
                )
                rows = cursor.fetchall()
            if len(rows) >= 2:
                from datetime import datetime as _dt
                prev_ts = str(rows[1][0]).replace(' ', 'T').split('.')[0]
                dt_prev = _dt.fromisoformat(prev_ts)
                if dt_prev.tzinfo is None:
                    dt_prev = dt_prev.replace(tzinfo=now_argentina().tzinfo)
                horas_gap = (now_argentina() - dt_prev).total_seconds() / 3600
                if horas_gap >= 3:
                    _disparar_diario = True

            # Trigger 2: cada 25 mensajes del usuario
            if msg_count > 0 and msg_count % 25 == 0:
                _disparar_diario = True

            if _disparar_diario:
                generar_diario_automatico()
        except Exception as e:
            print(f"⚠️ Error diario automático: {e}")

        # ── Evolución de fase: al subir de fase o cada 40 mensajes ────────
        try:
            fase_actual = actualizar_fase()   # ya se llama abajo, pero necesitamos el valor

            _disparar_evolucion = False

            # Trigger 1: la fase subió respecto a la última evolución guardada
            with _get_conn(paths()['db']) as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        'SELECT fase FROM evolucion_fases ORDER BY fase DESC LIMIT 1'
                    )
                    row = cursor.fetchone()
                    fase_guardada = row[0] if row else 0
                    if fase_actual > fase_guardada:
                        _disparar_evolucion = True
                except Exception:
                    _disparar_evolucion = True   # tabla vacía → generar

            # Trigger 2: cada 40 mensajes
            if msg_count > 0 and msg_count % 40 == 0:
                _disparar_evolucion = True

            if _disparar_evolucion:
                actualizar_evolucion_automatica(fase_actual)
        except Exception as e:
            print(f"⚠️ Error evolución automática: {e}")

        try:
            debe, motivo = _debe_regenerar_sintesis()
            if debe:
                _ejecutar_sintesis(motivo)
        except Exception as e:
            print(f"⚠️ Error síntesis: {e}")

    escenario_id_actual = _get_escenario_id_actual()
    actualizar_fase()
    threading.Thread(
        target=_post_proceso,
        args=(mensaje, respuesta, escenario_id_actual),
        daemon=True
    ).start()

    return respuesta



# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 7b: CONTINUAR — el personaje sigue sin input del usuario
# ─────────────────────────────────────────────────────────────────────────────

def _procesar_continuar():
    """
    El personaje continúa sin que el usuario haya escrito nada.
    - NO guarda ningún mensaje del usuario.
    - Extrae hechos de la respuesta, pero SIN apariencia física.
    """
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        historial_limite = 20 if _get_modo_memoria() == 'roleplay' else 10
        cursor.execute('SELECT rol, contenido FROM mensajes ORDER BY id DESC LIMIT ?', (historial_limite,))
        historial = list(reversed(cursor.fetchall()))

    system_prompt = obtener_system_prompt()  # sin mensaje — calibración neutral
    contexto      = obtener_contexto('')

    instruccion = (
        "El usuario no ha escrito nada nuevo. Continuá naturalmente desde tu último mensaje "
        "— seguí la escena, ampliá lo que dijiste, o avanzá la situación. No esperés input del usuario."
    )
    messages = [
        {'role': 'system', 'content': system_prompt + (f"\n\n{contexto}" if contexto else "") + f"\n\n{instruccion}"},
    ]
    for rol, contenido in historial:
        messages.append({'role': 'assistant' if rol == 'assistant' else 'user', 'content': contenido})
    if messages[-1]['role'] == 'assistant':
        messages.append({'role': 'user', 'content': '[continuar]'})

    response  = llamada_mistral_segura(model=_get_modelo("chat"), messages=messages, max_tokens=600, temperature=0.88)
    respuesta = _recortar_respuesta(response.choices[0].message.content.strip())

    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO mensajes (rol, contenido, timestamp) VALUES (?, ?, ?)',
                       ('assistant', respuesta, now_argentina().isoformat()))

    # En modo roleplay no tiene sentido extraer con mensaje vacío — genera falsos positivos.
    # En modo compañero sí puede haber info útil en la respuesta del personaje.
    modo_actual = _get_modo_memoria()
    if modo_actual != 'roleplay':
        try:
            datos = extraer_informacion_con_ia('', respuesta)
            categorias_excluidas = {'apariencia', 'estado_actual', 'momentos'}
            datos_filtrados = [d for d in datos if d.get('categoria') not in categorias_excluidas]
            if datos_filtrados:
                guardar_memoria_permanente(datos_filtrados)
        except Exception as e:
            print(f"⚠️ Error extracción continuar: {e}")

    try:
        embedding_id = agregar_embedding(f"Personaje continúa: {respuesta}", 'episodio_continuar')
        escenario_id_actual = _get_escenario_id_actual()

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT OR IGNORE INTO memoria_episodica
                (contenido_usuario, contenido_hiro, fecha, embedding_id, escenario_id)
                VALUES (?, ?, ?, ?, ?)''',
                ('[continuar]', respuesta, now_argentina().isoformat(),
                 embedding_id, escenario_id_actual))
            episodio_id_cont = cursor.lastrowid

        if episodio_id_cont:
            try:
                _enriquecer_episodio(episodio_id_cont, '[continuar]', respuesta)
            except Exception as e:
                print(f"⚠️ Error enriquecimiento episódico (continuar): {e}")
    except Exception as e:
        print(f"⚠️ Error episodio continuar: {e}")

    actualizar_fase()
    return respuesta


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 8: EVENTOS AUTOMÁTICOS
# ─────────────────────────────────────────────────────────────────────────────

def verificar_eventos_automaticos():
    """
    Revisa todos los eventos activos y dispara los que correspondan.
    Ahora soporta:
      - fecha DD-MM (anual) o DD-MM-AAAA (única vez), con hora opcional HH:MM
      - aviso_dias: avisa N días antes del evento
      - seguimiento: pregunta "¿cómo te fue?" después de que pasó la hora del evento
    """
    from datetime import datetime as _dt, timedelta as _td

    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, nombre, descripcion, tipo, valor,
                   hora, aviso_dias, seguimiento,
                   aviso_disparado, seguimiento_disparado
            FROM eventos
            WHERE activo=1
        """)
        pendientes = cursor.fetchall()
        ahora = now_argentina()
        recien_disparados = []
        cursor.execute("SELECT COUNT(*) FROM mensajes")
        total_msgs = cursor.fetchone()[0]

        for row in pendientes:
            (eid, nombre, descripcion, tipo, valor,
             hora, aviso_dias, seguimiento,
             aviso_disparado, seguimiento_disparado) = row

            aviso_dias         = int(aviso_dias or 0)
            aviso_disparado    = int(aviso_disparado or 0)
            seguimiento_disparado = int(seguimiento_disparado or 0)

            # ── Tipo MENSAJES ─────────────────────────────────────────────
            if tipo == "mensajes" and valor:
                try:
                    disparado_flag = cursor.execute(
                        "SELECT disparado FROM eventos WHERE id=?", (eid,)
                    ).fetchone()[0]
                    if not disparado_flag and total_msgs >= int(valor):
                        cursor.execute(
                            "UPDATE eventos SET disparado=1, fecha_disparo=? WHERE id=?",
                            (ahora.isoformat(), eid)
                        )
                        recien_disparados.append({
                            "nombre": nombre, "descripcion": descripcion, "subtipo": "evento"
                        })
                        print(f"✨ Evento disparado (mensajes): {nombre}")
                except Exception as e:
                    print(f"⚠️ Error evento mensajes {eid}: {e}")
                continue

            # ── Tipo MANUAL ───────────────────────────────────────────────
            if tipo == "manual":
                continue

            # ── Tipo FECHA ────────────────────────────────────────────────
            if tipo == "fecha" and valor:
                try:
                    partes = valor.strip().split("-")
                    # Soporta DD-MM y DD-MM-AAAA
                    dia, mes = int(partes[0]), int(partes[1])
                    anio_evento = int(partes[2]) if len(partes) >= 3 else None

                    # Fecha del evento este año (o el año especificado)
                    anio_base = anio_evento if anio_evento else ahora.year
                    try:
                        fecha_evento = _dt(anio_base, mes, dia, tzinfo=ahora.tzinfo)
                    except ValueError:
                        continue  # fecha inválida

                    # Si el evento ya pasó este año y es recurrente, apuntar al próximo año
                    if not anio_evento and fecha_evento.date() < ahora.date():
                        fecha_evento = _dt(anio_base + 1, mes, dia, tzinfo=ahora.tzinfo)

                    # Datetime exacto del evento (con hora si se especificó)
                    if hora:
                        try:
                            hh, mm = map(int, hora.strip().split(":"))
                            fecha_evento = fecha_evento.replace(hour=hh, minute=mm)
                        except Exception:
                            pass  # hora inválida → usar 00:00

                    dias_restantes = (fecha_evento.date() - ahora.date()).days

                    disparado_flag = cursor.execute(
                        "SELECT disparado FROM eventos WHERE id=?", (eid,)
                    ).fetchone()[0]

                    # ── 1. AVISO PREVIO ──────────────────────────────────
                    if (aviso_dias > 0 and not aviso_disparado
                            and 0 < dias_restantes <= aviso_dias):
                        msg_aviso = (
                            f"En {dias_restantes} día{'s' if dias_restantes != 1 else ''} "
                            f"tenés: {nombre}"
                        )
                        if hora:
                            msg_aviso += f" a las {hora}"
                        cursor.execute(
                            "UPDATE eventos SET aviso_disparado=1 WHERE id=?", (eid,)
                        )
                        recien_disparados.append({
                            "nombre": f"⏰ Recordatorio: {nombre}",
                            "descripcion": msg_aviso,
                            "subtipo": "aviso"
                        })
                        print(f"⏰ Aviso previo: {nombre} en {dias_restantes} días")

                    # ── 2. DISPARO DEL EVENTO (el día llegó / la hora pasó) ──
                    elif not disparado_flag and dias_restantes == 0:
                        # Si tiene hora, verificar que ya llegó
                        if hora:
                            if ahora >= fecha_evento:
                                cursor.execute(
                                    "UPDATE eventos SET disparado=1, fecha_disparo=? WHERE id=?",
                                    (ahora.isoformat(), eid)
                                )
                                recien_disparados.append({
                                    "nombre": nombre, "descripcion": descripcion, "subtipo": "evento"
                                })
                                print(f"✨ Evento disparado (fecha+hora): {nombre}")
                        else:
                            cursor.execute(
                                "UPDATE eventos SET disparado=1, fecha_disparo=? WHERE id=?",
                                (ahora.isoformat(), eid)
                            )
                            recien_disparados.append({
                                "nombre": nombre, "descripcion": descripcion, "subtipo": "evento"
                            })
                            print(f"✨ Evento disparado (fecha): {nombre}")

                    # ── 3. SEGUIMIENTO POST-EVENTO ───────────────────────
                    elif (disparado_flag and seguimiento and not seguimiento_disparado
                          and dias_restantes <= 0):
                        # Esperar al menos hasta después de la hora si tiene hora
                        listo = True
                        if hora:
                            listo = ahora >= fecha_evento
                        if listo:
                            cursor.execute(
                                "UPDATE eventos SET seguimiento_disparado=1 WHERE id=?", (eid,)
                            )
                            recien_disparados.append({
                                "nombre": f"💬 {nombre}",
                                "descripcion": seguimiento,
                                "subtipo": "seguimiento"
                            })
                            print(f"💬 Seguimiento: {nombre}")

                except Exception as e:
                    print(f"⚠️ Error evento fecha {eid}: {e}")
                continue

    return recien_disparados


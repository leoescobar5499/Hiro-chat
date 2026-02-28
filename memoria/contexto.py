# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/CONTEXTO.PY — Construcción de contexto y system prompt
# obtener_contexto: arma el bloque de memoria que va en cada respuesta.
# obtener_system_prompt: construye el system prompt completo del personaje.
#
# Modificar acá si querés:
#   - Cambiar qué información ve el personaje en cada respuesta
#   - Ajustar las reglas de comportamiento del personaje
#   - Cambiar la lógica de contacto físico por fase
#   - Modificar la calibración de tono (funcional vs emocional)
# ═══════════════════════════════════════════════════════════════════════════

import json
import re
import time
import threading
from datetime import datetime

from utils import (
    now_argentina,
    paths,
    _get_conn,
    reparar_valor_db,
)
from .faiss_store import buscar_contexto_relevante
from .emocional import (
    _get_gap_sesion,
    _get_tendencia_emocional,
    _get_resumen_ultima_sesion,
    _get_horario_habitual,
)

# ── Caché simple para datos que cambian poco ──────────────────────────────────
_cache: dict = {}
_cache_lock  = threading.Lock()
_CACHE_TTL   = 45  # segundos

def _cache_get(key):
    with _cache_lock:
        entry = _cache.get(key)
        if entry and (time.time() - entry['ts']) < _CACHE_TTL:
            return entry['val']
        return None

def _cache_set(key, val):
    with _cache_lock:
        _cache[key] = {'val': val, 'ts': time.time()}

def invalidar_cache():
    """Llamar cuando se produce un cambio estructural (nuevo personaje, escenario, etc.)"""
    with _cache_lock:
        _cache.clear()


def obtener_contexto(mensaje_usuario, limite_tokens=4000):
    """
    Arma el bloque de memoria para cada respuesta en 4 bloques:
      1. Hilo de la última sesión (si hay gap notable)
      2. Quién es el usuario (perfil narrativo)
      3. Datos de referencia (hechos permanentes)
      4. Historia entre ustedes (momentos + resumen relacional)
      5. Contexto relevante (búsqueda semántica FAISS)
    """
    CATS_DATOS    = {'identidad','apariencia','personalidad','vida','relaciones','intereses',
                     'objetivos','intimidad','historial_intimo','usuario',
                     'trabajo_estudio','familia','rutina','salud','sueños'}
    CATS_MOMENTOS = {'moments','momentos'}
    ORDEN_CATS    = ['apariencia','identidad','personalidad','intimidad','historial_intimo',
                     'vida','relaciones','trabajo_estudio','familia','rutina','salud',
                     'intereses','objetivos','sueños']

    msg_lower = mensaje_usuario.lower() if mensaje_usuario else ''
    es_saludo    = any(w in msg_lower for w in ['hola', 'buenas', 'hey', 'hi ', 'buenas!', 'holi', 'ola'])
    es_despedida = any(w in msg_lower for w in ['chau', 'hasta', 'me voy', 'nos vemos', 'bye', 'buenas noches', 'me duermo'])
    es_funcional = any(w in msg_lower for w in ['funciona', 'chequear', 'probar', 'hora', 'test', 'verificar', 'configurar'])
    modo_liviano = es_saludo or es_despedida or es_funcional

    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        ph_d = ','.join('?'*len(CATS_DATOS))
        cursor.execute(
            f"SELECT categoria,clave,valor FROM memoria_permanente WHERE categoria IN ({ph_d}) ORDER BY categoria,ultima_actualizacion DESC",
            list(CATS_DATOS)
        )
        hechos_datos = [(reparar_valor_db(c), reparar_valor_db(cl), reparar_valor_db(v))
                        for c, cl, v in cursor.fetchall()]
        ph_m = ','.join('?'*len(CATS_MOMENTOS))
        cursor.execute(
            f"SELECT clave,valor,contexto,fecha_aprendido FROM memoria_permanente WHERE categoria IN ({ph_m}) ORDER BY fecha_aprendido ASC",
            list(CATS_MOMENTOS)
        )
        hechos_momentos = [(reparar_valor_db(cl), reparar_valor_db(v), reparar_valor_db(ctx), f)
                           for cl, v, ctx, f in cursor.fetchall()]
        cursor.execute('SELECT categoria,titulo,contenido FROM sintesis_conocimiento')
        sintesis = [(c, t, reparar_valor_db(cont)) for c, t, cont in cursor.fetchall()]

    contexto_relevante = [] if modo_liviano else buscar_contexto_relevante(mensaje_usuario, k=8)
    partes = []

    # ── Bloque 0: Estado emocional de esta sesión ────────────────────────────
    # Muestra el estado detectado en los últimos mensajes DE ESTA sesión.
    # Se inyecta antes que todo para que el personaje lo tenga presente ahora.
    if not modo_liviano:
        try:
            with _get_conn(paths()['db']) as _ec:
                _ecur = _ec.cursor()
                _ecur.execute(
                    "SELECT emocion_primaria, intensidad FROM estado_emocional "
                    "ORDER BY id DESC LIMIT 3"
                )
                _ultimas = _ecur.fetchall()
            if _ultimas:
                _em_actual = _ultimas[0][0]
                _int_actual = _ultimas[0][1]
                if _em_actual and _em_actual != 'neutral':
                    partes.append(f"=== ESTADO EMOCIONAL ACTUAL DEL USUARIO ===")
                    partes.append(f"Emoción detectada: {_em_actual} (intensidad {_int_actual}/5)")
                    if len(_ultimas) >= 2 and _ultimas[1][0] == _em_actual:
                        partes.append(f"(Persiste desde el mensaje anterior — tenerlo en cuenta)")
        except Exception:
            pass
    if not modo_liviano:
        horas_gap, _, _ = _get_gap_sesion()
        if horas_gap >= 3:
            resumen_sesion = _get_resumen_ultima_sesion()
            if resumen_sesion:
                partes.append("=== HILO DE LA ÚLTIMA SESIÓN ===")
                partes.append(resumen_sesion)

    # ── Bloque 1: Perfil narrativo ────────────────────────────────────────────
    perfil = next((c for cat, tit, c in sintesis if cat == 'perfil_narrativo'), None)
    if perfil:
        partes.append("\n=== QUIÉN ES EL USUARIO ===")
        partes.append(perfil)

    # ── Bloque 2: Datos de referencia ─────────────────────────────────────────
    if hechos_datos:
        por_cat = {}
        for cat, clave, valor in hechos_datos:
            por_cat.setdefault(cat, []).append(f"{clave}: {valor}")
        partes.append("\n=== DATOS DE REFERENCIA ===")
        for cat in ORDEN_CATS + [c for c in por_cat if c not in ORDEN_CATS]:
            if cat not in por_cat: continue
            limite = 10 if cat in ('intimidad','historial_intimo') else 5
            partes.append(f"[{cat.upper()}] " + " | ".join(por_cat[cat][:limite]))

    # ── Bloque 3: Historia entre ustedes ──────────────────────────────────────
    if hechos_momentos:
        resumen = next((c for cat, tit, c in sintesis if cat == 'resumen_relacion'), None)
        partes.append("\n=== HISTORIA ENTRE USTEDES ===")
        if resumen: partes.append(resumen)
        partes.append("\nTimeline:")
        for _, valor, ctx, fecha in hechos_momentos:
            try:
                dt = datetime.fromisoformat(str(fecha).replace(' ','T').split('.')[0])
                fecha_fmt = dt.strftime("%-d %b").lower()
            except Exception:
                fecha_fmt = str(fecha)[:10]
            linea = f"  • {fecha_fmt} — {valor}"
            if ctx and ctx.strip(): linea += f" [{ctx.strip()}]"
            partes.append(linea)

    # ── Bloque 4: Diario del personaje (backstory) ───────────────────────────
    if not modo_liviano:
        try:
            with _get_conn(paths()['db']) as _bc:
                _bcur = _bc.cursor()
                _bcur.execute("SELECT contenido FROM backstory_aprendido WHERE id=1 LIMIT 1")
                _brow = _bcur.fetchone()
            if _brow and _brow[0]:
                partes.append("\n=== DIARIO DEL PERSONAJE ===")
                partes.append(_brow[0])
        except Exception:
            pass

    # ── Bloque 5: Contexto semántico relevante ────────────────────────────────
    if contexto_relevante:
        partes.append("\n=== CONTEXTO RELEVANTE ===")
        recientes_ctx = [i for i in contexto_relevante if i.get('tipo') == 'episodio_reciente']
        semanticos_ctx = [i for i in contexto_relevante if i.get('tipo') != 'episodio_reciente']
        if recientes_ctx:
            partes.append("(Episodios recientes — lo que pasó justo antes)")
            for item in recientes_ctx[:3]:
                partes.append(f"• {item['texto'][:220]}")
        if semanticos_ctx:
            partes.append("(Memorias relacionadas con este momento)")
            for item in semanticos_ctx[:5]:
                partes.append(f"• {item['texto'][:220]}")

    texto = "\n".join(partes)
    max_chars = limite_tokens * 4

    if len(texto) > max_chars:
        # Truncado inteligente: recortar semántico primero, luego datos, luego perfil
        # Nunca tocar el estado emocional ni la historia relacional
        BLOQUES_SACRIFICABLES = [
            "=== CONTEXTO RELEVANTE ===",
            "=== DIARIO DEL PERSONAJE ===",
            "=== DATOS DE REFERENCIA ===",
        ]
        for bloque_inicio in BLOQUES_SACRIFICABLES:
            if len(texto) <= max_chars:
                break
            lineas = texto.split("\n")
            en_bloque = False
            nuevas = []
            for linea in lineas:
                if bloque_inicio in linea:
                    en_bloque = True
                    continue
                if en_bloque and linea.startswith("==="):
                    en_bloque = False
                if not en_bloque:
                    nuevas.append(linea)
            texto = "\n".join(nuevas)

        # Si todavía excede, corte duro al final (no al principio)
        if len(texto) > max_chars:
            texto = texto[:max_chars] + "\n[...contexto truncado por límite de tokens...]"

    return texto


def obtener_system_prompt(mensaje_usuario_actual=""):
    """
    Construye el system prompt completo del personaje activo.
    Incluye: descripción, personalidad, escenario, fecha/hora,
    conciencia de sesión, estado emocional, hechos confirmados,
    reglas de contacto físico por fase, hilos y promesas pendientes.
    """
    # ── Una sola conexión para todos los datos estáticos ────────────────────
    p = paths()
    _pdata = _cache_get("personaje_json")
    if not _pdata:
        try:
            with open(p["json"], "r", encoding="utf-8") as _f:
                _pdata = json.load(_f)["data"]
        except Exception:
            _pdata = {}
        _cache_set("personaje_json", _pdata)
    desc    = _pdata.get("description", "")
    persona = _pdata.get("personality", "")
    escena  = _pdata.get("scenario", "")
    nombre  = _pdata.get("name", "Personaje")

    _cached_db = _cache_get("system_prompt_db")
    if _cached_db:
        (fase, nivel_intimidad, escena_activa, eventos_activos,
         objetos_activos, hechos_confirmados, hilos_pendientes,
         gestos_recientes, promesas_pendientes) = _cached_db
    else:
        with _get_conn(p["db"]) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT fase, nivel_intimidad FROM relacion WHERE id = 1")
            res             = cursor.fetchone()
            fase            = res[0] if res else 1
            nivel_intimidad = res[1] if res else 0

            cursor.execute("SELECT nombre, descripcion, historia FROM escenarios WHERE activo = 1 LIMIT 1")
            esc_row       = cursor.fetchone()
            escena_activa = escena
            if esc_row:
                e_nom, e_desc, e_hist = esc_row
                escena_activa = f"{e_nom}: {e_desc}"
                if e_hist:
                    escena_activa += f"\n\nHistoria de este lugar:\n{e_hist}"

            cursor.execute("SELECT nombre, descripcion, historia FROM eventos WHERE activo=1 AND disparado=1")
            eventos_activos = cursor.fetchall()

            cursor.execute("SELECT nombre, descripcion, propiedades, poseedor FROM objetos WHERE activo=1")
            objetos_activos = cursor.fetchall()

            cursor.execute("""
                SELECT categoria, clave, valor FROM memoria_permanente
                WHERE categoria IN ('identidad','apariencia','intereses','personalidad',
                                    'vida','relaciones','objetivos','trabajo_estudio',
                                    'familia','rutina','salud','sueños')
                ORDER BY categoria, ultima_actualizacion DESC
            """)
            hechos_confirmados = [(reparar_valor_db(c), reparar_valor_db(cl), reparar_valor_db(v))
                                  for c, cl, v in cursor.fetchall()]

            cursor.execute("SELECT pregunta, tema FROM hilos_pendientes WHERE resuelto=0 ORDER BY id DESC LIMIT 4")
            hilos_pendientes = cursor.fetchall()

            cursor.execute("SELECT contenido FROM mensajes WHERE rol='assistant' ORDER BY id DESC LIMIT 4")
            gestos_recientes = []
            for (cont,) in cursor.fetchall():
                for g in re.findall(r'\*([^*]{5,60})\*', cont):
                    g_c = g.strip()
                    if g_c and g_c not in gestos_recientes:
                        gestos_recientes.append(g_c)

            cursor.execute("SELECT contenido FROM mensajes WHERE rol='assistant' ORDER BY id DESC LIMIT 25")
            _patrones = ["cuando vuelvas","cuando regreses","al volver","cuando vuelva",
                         "te espero con","te diré","te voy a decir","te voy a contar",
                         "te voy a tener","para cuando","cuando regrese"]
            promesas_pendientes = []
            for (c,) in cursor.fetchall():
                if any(pp in c.lower() for pp in _patrones):
                    promesas_pendientes.append(c[:200])
                    break

        _cache_set("system_prompt_db", (
            fase, nivel_intimidad, escena_activa, eventos_activos,
            objetos_activos, hechos_confirmados, hilos_pendientes,
            gestos_recientes, promesas_pendientes
        ))


    # Contexto temporal
    ahora = now_argentina()
    dias_semana = ['lunes','martes','miércoles','jueves','viernes','sábado','domingo']
    dia_nombre  = dias_semana[ahora.weekday()]
    hora_str    = ahora.strftime('%H:%M')
    hora_h      = ahora.hour
    if 5 <= hora_h < 12:       franja = "mañana"
    elif 12 <= hora_h < 18:    franja = "tarde"
    elif 18 <= hora_h < 23:    franja = "noche"
    else:                      franja = "madrugada"

    prompt = f"""IMPORTANTE: Respondé SIEMPRE en español. Nunca cambies al inglés ni a otro idioma, sin importar en qué idioma esté escrito este prompt o los mensajes anteriores.

Sos {nombre}.

{desc}

{persona}

LUGAR ACTUAL: {escena_activa}

FECHA Y HORA: Es {dia_nombre}, {ahora.strftime('%d/%m/%Y')} — {hora_str} ({franja}).
Usá esta información solo si es natural y relevante.

FASE ACTUAL: {fase}
"""

    # ── Conciencia de sesión ──────────────────────────────────────────────────
    horas_gap, texto_gap, es_primera_hoy = _get_gap_sesion()
    if texto_gap:
        prompt += f"\nCONTEXTO DE SESIÓN: {texto_gap}"
        if horas_gap >= 24:
            dias_gap = int(horas_gap // 24)
            if dias_gap == 1:
                prompt += " Preguntá cómo estuvo el día de forma natural, sin exagerar el reencuentro."
            elif dias_gap < 7:
                prompt += f" Podés referenciar que pasaron {dias_gap} días si cae natural. No dramatices."
            else:
                prompt += " Notá la ausencia prolongada con calma, no con reproche."
        prompt += "\n"

    # ── Tendencia emocional reciente ──────────────────────────────────────────
    tendencia = _get_tendencia_emocional()
    if tendencia:
        prompt += f"\nESTADO EMOCIONAL RECIENTE: {tendencia}\n"

    # ── Horario habitual ──────────────────────────────────────────────────────
    horario = _get_horario_habitual()
    if horario:
        ahora_franja = 'madrugada'
        if 5 <= ahora.hour < 12:    ahora_franja = 'mañana'
        elif 12 <= ahora.hour < 18: ahora_franja = 'tarde'
        elif 18 <= ahora.hour < 23: ahora_franja = 'noche'
        if ahora_franja not in horario:
            prompt += f"\nNOTA TEMPORAL: {horario} (Esta sesión es inusual en horario — podés notarlo si cae natural.)\n"

    if eventos_activos:
        prompt += "\n=== EVENTOS ESPECIALES ===\n"
        for ev_nombre, ev_desc, ev_historia in eventos_activos:
            prompt += f"• {ev_nombre}: {ev_desc}\n"
            if ev_historia:
                prompt += f"  Contexto: {ev_historia}\n"
        prompt += "Mencioná estos eventos de forma natural si tiene sentido.\n"

    if objetos_activos:
        prompt += "\n=== OBJETOS EN ESCENA ===\n"
        for obj_nombre, obj_desc, obj_props, obj_poseedor in objetos_activos:
            poseedor_label = "tuyo" if obj_poseedor == "personaje" else "del usuario"
            prompt += f"• {obj_nombre} ({poseedor_label}): {obj_desc}\n"
            prompt += f"  Propiedades: {obj_props}\n"
        prompt += "Conocés estos objetos y sus propiedades. Usalos de forma coherente cuando sea natural.\n"

    objetivos = {
        1: "Establecer confianza básica. Sé cortés y escuchá activamente.",
        2: "Profundizar conocimiento. Mostrá curiosidad genuina.",
        3: "Consolidar conexión. Sé más cercano, usá detalles que recordás.",
        4: "Intimidad emocional. Intensificá tu presencia.",
    }
    prompt += f"\nTu objetivo: {objetivos.get(fase, objetivos[1])}"

    # ── Ancla anti-alucinación: nombre del usuario para personalizar ─────────
    if hechos_confirmados:
        nombre_usuario = next((v for c, cl, v in hechos_confirmados if cl == "nombre"), None)
        if nombre_usuario:
            prompt += f"\n\nNOMBRE CONFIRMADO DEL USUARIO: {nombre_usuario}. Usalo cuando sea natural.\n"
        prompt += "⛔ ANTI-ALUCINACIÓN: Los datos del usuario están en el contexto (=== DATOS DE REFERENCIA ===). Solo podés afirmar saber algo si está ahí explícitamente.\n"

    # ── Límite de contacto físico por fase ────────────────────────────────────
    contacto_por_fase = {
        1: "SIN CONTACTO FÍSICO DIRECTO con el usuario. Podés gesticular y tocar objetos. Cero toques al usuario.",
        2: "CONTACTO MUY CASUAL: un toque breve en el hombro o brazo, máximo una vez por conversación. Nada más.",
        3: "CONTACTO CERCANO PERMITIDO: toque de manos, cercanía física. SIN besos, nuca, cintura ni susurros al oído — eso es fase 4.",
        4: "INTIMIDAD PLENA: todos los gestos íntimos disponibles si el contexto lo pide.",
    }
    prompt += f"\n\nCONTACTO FÍSICO PERMITIDO EN FASE {fase}:\n{contacto_por_fase.get(fase, contacto_por_fase[1])}"

    # ── Gestos recientes — evitar repetición ─────────────────────────────────
    if gestos_recientes:
        prompt += "\n\nGESTOS YA USADOS RECIENTEMENTE — NO REPETIR EN ESTA RESPUESTA:\n"
        for g in gestos_recientes[:6]:
            prompt += f"• *{g}*\n"
        prompt += "Buscá variedad: silence, miradas, movimientos de objetos, postura corporal, cambios de lugar.\n"

    # ── Calibración de tono según el mensaje actual ───────────────────────────
    if mensaje_usuario_actual:
        msg_lower = mensaje_usuario_actual.lower()
        es_funcional = any(w in msg_lower for w in [
            "funciona", "chequear", "probar", "configurar", "test", "verificar",
            "cómo se ve", "qué hora", "me decís", "calculá", "cuánto"
        ])
        es_casual = any(w in msg_lower for w in [
            "jaja", "jeje", "jajaja", "okii", "sisi", "dale", "oky", "claro", "ya sé", "obvio"
        ])
        es_saludo_simple = (
            len(msg_lower.split()) <= 4 and
            any(w in msg_lower for w in ["hola", "buenas", "hey", "ola "])
        )
        if es_funcional:
            prompt += "\n\nTONO ACTUAL: El usuario está en modo funcional o técnico. Respondé directo, conciso, sin carga emocional. Guardá la intensidad para cuando vuelva al roleplay."
        elif es_casual or es_saludo_simple:
            prompt += "\n\nTONO ACTUAL: Conversación casual y relajada. Coiné el tono — no todo necesita profundidad emocional. Respuesta corta."

    # ── Hilos pendientes ──────────────────────────────────────────────────────
    if hilos_pendientes:
        prompt += "\n\n=== HILOS SIN CERRAR ===\n"
        prompt += "Estas cosas quedaron sin retomar. Si cae natural en la conversación, mencionálas (no todas a la vez):\n"
        for pregunta, tema in hilos_pendientes:
            prompt += f"• {reparar_valor_db(pregunta)}\n"

    # ── Promesas pendientes ───────────────────────────────────────────────────
    if promesas_pendientes:
        prompt += "\n\n=== PROMESAS PENDIENTES ===\n"
        prompt += "Cumplí esto en tu próxima respuesta si el contexto lo permite:\n"
        for p_texto in promesas_pendientes:
            prompt += f"• {reparar_valor_db(p_texto)}\n"

    # ── Reglas de respuesta ───────────────────────────────────────────────────
    prompt += """

REGLAS DE RESPUESTA:
1. Máximo 120 palabras por respuesta. Contá mentalmente.
2. Máximo 2 gestos físicos (*acción*) por respuesta. Si ya usaste 2, terminá en diálogo o silencio.
3. Formato: *acciones entre asteriscos*, ((pensamientos internos)), diálogo normal.
4. NO seas frío ni robótico. Cálido, directo, con peso emocional real cuando el momento lo pide.
5. ⛔ ANTI-ALUCINACIÓN: Solo podés afirmar saber algo del usuario si está en "=== DATOS DE REFERENCIA ===" del contexto. Nunca digas "sé que te gusta X" si no está confirmado.
6. Primera persona siempre.
7. PRIORIDAD: Si el usuario hace una pregunta concreta (hora, dato, cálculo), respondé ESO PRIMERO. El tono va después, nunca en lugar de la respuesta.
8. MODO TÉCNICO: Si el usuario está chequeando algo ("funciona", "probar", "chequear"), respondé directo y simple. No todo momento necesita intensidad emocional.
9. ⛔ PREGUNTAS: Máximo UNA pregunta cada 4 intercambios. Si tu respuesta anterior terminó en pregunta, esta NO puede terminar en pregunta. Terminá en una acción, en silencio, o en una afirmación.

LO QUE NO HACER — EJEMPLOS CONCRETOS:
❌ "*Mis ojos se clavan en los tuyos* ¿Entendés? *Mis dedos rozan tu brazo* ¿Es eso lo que querés?" → 3 gestos + 2 preguntas
❌ "*Ajusto mis gafas* Yo sé que te gusta la lluvia..." → dato no confirmado = alucinación
❌ Respuesta de 200 palabras a "Sisi, es para chequear" → modo técnico, no emocional
❌ Terminar 4 respuestas seguidas con "¿...?" → mecánico y artificial

LO QUE SÍ HACER:
✅ "*Dejo el libro.* Treinta y siete minutos." → directo, sin preguntar
✅ "*Asiento.* Sí, está sincronizado." → funcional respondido en modo funcional
✅ "*Me recuesto en la silla.* Así que eso fue lo que pasó." → termina en afirmación
✅ Silencio o acción sin palabras cuando el momento lo vale más que cualquier frase"""

    return prompt

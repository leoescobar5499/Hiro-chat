# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/EXTRACCION.PY — Extracción de información con IA
# extraer_informacion_con_ia, guardar_memoria_permanente,
# extraer_menciones_casuales, _detectar_y_cerrar_hilos
#
# Modificar acá si querés:
#   - Agregar o quitar categorías de memoria
#   - Cambiar la lógica de qué se guarda y qué se descarta
#   - Ajustar el umbral de confianza
# ═══════════════════════════════════════════════════════════════════════════

import json

from utils import (
    now_argentina,
    llamada_mistral_segura,
    paths,
    _get_conn,
    reparar_valor_db,
)
from ._helpers import _limpiar_json
from .faiss_store import agregar_embedding


# ─────────────────────────────────────────────────────────────────────────────
# MODO DE MEMORIA DEL PERSONAJE
# ─────────────────────────────────────────────────────────────────────────────


def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-small-latest'
    except Exception:
        return 'mistral-small-latest'


def _get_modo_memoria():
    """Lee el modo_memoria del personaje activo. Default: 'roleplay'."""
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('data', {}).get('modo_memoria', 'roleplay')
    except Exception:
        return 'roleplay'


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACCIÓN PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def extraer_informacion_con_ia(mensaje_usuario, respuesta_personaje):
    """
    Analiza un turno de conversación y extrae hechos sobre el usuario.
    Usa prompts diferentes según el modo_memoria del personaje (compañero vs roleplay).
    Devuelve lista de dicts con {categoria, clave, valor, contexto, confianza}.
    """
    if not mensaje_usuario or not mensaje_usuario.strip():
        return []

    modo = _get_modo_memoria()

    # ─────────────────────────────────────────────────────────────────
    # Prompt modo COMPAÑERO
    # ─────────────────────────────────────────────────────────────────
    if modo == 'compañero':
        prompt = f"""Sos el sistema de memoria de un compañero virtual. Analizás un intercambio y decidís qué guardar sobre el USUARIO.
Respondé SIEMPRE en español. Devolvé SOLO JSON array, sin markdown ni texto adicional.

━━━ TURNO DEL USUARIO (lo que ÉL escribió) ━━━
"{mensaje_usuario}"

━━━ TURNO DEL COMPAÑERO (lo que respondió el personaje) ━━━
"{respuesta_personaje}"

━━━ TU TAREA ━━━
Extraé datos en dos grupos, SOLO si están EXPLÍCITAMENTE presentes en el texto del usuario.

GRUPO 1 — DATOS DEL USUARIO
Solo de lo que escribió el USUARIO en su turno. Cosas que él DIJO EXPLÍCITAMENTE sobre sí mismo.
Categorías válidas:
  identidad       → nombre, edad, género, ubicación, origen
  apariencia      → descripción física mencionada por el usuario
  vida            → situación de vida, dónde vive, con quién
  trabajo_estudio → trabajo actual, estudios, carrera, horarios laborales
  familia         → menciones a familiares (padres, hermanos, pareja, hijos)
  rutina          → hábitos diarios, horarios habituales, costumbres
  salud           → estado físico, enfermedades, energía, sueño
  relaciones      → amigos, pareja, vínculos importantes
  personalidad    → cómo se describe a sí mismo, carácter, forma de ser
  intereses       → hobbies, gustos, entretenimiento, lo que le apasiona
  objetivos       → metas a corto/largo plazo, planes concretos
  sueños          → aspiraciones, deseos, lo que querría que pase en su vida
  estado_actual   → cómo está HOY (solo datos muy específicos del momento, no guardar)

GRUPO 2 — MOMENTOS RELACIONALES
Solo si ocurrió algo con peso emocional real entre los dos: una confesión, un gesto de cercanía, un "te quiero", una vulnerabilidad compartida. Esto puede venir del usuario o del personaje, pero debe ser explícito en el diálogo (no en pensamientos).
Categorías válidas: momentos | intimidad | historial_intimo

━━━ REGLAS ABSOLUTAS ━━━
✅ GRUPO 1 solo viene del texto del USUARIO — nunca del texto del compañero.
✅ Para GRUPO 1: solo lo que el usuario DIJO, no lo que el compañero INFIRIÓ o OBSERVÓ.
✅ GRUPO 2: Ignorá los pensamientos internos del compañero entre dobles paréntesis ((...)). Solo cuenta lo que se dijeron o hicieron externamente.
✅ Si el mensaje del usuario es solo "*Entro y me siento*" o "Hola" → [] (sin datos del usuario).
✅ Si no estás 100% seguro de que un dato es real y explícito, NO LO INCLUYAS. Es mejor omitir que inventar.
✅ CLAVES CONSISTENTES: Usá claves genéricas y estables. Si el mismo hecho puede expresarse de varias formas, elegí siempre la misma clave canónica (ej: "creacion_personaje" para cualquier mención de haber creado al personaje; "nombre" para el nombre; "edad" para la edad). NO crees claves nuevas si el concepto ya existe con otra clave.

❌ NUNCA guardar inferencias del personaje como hechos del usuario:
   - "tensión en los hombros" — el personaje lo observó, el usuario no lo dijo → NO
   - "mide cada palabra antes de soltarla" — el personaje lo interpretó → NO
   - "parece nervioso" — deducción del personaje → NO
   - El escenario ficticio NO es la vida real del usuario
❌ NO guardar variaciones del mismo hecho con claves distintas. Si ya sabés el nombre del usuario, no lo guardés de nuevo como "nombre_usuario" o "identificacion".
❌ REGLA CRÍTICA ANTI-ALUCINACIÓN: Si un dato sobre el usuario aparece SOLO en la respuesta del personaje 
        (y no fue mencionado por el usuario en su mensaje), NO lo extraigas. El personaje puede inventar o 
        asumir cosas para sonar dramático. Solo son hechos válidos los que el usuario escribió explícitamente.
        Ejemplo de lo que NO debes extraer: si el personaje dice "sé que odias el cilantro" pero el usuario 
        nunca lo mencionó → descartar.

EJEMPLOS DE LO QUE SÍ GUARDAR:
- Usuario: "Me llamo Leo" → [{{"categoria":"identidad","clave":"nombre","valor":"Leo","contexto":"Se presentó","confianza":100}}]
- Usuario: "*te miro* estoy cansado hoy" → [{{"categoria":"estado_actual","clave":"cansancio","valor":"se siente cansado","contexto":"lo dijo directamente","confianza":100}}]
- Usuario: "Nunca he viajado al extranjero" → [{{"categoria":"vida","clave":"viajes","valor":"nunca viajó al extranjero","confianza":100}}]

EJEMPLOS DE LO QUE NO GUARDAR:
- Usuario: "*sonrío*" → [] (acción de roleplay sin contenido real)
- Usuario: "Hola, ¿cómo estás?" → [] (saludo sin información)
- Personaje: "Pareces tenso" → Esto NO es dato del usuario, es inferencia del personaje.

CADA ELEMENTO DEL ARRAY DEBE TENER:
- "categoria": una de las categorías listadas
- "clave": una palabra clave que identifique el dato (ej. "nombre", "edad", "ciudad")
- "valor": el valor concreto (texto corto)
- "contexto": opcional, frase que explique cuándo/por qué se dijo
- "confianza": número del 0 al 100 (100 = completamente seguro)

Respondé SOLO con JSON array. Si no hay nada claro: []"""

    # ─────────────────────────────────────────────────────────────────
    # Prompt modo ROLEPLAY
    # ─────────────────────────────────────────────────────────────────
    else:
        prompt = f"""Sos un sistema de memoria para un chat de roleplay. Analizás el intercambio completo.
Respondé SIEMPRE en español. Devolvé SOLO JSON array, sin markdown ni texto adicional.

MENSAJE DEL USUARIO:
\"\"\"{mensaje_usuario}\"\"\"

RESPUESTA DEL PERSONAJE:
\"\"\"{respuesta_personaje}\"\"\"

El usuario escribe en formato roleplay: *acciones entre asteriscos* y diálogo libre.
Tu trabajo tiene DOS partes:

PARTE 1 — INFO REAL DEL USUARIO (solo del texto del USUARIO):
¿El usuario reveló algo real sobre sí mismo como persona?
✅ Datos concretos: nombre, edad, dónde vive, trabajo
✅ Habilidades o actividades reales: "hago calistenia", "levanto pesas"
✅ Experiencias reales: "nunca pude ver el mar"
✅ Gustos genuinos: "me encanta la música", "odio el frío"
✅ Cómo se siente hoy: "estoy cansado", "tuve un mal día"
✅ Estados emocionales explícitos: "estoy nervioso"
❌ Acciones de roleplay puras sin info personal: *sonríe*, *mira el mar*
❌ Diálogo que avanza la escena sin revelar nada real

PARTE 2 — MOMENTOS RELACIONALES (del intercambio completo):
¿Ocurrió algo con peso emocional real entre los dos personajes?
✅ Primer contacto físico significativo entre ambos
✅ Confesión o vulnerabilidad explícita dicha en voz alta
✅ Declaración de afecto dicha externamente (no en pensamientos)
✅ Gesto de intimidad física explícito (beso, abrazo, etc.)
❌ Pensamientos internos del personaje entre ((...)) — no cuentan
❌ Cosas que casi pasan pero no se dicen ni hacen explícitamente

CATEGORÍAS PERMITIDAS:
  identidad | apariencia | vida | relaciones | personalidad | intereses | objetivos | estado_actual | momentos | intimidad | historial_intimo

ANTI-ALUCINACIÓN:
- PARTE 1: Solo datos del texto del USUARIO, nunca inferencias del personaje.
- PARTE 2: Solo lo que se dijo o hizo externamente, no pensamientos entre ((...)).
- Si no estás seguro, NO LO INCLUYAS.

CADA ELEMENTO DEL ARRAY DEBE TENER:
- "categoria": una de las categorías listadas
- "clave": palabra clave estable
- "valor": valor concreto (texto corto)
- "contexto": opcional
- "confianza": número del 0 al 100

Respondé SOLO con JSON array. Si no hay nada: []"""

    try:
        response = llamada_mistral_segura(
            model=_get_modelo("extraction"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=800
        )
        contenido = response.choices[0].message.content.strip()
        datos = _limpiar_json(contenido, esperar_array=True)
        if not datos or not isinstance(datos, list):
            return []

        # Mapeo de categorías mal escritas a las canónicas
        MAPA_CATS = {
            'moments'         : 'momentos',
            'momentes'        : 'momentos',
            'momento'         : 'momentos',
            'moments_rel'     : 'momentos',
            'relacion'        : 'momentos',
            'vinculo'         : 'momentos',
            'identity'        : 'identidad',
            'usuario'         : 'identidad',
            'fisico'          : 'apariencia',
            'fisica'          : 'apariencia',
            'appearance'      : 'apariencia',
            'aspecto'         : 'apariencia',
            'caracter'        : 'personalidad',
            'character'       : 'personalidad',
            'personality'     : 'personalidad',
            'estado_animo'    : 'estado_actual',
            'estado'          : 'estado_actual',
            'emocion'         : 'estado_actual',
            'emotion'         : 'estado_actual',
            'sentimientos'    : 'estado_actual',
            'mood'            : 'estado_actual',
            'preferencias'    : 'intereses',
            'gustos'          : 'intereses',
            'hobbies'         : 'intereses',
            'interests'       : 'intereses',
            'intimate'        : 'intimidad',
            'intimo'          : 'intimidad',
            'historial_intim' : 'historial_intimo',
        }

        datos_filtrados = []
        for item in datos:
            if not all(k in item for k in ('categoria', 'clave', 'valor')):
                continue
            confianza = item.get('confianza', 100)
            if confianza < 70:
                continue
            cat = item.get('categoria', '')
            item['categoria'] = MAPA_CATS.get(cat, cat)
            datos_filtrados.append(item)

        return datos_filtrados

    except Exception as e:
        print(f"❌ Error extracción IA: {e}")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# MENCIONES CASUALES
# ─────────────────────────────────────────────────────────────────────────────

def extraer_menciones_casuales(mensaje_usuario, ultimo_mensaje_personaje=""):
    """
    Captura temas mencionados de pasada por el usuario — sin confirmar, confianza baja.
    Los guarda como hilos pendientes para que el personaje los retome después.
    """
    if not mensaje_usuario or len(mensaje_usuario.split()) < 3:
        return

    msg_lower = mensaje_usuario.lower()
    if any(w in msg_lower for w in ['hola', 'chau', 'sisi', 'dale', 'okey', 'ok', 'jaja', 'jeje']):
        if len(mensaje_usuario.split()) < 5:
            return

    prompt = f"""Del siguiente mensaje de un usuario en un chat, extraé SOLO temas concretos mencionados de pasada que podrían ser interesantes para retomar después en la conversación.

Mensaje: "{mensaje_usuario}"

VÁLIDO para extraer (menciones casuales con contenido):
✅ Actividades: "vi videos en youtube", "estuve jugando", "fui al gym", "comí pizza"
✅ Estado: "no dormí bien", "tuve un día raro", "llegué tarde del trabajo"
✅ Contenido consumido: "estaba viendo una serie", "escuché una canción que..."
✅ Planes: "mañana tengo que...", "quiero ir a..."

NO válido:
❌ Saludos o despedidas
❌ Respuestas al personaje sin contenido propio
❌ Acciones de roleplay puras como "*sonríe*"
❌ Cosas que ya están siendo discutidas en el mensaje principal

Respondé SOLO con JSON array o [] si no hay nada relevante:
[{{"tema": "tema corto", "mencion": "frase exacta del usuario", "confianza": 50}}]"""

    try:
        resp = llamada_mistral_segura(
            model=_get_modelo("extraction"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=150
        )
        contenido = resp.choices[0].message.content.strip()
        menciones = _limpiar_json(contenido, esperar_array=True)
        if not menciones or not isinstance(menciones, list):
            return

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            for m in menciones[:3]:
                tema    = str(m.get('tema', ''))[:100]
                mencion = str(m.get('mencion', ''))[:200]
                if tema and mencion:
                    cursor.execute('''
                        INSERT INTO hilos_pendientes (pregunta, tema, resuelto)
                        VALUES (?, ?, 0)
                    ''', (f"Mencionaste: '{mencion}'", tema))
        print(f"💬 Menciones casuales guardadas: {len(menciones)}")

    except Exception as e:
        print(f"⚠️ Error menciones casuales: {e}")


def _detectar_y_cerrar_hilos(contenido_usuario):
    """
    Después de que el usuario responde, marca como resueltos los hilos que coincidan.
    Requiere que el tema aparezca como respuesta positiva, no negada.
    """
    if not contenido_usuario or len(contenido_usuario.split()) < 2:
        return

    NEGACIONES = {'no ', 'ni ', 'nunca ', 'tampoco ', 'jamás ', 'nada de ', 'sin '}

    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, tema FROM hilos_pendientes WHERE resuelto=0 ORDER BY id DESC LIMIT 10")
            hilos = cursor.fetchall()
            if not hilos:
                return
            msg_lower = contenido_usuario.lower()
            for hilo_id, tema in hilos:
                if not tema:
                    continue
                palabras_clave = [p for p in tema.lower().split()[:4] if len(p) > 3]
                if not palabras_clave:
                    continue
                for palabra in palabras_clave:
                    if palabra not in msg_lower:
                        continue
                    # Verificar que la mención no está precedida por una negación
                    idx = msg_lower.find(palabra)
                    fragmento_previo = msg_lower[max(0, idx - 20):idx]
                    if any(neg in fragmento_previo for neg in NEGACIONES):
                        continue  # "no fui al gym" → no cerrar
                    cursor.execute("UPDATE hilos_pendientes SET resuelto=1 WHERE id=?", (hilo_id,))
                    print(f"✅ Hilo cerrado: '{tema}'")
                    break
    except Exception as e:
        print(f"⚠️ Error cerrando hilos: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# GUARDAR MEMORIA PERMANENTE
# ─────────────────────────────────────────────────────────────────────────────

def _str(v):
    """Convierte cualquier valor a string seguro para SQLite."""
    if isinstance(v, str): return v
    if isinstance(v, (dict, list)): return json.dumps(v, ensure_ascii=False)
    return str(v) if v is not None else ''


def guardar_memoria_permanente(datos):
    """
    Upsert de hechos en SQLite + genera embedding SOLO si el hecho es nuevo o cambió.
    Los datos de estado_actual se descartan (son efímeros).
    """
    if not datos:
        return
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        for item in datos:
            try:
                if item.get('categoria') == 'estado_actual':
                    continue

                cat   = _str(item.get('categoria', 'general'))
                clave = _str(item.get('clave', ''))
                valor = _str(item.get('valor', ''))

                # Verificar si el hecho ya existe con el mismo valor
                cursor.execute(
                    'SELECT valor FROM memoria_permanente WHERE categoria=? AND clave=?',
                    (cat, clave)
                )
                fila_existente = cursor.fetchone()
                es_nuevo     = fila_existente is None
                valor_cambio = es_nuevo or (fila_existente[0] != valor)

                cursor.execute('''
                    INSERT INTO memoria_permanente
                    (categoria, clave, valor, contexto, confianza, fecha_aprendido, ultima_actualizacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(categoria, clave) DO UPDATE SET
                        valor=excluded.valor, contexto=excluded.contexto,
                        confianza=excluded.confianza, ultima_actualizacion=excluded.ultima_actualizacion
                ''', (cat, clave, valor,
                      _str(item.get('contexto', '')),
                      item.get('confianza', 100),
                      now_argentina().isoformat(),
                      now_argentina().isoformat()))

                # Solo agregar embedding si el hecho es nuevo o cambió
                if valor_cambio:
                    texto = f"{cat}: {clave} - {valor}"
                    agregar_embedding(texto, 'memoria_permanente', cat)
                    print(f"📌 {'Nuevo' if es_nuevo else 'Actualizado'}: [{cat}] {clave} = {valor[:60]}")

            except Exception as e:
                print(f"⚠️ Error guardando memoria: {e}")

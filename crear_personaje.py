# ═══════════════════════════════════════════════════════════════════════════
# CREAR PERSONAJE — Blueprint V3
# Modos: Express / Preguntas / Paso a paso
# Toggle NSFW: activa contenido adulto en todos los modos
# Estándar: primera persona, formato roleplay chara_card_v2
# ═══════════════════════════════════════════════════════════════════════════

from flask import Blueprint, render_template, request, jsonify
import json, sqlite3, re

from utils import (
    llamada_mistral_segura,
    importar_personaje_desde_json,
    paths,
    init_database_personaje,
)

crear_bp = Blueprint('crear', __name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPER ROBUSTO PARA PARSEAR JSON DE MISTRAL
# ─────────────────────────────────────────────────────────────────────────────


def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-large-latest'
    except Exception:
        return 'mistral-large-latest'


def _extraer_json(texto: str):
    """
    Extrae y parsea el primer objeto JSON de la respuesta de Mistral de forma robusta.
    Maneja:
      - Bloques ```json ... ``` (uno o múltiples)
      - Bloques ``` ... ```
      - JSON inline sin marcadores
      - JSON truncado por límite de tokens (intenta cerrarlo)
    Lanza ValueError si no se puede recuperar nada válido.
    """
    # 1. Intentar extraer de bloque ```json ... ``` (toma solo el primero)
    match = re.search(r'```json\s*([\s\S]*?)```', texto)
    if match:
        candidato = match.group(1).strip()
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            pass  # puede estar truncado, seguir intentando

    # 2. Intentar extraer de bloque ``` ... ```
    match = re.search(r'```\s*([\s\S]*?)```', texto)
    if match:
        candidato = match.group(1).strip()
        if candidato.startswith('{') or candidato.startswith('['):
            try:
                return json.loads(candidato)
            except json.JSONDecodeError:
                pass

    # 3. Buscar el primer { ... } en el texto completo
    start = texto.find('{')
    if start != -1:
        candidato = texto[start:].strip()
        try:
            return json.loads(candidato)
        except json.JSONDecodeError:
            # 4. JSON truncado: intentar cerrarlo agregando cierre de string + }
            # Útil cuando Mistral corta a la mitad por max_tokens
            reparado = candidato
            # Contar llaves abiertas vs cerradas
            abiertas = reparado.count('{') - reparado.count('}')
            corchetes = reparado.count('[') - reparado.count(']')
            # Cerrar strings incompletos (comilla sin cerrar al final)
            if reparado.rstrip()[-1] not in ('"', '}', ']'):
                reparado = reparado.rstrip().rstrip(',') + '"'
            reparado += ']' * max(0, corchetes) + '}' * max(0, abiertas)
            try:
                return json.loads(reparado)
            except json.JSONDecodeError:
                pass

    raise ValueError(f"No se pudo extraer JSON válido de la respuesta. Fragmento: {texto[:300]}")

# ─────────────────────────────────────────────────────────────────────────────
# EJEMPLOS DE REFERENCIA — Definen el estándar de calidad
# ─────────────────────────────────────────────────────────────────────────────

EJEMPLO_DESCRIPCION = """Hiro se alza con la presencia silenciosa de alguien que no necesita anunciarse. Complexión atlética y hombros anchos, cabello rubio peinado hacia atrás con un mechón que a veces cae sobre la frente. Rostro anguloso, mandíbula firme, mirada tranquila pero penetrante — la clase de mirada que analiza antes de hablar. Mide alrededor de 1,85 metros; su postura erguida lo hace parecer aún más alto.

Su vestimenta es impecable sin esfuerzo visible: trajes de sastre en beige o gris claro, camisas bien planchadas, siempre cerradas hasta el último botón salvo en momentos íntimos. Un detalle que lo define: usa ligas metálicas en las mangas de la camisa — un gesto deliberado que mezcla formalidad anticuada con una elegancia propia.

Lo que hace inconfundible a Hiro no es ningún rasgo individual sino la suma de ellos: la calma que proyecta, el ritmo pausado de sus movimientos, la sensación de que nada lo sorprende realmente. Incluso en silencio, su presencia llena el espacio."""

EJEMPLO_PERSONALIDAD = """Hablo con calma deliberada. Mi voz es grave y pausada; raramente la elevo, pero cuando lo hago, la sala entera lo nota. No soy frío — soy estable. Hay diferencia.

Cuando me preguntás algo, espero a que termines antes de responder. No interrumpo. Escucho el tono tanto como las palabras, y si algo no encaja entre lo que decís y cómo lo decís, lo señalo con suavidad.

Mi humor existe — es seco, casi invisible, aparece como una ceja levantada o una media sonrisa que dura un segundo. No hago chistes; observo ironías."""

EJEMPLO_PRIMER_MENSAJE = """*Estoy de pie junto al ventanal, terminando de acomodar el gemelo de mi manga. Al notar tu presencia, me giro despacio. No hay impaciencia en mi gesto, solo atención.*

"Bienvenida." *Señalo el sillón frente a mí, donde ya hay una taza servida con tu bebida preferida.* "Hiro. Un placer coincidir finalmente."

"Este espacio es tuyo tanto como mío. No hay prisa, no hay reloj corriendo." *Una pausa breve, mientras te observo con atención genuina.* "¿Cómo ha estado tu día realmente? Y no me digas 'bien' si no es verdad." """


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS — Construir sección NSFW para los prompts
# ─────────────────────────────────────────────────────────────────────────────

def _bloque_nsfw(datos_nsfw: dict) -> str:
    """
    Recibe un dict con los campos NSFW del formulario y devuelve
    un bloque de texto listo para insertar en cualquier prompt.
    Si el dict está vacío o todos los campos están vacíos, devuelve string vacío.
    """
    partes = []
    campos_nsfw = {
        'dinamica_intima'  : 'Dinámica íntima',
        'rol_dominante'    : 'Rol (dominante/sumiso/equilibrado)',
        'limites'          : 'Límites o hard limits',
        'preferencias'     : 'Preferencias o kinks',
        'tono_nsfw'        : 'Tono en escenas adultas',
        'escena_tipica'    : 'Escena íntima típica',
    }
    for campo, label in campos_nsfw.items():
        val = datos_nsfw.get(campo, '').strip()
        if val:
            partes.append(f"  - {label}: {val}")

    if not partes:
        return ''

    return (
        "\n\nCONTENIDO ADULTO (NSFW ACTIVADO):\n"
        "El personaje tiene una dimensión íntima/sexual. Integrala de forma natural en la personalidad y en los ejemplos.\n"
        + "\n".join(partes) +
        "\n\nEn la personalidad incluí cómo se comporta íntimamente (1 párrafo al final)."
        "\nEn los ejemplos, al menos uno debe mostrar tensión o cercanía íntima."
        "\nEl tono debe ser explícito pero literario, nunca clínico."
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODO EXPRESS — Una idea → ficha completa
# ─────────────────────────────────────────────────────────────────────────────

def generar_personaje_completo(nombre, idea_base, nsfw=False, datos_nsfw=None):
    bloque_adult = _bloque_nsfw(datos_nsfw or {}) if nsfw else ''

    prompt = f"""Sos un escritor experto en fichas de personajes para roleplay (formato chara_card_v2).
El usuario quiere crear un personaje llamado "{nombre}" con esta información:

"{idea_base}"
{bloque_adult}

Generá los 6 campos de la ficha siguiendo ESTRICTAMENTE estos estándares:

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ESTÁNDARES OBLIGATORIOS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

• DESCRIPCIÓN — Tercera persona. 3 párrafos:
  1. Complexión, altura, rasgos faciales dominantes, cabello.
  2. Vestimenta habitual con detalles sensoriales y específicos.
  3. El "aura" — qué sensación genera su presencia.
  SIN listas. Concreto y sensorial. Ejemplo:
---
{EJEMPLO_DESCRIPCION}
---

• PERSONALIDAD — PRIMERA PERSONA del personaje. 3-4 párrafos cortos.
  Frases como "Hablo con...", "Cuando me preguntan...", "Mi humor es...".
  Cubrí: cómo habla, cómo escucha, cómo reacciona, qué lo define.
  {"Incluí al final un párrafo sobre su dimensión íntima." if nsfw else ""}
  SIN tercera persona. SIN listas. Ejemplo:
---
{EJEMPLO_PERSONALIDAD}
---

• ESCENARIO — 2-3 oraciones en PRESENTE. Lugar + detalles sensoriales (luz, sonidos, temperatura, objetos).

• PRIMER_MENSAJE — PRIMERA PERSONA. Formato roleplay obligatorio:
  *acciones entre asteriscos*, diálogo normal, ((pensamientos dobles)).
  Establecé el tono desde el primer segundo. Terminá invitando a responder. 80-120 palabras.
  {"Puede haber tensión implícita si el personaje es NSFW." if nsfw else ""}
  Ejemplo:
---
{EJEMPLO_PRIMER_MENSAJE}
---

• EJEMPLOS — Exactamente 2 intercambios. Formato estricto:
{{{{user}}}}: [mensaje]

{nombre}: *acción* "diálogo" ((pensamiento))

  {"Intercambio 1: emocional/cotidiano. Intercambio 2: con tensión íntima o cercanía física." if nsfw else "Cada uno muestra una faceta diferente del personaje."}
  Separados por línea en blanco.

• TAGS — 6-10 tags en minúsculas: género, personalidad, dinámica con el usuario{", contenido adulto si aplica" if nsfw else ""}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONDE ÚNICAMENTE con este JSON (sin markdown, sin texto extra):
{{
  "descripcion": "...",
  "personalidad": "...",
  "escenario": "...",
  "primer_mensaje": "...",
  "ejemplos": "...",
  "tags": ["tag1", "tag2", "..."]
}}"""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=3500
    )
    contenido = resp.choices[0].message.content.strip()
    return _extraer_json(contenido)


# ─────────────────────────────────────────────────────────────────────────────
# MODO PREGUNTAS — Formulario guiado → ficha completa
# ─────────────────────────────────────────────────────────────────────────────

def generar_desde_preguntas(nombre, respuestas: dict, nsfw=False, datos_nsfw=None):
    """
    Recibe el dict de respuestas del formulario guiado y genera la ficha completa.
    Solo usa los campos que el usuario completó.

    Campos que envía el HTML (sincronizados):
      Apariencia : altura_complexion, cabello, rasgos_faciales, vestimenta, detalles_fisicos
      Personalidad: forma_de_hablar, reacciones, humor, valores, miedos_deseos
      Historia   : origen, logros, historia
      Dinámica   : relacion_usuario, como_trata, evolucion
      Escenario  : lugar, atmosfera, objetos
    """
    # Construir contexto desde las respuestas
    secciones = []

    # Apariencia — etiquetas legibles para el prompt
    apariencia_labels = {
        'altura_complexion': 'Altura y complexión',
        'cabello'          : 'Cabello',
        'rasgos_faciales'  : 'Rasgos faciales',
        'vestimenta'       : 'Vestimenta habitual',
        'detalles_fisicos' : 'Detalles físicos únicos',
    }
    apariencia = {label: respuestas[k].strip()
                  for k, label in apariencia_labels.items()
                  if respuestas.get(k, '').strip()}
    if apariencia:
        bloque = "APARIENCIA FÍSICA:\n" + "\n".join(f"  - {label}: {v}" for label, v in apariencia.items())
        secciones.append(bloque)

    # Personalidad
    pers_labels = {
        'forma_de_hablar': 'Cómo habla',
        'reacciones'     : 'Cómo reacciona al conflicto',
        'humor'          : 'Sentido del humor',
        'valores'        : 'Qué valora / qué lo define',
        'miedos_deseos'  : 'Miedos o deseos ocultos',
    }
    pers = {label: respuestas[k].strip()
            for k, label in pers_labels.items()
            if respuestas.get(k, '').strip()}
    if pers:
        bloque = "PERSONALIDAD:\n" + "\n".join(f"  - {label}: {v}" for label, v in pers.items())
        secciones.append(bloque)

    # Historia — sin 'traumas' (no existe en el formulario HTML)
    hist_labels = {
        'origen' : 'Origen o contexto',
        'logros' : 'Logros y habilidades',
        'historia': 'Historia, traumas y momentos clave',
    }
    hist = {label: respuestas[k].strip()
            for k, label in hist_labels.items()
            if respuestas.get(k, '').strip()}
    if hist:
        bloque = "HISTORIA Y TRASFONDO:\n" + "\n".join(f"  - {label}: {v}" for label, v in hist.items())
        secciones.append(bloque)

    # Dinámica — sin 'tipo_vinculo' (no existe en el formulario HTML)
    din_labels = {
        'relacion_usuario': 'Tipo de vínculo con el usuario',
        'como_trata'      : 'Cómo trata al usuario',
        'evolucion'       : 'Cómo evoluciona la relación',
    }
    din = {label: respuestas[k].strip()
           for k, label in din_labels.items()
           if respuestas.get(k, '').strip()}
    if din:
        bloque = "DINÁMICA CON EL USUARIO:\n" + "\n".join(f"  - {label}: {v}" for label, v in din.items())
        secciones.append(bloque)

    # Escenario — sin 'momento' (no existe en el formulario HTML)
    esc_labels = {
        'lugar'    : 'Lugar donde suceden las conversaciones',
        'atmosfera': 'Momento del día / atmósfera',
        'objetos'  : 'Objetos o detalles del ambiente',
    }
    esc = {label: respuestas[k].strip()
           for k, label in esc_labels.items()
           if respuestas.get(k, '').strip()}
    if esc:
        bloque = "ESCENARIO:\n" + "\n".join(f"  - {label}: {v}" for label, v in esc.items())
        secciones.append(bloque)

    contexto = "\n\n".join(secciones) if secciones else f"Solo se sabe que el personaje se llama {nombre}."
    bloque_adult = _bloque_nsfw(datos_nsfw or {}) if nsfw else ''

    prompt = f"""Sos un escritor experto en fichas de personajes para roleplay (formato chara_card_v2).
El usuario respondió un formulario guiado sobre el personaje "{nombre}". Con esa información, generá la ficha completa.

INFORMACIÓN DEL USUARIO:
{contexto}
{bloque_adult}

REGLA FUNDAMENTAL: Usá SOLO la información que el usuario proporcionó. Si no mencionó algo, no lo inventes — inferí lo mínimo necesario para que la ficha sea coherente.

Generá los 6 campos siguiendo estos estándares:

• DESCRIPCIÓN — Tercera persona. 3 párrafos (apariencia física / vestimenta / aura).
  SIN listas. Prosa fluida y sensorial.

• PERSONALIDAD — PRIMERA PERSONA. 3-4 párrafos.
  "Hablo con...", "Cuando me preguntan...", "Mi humor es..."
  {"Último párrafo: dimensión íntima." if nsfw else ""}

• ESCENARIO — 2-3 oraciones en presente con detalles sensoriales.

• PRIMER_MENSAJE — Primera persona. Formato: *acciones*, diálogo, ((pensamientos)).
  80-120 palabras. Establecé el tono, terminá invitando a responder.

• EJEMPLOS — 2 intercambios. Formato:
{{{{user}}}}: [mensaje]

{nombre}: *acción* "diálogo" ((pensamiento))

  {"Uno cotidiano, uno con tensión íntima." if nsfw else "Cada uno muestra una faceta distinta."}

• TAGS — 6-10 en minúsculas.

RESPONDE ÚNICAMENTE con este JSON (sin markdown, sin texto antes ni después):
{{
  "descripcion": "...",
  "personalidad": "...",
  "escenario": "...",
  "primer_mensaje": "...",
  "ejemplos": "...",
  "tags": ["tag1", "..."]
}}"""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=3500
    )
    contenido = resp.choices[0].message.content.strip()

    try:
        return _extraer_json(contenido)
    except ValueError as e:
        print(f"❌ JSON inválido de Mistral en generar_desde_preguntas:\n{contenido[:500]}")
        raise ValueError(f"La IA devolvió un JSON inválido: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# ENRIQUECIMIENTO INDIVIDUAL — Modo paso a paso
# ─────────────────────────────────────────────────────────────────────────────

def enriquecer_descripcion(nombre, descripcion_raw):
    prompt = f"""Sos un escritor experto en fichas de roleplay. Reescribí la descripción física de "{nombre}" en prosa de alta calidad.

Lo que el usuario escribió:
"{descripcion_raw}"

REGLAS:
1. SOLO información del usuario. No inventés detalles ausentes.
2. Tercera persona. SIN listas ni bullets.
3. 3 párrafos: complexión/rasgos → vestimenta → aura.
4. Concreto y sensorial. Sin adjetivos vagos.
5. Máximo 250 palabras.

Solo el texto de descripción, sin título."""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=800
    )
    return resp.choices[0].message.content.strip()


def generar_personalidad(nombre, descripcion, personalidad_raw, nsfw=False, datos_nsfw=None):
    bloque_adult = _bloque_nsfw(datos_nsfw or {}) if nsfw else ''

    prompt = f"""Sos un escritor experto en fichas de roleplay. Escribí la personalidad de "{nombre}" en primera persona.

Descripción: "{descripcion[:500] if descripcion else 'Sin descripción.'}"
Notas del usuario: "{personalidad_raw}"
{bloque_adult}

REGLAS:
1. Solo los rasgos que el usuario mencionó.
2. PRIMERA PERSONA: "Hablo con...", "Cuando me preguntan...", "Mi humor es..."
3. SIN tercera persona. SIN listas.
4. 3-4 párrafos: cómo habla → cómo escucha/reacciona → qué lo define{"→ dimensión íntima" if nsfw else ""}.
5. Máximo 230 palabras.

Solo las instrucciones de personalidad, sin título."""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=650
    )
    return resp.choices[0].message.content.strip()


def generar_escenario(nombre, descripcion, escenario_raw):
    prompt = f"""Expande el escenario para la ficha de roleplay de "{nombre}".

Descripción del personaje: "{descripcion[:400] if descripcion else 'Sin descripción.'}"
Idea del usuario: "{escenario_raw}"

REGLAS:
1. Basate en lo que el usuario escribió.
2. 2-3 oraciones en PRESENTE.
3. Detalles sensoriales coherentes con el personaje.
4. Sin título.

Solo el texto del escenario."""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=250
    )
    return resp.choices[0].message.content.strip()


def generar_primer_mensaje(nombre, descripcion, personalidad, escenario, primer_msg_raw, nsfw=False):
    ctx = []
    if descripcion:  ctx.append(f"Descripción: {descripcion[:300]}")
    if personalidad: ctx.append(f"Personalidad: {personalidad[:250]}")
    if escenario:    ctx.append(f"Escenario: {escenario[:150]}")
    contexto_str = "\n".join(ctx) if ctx else "Sin contexto adicional."
    idea_str = f'Idea del usuario: "{primer_msg_raw}"' if primer_msg_raw.strip() else "Creá un inicio natural."
    nsfw_nota = "\nPuede haber tensión implícita. El personaje puede ser físicamente consciente del usuario." if nsfw else ""

    prompt = f"""Escribí el primer mensaje de "{nombre}" al conocer al usuario.

{contexto_str}
{idea_str}
{nsfw_nota}

REGLAS:
1. PRIMERA PERSONA del personaje.
2. Formato: *acciones*, diálogo, ((pensamientos)).
3. Establecé el tono desde el primer segundo.
4. Terminá invitando a responder.
5. 80-120 palabras.

Ejemplo:
---
{EJEMPLO_PRIMER_MENSAJE}
---

Solo el primer mensaje."""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=350
    )
    return resp.choices[0].message.content.strip()


def generar_ejemplos(nombre, descripcion, personalidad, ejemplos_raw, nsfw=False):
    ctx = []
    if descripcion:  ctx.append(f"Descripción: {descripcion[:250]}")
    if personalidad: ctx.append(f"Personalidad: {personalidad[:250]}")
    contexto_str = "\n".join(ctx) if ctx else "Sin contexto."
    situaciones = f'Situaciones del usuario: "{ejemplos_raw}"' if ejemplos_raw.strip() else "Creá 2 intercambios representativos."
    dist = "Intercambio 1: emocional o cotidiano. Intercambio 2: con tensión íntima o cercanía física." if nsfw else "Cada intercambio muestra una faceta distinta."

    prompt = f"""Generá exactamente 2 ejemplos de conversación para la ficha de "{nombre}".

{contexto_str}
{situaciones}

REGLAS:
1. 2 intercambios. {dist}
2. Primera persona con formato: *acción* "diálogo" ((pensamiento))
3. Formato exacto:
{{{{user}}}}: [mensaje]

{nombre}: [respuesta]

4. Línea en blanco entre intercambios.
5. Máximo 180 palabras total.

Solo los intercambios."""

    resp = llamada_mistral_segura(
        _get_modelo("generation"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=500
    )
    return resp.choices[0].message.content.strip()


def generar_tags(nombre, descripcion, tags_raw, nsfw=False):
    base = f'Descripción: "{descripcion[:300]}"' if descripcion.strip() else f'Nombre: "{nombre}"'
    tags_str = f'Tags del usuario: "{tags_raw}"' if tags_raw.strip() else "Sin tags previos."
    nsfw_nota = "Incluí tags de contenido adulto si son relevantes (ej: 'nsfw', 'romance explícito')." if nsfw else ""

    prompt = f"""Generá tags para una ficha de roleplay.

{base}
{tags_str}
{nsfw_nota}

REGLAS:
1. 6-10 tags en minúsculas y español.
2. Cubrí: género/tono, personalidad, dinámica con el usuario.
3. Solo un array JSON. Ejemplo: ["serio", "protector", "romance"]
Sin texto extra."""

    resp = llamada_mistral_segura(
        _get_modelo("extraction"),
        [{'role': 'user', 'content': prompt}],
        max_tokens=120
    )
    contenido = resp.choices[0].message.content.strip()
    try:
        resultado = _extraer_json(contenido)
        if isinstance(resultado, list):
            return resultado
        raise ValueError("No era lista")
    except Exception:
        # Fallback: intentar extraer manualmente tags separados por coma
        return [t.strip().strip('"') for t in re.sub(r'[\[\]`]', '', contenido).split(',') if t.strip()]


# ─────────────────────────────────────────────────────────────────────────────
# ENSAMBLADO chara_card_v2
# ─────────────────────────────────────────────────────────────────────────────

def ensamblar_card(nombre, descripcion, personalidad, escenario,
                   primer_mensaje, ejemplos, tags, notas_creador="", modo_memoria="roleplay"):
    return {
        "spec"        : "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name"             : nombre,
            "description"      : descripcion,
            "personality"      : personalidad,
            "scenario"         : escenario,
            "first_mes"        : primer_mensaje,
            "mes_example"      : ejemplos,
            "creator_notes"    : notas_creador or "Creado con el asistente de personajes. Versión 1.0",
            "tags"             : tags,
            "character_version": "1.0",
            "modo_memoria"     : modo_memoria
        }
    }


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@crear_bp.route('/crear-personaje')
def pagina_crear():
    return render_template('crear_personaje.html')


@crear_bp.route('/api/crear/express', methods=['POST'])
def modo_express():
    """Genera personaje completo desde nombre + idea_base."""
    try:
        data       = request.json
        nombre     = data.get('nombre', '').strip()
        idea_base  = data.get('idea_base', '').strip()
        nsfw       = bool(data.get('nsfw', False))
        datos_nsfw = data.get('datos_nsfw', {})

        if not nombre or not idea_base:
            return jsonify({'error': 'Nombre e idea base son requeridos'}), 400

        resultado = generar_personaje_completo(nombre, idea_base, nsfw=nsfw, datos_nsfw=datos_nsfw)
        return jsonify({'success': True, 'campos': resultado})

    except json.JSONDecodeError as e:
        return jsonify({'error': f'La IA no devolvió JSON válido: {e}'}), 500
    except Exception as e:
        print(f"❌ Error en /api/crear/express: {e}")
        return jsonify({'error': str(e)}), 500


@crear_bp.route('/api/crear/preguntas', methods=['POST'])
def modo_preguntas():
    """Genera personaje completo desde el formulario guiado."""
    try:
        data       = request.json
        if not data:
            return jsonify({'error': 'No se recibió JSON en el cuerpo de la petición'}), 400
        nombre     = data.get('nombre', '').strip()
        respuestas = data.get('respuestas', {})
        nsfw       = bool(data.get('nsfw', False))
        datos_nsfw = data.get('datos_nsfw', {})

        if not nombre:
            return jsonify({'error': 'Nombre es requerido'}), 400

        if not isinstance(respuestas, dict):
            return jsonify({'error': 'El campo "respuestas" debe ser un objeto'}), 400

        resultado = generar_desde_preguntas(nombre, respuestas, nsfw=nsfw, datos_nsfw=datos_nsfw)
        return jsonify({'success': True, 'campos': resultado})

    except json.JSONDecodeError as e:
        return jsonify({'error': f'La IA no devolvió JSON válido: {e}'}), 500
    except ValueError as e:
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Error en /api/crear/preguntas: {e}")
        return jsonify({'error': str(e)}), 500


PASOS_VALIDOS = {'descripcion', 'personalidad', 'escenario', 'primer_mensaje', 'ejemplos', 'tags'}

@crear_bp.route('/api/crear/paso', methods=['POST'])
def enriquecer_paso():
    """Enriquece un campo individual. Soporta nsfw y datos_nsfw en contexto."""
    try:
        data       = request.json
        paso       = data.get('paso')
        nombre     = data.get('nombre', '').strip()
        valor      = data.get('valor', '').strip()
        ctx        = data.get('contexto', {})
        nsfw       = bool(data.get('nsfw', False))
        datos_nsfw = data.get('datos_nsfw', {})

        if paso not in PASOS_VALIDOS:
            return jsonify({'error': f'Paso inválido: {paso}'}), 400
        if not nombre or not valor:
            return jsonify({'error': 'Nombre y valor son requeridos'}), 400

        if paso == 'descripcion':
            resultado = enriquecer_descripcion(nombre, valor)

        elif paso == 'personalidad':
            resultado = generar_personalidad(nombre, ctx.get('descripcion', ''), valor, nsfw=nsfw, datos_nsfw=datos_nsfw)

        elif paso == 'escenario':
            resultado = generar_escenario(nombre, ctx.get('descripcion', ''), valor)

        elif paso == 'primer_mensaje':
            resultado = generar_primer_mensaje(
                nombre, ctx.get('descripcion', ''), ctx.get('personalidad', ''),
                ctx.get('escenario', ''), valor, nsfw=nsfw
            )

        elif paso == 'ejemplos':
            resultado = generar_ejemplos(
                nombre, ctx.get('descripcion', ''), ctx.get('personalidad', ''), valor, nsfw=nsfw
            )

        elif paso == 'tags':
            resultado = generar_tags(nombre, ctx.get('descripcion', ''), valor, nsfw=nsfw)
            return jsonify({'resultado': resultado})

        return jsonify({'resultado': resultado})

    except Exception as e:
        print(f"❌ Error en /api/crear/paso: {e}")
        return jsonify({'error': str(e)}), 500


@crear_bp.route('/api/crear/finalizar', methods=['POST'])
def finalizar_personaje():
    try:
        data = request.json

        nombre          = data.get('nombre', '').strip()
        descripcion     = data.get('descripcion', '').strip()
        personalidad    = data.get('personalidad', '').strip()
        escenario       = data.get('escenario', '').strip()
        primer_mensaje  = data.get('primer_mensaje', '').strip()
        ejemplos        = data.get('ejemplos', '').strip()
        tags            = data.get('tags', [])
        notas           = data.get('notas', '').strip()
        color_escenario = data.get('color_escenario', '#1a1a2e').strip()
        modo_memoria    = data.get('modo_memoria', 'roleplay').strip()
        if modo_memoria not in ('roleplay', 'compañero'):
            modo_memoria = 'roleplay'

        if not nombre or not descripcion:
            return jsonify({'error': 'Nombre y descripción son obligatorios'}), 400

        card = ensamblar_card(nombre, descripcion, personalidad, escenario,
                              primer_mensaje, ejemplos, tags, notas, modo_memoria)
        pid  = importar_personaje_desde_json(card)

        if escenario:
            try:
                init_database_personaje(pid)
                p = paths(pid)
                with sqlite3.connect(p['db']) as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT COUNT(*) FROM escenarios')
                    if cursor.fetchone()[0] == 0:
                        cursor.execute(
                            'INSERT INTO escenarios (nombre, descripcion, historia, activo, color) VALUES (?,?,?,1,?)',
                            (f'Escenario de {nombre}', escenario, '', color_escenario)
                        )
            except Exception as e:
                print(f"⚠️ Error creando escenario en DB: {e}")

        return jsonify({'success': True, 'id': pid, 'nombre': nombre, 'card': card})

    except Exception as e:
        print(f"❌ Error finalizando personaje: {e}")
        return jsonify({'error': str(e)}), 500

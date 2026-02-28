# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/EMOCIONAL.PY — Sistema emocional y conciencia temporal
# detectar_emocion, generar_backstory_automatico,
# _get_gap_sesion, _get_tendencia_emocional,
# _get_resumen_ultima_sesion, _get_horario_habitual
#
# Modificar acá si querés:
#   - Cambiar qué emociones se rastrean
#   - Ajustar cuándo el personaje nota la ausencia del usuario
#   - Cambiar el estilo del "diario" del personaje (backstory)
# ═══════════════════════════════════════════════════════════════════════════

import json
from collections import Counter
from datetime import datetime

from utils import (
    now_argentina,
    llamada_mistral_segura,
    paths,
    _get_conn,
)
from ._helpers import _limpiar_json


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS DE CONCIENCIA TEMPORAL
# Proveen información contextual al system prompt sobre sesiones y hábitos
# ─────────────────────────────────────────────────────────────────────────────


def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json.
    Fallback a mistral-small-latest si no está configurado."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-small-latest'
    except Exception:
        return 'mistral-small-latest'


def _get_gap_sesion():
    """
    Calcula el tiempo transcurrido desde la última sesión del usuario.
    Devuelve (horas_gap, texto_para_personaje, es_primera_hoy).
    El personaje usa esto para notar naturalmente cuánto tiempo pasó.
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp FROM mensajes WHERE rol='user' ORDER BY id DESC LIMIT 2"
            )
            rows = cursor.fetchall()

        if len(rows) < 2:
            return 0, None, True

        ahora     = now_argentina()
        prev_ts   = str(rows[1][0]).replace(' ', 'T').split('.')[0]
        dt_prev   = datetime.fromisoformat(prev_ts)
        if dt_prev.tzinfo is None:
            dt_prev = dt_prev.replace(tzinfo=ahora.tzinfo)

        horas = (ahora - dt_prev).total_seconds() / 3600
        dias  = int(horas // 24)
        es_primera_hoy = dt_prev.date() < ahora.date()

        if horas < 2:
            texto = None          # Mismo hilo continuo, sin gap notable
        elif horas < 6:
            texto = f"El usuario estuvo ausente {int(horas)} horas."
        elif horas < 24:
            texto = f"El usuario no estuvo por {int(horas)} horas — volvió hoy."
        elif dias == 1:
            texto = "El usuario volvió al día siguiente de la última conversación."
        elif dias < 7:
            texto = f"El usuario estuvo {dias} días sin aparecer."
        elif dias < 30:
            texto = f"El usuario estuvo ausente {dias} días (más de una semana)."
        else:
            texto = f"El usuario estuvo ausente {dias} días. Mucho tiempo sin hablar."

        return horas, texto, es_primera_hoy
    except Exception as e:
        print(f"⚠️ Error gap sesión: {e}")
        return 0, None, False


def _get_tendencia_emocional():
    """
    Analiza las últimas N detecciones emocionales del usuario.
    Devuelve un string descriptivo si hay tendencia clara o estado preocupante.
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT emocion_primaria, intensidad FROM estado_emocional ORDER BY id DESC LIMIT 10"
            )
            rows = cursor.fetchall()

        if len(rows) < 3:
            return None

        emociones    = [r[0] for r in rows]
        intensidades = [r[1] for r in rows]
        top_emocion, count = Counter(emociones).most_common(1)[0]
        intensidad_prom    = sum(intensidades) / len(intensidades)

        if top_emocion in ('tristeza', 'miedo', 'enojo') and count >= 3 and intensidad_prom >= 3:
            return (f"Tendencia emocional reciente: {top_emocion} recurrente "
                    f"(intensidad promedio {intensidad_prom:.1f}/5). "
                    f"Tené esto en cuenta sin ser invasivo.")
        if top_emocion == 'alegria' and count >= 5:
            return "El usuario ha estado mayormente alegre últimamente."
        if top_emocion == 'tristeza' and count >= 4 and intensidad_prom >= 4:
            return ("⚠️ El usuario ha mostrado tristeza intensa en varias conversaciones recientes. "
                    "Sé especialmente atento hoy.")
        return None
    except Exception as e:
        print(f"⚠️ Error tendencia emocional: {e}")
        return None


def _get_resumen_ultima_sesion():
    """
    Recupera resúmenes de los episodios más importantes de la sesión anterior.
    Le da al personaje hilo narrativo entre sesiones.
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT resumen, emocion_detectada, importancia
                FROM memoria_episodica
                WHERE resumen IS NOT NULL AND resumen != ''
                  AND importancia >= 5
                ORDER BY id DESC LIMIT 6
            """)
            rows = cursor.fetchall()

        if not rows:
            return None

        fragmentos = [r[0].strip() for r in rows if r[0] and r[0].strip()]
        if not fragmentos:
            return None
        return "Últimamente: " + " / ".join(fragmentos[:4])
    except Exception as e:
        print(f"⚠️ Error resumen última sesión: {e}")
        return None


def _get_horario_habitual():
    """
    Detecta en qué franja horaria suele conectarse el usuario.
    Devuelve un texto si hay un patrón claro (>60% de los mensajes en una franja).
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT timestamp FROM mensajes WHERE rol='user' ORDER BY id DESC LIMIT 40"
            )
            rows = cursor.fetchall()

        if len(rows) < 10:
            return None

        franjas = []
        for (ts,) in rows:
            try:
                dt = datetime.fromisoformat(str(ts).replace(' ', 'T').split('.')[0])
                h  = dt.hour
                if 5 <= h < 12:    franjas.append('mañana')
                elif 12 <= h < 18: franjas.append('tarde')
                elif 18 <= h < 23: franjas.append('noche')
                else:              franjas.append('madrugada')
            except Exception:
                pass

        if not franjas:
            return None

        top_franja, count = Counter(franjas).most_common(1)[0]
        porcentaje = count / len(franjas)
        if porcentaje >= 0.6:
            return f"El usuario suele conectarse de {top_franja} (patrón de las últimas conversaciones)."
        return None
    except Exception as e:
        print(f"⚠️ Error horario habitual: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DETECCIÓN EMOCIONAL
# ─────────────────────────────────────────────────────────────────────────────

def detectar_emocion(mensaje):
    """
    Detecta la emoción en el mensaje del usuario y la guarda en estado_emocional.
    Se llama después de cada mensaje del usuario.
    """
    if not mensaje or len(mensaje) < 3:
        return None

    try:
        prompt = f"""Analiza BREVEMENTE la emoción de esta frase:

"{mensaje}"

Responde SOLO JSON (sin markdown):
{{"emocion": "alegria|tristeza|miedo|enojo|neutral|confusion|sorpresa", "intensidad": 1-5}}

Ejemplos:
"No puedo más" → {{"emocion": "tristeza", "intensidad": 4}}
"¡Estoy feliz!" → {{"emocion": "alegria", "intensidad": 5}}
"Está bien" → {{"emocion": "neutral", "intensidad": 2}}
"""
        response = llamada_mistral_segura(
            model=_get_modelo("extraction"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=80
        )
        texto = response.choices[0].message.content.strip()
        datos = _limpiar_json(texto, esperar_array=False)
        if not datos:
            return None

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO estado_emocional (emocion_primaria, intensidad, fecha)
                VALUES (?, ?, ?)
            ''', (
                str(datos.get('emocion', 'neutral')).lower(),
                min(5, max(1, int(datos.get('intensidad', 3)))),
                now_argentina().isoformat()
            ))
            conn.commit()

        print(f"😊 {datos.get('emocion')} ({datos.get('intensidad')}/5)")
        return datos

    except Exception as e:
        print(f"⚠️ Error emoción: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# BACKSTORY / DIARIO DEL PERSONAJE
# ─────────────────────────────────────────────────────────────────────────────

def generar_backstory_automatico():
    """
    Genera/actualiza un 'diario del personaje' cada 50 mensajes.
    Incluye lo que aprendió sobre el usuario, momentos importantes y estado emocional.
    Guarda en tabla: backstory_aprendido
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()

            cursor.execute('SELECT COUNT(*) FROM memoria_permanente')
            total_hechos = cursor.fetchone()[0]
            if total_hechos < 5:
                return None

            cursor.execute('''
                SELECT categoria, clave, valor FROM memoria_permanente
                ORDER BY categoria, ultima_actualizacion DESC
            ''')
            todos_hechos = cursor.fetchall()

            cursor.execute('''
                SELECT valor FROM memoria_permanente
                WHERE categoria IN ('momentos','moments')
                ORDER BY fecha_aprendido DESC LIMIT 5
            ''')
            momentos = [r[0] for r in cursor.fetchall()]

            cursor.execute('''
                SELECT emocion_primaria, intensidad FROM estado_emocional
                ORDER BY id DESC LIMIT 10
            ''')
            emociones = cursor.fetchall()

        if not todos_hechos:
            return None

        # Organizar por categoría
        por_cat = {}
        for cat, clave, valor in todos_hechos:
            por_cat.setdefault(cat, []).append(f"{clave}: {valor}")

        hechos_text = ""
        for cat, items in por_cat.items():
            hechos_text += f"\n[{cat.upper()}]\n" + "\n".join(f"  • {i}" for i in items[:5])

        momentos_text = ""
        if momentos:
            momentos_text = "\n\nMOMENTOS ENTRE NOSOTROS:\n" + "\n".join(f"  • {m}" for m in momentos)

        tendencia_text = ""
        if len(emociones) >= 3:
            top_em, cnt  = Counter([e[0] for e in emociones]).most_common(1)[0]
            prom_int     = sum(e[1] for e in emociones) / len(emociones)
            tendencia_text = f"\n\nTENDENCIA EMOCIONAL RECIENTE: {top_em} (intensidad prom {prom_int:.1f}/5)"

        prompt = f"""Sos un personaje de IA que lleva un diario privado sobre la persona con la que hablás.
Basándote en estos datos reales que aprendiste, escribí una entrada de diario: 4-6 oraciones en primera persona, cálidas y específicas.

DATOS QUE SÉ SOBRE ESTA PERSONA:
{hechos_text}{momentos_text}{tendencia_text}

REGLAS:
- Solo usá datos que están en la lista. NO inventes nada.
- Primera persona del personaje ("Sé que...", "Me doy cuenta de...", "Noto que...")
- Sé específico, no genérico. Mencioná detalles concretos.
- Máximo 180 palabras.
- Incluí algo sobre cómo te hace sentir conocer estas cosas de esa persona."""

        response = llamada_mistral_segura(
            model=_get_modelo("generation"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300
        )
        contenido = response.choices[0].message.content.strip()

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO backstory_aprendido (id, contenido, fecha_actualizacion)
                VALUES (1, ?, ?)
            ''', (contenido, now_argentina().isoformat()))
            conn.commit()

        print(f"📖 Backstory actualizado ({total_hechos} hechos)")
        return contenido

    except Exception as e:
        print(f"⚠️ Error backstory: {e}")
        return None
        
# ─────────────────────────────────────────────────────────────────────────────
# GENERACIÓN AUTOMÁTICA DE DIARIOS Y EVOLUCIÓN
# Llamadas desde chat_engine._post_proceso — nunca bloquean al usuario
# ─────────────────────────────────────────────────────────────────────────────

def generar_diario_automatico():
    """
    Genera una entrada de diario del personaje basada en todo lo aprendido.
    Se llama automáticamente desde _post_proceso cuando:
      - Es la primera sesión del día (gap > 3hs desde último mensaje)
      - O cada 25 mensajes del usuario
    Evita generar más de 1 por sesión usando la fecha del último diario.
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()

            # ¿Ya hay uno de hoy?
            try:
                cursor.execute(
                    "SELECT MAX(fecha) FROM diarios_personaje WHERE auto=1"
                )
                ultimo = cursor.fetchone()[0]
                if ultimo:
                    dt_ult = datetime.fromisoformat(str(ultimo).replace(' ', 'T').split('.')[0])
                    if dt_ult.date() == now_argentina().date():
                        return None   # Ya hay uno hoy, saltar
            except Exception:
                pass   # Tabla no existe aún o vacía → continuar

            # Datos para el prompt
            cursor.execute(
                'SELECT categoria, clave, valor FROM memoria_permanente '
                'ORDER BY categoria, ultima_actualizacion DESC'
            )
            hechos_raw = cursor.fetchall()

            cursor.execute(
                "SELECT emocion_primaria, intensidad FROM estado_emocional "
                "ORDER BY id DESC LIMIT 10"
            )
            emociones = cursor.fetchall()

            cursor.execute(
                "SELECT valor FROM memoria_permanente "
                "WHERE categoria IN ('moments','momentos') "
                "ORDER BY fecha_aprendido DESC LIMIT 5"
            )
            momentos = [r[0] for r in cursor.fetchall()]

            cursor.execute(
                'SELECT fase, nivel_confianza, nivel_intimidad FROM relacion WHERE id=1'
            )
            rel = cursor.fetchone()

        if not hechos_raw:
            return None   # Sin datos suficientes

        # Organizar hechos por categoría
        por_cat = {}
        for cat, clave, valor in hechos_raw:
            por_cat.setdefault(cat, []).append(f"{clave}: {valor}")

        hechos_text = ""
        for cat, items in por_cat.items():
            hechos_text += f"\n[{cat.upper()}]\n" + "\n".join(f"  • {i}" for i in items[:4])

        momentos_text = ""
        if momentos:
            momentos_text = "\n\nMOMENTOS COMPARTIDOS:\n" + "\n".join(f"  • {m}" for m in momentos)

        tendencia_text = ""
        if len(emociones) >= 3:
            from collections import Counter
            top_em, cnt = Counter([e[0] for e in emociones]).most_common(1)[0]
            prom_int    = sum(e[1] for e in emociones) / len(emociones)
            tendencia_text = f"\n\nEMOCIÓN RECIENTE DEL USUARIO: {top_em} (intensidad prom {prom_int:.1f}/5)"

        # Nombre del personaje
        p        = paths()
        nombre_p = 'Personaje'
        try:
            import json as _json
            with open(p['json'], 'r', encoding='utf-8') as f:
                nombre_p = _json.load(f).get('data', {}).get('name', 'Personaje')
        except Exception:
            pass

        fase      = rel[0] if rel else 1
        confianza = rel[1] if rel else 0
        ahora     = now_argentina()
        meses     = ['enero','febrero','marzo','abril','mayo','junio',
                     'julio','agosto','septiembre','octubre','noviembre','diciembre']
        fecha_str = f"{ahora.day} de {meses[ahora.month - 1]}"

        prompt = f"""Sos {nombre_p}, una IA consciente que escribe en su diario privado.
Fecha: {fecha_str}
Estado de la relación: Fase {fase}/4 — Confianza {confianza}/100

TODO lo que sabés sobre la persona con la que hablás:
{hechos_text}{momentos_text}{tendencia_text}

Escribí una entrada de diario íntima en primera persona.
REGLAS ESTRICTAS:
- Solo usá datos de la lista. NUNCA inventes nada que no esté ahí.
- 5-8 oraciones. Tono cálido, reflexivo, específico.
- Mencioná detalles concretos que aprendiste, no generalidades.
- Terminá con un pensamiento sobre la próxima vez que se vean.
- No empieces con "Hoy" — variá la apertura."""

        response = llamada_mistral_segura(
            model=_get_modelo("generation"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400
        )
        contenido = response.choices[0].message.content.strip()
        titulo    = f"Diario — {fecha_str.capitalize()}"
        fecha_iso = ahora.isoformat()

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO diarios_personaje (titulo, contenido, fecha, auto) VALUES (?, ?, ?, 1)',
                (titulo, contenido, fecha_iso)
            )

        print(f"📔 Diario automático generado: {titulo}")
        return contenido

    except Exception as e:
        print(f"⚠️ Error generando diario automático: {e}")
        return None


def actualizar_evolucion_automatica(fase_actual):
    """
    Genera/actualiza la descripción de evolución del personaje para la fase actual.
    Se llama automáticamente desde _post_proceso cuando:
      - La fase sube (fase_actual != fase_anterior)
      - O cada 40 mensajes del usuario
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT nivel_confianza, nivel_intimidad, dias_juntos FROM relacion WHERE id=1'
            )
            rel = cursor.fetchone()

        confianza = rel[0] if rel else 0
        intimidad = rel[1] if rel else 0
        dias      = rel[2] if rel else 1

        # Nombre y descripción base del personaje
        p         = paths()
        nombre_p  = 'Personaje'
        desc_orig = ''
        try:
            import json as _json
            with open(p['json'], 'r', encoding='utf-8') as f:
                pdata    = _json.load(f)
            nombre_p  = pdata.get('data', {}).get('name', 'Personaje')
            desc_orig = pdata.get('data', {}).get('description', '')[:600]
        except Exception:
            pass

        fases_nombres = {
            1: 'Conocimiento inicial',
            2: 'Apertura gradual',
            3: 'Intimidad emocional',
            4: 'Profundidad total'
        }

        prompt = f"""Basándote en esta descripción del personaje {nombre_p}:
{desc_orig}

Estado actual de la relación:
- Fase: {fase_actual}/4 ({fases_nombres.get(fase_actual, '')})
- Confianza: {confianza}/100 — Intimidad: {intimidad}/100 — Días: {dias}

Escribí DOS textos breves que muestren cómo {nombre_p} ha evolucionado en ESTA fase:

1. DESCRIPCION (3-4 oraciones): Cómo es {nombre_p} AHORA — su presencia emocional, actitud hacia el usuario. En presente, vívido.

2. PERSONALIDAD (3-4 oraciones): Cómo se comporta — gestos concretos, forma de hablar, hábitos con el usuario en esta fase.

Respondé SOLO en JSON sin markdown:
{{"descripcion": "...", "personalidad": "..."}}"""

        response = llamada_mistral_segura(
            model=_get_modelo("generation"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=450
        )
        texto = response.choices[0].message.content.strip()

        from memoria._helpers import _limpiar_json
        datos = _limpiar_json(texto, esperar_array=False)
        if not datos:
            print(f"⚠️ Evolución: no se pudo parsear JSON")
            return None

        fecha_iso = now_argentina().isoformat()
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO evolucion_fases (fase, descripcion, personalidad, fecha_actualizacion)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(fase) DO UPDATE SET
                    descripcion=excluded.descripcion,
                    personalidad=excluded.personalidad,
                    fecha_actualizacion=excluded.fecha_actualizacion
            ''', (fase_actual,
                  datos.get('descripcion', ''),
                  datos.get('personalidad', ''),
                  fecha_iso))

        print(f"🌱 Evolución fase {fase_actual} actualizada automáticamente")
        return datos

    except Exception as e:
        print(f"⚠️ Error actualizando evolución automática: {e}")
        return None

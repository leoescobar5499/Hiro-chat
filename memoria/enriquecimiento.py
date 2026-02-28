# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/ENRIQUECIMIENTO.PY — Enriquecimiento episódico
# _enriquecer_episodio: después de guardar un episodio, llama a IA para
# rellenar resumen, temas, emoción e importancia.
#
# Modificar acá si querés:
#   - Cambiar la escala de importancia
#   - Agregar nuevos campos al análisis del episodio
#   - Ajustar cuántos temas frecuentes se trackean
# ═══════════════════════════════════════════════════════════════════════════

import json
from collections import Counter

from utils import (
    now_argentina,
    llamada_mistral_segura,
    paths,
    _get_conn,
)
from ._helpers import _limpiar_json



def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json.
    Fallback a mistral-small-latest si no está configurado."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-small-latest'
    except Exception:
        return 'mistral-small-latest'


def _enriquecer_episodio(episodio_id, contenido_usuario, contenido_personaje):
    """
    Rellena resumen, temas, emocion_detectada e importancia de un episodio recién guardado.
    También actualiza los temas_frecuentes en la tabla relacion.
    """
    if not contenido_usuario or contenido_usuario == '[continuar]':
        texto_analizar = f"Personaje: {contenido_personaje}"
    else:
        texto_analizar = f"Usuario: {contenido_usuario}\nPersonaje: {contenido_personaje}"

    prompt = f"""Analizá este intercambio de un chat de roleplay/compañero virtual:

{texto_analizar}

Respondé SOLO con JSON con estos 4 campos:
{{
  "resumen": "Una oración que capture qué pasó en este intercambio (máximo 20 palabras)",
  "temas": ["tema1", "tema2"],
  "emocion": "la emoción principal del usuario en este intercambio (una palabra: curiosidad/alegría/tristeza/nerviosismo/intimidad/indiferencia/sorpresa/neutro)",
  "importancia": <número del 1 al 10>
}}

ESCALA DE IMPORTANCIA — sé estricto:
1-2: Saludo básico, "*entra*", "*se sienta*", acción sin contenido
3-4: Pregunta simple, acción de roleplay con algo de diálogo
5-6: Intercambio con contenido real (el usuario contó algo de su día, hizo una pregunta personal)
7-8: Momento significativo (confesión, dato personal importante, primer contacto emocional)
9-10: Momento clave de la relación (declaración de afecto, decisión importante, vulnerabilidad profunda)

EJEMPLOS:
- "*Entro y me siento* Hola. Me llamo Leo" → importancia: 3 (presentación básica)
- "Soy gay jajaj" → importancia: 7 (confesión personal)
- "te quiero" → importancia: 9 (declaración de afecto)"""

    try:
        resp = llamada_mistral_segura(
            model=_get_modelo("enrichment"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=200
        )
        contenido = resp.choices[0].message.content.strip()
        datos = _limpiar_json(contenido, esperar_array=False)
        if not datos:
            return

        resumen     = str(datos.get('resumen', ''))[:500]
        temas       = datos.get('temas', [])
        if not isinstance(temas, list): temas = []
        temas_json  = json.dumps(temas, ensure_ascii=False)
        emocion     = str(datos.get('emocion', ''))[:50]
        importancia = max(1, min(10, int(datos.get('importancia', 5))))

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE memoria_episodica
                SET resumen=?, temas=?, emocion_detectada=?, importancia=?
                WHERE id=?
            ''', (resumen, temas_json, emocion, importancia, episodio_id))
        print(f"✅ Episodio {episodio_id} enriquecido — importancia:{importancia} emoción:{emocion}")

        # Actualizar temas frecuentes en la relación
        try:
            with _get_conn(paths()['db']) as conn2:
                c2 = conn2.cursor()
                c2.execute("SELECT temas FROM memoria_episodica WHERE temas IS NOT NULL ORDER BY id DESC LIMIT 30")
                todos_temas = []
                for (t_json,) in c2.fetchall():
                    try: todos_temas.extend(json.loads(t_json))
                    except Exception: pass
                if todos_temas:
                    top_temas = [t for t, _ in Counter(todos_temas).most_common(8)]
                    c2.execute("UPDATE relacion SET temas_frecuentes=? WHERE id=1",
                               (json.dumps(top_temas, ensure_ascii=False),))
        except Exception as e_tf:
            print(f"⚠️ Error actualizando temas_frecuentes: {e_tf}")

    except Exception as e:
        print(f"⚠️ Error enriqueciendo episodio {episodio_id}: {e}")

# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/SINTESIS.PY — Síntesis de conocimiento y perfil narrativo
# _debe_regenerar_sintesis, _ejecutar_sintesis,
# generar_perfil_narrativo, generar_resumen_relacion, generar_sintesis
#
# Modificar acá si querés:
#   - Cambiar cuándo se regenera la síntesis (triggers)
#   - Cambiar el estilo del perfil narrativo del usuario
#   - Cambiar cómo se describe la historia relacional
# ═══════════════════════════════════════════════════════════════════════════

import json
from datetime import datetime

from utils import (
    now_argentina,
    llamada_mistral_segura,
    paths,
    _get_conn,
    reparar_valor_db,
)



def _get_modelo(tarea):
    """Lee el modelo configurado para esta tarea desde api_config.json.
    Fallback a mistral-small-latest si no está configurado."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get(tarea) or 'mistral-small-latest'
    except Exception:
        return 'mistral-small-latest'


def _debe_regenerar_sintesis():
    """
    Retorna (bool, motivo_str).
    Triggers:
      A) 3+ hs de pausa entre mensajes (nueva sesión)
      B) 15+ hechos nuevos desde la última síntesis
      C) 72+ hs sin actualizar (fallback de seguridad)
    """
    ahora = now_argentina()
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp FROM mensajes WHERE rol='user' ORDER BY id DESC LIMIT 2")
        rows = cursor.fetchall()
        penultimo_ts = rows[1][0] if len(rows) >= 2 else None
        cursor.execute("SELECT MAX(fecha_actualizacion) FROM sintesis_conocimiento")
        ultima_sint_ts = cursor.fetchone()[0]
        if ultima_sint_ts:
            cursor.execute("SELECT COUNT(*) FROM memoria_permanente WHERE fecha_aprendido > ?", (ultima_sint_ts,))
        else:
            cursor.execute("SELECT COUNT(*) FROM memoria_permanente")
        hechos_nuevos = cursor.fetchone()[0]

    if penultimo_ts:
        try:
            dt_prev = datetime.fromisoformat(str(penultimo_ts).replace(' ','T').split('.')[0])
            if dt_prev.tzinfo is None: dt_prev = dt_prev.replace(tzinfo=ahora.tzinfo)
            if (ahora - dt_prev).total_seconds() / 3600 >= 3:
                return True, f"nueva sesión ({(ahora - dt_prev).total_seconds()/3600:.1f}hs de pausa)"
        except Exception: pass

    if hechos_nuevos >= 15:
        return True, f"material acumulado ({hechos_nuevos} hechos nuevos)"

    if ultima_sint_ts:
        try:
            dt_sint = datetime.fromisoformat(str(ultima_sint_ts).replace(' ','T').split('.')[0])
            if dt_sint.tzinfo is None: dt_sint = dt_sint.replace(tzinfo=ahora.tzinfo)
            horas = (ahora - dt_sint).total_seconds() / 3600
            if horas >= 72: return True, f"fallback 72hs ({horas:.0f}hs sin actualizar)"
        except Exception: pass
    else:
        return True, "primera síntesis"

    return False, "no corresponde"


def _ejecutar_sintesis(motivo=""):
    """Corre el pipeline completo de síntesis."""
    print(f"🧠 Regenerando síntesis — motivo: {motivo}")
    for fn, nombre in [
        (generar_perfil_narrativo, "perfil"),
        (generar_resumen_relacion, "relación"),
        (generar_sintesis,         "categorías"),
    ]:
        try: fn()
        except Exception as e: print(f"⚠️ Error síntesis {nombre}: {e}")


def generar_resumen_relacion():
    """Genera párrafo narrativo de la historia relacional en prosa."""
    CATS_MOMENTOS = {'moments', 'momentos'}
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(CATS_MOMENTOS))
        cursor.execute(
            f"SELECT clave, valor, contexto, fecha_aprendido FROM memoria_permanente WHERE categoria IN ({placeholders}) ORDER BY fecha_aprendido ASC",
            list(CATS_MOMENTOS)
        )
        momentos = cursor.fetchall()

    if not momentos:
        return

    if len(momentos) < 2:
        resumen_simple = "La relación está en sus inicios. Aún estamos intercambiando las primeras impresiones."
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sintesis_conocimiento
                (categoria, titulo, contenido, fuentes, fecha_creacion, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(categoria, titulo) DO UPDATE SET
                    contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
            ''', ('resumen_relacion', 'Historia entre ustedes', resumen_simple, '[]',
                  now_argentina().isoformat(), now_argentina().isoformat()))
        print("✅ Resumen relacional (inicial) actualizado")
        return

    lineas = []
    for clave, valor, ctx, fecha in momentos:
        try:
            dt = datetime.fromisoformat(str(fecha).replace(' ', 'T').split('.')[0])
            fecha_fmt = dt.strftime("%-d %b").lower()
        except Exception:
            fecha_fmt = str(fecha)[:10]
        linea = f"- {fecha_fmt}: {valor}"
        if ctx and ctx.strip(): linea += f" ({ctx.strip()})"
        lineas.append(linea)

    prompt = f"""Estos son los momentos importantes entre el usuario y su compañero virtual:
{chr(10).join(lineas)}
Escribí un párrafo de 3-4 oraciones que cuente la historia de esta relación. No uses listas. Primera persona del compañero recordando lo que construyeron juntos.
IMPORTANTE: No inventes sentimientos de "siempre" o "eterno" si la relación es corta. Sé fiel a la línea de tiempo."""

    try:
        resp = llamada_mistral_segura(
            model=_get_modelo("synthesis"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=250
        )
        resumen = resp.choices[0].message.content.strip()
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sintesis_conocimiento
                (categoria, titulo, contenido, fuentes, fecha_creacion, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(categoria, titulo) DO UPDATE SET
                    contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
            ''', ('resumen_relacion', 'Historia entre ustedes', resumen, '[]',
                  now_argentina().isoformat(), now_argentina().isoformat()))
        print("✅ Resumen relacional actualizado")
    except Exception as e:
        print(f"⚠️ Error resumen relacional: {e}")


def generar_perfil_narrativo():
    """Genera un párrafo narrativo sobre el usuario en prosa. Base para obtener_contexto."""
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT categoria, clave, valor FROM memoria_permanente ORDER BY categoria, ultima_actualizacion DESC')
        hechos_raw = cursor.fetchall()

    if not hechos_raw:
        return

    if len(hechos_raw) < 3:
        perfil_simple = "Apenas nos estamos conociendo. Por ahora solo sé datos básicos y puntuales."
        fuentes_str = json.dumps([f"{c}:{cl}" for c, cl, v in hechos_raw])
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sintesis_conocimiento
                (categoria, titulo, contenido, fuentes, fecha_creacion, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(categoria, titulo) DO UPDATE SET
                    contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
            ''', ('perfil_narrativo', 'Quién es el usuario', perfil_simple,
                  fuentes_str,
                  now_argentina().isoformat(), now_argentina().isoformat()))
        print("✅ Perfil narrativo: Pocos datos, usando default.")
        return

    hechos_texto = "\n".join(f"- [{cat}] {clave}: {valor}" for cat, clave, valor in hechos_raw)

    prompt = f"""Tenés estos datos HECHOS Y CONFIRMADOS sobre una persona real con la que hablás:

{hechos_texto}

Tu tarea: Escribir un perfil BREVE (máximo 50 palabras) sobre quién es esta persona.

⛔ PROHIBICIONES ESTRICTAS:
1. NO uses palabras como "rutina", "siempre", "frecuentemente", "amigo" o "cercano" a menos que los datos lo digan explícitamente.
2. NO asumas sentimientos del usuario que no estén escritos ahí.
3. NO inventes que "le gusta hablar conmigo" si no está en los datos.
4. Escribí en tercera persona y sé objetivo.

Objetivo: Un resumen útil y seco, no una novela."""

    try:
        resp = llamada_mistral_segura(
            model=_get_modelo("synthesis"),
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300
        )
        perfil = resp.choices[0].message.content.strip()
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO sintesis_conocimiento
                (categoria, titulo, contenido, fuentes, fecha_creacion, fecha_actualizacion)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(categoria, titulo) DO UPDATE SET
                    contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
            ''', ('perfil_narrativo', 'Quién es el usuario', perfil,
                  json.dumps([f"{c}:{cl}" for c, cl, v in hechos_raw]),
                  now_argentina().isoformat(), now_argentina().isoformat()))
        print("✅ Perfil narrativo actualizado")
    except Exception as e:
        print(f"⚠️ Error perfil narrativo: {e}")


def generar_sintesis():
    """
    Síntesis por categoría — solo para categorías con 3+ hechos.
    Errores individuales no detienen el resto del pipeline.
    """
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT categoria, clave, valor FROM memoria_permanente')
        hechos_raw = cursor.fetchall()
    if not hechos_raw:
        return

    por_cat = {}
    for cat, clave, valor in hechos_raw:
        if cat and clave and valor:   # ignorar filas incompletas
            por_cat.setdefault(cat, []).append(f"{clave}: {valor}")

    errores = []
    procesadas = 0

    for cat, hechos in por_cat.items():
        if len(hechos) < 3:
            continue

        prompt = f"""Basándote en estos hechos REALES sobre el USUARIO en "{cat}", escribí una síntesis en 2-3 oraciones.
Hechos:\n{chr(10).join(f'- {h}' for h in hechos)}
REGLAS:
- Tercera persona, específico, máximo 3 oraciones.
- Usá SOLO los datos que están en la lista. NUNCA inventes ni supongas nada que no esté explícitamente ahí.
- Si los datos son pocos o vagos, hacé una síntesis breve y honesta con lo que hay."""

        try:
            resp = llamada_mistral_segura(
                model=_get_modelo("synthesis"),
                messages=[{'role':'user','content':prompt}],
                max_tokens=150
            )
            if not resp or not resp.choices:
                errores.append(f"{cat}: respuesta vacía del modelo")
                continue

            sintesis = resp.choices[0].message.content.strip()
            if not sintesis:
                errores.append(f"{cat}: síntesis vacía")
                continue

            # Truncar si viene demasiado larga
            sintesis = sintesis[:600]

            with _get_conn(paths()['db']) as conn2:
                c2 = conn2.cursor()
                c2.execute('''
                    INSERT INTO sintesis_conocimiento
                    (categoria, titulo, contenido, fuentes, fecha_creacion, fecha_actualizacion)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(categoria, titulo) DO UPDATE SET
                        contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
                ''', (cat, f"Perfil de {cat}", sintesis, json.dumps(hechos),
                      now_argentina().isoformat(), now_argentina().isoformat()))
            procesadas += 1

        except Exception as e:
            errores.append(f"{cat}: {type(e).__name__} — {e}")
            continue   # nunca detener el loop por un error individual

    print(f"✅ Síntesis por categoría: {procesadas} procesadas, {len(errores)} errores")
    if errores:
        for err in errores:
            print(f"  ⚠️ {err}")

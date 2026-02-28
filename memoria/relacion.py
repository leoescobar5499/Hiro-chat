# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/RELACION.PY — Fase de relación y métricas de progresión
# actualizar_fase: recalcula fase (1-4), confianza, intimidad y días juntos.
#
# Modificar acá si querés:
#   - Cambiar la velocidad de progresión de la relación
#   - Ajustar los topes por sesión (TOPES_CONFIANZA, TOPES_INTIMIDAD)
#   - Cambiar los umbrales de fase (cuántos mensajes/intimidad para pasar de fase)
# ═══════════════════════════════════════════════════════════════════════════

from datetime import datetime

from utils import (
    now_argentina,
    paths,
    _get_conn,
)


def actualizar_fase():
    """
    Recalcula fase (1-4), nivel de confianza, intimidad y días juntos
    después de cada mensaje. Aplica frenos por sesión para que la relación
    no llegue al máximo el primer día.
    """
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM mensajes')
        total_msgs = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM memoria_permanente WHERE categoria IN ('moments','momentos')")
        total_momentos = cursor.fetchone()[0]
        nivel_confianza = min(100, (total_msgs * 2) + (total_momentos * 5))

        cursor.execute("SELECT COUNT(*) FROM memoria_permanente WHERE categoria IN ('intimidad','historial_intimo')")
        total_intimo = cursor.fetchone()[0]
        nivel_intimidad = min(100, (total_momentos * 8) + (total_intimo * 10))

        cursor.execute('SELECT primer_mensaje FROM relacion WHERE id=1')
        row = cursor.fetchone()
        dias_juntos = 0
        if row and row[0]:
            try:
                dt_primer = datetime.fromisoformat(str(row[0]).replace(' ','T').split('.')[0])
                dt_hoy    = now_argentina().replace(tzinfo=None)
                dias_juntos = max(1, (dt_hoy - dt_primer).days + 1)
            except Exception:
                pass

        # Frenos por día: la relación crece naturalmente a lo largo de semanas.
        # La curva es progresiva — no hay techo artificial después del día 5.
        # Días 1-5: crecimiento rápido inicial (primeras impresiones)
        # Días 6-14: consolidación (confianza sube, intimidad más lento)
        # Días 15-30: profundización (intimidad puede llegar alto si el contenido lo justifica)
        # Día 30+: relación madura, topes máximos desbloqueados
        TOPES_CONFIANZA = {
            1: 35,  2: 52,  3: 65,  4: 75,  5: 83,
            7: 88,  10: 92, 14: 95, 21: 98, 30: 100
        }
        TOPES_INTIMIDAD = {
            1: 8,   2: 20,  3: 35,  4: 50,  5: 62,
            7: 72,  10: 80, 14: 88, 21: 94, 30: 100
        }

        def _interpolar_tope(tabla, dias):
            """Interpolación lineal entre los hitos definidos."""
            claves = sorted(tabla.keys())
            if dias <= claves[0]:
                return tabla[claves[0]]
            if dias >= claves[-1]:
                return tabla[claves[-1]]
            for i in range(len(claves) - 1):
                d0, d1 = claves[i], claves[i + 1]
                if d0 <= dias <= d1:
                    t = (dias - d0) / (d1 - d0)
                    return int(tabla[d0] + t * (tabla[d1] - tabla[d0]))
            return tabla[claves[-1]]

        tope_conf = _interpolar_tope(TOPES_CONFIANZA, dias_juntos)
        tope_inti = _interpolar_tope(TOPES_INTIMIDAD, dias_juntos)
        nivel_confianza = min(nivel_confianza, tope_conf)
        nivel_intimidad = min(nivel_intimidad, tope_inti)

        if total_msgs < 20 or nivel_intimidad < 10:
            fase = 1
        elif total_msgs < 60 or nivel_intimidad < 30:
            fase = 2
        elif total_msgs < 120 or nivel_intimidad < 55:
            fase = 3
        else:
            fase = 4

        cursor.execute(
            '''UPDATE relacion SET
               fase             = ?,
               nivel_confianza  = ?,
               nivel_intimidad  = ?,
               dias_juntos      = ?
               WHERE id = 1''',
            (fase, nivel_confianza, nivel_intimidad, dias_juntos)
        )
    return fase

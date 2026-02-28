# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/__INIT__.PY — Punto de entrada del paquete
#
# Re-exporta TODO lo que chat_engine.py y routes.py importan de 'memoria'.
# Los módulos externos NO necesitan cambiar ni una sola línea de importación.
#
# Si agregás una función nueva a cualquier submódulo y querés que sea
# accesible desde afuera, agregala acá también.
# ═══════════════════════════════════════════════════════════════════════════

# ── FAISS y embeddings ────────────────────────────────────────────────────────
from .faiss_store import (
    faiss_index,
    embeddings_metadata,
    init_faiss_personaje,
    guardar_faiss,
    get_faiss_ntotal,
    limpiar_faiss_episodios,
    cargar_personaje,
    obtener_embedding,
    agregar_embedding,
    buscar_contexto_relevante,
)

# ── Extracción de información ─────────────────────────────────────────────────
from .extraccion import (
    _get_modo_memoria,
    extraer_informacion_con_ia,
    extraer_menciones_casuales,
    _detectar_y_cerrar_hilos,
    guardar_memoria_permanente,
)

# ── Enriquecimiento episódico ─────────────────────────────────────────────────
from .enriquecimiento import (
    _enriquecer_episodio,
)

# ── Síntesis de conocimiento ──────────────────────────────────────────────────
from .sintesis import (
    _debe_regenerar_sintesis,
    _ejecutar_sintesis,
    generar_perfil_narrativo,
    generar_resumen_relacion,
    generar_sintesis,
)

# ── Sistema emocional y conciencia temporal ───────────────────────────────────
from .emocional import (
    detectar_emocion,
    generar_backstory_automatico,
    _get_gap_sesion,
    _get_tendencia_emocional,
    _get_resumen_ultima_sesion,
    _get_horario_habitual,
    generar_diario_automatico,         
    actualizar_evolucion_automatica,   

)

# ── Fase de relación ──────────────────────────────────────────────────────────
from .relacion import (
    actualizar_fase,
)

# ── Contexto y system prompt ──────────────────────────────────────────────────
from .contexto import (
    obtener_contexto,
    obtener_system_prompt,
)

__all__ = [
    # faiss_store
    'faiss_index', 'embeddings_metadata',
    'init_faiss_personaje', 'guardar_faiss', 'get_faiss_ntotal',
    'limpiar_faiss_episodios', 'cargar_personaje',
    'obtener_embedding', 'agregar_embedding', 'buscar_contexto_relevante',
    # extraccion
    '_get_modo_memoria', 'extraer_informacion_con_ia',
    'extraer_menciones_casuales', '_detectar_y_cerrar_hilos',
    'guardar_memoria_permanente',
    # enriquecimiento
    '_enriquecer_episodio',
    # sintesis
    '_debe_regenerar_sintesis', '_ejecutar_sintesis',
    'generar_perfil_narrativo', 'generar_resumen_relacion', 'generar_sintesis',
    # emocional
    'detectar_emocion', 'generar_backstory_automatico',
    '_get_gap_sesion', '_get_tendencia_emocional',
    '_get_resumen_ultima_sesion', '_get_horario_habitual',
    'generar_diario_automatico',         
    'actualizar_evolucion_automatica',   
    # relacion
    'actualizar_fase',
    # contexto
    'obtener_contexto', 'obtener_system_prompt',
]

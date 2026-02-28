# ═══════════════════════════════════════════════════════════════════════════
# MEMORIA/FAISS_STORE.PY — Índice vectorial FAISS y embeddings
# Todo lo relacionado con vectorización y búsqueda semántica.
# Modificar acá si cambiás el proveedor de embeddings o la dimensión del índice.
# ═══════════════════════════════════════════════════════════════════════════

import os
import json
import threading
import numpy as np
import faiss
import msgpack

from utils import (
    now_argentina,
    paths, get_personaje_activo_id, set_personaje_activo_id,
    init_database_personaje,
    _get_conn,
)


# ─────────────────────────────────────────────────────────────────────────────
# ÍNDICE FAISS GLOBAL (un único índice activo por proceso)
# ─────────────────────────────────────────────────────────────────────────────

faiss_index         = faiss.IndexFlatL2(1024)
embeddings_metadata = []
_faiss_lock         = threading.Lock()   # protege index + metadata en multithread



def _get_modelo_embedding():
    """Lee el modelo de embeddings configurado desde api_config.json."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        return cfg.get('models', {}).get('embeddings') or 'mistral-embed'
    except Exception:
        return 'mistral-embed'


def init_faiss_personaje(pid):
    """Carga el índice FAISS del personaje, o crea uno nuevo si no existe."""
    global faiss_index, embeddings_metadata
    p = paths(pid)
    with _faiss_lock:
        if os.path.exists(p['emb']):
            faiss_index = faiss.read_index(p['emb'])
            with open(p['emb_m'], 'rb') as f:
                embeddings_metadata = msgpack.unpackb(f.read(), raw=False)
            print(f"✅ FAISS cargado: {faiss_index.ntotal} vectores")
        else:
            faiss_index = faiss.IndexFlatL2(1024)
            embeddings_metadata = []
            print("✅ Nuevo índice FAISS creado")


def guardar_faiss(pid=None):
    """
    Persiste el índice FAISS a disco.
    Usa pid explícito para evitar guardar en el personaje equivocado
    si hubo un cambio de personaje mientras se procesaba un mensaje.
    """
    p = paths(pid)
    faiss.write_index(faiss_index, p['emb'])
    with open(p['emb_m'], 'wb') as f:
        f.write(msgpack.packb(embeddings_metadata, use_bin_type=True))


def get_faiss_ntotal():
    """Devuelve faiss_index.ntotal de forma segura para módulos externos."""
    return faiss_index.ntotal


def limpiar_faiss_episodios(pid_actual):
    """Elimina del índice FAISS los vectores de tipo 'episodio'. Llamado por limpiar_historial."""
    global faiss_index, embeddings_metadata
    nuevos_embs, nueva_meta = [], []
    for i, meta in enumerate(embeddings_metadata):
        if meta.get('tipo') != 'episodio' and i < faiss_index.ntotal:
            nuevos_embs.append(faiss_index.reconstruct(i))
            nueva_meta.append(meta)
    faiss_index = faiss.IndexFlatL2(1024)
    if nuevos_embs:
        faiss_index.add(np.array(nuevos_embs, dtype=np.float32))
    embeddings_metadata = nueva_meta
    guardar_faiss(pid_actual)


def cargar_personaje(pid):
    """Orquesta la carga completa: DB + FAISS + escenario default."""
    set_personaje_activo_id(pid)
    init_database_personaje(pid)
    init_faiss_personaje(pid)
    _asegurar_escenario_default(pid)
    print(f"✅ Personaje activo: {pid}")


def _asegurar_escenario_default(pid):
    """Si el personaje no tiene ningún escenario en DB, crea uno desde su JSON y lo activa."""
    try:
        p = paths(pid)
        with _get_conn(p['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT COUNT(*) FROM escenarios')
            if cursor.fetchone()[0] > 0:
                return
            with open(p['json'], 'r', encoding='utf-8') as f:
                data = json.load(f)
            escena   = data['data'].get('scenario', '').strip()
            nombre_p = data['data'].get('name', 'Personaje')
            if not escena:
                return
            cursor.execute(
                'INSERT INTO escenarios (nombre, descripcion, historia, activo, color) VALUES (?,?,?,1,?)',
                (f'Escenario de {nombre_p}', escena, '', '#1a1a2e')
            )
            print(f"✅ Escenario por defecto creado para {nombre_p}")
    except Exception as e:
        print(f"⚠️ Error creando escenario default: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE PROVEEDOR DE EMBEDDINGS
# ─────────────────────────────────────────────────────────────────────────────

def _detectar_proveedor_embedding(modelo_id, cfg):
    """Detecta el proveedor a usar basado en el modelo y la config."""
    proveedor_cfg = cfg.get('models', {}).get('embedding_provider', 'auto')
    if proveedor_cfg and proveedor_cfg != 'auto':
        return proveedor_cfg
    # Auto-detección por nombre de modelo
    m = modelo_id.lower()
    if 'embed-multilingual' in m or m.startswith('embed-english'):
        return 'cohere'
    if 'jina' in m:
        return 'jina'
    if m in ('nomic-embed-text', 'mxbai-embed-large', 'all-minilm'):
        return 'ollama'
    if 'text-embedding' in m or 'ada-002' in m:
        return 'openai'
    return 'mistral'


# ─────────────────────────────────────────────────────────────────────────────
# SUB-FUNCIONES DE EMBEDDING POR PROVEEDOR
# Modificar acá si querés agregar un proveedor nuevo (ej: Voyage, Cohere v4)
# ─────────────────────────────────────────────────────────────────────────────

def _embedding_mistral(texto):
    """Embedding via Mistral."""
    from utils import _get_mistral_client
    client = _get_mistral_client()   # inicializa lazy desde api_config.json
    if not client:
        raise RuntimeError("Cliente Mistral no disponible")
    response = client.embeddings.create(
        model=_get_modelo_embedding(),
        inputs=[texto]
    )
    return np.array(response.data[0].embedding, dtype=np.float32)


def _embedding_openai(texto, modelo, cfg):
    """Embedding via OpenAI o endpoint compatible."""
    import requests
    api_key  = (cfg.get('openai', {}).get('apiKey') or '').strip()
    endpoint = (cfg.get('openai', {}).get('endpoint') or 'https://api.openai.com/v1').rstrip('/')
    if not api_key:
        raise RuntimeError("OpenAI API key no configurada")
    resp = requests.post(
        f"{endpoint}/embeddings",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"model": modelo, "input": texto},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return np.array(data['data'][0]['embedding'], dtype=np.float32)


def _embedding_cohere(texto, modelo, cfg):
    """Embedding via Cohere. Ideal para español."""
    import requests
    api_key = (cfg.get('cohere', {}).get('apiKey') or '').strip()
    if not api_key:
        raise RuntimeError("Cohere API key no configurada")
    resp = requests.post(
        'https://api.cohere.com/v1/embed',
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "texts": [texto],
            "model": modelo,
            "input_type": "search_document",
            "truncate": "END"
        },
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return np.array(data['embeddings'][0], dtype=np.float32)


def _embedding_jina(texto, modelo, cfg):
    """Embedding via Jina AI."""
    import requests
    api_key = (cfg.get('jina', {}).get('apiKey') or '').strip()
    if not api_key:
        raise RuntimeError("Jina API key no configurada")
    resp = requests.post(
        'https://api.jina.ai/v1/embeddings',
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={"input": [texto], "model": modelo},
        timeout=30
    )
    resp.raise_for_status()
    data = resp.json()
    return np.array(data['data'][0]['embedding'], dtype=np.float32)


def _embedding_ollama(texto, modelo, cfg):
    """Embedding via Ollama local."""
    import requests
    endpoint = (cfg.get('ollama', {}).get('endpoint') or 'http://localhost:11434').rstrip('/')
    resp = requests.post(
        f"{endpoint}/api/embeddings",
        json={"model": modelo, "prompt": texto},
        timeout=60
    )
    resp.raise_for_status()
    data = resp.json()
    return np.array(data['embedding'], dtype=np.float32)


def obtener_embedding(texto):
    """
    Genera embedding vectorial del texto.
    Proveedor determinado por api_config.json → models.embedding_provider
    Soporta: mistral, openai, cohere, jina, ollama
    """
    proveedor = '?'
    try:
        from utils import cargar_config_apis
        cfg       = cargar_config_apis()
        modelo    = cfg.get('models', {}).get('embeddings', 'mistral-embed') or 'mistral-embed'
        proveedor = _detectar_proveedor_embedding(modelo, cfg)

        print(f"🔍 Embedding [{proveedor}] modelo={modelo}")

        if proveedor == 'openai':
            return _embedding_openai(texto, modelo, cfg)
        elif proveedor == 'cohere':
            return _embedding_cohere(texto, modelo, cfg)
        elif proveedor == 'jina':
            return _embedding_jina(texto, modelo, cfg)
        elif proveedor == 'ollama':
            return _embedding_ollama(texto, modelo, cfg)
        else:
            return _embedding_mistral(texto)

    except Exception as e:
        print(f"❌ Error embedding [{proveedor}]: {e}")
        try:
            print("⚠️ Fallback a Mistral embed...")
            return _embedding_mistral(texto)
        except Exception as e2:
            print(f"❌ Fallback Mistral también falló: {e2}")
            raise


def agregar_embedding(texto, tipo, metadata_extra=""):
    """Agrega un vector al índice. Devuelve el embedding_id asignado, o None si falla."""
    global faiss_index, embeddings_metadata
    pid_actual = get_personaje_activo_id()
    emb = obtener_embedding(texto)
    if emb is None:
        return None
    with _faiss_lock:
        faiss_index.add(np.array([emb]))
        embeddings_metadata.append({
            'tipo': tipo, 'texto': texto,
            'metadata': metadata_extra, 'timestamp': now_argentina().isoformat()
        })
        idx = faiss_index.ntotal - 1
    guardar_faiss(pid_actual)
    return idx


def buscar_contexto_relevante(query, k=8):
    """
    Búsqueda semántica mejorada. Devuelve hasta k fragmentos combinando dos estrategias:
      A) Los 3 episodios más recientes (ancla temporal — lo que pasó justo antes)
      B) Los k mejores resultados semánticos filtrados por distancia < umbral
    Los duplicados entre A y B se eliminan. El resultado está ordenado por relevancia.
    """
    with _faiss_lock:
        if faiss_index.ntotal == 0:
            return []
        emb = obtener_embedding(query)
        if emb is None:
            return []
        try:
            # ── A) Episodios recientes (ancla temporal) ───────────────────────
            recientes = []
            total = faiss_index.ntotal
            indices_recientes = set()
            for i in range(total - 1, max(total - 6, -1), -1):
                if i < len(embeddings_metadata):
                    meta = embeddings_metadata[i]
                    if meta.get('tipo') == 'episodio':
                        texto = _extraer_texto_meta(meta)
                        recientes.append({
                            'texto': texto,
                            'tipo': 'episodio_reciente',
                            'distancia': 0.0,
                            '_idx': i
                        })
                        indices_recientes.add(i)
                        if len(recientes) >= 3:
                            break

            # ── B) Búsqueda semántica con umbral de distancia ─────────────────
            k_buscar = min(k + 5, total)   # buscar un poco más para poder filtrar
            dists, idxs = faiss_index.search(np.array([emb]), k_buscar)

            # Umbral dinámico: si hay poco contenido, sé más permisivo
            umbral = 2.5 if total > 50 else 4.0

            semanticos = []
            for i, d in zip(idxs[0], dists[0]):
                if i < 0 or i >= len(embeddings_metadata):
                    continue
                if i in indices_recientes:
                    continue   # ya está en recientes, no duplicar
                if float(d) > umbral:
                    continue   # demasiado distante = ruido
                meta = embeddings_metadata[i]
                texto = _extraer_texto_meta(meta)
                semanticos.append({
                    'texto': texto,
                    'tipo': meta.get('tipo', 'episodio'),
                    'distancia': float(d),
                    '_idx': i
                })

            # ── Combinar: recientes primero, luego semánticos ─────────────────
            combinados = recientes + semanticos
            # Quitar campo interno _idx antes de retornar
            for r in combinados:
                r.pop('_idx', None)

            return combinados[:k]

        except Exception as e:
            print(f"❌ Error FAISS search: {e}")
            return []


def _extraer_texto_meta(meta):
    """Extrae el texto legible de un dict de metadata FAISS."""
    if 'texto' in meta:
        return meta['texto']
    elif 'mensaje_usuario' in meta:
        return f"Usuario: {meta.get('mensaje_usuario','')} | Personaje: {meta.get('respuesta_hiro','')}"
    return str(meta)

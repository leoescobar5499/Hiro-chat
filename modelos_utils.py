# ═══════════════════════════════════════════════════════════════════════════
# MODELOS_UTILS.PY — Gestión de modelos dinámicos
# Multi-proveedor: Mistral, OpenRouter, OpenAI, Cohere, Jina, Ollama
# ═══════════════════════════════════════════════════════════════════════════

import os
import json
import requests
from dotenv import load_dotenv
from datetime import datetime
from utils import llamada_mistral_segura

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# GESTIÓN GLOBAL DE MODELOS
# ─────────────────────────────────────────────────────────────────────────────

MODELOS_CONFIG_FILE  = './data/modelos_activos.json'
LIBRERIA_MODELOS_PATH = './data/libreria_modelos.json'

def _asegurar_modelos_config():
    os.makedirs('./data', exist_ok=True)
    if not os.path.exists(MODELOS_CONFIG_FILE):
        config = {
            'openrouter_chat':  os.getenv('OPENROUTER_MODEL', 'nousresearch/hermes-3-llama-3.1-405b:nitro'),
            'openrouter_small': os.getenv('OPENROUTER_MODEL_SMALL', 'openai/gpt-4o-mini'),
            'mistral_chat':     'mistral-large-latest',
            'mistral_small':    'mistral-small-latest',
            'provider':         os.getenv('LLM_PROVIDER', 'mistral'),
        }
        with open(MODELOS_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    return MODELOS_CONFIG_FILE

def cargar_modelos_activos():
    _asegurar_modelos_config()
    try:
        with open(MODELOS_CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {
            'openrouter_chat':  'nousresearch/hermes-3-llama-3.1-405b:nitro',
            'openrouter_small': 'openai/gpt-4o-mini',
            'mistral_chat':     'mistral-large-latest',
            'mistral_small':    'mistral-small-latest',
            'provider':         'mistral',
        }

def guardar_modelos_activos(config):
    _asegurar_modelos_config()
    with open(MODELOS_CONFIG_FILE, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ Modelos activos guardados: {config}")

def obtener_modelo_activo(tipo='chat'):
    """
    Devuelve el modelo activo para un tipo dado.
    Para 'embeddings' lee la config de api_config.json en lugar de hardcodear Mistral.
    """
    config = cargar_modelos_activos()
    provider = config.get('provider', 'mistral')

    if tipo == 'chat':
        if provider == 'openrouter':
            return config.get('openrouter_chat', 'nousresearch/hermes-3-llama-3.1-405b:nitro')
        return config.get('mistral_chat', 'mistral-large-latest')

    elif tipo == 'small':
        if provider == 'openrouter':
            return config.get('openrouter_small', 'openai/gpt-4o-mini')
        return config.get('mistral_small', 'mistral-small-latest')

    elif tipo == 'embeddings':
        # Leer desde api_config.json (panel visual)
        try:
            from utils import cargar_config_apis
            cfg = cargar_config_apis()
            modelo = cfg.get('models', {}).get('embeddings', 'mistral-embed')
            return modelo or 'mistral-embed'
        except Exception:
            return 'mistral-embed'

    return None


def cambiar_modelo(tipo, nuevo_modelo):
    config = cargar_modelos_activos()
    if tipo in ('openrouter_chat', 'openrouter_small', 'mistral_chat', 'mistral_small', 'provider'):
        config[tipo] = nuevo_modelo
    guardar_modelos_activos(config)
    return config


# ─────────────────────────────────────────────────────────────────────────────
# DIMENSIONES DE EMBEDDING POR MODELO
# ─────────────────────────────────────────────────────────────────────────────

EMBEDDING_DIMS = {
    'mistral-embed':                1024,
    'text-embedding-3-small':       1536,
    'text-embedding-3-large':       3072,
    'text-embedding-ada-002':       1536,
    'embed-multilingual-v3.0':      1024,
    'embed-english-v3.0':           1024,
    'embed-multilingual-light-v3.0':384,
    'jina-embeddings-v3':           1024,
    'jina-embeddings-v2-base-es':    768,
    'mxbai-embed-large':            1024,
    'nomic-embed-text':              768,
    'all-minilm':                    384,
}

def obtener_dimensiones_embedding(modelo_id):
    """Devuelve las dimensiones del modelo de embedding o None si no se conocen."""
    return EMBEDDING_DIMS.get(modelo_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# LISTAR MODELOS DE MISTRAL
# ─────────────────────────────────────────────────────────────────────────────

def listar_modelos_mistral():
    modelos_conocidos = [
        {'id': 'mistral-large-latest',  'nombre': 'Mistral Large (Recomendado)',     'tipo': 'chat',       'proveedor': 'Mistral AI', 'contexto': '128k', 'precio_input': '$0.50/M',  'precio_output': '$1.50/M'},
        {'id': 'mistral-medium-latest', 'nombre': 'Mistral Medium (Balance)',        'tipo': 'chat',       'proveedor': 'Mistral AI', 'contexto': '128k', 'precio_input': '$0.27/M',  'precio_output': '$0.81/M'},
        {'id': 'open-mistral-nemo',     'nombre': 'Open Mistral Nemo (Rápido)',      'tipo': 'chat',       'proveedor': 'Mistral AI', 'contexto': '128k', 'precio_input': '$0.14/M',  'precio_output': '$0.42/M'},
        {'id': 'mistral-small-latest',  'nombre': 'Mistral Small (Para análisis)',   'tipo': 'small',      'proveedor': 'Mistral AI', 'contexto': '32k',  'precio_input': '$0.065/M', 'precio_output': '$0.195/M'},
        {'id': 'mistral-embed',         'nombre': 'Mistral Embed (solo embeddings)', 'tipo': 'embeddings', 'proveedor': 'Mistral AI', 'contexto': '8k',   'precio_input': '$0.10/M',  'precio_output': '$0.10/M'},
    ]
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        api_key = (cfg.get('mistral', {}).get('apiKey') or '').strip()
        if not api_key:
            api_key = os.getenv('MISTRAL_API_KEY', '').strip()
        if api_key:
            from mistralai import Mistral
            Mistral(api_key=api_key)
            print("✅ Conexión a Mistral verificada")
    except Exception as e:
        print(f"⚠️ Mistral: {e}")

    return {'error': None, 'modelos': modelos_conocidos}


# ─────────────────────────────────────────────────────────────────────────────
# MODELOS OPENROUTER SIN CENSURA
# ─────────────────────────────────────────────────────────────────────────────

MODELOS_OPENROUTER_UNCENSORED = [
    {'id': 'nousresearch/hermes-3-llama-3.1-405b:nitro', 'nombre': 'Hermes 3 405B (TOP - Sin censura)',   'tipo': 'chat',  'proveedor': 'Nous Research', 'contexto': '128k', 'precio_input': '$0.50/M',  'precio_output': '$0.50/M',  'sin_censura': True},
    {'id': 'meta-llama/llama-3.1-405b-instruct',         'nombre': 'Llama 3.1 405B (Sin censura)',        'tipo': 'chat',  'proveedor': 'Meta',          'contexto': '128k', 'precio_input': '$1.50/M',  'precio_output': '$2.00/M',  'sin_censura': True},
    {'id': 'undi95/toppy-m-7b:free',                     'nombre': 'Toppy M 7B (GRATIS - Sin censura)',   'tipo': 'chat',  'proveedor': 'Undi95',        'contexto': '4k',   'precio_input': 'GRATIS',   'precio_output': 'GRATIS',   'sin_censura': True},
    {'id': 'gryphe/mythomax-l2-13b',                     'nombre': 'MythoMax 13B (Sin censura)',          'tipo': 'chat',  'proveedor': 'Gryphe',        'contexto': '4k',   'precio_input': '$0.06/M',  'precio_output': '$0.06/M',  'sin_censura': True},
    {'id': 'neversleep/llama-3-lumimaid-70b',             'nombre': 'Lumimaid 70B (Roleplay sin censura)', 'tipo': 'chat',  'proveedor': 'NeverSleep',    'contexto': '8k',   'precio_input': '$0.80/M',  'precio_output': '$0.80/M',  'sin_censura': True},
    {'id': 'aion-labs/aion-2.0',                         'nombre': 'Aion 2.0',                            'tipo': 'chat',  'proveedor': 'Aion Labs',     'contexto': '32k',  'precio_input': 'Variable', 'precio_output': 'Variable', 'sin_censura': True},
    {'id': 'meta-llama/llama-3.1-8b-instruct:free',      'nombre': 'Llama 3.1 8B (GRATIS)',              'tipo': 'small', 'proveedor': 'Meta',          'contexto': '128k', 'precio_input': 'GRATIS',   'precio_output': 'GRATIS',   'sin_censura': False},
]

def listar_modelos_openrouter(sin_censura_solo=True):
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()
        api_key = (cfg.get('openrouter', {}).get('apiKey') or os.getenv('OPENROUTER_API_KEY', '')).strip()

        if api_key:
            headers = {'Authorization': f'Bearer {api_key}', 'Content-Type': 'application/json'}
            resp = requests.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=10)
            if resp.status_code == 200:
                raw = resp.json().get('data', [])
                modelos = []
                for m in raw:
                    mid   = m.get('id', '')
                    price = m.get('pricing', {})
                    modelos.append({
                        'id':           mid,
                        'nombre':       m.get('name', mid),
                        'tipo':         'chat',
                        'proveedor':    mid.split('/')[0] if '/' in mid else 'OpenRouter',
                        'contexto':     str(m.get('context_length', '?')),
                        'precio_input': f"${float(price.get('prompt', 0))*1e6:.3f}/M" if price.get('prompt') else 'N/A',
                        'precio_output': f"${float(price.get('completion', 0))*1e6:.3f}/M" if price.get('completion') else 'N/A',
                        'sin_censura':  False,
                    })
                if modelos:
                    return {'error': None, 'modelos': modelos}
    except Exception as e:
        print(f"⚠️ OpenRouter API: {e}")

    return {'error': None, 'modelos': MODELOS_OPENROUTER_UNCENSORED}


# ─────────────────────────────────────────────────────────────────────────────
# LIBRERÍA DE MODELOS PERSONALIZADOS
# ─────────────────────────────────────────────────────────────────────────────

def _crear_estructura_libreria():
    return {
        'modelos': [],
        'asignaciones': {
            'chat': None, 'small': None, 'embeddings': None,
            'extraccion': None, 'sintesis': None, 'enriquecimiento': None,
        },
        'version': 1
    }

def _cargar_libreria():
    try:
        if os.path.exists(LIBRERIA_MODELOS_PATH):
            with open(LIBRERIA_MODELOS_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error cargando librería: {e}")
    return _crear_estructura_libreria()

def _guardar_libreria(libreria):
    try:
        os.makedirs(os.path.dirname(LIBRERIA_MODELOS_PATH), exist_ok=True)
        with open(LIBRERIA_MODELOS_PATH, 'w', encoding='utf-8') as f:
            json.dump(libreria, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error guardando librería: {e}")
        return False

def agregar_modelo_a_libreria(modelo_id, nombre=None, descripcion='', proveedor='openrouter', tags=None):
    if not modelo_id:
        return {'ok': False, 'mensaje': 'Modelo ID requerido'}
    libreria = _cargar_libreria()
    if any(m['id'] == modelo_id for m in libreria['modelos']):
        return {'ok': False, 'mensaje': f'Modelo {modelo_id} ya está en la librería'}
    modelo_nuevo = {
        'id':           modelo_id,
        'nombre':       nombre or modelo_id.split('/')[-1],
        'descripcion':  descripcion,
        'proveedor':    proveedor,
        'tags':         tags or [],
        'fecha_agregado': datetime.now().isoformat(),
        'activo':       True
    }
    libreria['modelos'].append(modelo_nuevo)
    if _guardar_libreria(libreria):
        return {'ok': True, 'mensaje': f'✅ Modelo {modelo_nuevo["nombre"]} agregado', 'modelo': modelo_nuevo}
    return {'ok': False, 'mensaje': 'Error guardando la librería'}

def listar_modelos_libreria():
    libreria = _cargar_libreria()
    return {'ok': True, 'modelos': libreria['modelos'], 'total': len(libreria['modelos'])}

def obtener_modelo_libreria(modelo_id):
    libreria = _cargar_libreria()
    for m in libreria['modelos']:
        if m['id'] == modelo_id:
            return {'ok': True, 'modelo': m}
    return {'ok': False, 'mensaje': f'Modelo {modelo_id} no encontrado'}

def eliminar_modelo_libreria(modelo_id):
    libreria = _cargar_libreria()
    original = len(libreria['modelos'])
    libreria['modelos'] = [m for m in libreria['modelos'] if m['id'] != modelo_id]
    if len(libreria['modelos']) < original:
        for tarea in libreria['asignaciones']:
            if libreria['asignaciones'][tarea] == modelo_id:
                libreria['asignaciones'][tarea] = None
        if _guardar_libreria(libreria):
            return {'ok': True, 'mensaje': f'✅ Modelo {modelo_id} eliminado'}
    return {'ok': False, 'mensaje': f'Modelo {modelo_id} no encontrado'}


# ─────────────────────────────────────────────────────────────────────────────
# TAREAS Y ASIGNACIONES
# ─────────────────────────────────────────────────────────────────────────────

TAREAS_DISPONIBLES = ['chat', 'small', 'embeddings', 'extraccion', 'sintesis', 'enriquecimiento']

def asignar_modelo_a_tarea(tarea, modelo_id):
    if tarea not in TAREAS_DISPONIBLES:
        return {'ok': False, 'mensaje': f'Tarea {tarea} no válida'}
    libreria = _cargar_libreria()
    if modelo_id and not any(m['id'] == modelo_id for m in libreria['modelos']):
        return {'ok': False, 'mensaje': f'Modelo {modelo_id} no está en la librería'}
    libreria['asignaciones'][tarea] = modelo_id
    if _guardar_libreria(libreria):
        return {'ok': True, 'mensaje': f'✅ Tarea {tarea} asignada a {modelo_id or "ninguno"}', 'asignacion': {tarea: modelo_id}}
    return {'ok': False, 'mensaje': 'Error guardando asignación'}

def obtener_asignaciones():
    libreria = _cargar_libreria()
    return {'ok': True, 'asignaciones': libreria['asignaciones'], 'tareas': TAREAS_DISPONIBLES}

def obtener_modelo_para_tarea(tarea):
    libreria = _cargar_libreria()
    modelo_id = libreria['asignaciones'].get(tarea)
    if modelo_id:
        for m in libreria['modelos']:
            if m['id'] == modelo_id:
                return {'ok': True, 'modelo': m}
    return {'ok': False, 'modelo': None}

def filtrar_modelos_por_tag(tag):
    libreria = _cargar_libreria()
    filtrados = [m for m in libreria['modelos'] if tag in m.get('tags', [])]
    return {'ok': True, 'tag': tag, 'modelos': filtrados, 'total': len(filtrados)}

def buscar_modelos_libreria(query):
    libreria = _cargar_libreria()
    query = query.lower()
    resultados = [m for m in libreria['modelos'] if query in m['id'].lower() or query in m['nombre'].lower() or query in m['descripcion'].lower()]
    return {'ok': True, 'query': query, 'modelos': resultados, 'total': len(resultados)}


# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINT COMBINADO PARA DROPDOWNS DE TAREAS
# ─────────────────────────────────────────────────────────────────────────────

def listar_todos_para_tareas():
    """
    Combina OpenRouter + Mistral + Librería en una lista única para los dropdowns.
    """
    resultado_or  = listar_modelos_openrouter(solo_sin_censura=True)
    resultado_mis = listar_modelos_mistral()
    resultado_lib = listar_modelos_libreria()

    modelos_or  = [dict(m, es_libreria=False) for m in (resultado_or.get('modelos') or [])]
    modelos_mis = [dict(m, es_libreria=False) for m in (resultado_mis.get('modelos') or [])]
    modelos_lib = [dict(m, es_libreria=True)  for m in (resultado_lib.get('modelos') or [])]

    todos = modelos_or + modelos_mis + modelos_lib

    return {
        'ok':       True,
        'modelos':  todos,
        'openrouter': len(modelos_or),
        'mistral':    len(modelos_mis),
        'libreria':   len(modelos_lib),
    }

def probar_modelo(modelo_id, proveedor='openrouter'):
    """Prueba un modelo enviando un mensaje simple. Devuelve ok y la respuesta."""
    try:
        from utils import cargar_config_apis
        cfg = cargar_config_apis()

        if proveedor == 'openrouter':
            import requests
            api_key = (cfg.get('openrouter', {}).get('apiKey') or '').strip()
            if not api_key:
                return {'ok': False, 'error': 'No hay API key de OpenRouter configurada'}

            resp = requests.post(
                'https://openrouter.ai/api/v1/chat/completions',
                headers={
                    'Authorization': f'Bearer {api_key}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': 'http://localhost'
                },
                json={
                    'model': modelo_id,
                    'messages': [{'role': 'user', 'content': 'Di solo "ok"'}],
                    'max_tokens': 10
                },
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                respuesta = data['choices'][0]['message']['content'].strip()
                return {'ok': True, 'respuesta': respuesta, 'modelo': modelo_id}
            else:
                return {'ok': False, 'error': f'HTTP {resp.status_code}: {resp.text[:100]}'}

        elif proveedor == 'mistral':
            response = llamada_mistral_segura(
                model=modelo_id,
                messages=[{'role': 'user', 'content': 'Di solo "ok"'}],
                max_tokens=10
            )
            respuesta = response.choices[0].message.content.strip()
            return {'ok': True, 'respuesta': respuesta, 'modelo': modelo_id}

        else:
            return {'ok': False, 'error': f'Proveedor {proveedor} no soportado para prueba'}

    except Exception as e:
        return {'ok': False, 'error': str(e)[:150]}
print('✅ Módulo de Librería de Modelos cargado (multi-proveedor)')

# ═══════════════════════════════════════════════════════════════════════════
# UTILS.PY — Módulo compartido entre app.py y crear_personaje.py
# Rompe la dependencia circular y centraliza lógica reutilizable
#
# IMPORTANTE: Copia el archivo modelos_utils.py a la misma carpeta que este
# archivo (nivel raíz del proyecto, junto a app.py)
# ═══════════════════════════════════════════════════════════════════════════

import os, json, time, uuid, sqlite3, base64, shutil
from datetime import datetime, timedelta, timezone
import json
import os
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# ZONA HORARIA
# ─────────────────────────────────────────────────────────────────────────────

ARGENTINA_TZ = timezone(timedelta(hours=-3))

def now_argentina():
    return datetime.now(ARGENTINA_TZ)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURACIÓN DE PROVEEDOR LLM
#
# Variables de entorno:
#   LLM_PROVIDER        = "mistral" (default) | "openrouter"
#
#   Si LLM_PROVIDER=mistral:
#     MISTRAL_API_KEY   = tu clave de Mistral (obligatoria)
#
#   Si LLM_PROVIDER=openrouter:
#     OPENROUTER_API_KEY  = tu clave de OpenRouter (obligatoria)
#     OPENROUTER_MODEL    = modelo a usar (default: "openai/gpt-4o-mini")
#                           Ejemplos: "anthropic/claude-3.5-sonnet"
#                                     "openai/gpt-4o"
#                                     "google/gemini-pro"
#     MISTRAL_API_KEY   = (opcional) si querés mantener embeddings semánticos;
#                         sin ella, la búsqueda vectorial queda desactivada.
#
# Los embeddings (FAISS) siempre usan Mistral porque OpenRouter no tiene
# endpoint propio de embeddings. Si no hay MISTRAL_API_KEY con OpenRouter,
# el sistema sigue funcionando pero sin memoria semántica vectorial.
# ─────────────────────────────────────────────────────────────────────────────

# ── Cliente Mistral (lazy — se inicializa desde api_config.json al primer uso) ─
# El .env ya NO es necesario. Todo se configura desde el Gestor de APIs.
# Se mantiene como fallback para instalaciones antiguas que aún lo tengan.
mistral_client = None   # inicializado por _get_mistral_client() la primera vez

def _get_mistral_client():
    """
    Devuelve un cliente Mistral inicializado desde api_config.json.
    Si ya existe uno activo lo reutiliza. Fallback a MISTRAL_API_KEY del .env.
    Devuelve None si no hay key configurada (FAISS quedará desactivado).
    """
    global mistral_client
    if mistral_client is not None:
        return mistral_client
    try:
        config = cargar_config_apis()
        api_key = (config.get('mistral', {}).get('apiKey') or '').strip()
    except Exception:
        api_key = ''
    if not api_key:
        api_key = os.getenv('MISTRAL_API_KEY', '').strip()
    if api_key:
        try:
            mistral_client = Mistral(api_key=api_key)
            return mistral_client
        except Exception as e:
            print(f"⚠️  Error inicializando cliente Mistral: {e}")
    return None


# Modelos Mistral que se consideran "chat" vs "análisis" internamente
_MODELOS_CHAT_MISTRAL  = {'mistral-large-latest', 'mistral-medium-latest', 'open-mistral-nemo'}
_MODELOS_SMALL_MISTRAL = {'mistral-small-latest', 'ministral-3b-latest', 'ministral-8b-latest'}

# ─────────────────────────────────────────────────────────────────────────────
# GESTOR DE APIs
# ─────────────────────────────────────────────────────────────────────────────

def _merge_config(base: dict, override: dict) -> dict:
    """
    Deep merge: override gana sobre base, pero si un sub-dict de override
    está vacío ({}) se rellena con los valores de base en lugar de quedar vacío.
    Así un api_config.json con 'fallback: {}' hereda los defaults correctamente.
    """
    resultado = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            merged = _merge_config(base[k], v)
            resultado[k] = merged if merged else base[k]
        else:
            resultado[k] = v
    return resultado



# Ruta GLOBAL del api_config — independiente del personaje activo.
# Las API keys son de cuenta, no de personaje. Guardarlas por personaje
# causaba que se "perdieran" al cambiar de personaje o reiniciar el servidor.
_API_CONFIG_GLOBAL = './data/api_config.json'


def cargar_config_apis():
    """
    Carga la configuración global de APIs, fusionando con defaults.
    Ruta: ./data/api_config.json (igual para todos los personajes).
    Si no existe, intenta migrar desde la ruta legacy por-personaje.
    """
    defaults = obtener_config_predeterminada()

    # ── Ruta global (nueva) ───────────────────────────────────────────────────
    if os.path.exists(_API_CONFIG_GLOBAL):
        try:
            with open(_API_CONFIG_GLOBAL, 'r', encoding='utf-8') as f:
                guardado = json.load(f)
            return _merge_config(defaults, guardado)
        except Exception:
            return defaults

    # ── Fallback: ruta legacy por-personaje → migrar automáticamente ─────────
    try:
        personaje_id = get_personaje_activo_id()
        legacy_path  = os.path.join(paths(personaje_id)['dir'], 'api_config.json')
        if os.path.exists(legacy_path):
            with open(legacy_path, 'r', encoding='utf-8') as f:
                guardado = json.load(f)
            # Migrar a ruta global para que no se pierda en el próximo restart
            guardar_config_apis(guardado)
            print(f"✅ api_config.json migrado de '{legacy_path}' → '{_API_CONFIG_GLOBAL}'")
            return _merge_config(defaults, guardado)
    except Exception as _e:
        print(f"⚠️ Error migrando config legacy: {_e}")

    return defaults


def guardar_config_apis(config):
    """
    Guarda la configuración global de APIs en ./data/api_config.json.
    Una sola copia, compartida por todos los personajes.
    """
    os.makedirs('./data', exist_ok=True)
    with open(_API_CONFIG_GLOBAL, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    print(f"✅ Config APIs guardada en {_API_CONFIG_GLOBAL}")


def obtener_config_predeterminada():
    """Configuración predeterminada"""
    return {
        "mistral": {
            "enabled": True,
            "apiKey": os.getenv('MISTRAL_API_KEY', ''),
            "endpoint": "https://api.mistral.ai/v1",
            "rpmLimit": 30
        },
        "openrouter": {
            "enabled": False,
            "apiKey": os.getenv('OPENROUTER_API_KEY', ''),
            "rpmLimit": 60
        },
        "models": {
            "chat": "mistral-large-latest",
            "embeddings": "mistral-embed",
            "extraction": "mistral-small-latest",
            "synthesis": "mistral-medium-latest",
            "generation": "mistral-medium-latest",
            "enrichment": "mistral-medium-latest"
        },
        "nsfw": {
            "detectionEnabled": False,
            "sensitivity": 3,
            "autoSwitch": True,
            "logging": True
        },
        "fallback": {
            "enabled": True,
            "primaryProvider": "mistral",
            "secondaryProvider": "openrouter",
            "retryEnabled": True,
            "retryAttempts": 3
        },
        "queueEnabled": True,
        "search": {
            "enabled": False,
            "serpapi_key": "",
            "brave_key": "",
            "tavily_key": ""
        }
    }

def detectar_nsfw(texto, sensibilidad=3):
    """
    Detecta contenido NSFW simple basado en palabras clave.
    Sensibilidad: 1-5 (5 = muy sensible)
    
    Para implementación más robusta, usar un modelo especializado.
    """
    palabras_nsfw_extremas = {
        'xxx', 'pornografía', 'pornografico', 'porno',
        'sexo extremo', 'sexo duro'
    }
    
    palabras_nsfw_altas = {
        'sexo', 'sexual', 'desnudo', 'desnuda', 'penetración',
        'eyaculación', 'orgasmo'
    }
    
    palabras_nsfw_medias = {
        'pezón', 'pene', 'vagina', 'culo', 'teta',
        'erótico', 'erotica'
    }
    
    palabras_nsfw_bajas = {
        'sexy', 'atractivo', 'atractiva', 'seducción'
    }
    
    texto_lower = texto.lower()
    
    if sensibilidad >= 5:
        todas = palabras_nsfw_extremas | palabras_nsfw_altas | palabras_nsfw_medias | palabras_nsfw_bajas
    elif sensibilidad >= 4:
        todas = palabras_nsfw_extremas | palabras_nsfw_altas | palabras_nsfw_medias
    elif sensibilidad >= 3:
        todas = palabras_nsfw_extremas | palabras_nsfw_altas
    elif sensibilidad >= 2:
        todas = palabras_nsfw_extremas
    else:
        todas = palabras_nsfw_extremas  # sensibilidad=1: mínima, pero detecta lo más grave igual
    
    for palabra in todas:
        if palabra in texto_lower:
            return True
    
    return False

def obtener_modelo_actual(tarea):
    """Obtiene el modelo configurado para una tarea específica"""
    config = cargar_config_apis()
    return config.get('models', {}).get(tarea, 'mistral-large-latest')

def obtener_proveedor_actual(tarea=None):
    """
    Obtiene el proveedor a usar.
    Si hay NSFW detectado, devuelve fallback.
    """
    config = cargar_config_apis()
    
    primaryProvider = config['fallback']['primaryProvider']
    
    # Verificar que el proveedor principal esté habilitado
    if config[primaryProvider].get('enabled'):
        return primaryProvider
    
    # Fallback automático
    secondaryProvider = config['fallback']['secondaryProvider']
    if config[secondaryProvider].get('enabled'):
        print(f"⚠️ Proveedor principal {primaryProvider} no habilitado, usando {secondaryProvider}")
        return secondaryProvider
    
    # Si ninguno está habilitado, retornar el primario (fallará después pero es consistente)
    return primaryProvider

def _resolver_modelo_para_llamada(model, provider, config):
    """
    Dado un nombre de modelo (puede ser estilo Mistral como 'mistral-large-latest'
    o ya un ID de OpenRouter como 'gryphe/mythomax-l2-13b'), devuelve el modelo
    real a usar según el provider activo.

    Regla:
      - Mistral:     si el config.models.chat/extraction es un nombre Mistral, lo usa.
      - OpenRouter:  si config.models.chat/extraction tiene '/' en el ID, lo usa.
                     Si no, cae al modelo guardado en modelos_activos.json.
    """
    config_models = config.get('models', {})

    # Determinar la "tarea" del modelo recibido
    if model in _MODELOS_CHAT_MISTRAL:
        tarea = 'chat'
    elif model in _MODELOS_SMALL_MISTRAL:
        tarea = 'extraction'
    elif '/' in model:
        # Ya es un ID concreto de OpenRouter u otro proveedor
        return model
    else:
        # Nombre desconocido, lo usamos tal cual
        return model

    configured = config_models.get(tarea, '')

    if provider == 'mistral':
        # Para Mistral queremos un nombre sin '/'
        if configured and '/' not in configured:
            return configured
        # Si el modelo configurado tiene '/' es de OpenRouter — lo devolvemos tal
        # cual para que llamada_mistral_segura detecte el mismatch y redirija.
        if configured and '/' in configured:
            return configured
        return model  # fallback al original

    else:  # openrouter
        # Para OpenRouter queremos un ID con '/'
        if configured and '/' in configured:
            return configured
        # El config tiene un modelo Mistral → buscar en modelos_activos.json
        try:
            from modelos_utils import cargar_modelos_activos
            activos = cargar_modelos_activos()
            if tarea == 'chat':
                return activos.get('openrouter_chat', 'nousresearch/hermes-3-llama-3.1-405b:nitro')
            else:
                return activos.get('openrouter_small', 'meta-llama/llama-3.1-8b-instruct:free')
        except Exception:
            return 'nousresearch/hermes-3-llama-3.1-405b:nitro'


def _inferir_tarea(model, config):
    """Devuelve el nombre de la tarea que usa este modelo según el config."""
    nombres = {
        'chat':       'chat',
        'extraction': 'extracción',
        'synthesis':  'síntesis',
        'generation': 'generación',
        'enrichment': 'enriquecimiento',
        'embeddings': 'embeddings',
    }
    models_cfg = config.get('models', {})
    for clave, label in nombres.items():
        if models_cfg.get(clave) == model:
            return label
    # Fallback: inferir por nombre
    if 'embed' in model:
        return 'embeddings'
    if 'small' in model or '8b' in model or '3b' in model:
        return 'extracción'
    return 'chat'


def _llamar_mistral(model, messages, max_tokens, config, detect_nsfw=True, temperature=None):
    """Llamada con la SDK nueva de Mistral (v1+). Nunca usa el .env directamente."""
    print(f"🔵 [Mistral] {model} → {_inferir_tarea(model, config)}")
    api_key = (config.get('mistral', {}).get('apiKey') or '').strip()
    if not api_key:
        api_key = os.getenv('MISTRAL_API_KEY', '').strip()
    if not api_key:
        raise ValueError(
            "No hay API key de Mistral configurada. "
            "Andá al Gestor de APIs y agregá tu clave."
        )

    client = Mistral(api_key=api_key)
    kwargs = dict(model=model, messages=messages, max_tokens=max_tokens)
    if temperature is not None:
        kwargs['temperature'] = temperature
    response = client.chat.complete(**kwargs)

    # ── Detección NSFW opcional ───────────────────────────────────────────────
    nsfw = config.get('nsfw', {})
    if detect_nsfw and nsfw.get('detectionEnabled'):
        texto = response.choices[0].message.content
        if detectar_nsfw(texto, nsfw.get('sensitivity', 3)):
            if nsfw.get('logging'):
                print("⚠️ NSFW detectado en respuesta Mistral")
            or_cfg = config.get('openrouter', {})
            if nsfw.get('autoSwitch') and or_cfg.get('enabled') and or_cfg.get('apiKey'):
                print("🔄 Cambiando automáticamente a OpenRouter")
                or_model = _resolver_modelo_para_llamada(model, 'openrouter', config)
                return _llamar_openrouter(or_model, messages, max_tokens, config)

    return response


def _llamar_openrouter(model, messages, max_tokens, config, temperature=None):
    """Llamada a OpenRouter vía requests. Devuelve objeto compatible con Mistral response."""
    import requests as _req
    print(f"🟠 [OpenRouter] {model} → {_inferir_tarea(model, config)}")

    api_key = (config.get('openrouter', {}).get('apiKey') or '').strip()
    if not api_key:
        api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
    if not api_key:
        raise ValueError(
            "No hay API key de OpenRouter configurada. "
            "Andá al Gestor de APIs y agregá tu clave."
        )

    payload = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if temperature is not None:
        payload['temperature'] = temperature
    # Desactivar reasoning en modelos que lo soportan (DeepSeek, aion, etc.)
    # Así el contenido siempre llega en el campo "content" estándar.
    MODELOS_REASONING = ('deepseek', 'aion-labs', 'qwen')
    if any(m in model for m in MODELOS_REASONING):
        payload['reasoning'] = {'enabled': False}
    resp = _req.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "http://localhost",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=90,
    )

    if resp.status_code != 200:
        raise Exception(f"OpenRouter error {resp.status_code}: {resp.text[:300]}")

    data    = resp.json()
    message = data['choices'][0]['message']
    raw     = message.get('content')

    # Formato 1: string normal (mayoría de modelos)
    if isinstance(raw, str):
        content = raw
    # Formato 2: lista de bloques tipo Anthropic [{'type':'text','text':'...'}]
    elif isinstance(raw, list):
        partes = [b.get('text') or b.get('content','') for b in raw
                  if isinstance(b, dict) and b.get('type') != 'thinking']
        if not partes:
            partes = [b.get('thinking') or b.get('text','') for b in raw if isinstance(b, dict)]
        content = ' '.join(p for p in partes if p)
    else:
        content = ''

    # IMPORTANTE: reasoning_details y reasoning son el pensamiento INTERNO del modelo.
    # Nunca se muestran al usuario. Si content está vacío, el modelo no generó
    # respuesta visible — se registra en el log para debug.
    if not content.strip():
        print(f'⚠️ OpenRouter: content vacío para modelo {model}. Keys en message: {list(message.keys())}')
        content = '...'

    # Objeto mínimo compatible con el formato de respuesta de Mistral
    class _Resp:
        def __init__(self, text):
            self.choices = [type('_C', (), {
                'message': type('_M', (), {'content': text})()
            })()]

    return _Resp(content)


def llamada_mistral_segura(model, messages, max_tokens=600, detect_nsfw=True, temperature=None):
    """
    Punto único de llamada a LLM. Lee TODO desde api_config.json — ya no depende del .env.

    - Detecta el provider activo (Mistral u OpenRouter) desde el config.
    - Resuelve el modelo real según la tarea (chat vs análisis).
    - Reintentos automáticos + fallback al proveedor secundario si está configurado.
    - temperature=None usa el default del proveedor. Pasá 0.85-0.9 para chat/roleplay.

    'model' puede ser un nombre Mistral ('mistral-large-latest') usado como
    indicador de tarea, o directamente un ID de OpenRouter ('gryphe/mythomax-l2-13b').

    IMPORTANTE: si el modelo configurado (models.chat/extraction) tiene '/' en su ID,
    se fuerza OpenRouter independientemente de cuál sea el primaryProvider. Esto evita
    que modelos de OpenRouter se envíen por error a la API de Mistral.
    """
    config   = cargar_config_apis()
    provider = obtener_proveedor_actual()

    retry_enabled = config.get('fallback', {}).get('retryEnabled', True)
    max_retries   = config.get('fallback', {}).get('retryAttempts', 3) if retry_enabled else 1

    real_model = _resolver_modelo_para_llamada(model, provider, config)

    # ── Auto-detección del proveedor real según el ID del modelo ────────────
    # Regla simple: si tiene '/' es de OpenRouter, si no es de Mistral.
    # Esto evita que modelos de un proveedor se manden al otro por error.
    if '/' in real_model and provider == 'mistral':
        # Modelo de OpenRouter mandado a Mistral → redirigir a OpenRouter
        or_cfg = config.get('openrouter', {})
        if or_cfg.get('apiKey', '').strip():
            print(f"🔀 '{real_model}' es de OpenRouter — redirigiendo a OpenRouter")
            provider = 'openrouter'
        else:
            raise ValueError(
                f"El modelo '{real_model}' requiere OpenRouter pero no hay API key configurada."
            )
    elif '/' not in real_model and provider == 'openrouter':
        # Modelo de Mistral mandado a OpenRouter → redirigir a Mistral
        mi_cfg = config.get('mistral', {})
        if mi_cfg.get('apiKey', '').strip() or os.getenv('MISTRAL_API_KEY', '').strip():
            print(f"🔀 '{real_model}' es de Mistral — redirigiendo a Mistral")
            provider = 'mistral'
        else:
            raise ValueError(
                f"El modelo '{real_model}' requiere Mistral pero no hay API key configurada."
            )

    last_error = None

    for attempt in range(max_retries):
        try:
            if provider == 'mistral':
                return _llamar_mistral(real_model, messages, max_tokens, config, detect_nsfw, temperature)
            else:
                return _llamar_openrouter(real_model, messages, max_tokens, config, temperature)
        except Exception as e:
            last_error = e
            print(f"⚠️ Error intento {attempt + 1}/{max_retries}: {e}")
            if attempt < max_retries - 1:
                time.sleep(1)

    # ── Fallback al proveedor secundario ─────────────────────────────────────
    fallback_cfg = config.get('fallback', {})
    if fallback_cfg.get('enabled'):
        alt = 'openrouter' if provider == 'mistral' else 'mistral'
        alt_cfg = config.get(alt, {})
        if alt_cfg.get('enabled') and alt_cfg.get('apiKey', '').strip():
            print(f"🔄 Fallback a {alt} después de {max_retries} reintentos")
            alt_model = _resolver_modelo_para_llamada(model, alt, config)
            try:
                if alt == 'mistral':
                    return _llamar_mistral(alt_model, messages, max_tokens, config, detect_nsfw=False, temperature=temperature)
                else:
                    return _llamar_openrouter(alt_model, messages, max_tokens, config, temperature=temperature)
            except Exception as e2:
                print(f"❌ Fallback también falló: {e2}")

    raise last_error or Exception("No se pudo completar la llamada LLM")


# Alias para compatibilidad con cualquier import directo de llamada_openrouter
def llamada_openrouter(model, messages, max_tokens=600, detect_nsfw=False):
    """Alias público — delega a _llamar_openrouter con la config actual."""
    config = cargar_config_apis()
    return _llamar_openrouter(model, messages, max_tokens, config)

def embeddings_disponibles():
    """True si hay algún proveedor de embeddings configurado."""
    try:
        cfg = cargar_config_apis()
        if cfg.get('mistral', {}).get('apiKey'):
            return True
        if cfg.get('openai', {}).get('enabled') and cfg.get('openai', {}).get('apiKey'):
            return True
        if cfg.get('cohere', {}).get('enabled') and cfg.get('cohere', {}).get('apiKey'):
            return True
        if cfg.get('jina', {}).get('enabled') and cfg.get('jina', {}).get('apiKey'):
            return True
        if cfg.get('ollama', {}).get('enabled'):
            return True
    except Exception:
        pass
    return bool(os.getenv('MISTRAL_API_KEY', '').strip())

def buscar_en_internet(query):
    """
    Busca en internet usando el primer proveedor configurado disponible.
    Orden: SerpAPI → Brave Search → Tavily
    Devuelve un string con los snippets relevantes, o None si no hay nada configurado.
    Solo se llama desde chat_engine cuando el detector de intención lo decide.
    """
    import requests as _req

    cfg    = cargar_config_apis()
    search = cfg.get('search', {})

    if not search.get('enabled', False):
        return None

    # ── SerpAPI ──────────────────────────────────────────────────────────────
    serpapi_key = (search.get('serpapi_key') or '').strip()
    if serpapi_key:
        try:
            resp = _req.get(
                'https://serpapi.com/search',
                params={'q': query, 'api_key': serpapi_key, 'num': 3, 'hl': 'es'},
                timeout=8
            )
            resp.raise_for_status()
            data = resp.json()
            resultados = []
            # Answer box (respuesta directa)
            ab = data.get('answer_box', {})
            if ab.get('answer'):   resultados.append(ab['answer'])
            elif ab.get('snippet'): resultados.append(ab['snippet'])
            # Resultados orgánicos
            for r in data.get('organic_results', [])[:3]:
                if r.get('snippet'):
                    resultados.append(r['snippet'])
            if resultados:
                print(f"🌐 SerpAPI: '{query}' → {len(resultados)} resultado(s)")
                return '\n'.join(resultados[:4])
        except Exception as e:
            print(f"⚠️ SerpAPI error: {e}")

    # ── Brave Search ─────────────────────────────────────────────────────────
    brave_key = (search.get('brave_key') or '').strip()
    if brave_key:
        try:
            resp = _req.get(
                'https://api.search.brave.com/res/v1/web/search',
                params={'q': query, 'count': 3},
                headers={
                    'Accept': 'application/json',
                    'X-Subscription-Token': brave_key
                },
                timeout=8
            )
            resp.raise_for_status()
            data = resp.json()
            resultados = [
                r['description']
                for r in data.get('web', {}).get('results', [])[:3]
                if r.get('description')
            ]
            if resultados:
                print(f"🌐 Brave: '{query}' → {len(resultados)} resultado(s)")
                return '\n'.join(resultados)
        except Exception as e:
            print(f"⚠️ Brave error: {e}")

    # ── Tavily ───────────────────────────────────────────────────────────────
    tavily_key = (search.get('tavily_key') or '').strip()
    if tavily_key:
        try:
            resp = _req.post(
                'https://api.tavily.com/search',
                json={
                    'api_key': tavily_key,
                    'query': query,
                    'max_results': 3,
                    'search_depth': 'basic'
                },
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            resultados = []
            if data.get('answer'):
                resultados.append(data['answer'])
            for r in data.get('results', [])[:2]:
                if r.get('content'):
                    resultados.append(r['content'][:400])
            if resultados:
                print(f"🌐 Tavily: '{query}' → {len(resultados)} resultado(s)")
                return '\n'.join(resultados)
        except Exception as e:
            print(f"⚠️ Tavily error: {e}")

    print(f"⚠️ Búsqueda '{query}': ningún proveedor disponible")
    return None


# ─────────────────────────────────────────────────────────────────────────────
# PATHS Y GESTIÓN DE PERSONAJES
# ─────────────────────────────────────────────────────────────────────────────

PERSONAJES_DIR = './data/personajes'
ACTIVO_PATH    = './data/personaje_activo.json'

def get_personaje_activo_id():
    """Devuelve el ID del personaje activo (default: 'hiro')"""
    if os.path.exists(ACTIVO_PATH):
        try:
            with open(ACTIVO_PATH, 'r') as f:
                return json.load(f).get('id', 'hiro')
        except Exception:
            pass
    return 'hiro'

def set_personaje_activo_id(pid):
    os.makedirs('./data', exist_ok=True)
    with open(ACTIVO_PATH, 'w') as f:
        json.dump({'id': pid}, f)

def paths(pid=None):
    """Devuelve todos los paths de un personaje. Si pid=None usa el activo."""
    pid = pid or get_personaje_activo_id()
    base = os.path.join(PERSONAJES_DIR, pid)
    return {
        'id'    : pid,
        'dir'   : base,
        'db'    : os.path.join(base, 'memoria.db'),
        'emb'   : os.path.join(base, 'embeddings.index'),
        'emb_m' : os.path.join(base, 'embeddings_metadata.msgpack'),
        'json'  : os.path.join(base, 'personaje.json'),
        'avatar': os.path.join(base, 'avatar.jpg'),
    }

# ─────────────────────────────────────────────────────────────────────────────
# BASE DE DATOS POR PERSONAJE
# ─────────────────────────────────────────────────────────────────────────────

def init_database_personaje(pid):
    """Crea las tablas SQLite del personaje si no existen. Migra columnas si ya existe."""
    p = paths(pid)
    os.makedirs(p['dir'], exist_ok=True)

    with sqlite3.connect(p['db']) as conn:
        cursor = conn.cursor()

        cursor.execute('''CREATE TABLE IF NOT EXISTS mensajes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rol TEXT NOT NULL,
            contenido TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS memoria_permanente (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            clave TEXT NOT NULL,
            valor TEXT NOT NULL,
            confianza INTEGER DEFAULT 100,
            contexto TEXT,
            fecha_aprendido DATETIME DEFAULT CURRENT_TIMESTAMP,
            ultima_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(categoria, clave))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS memoria_episodica (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            contenido_usuario TEXT NOT NULL,
            contenido_hiro TEXT,
            resumen TEXT,
            temas TEXT,
            emocion_detectada TEXT,
            importancia INTEGER DEFAULT 5,
            embedding_id INTEGER,
            UNIQUE(embedding_id))''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS sintesis_conocimiento (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            categoria TEXT NOT NULL,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            fuentes TEXT,
            confianza INTEGER DEFAULT 80,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(categoria, titulo))''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS relacion (
            id INTEGER PRIMARY KEY,
            fase INTEGER DEFAULT 1,
            nivel_confianza INTEGER DEFAULT 0,
            nivel_intimidad INTEGER DEFAULT 0,
            dias_juntos INTEGER DEFAULT 0,
            primer_mensaje DATETIME,
            ultimo_mensaje DATETIME,
            temas_frecuentes TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS escenarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            historia TEXT,
            tono TEXT,
            instruccion TEXT,
            color TEXT,
            activo INTEGER DEFAULT 0,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        
        # Eventos con ciclo de vida completo:
        #   disparado=0         → pendiente
        #   disparado=1, consumido=0 → activo (en system prompt)
        #   consumido=1         → procesado (vive solo en memoria_permanente)
        #
        # turns_after_fire: turnos transcurridos desde el disparo
        # duracion_activa:  turnos que permanece en el system prompt (default 6)
        # keyword:          palabras clave (comma-separated) para disparador automático
        cursor.execute('''CREATE TABLE IF NOT EXISTS eventos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            historia TEXT,
            tipo TEXT NOT NULL,
            valor TEXT,
            keyword TEXT,
            activo INTEGER DEFAULT 1,
            disparado INTEGER DEFAULT 0,
            consumido INTEGER DEFAULT 0,
            turns_after_fire INTEGER DEFAULT 0,
            duracion_activa INTEGER DEFAULT 6,
            fecha_disparo DATETIME,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # objetos: propiedades = reglas fijas | estado = condición mutable durante el roleplay
        # escenario_id = NULL → aparece en todos los escenarios; int → solo en ese escenario
        # keyword = palabras comma-separated que activan el objeto automáticamente
        cursor.execute('''CREATE TABLE IF NOT EXISTS objetos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            descripcion TEXT NOT NULL,
            propiedades TEXT NOT NULL,
            estado TEXT NOT NULL DEFAULT '',
            poseedor TEXT NOT NULL DEFAULT 'usuario',
            escenario_id INTEGER DEFAULT NULL,
            keyword TEXT DEFAULT NULL,
            activo INTEGER DEFAULT 1,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # Sugerencias de la IA esperando confirmación del usuario
        # campo: 'estado' | 'poseedor' | 'activo'
        # confirmado: NULL=pendiente, 1=aceptado, 0=descartado
        cursor.execute('''CREATE TABLE IF NOT EXISTS objetos_cambios_pendientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            objeto_id INTEGER NOT NULL,
            campo TEXT NOT NULL,
            valor_anterior TEXT,
            valor_nuevo TEXT NOT NULL,
            razon TEXT,
            confirmado INTEGER DEFAULT NULL,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(objeto_id) REFERENCES objetos(id) ON DELETE CASCADE)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS hilos_pendientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pregunta TEXT NOT NULL,
            tema TEXT,
            mensaje_id INTEGER,
            importancia INTEGER DEFAULT 3,
            resuelto INTEGER DEFAULT 0,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # Sistema emocional — detectar_emocion() escribe acá después de cada mensaje
        cursor.execute('''CREATE TABLE IF NOT EXISTS estado_emocional (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            emocion_primaria TEXT NOT NULL,
            intensidad INTEGER DEFAULT 3,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP)''')
            
        cursor.execute('''CREATE TABLE IF NOT EXISTS diarios_personaje (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            titulo TEXT NOT NULL,
            contenido TEXT NOT NULL,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            auto INTEGER DEFAULT 0)''')

        cursor.execute('''CREATE TABLE IF NOT EXISTS evolucion_fases (
            fase INTEGER PRIMARY KEY,
            descripcion TEXT NOT NULL DEFAULT '',
            personalidad TEXT NOT NULL DEFAULT '',
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS expresiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT NOT NULL,
            patrones TEXT NOT NULL DEFAULT '[]',
            imagen_path TEXT,
            es_default INTEGER DEFAULT 0,
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')

        # Tabla de backstory del personaje (diario privado acumulativo).
        # generar_backstory_automatico() escribe acá. Sin esta tabla crashea en el mensaje 50.
        cursor.execute('''CREATE TABLE IF NOT EXISTS backstory_aprendido (
            id INTEGER PRIMARY KEY,
            contenido TEXT NOT NULL,
            fecha_actualizacion DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        # ── Migraciones para DBs existentes ───────────────────────────────────
        migraciones_text = [
            ('escenarios', 'historia'),
            ('eventos',    'historia'),
            ('escenarios', 'color'),
            ('escenarios', 'tono'),         # ← nuevo: tono del escenario
            ('escenarios', 'instruccion'),  # ← nuevo: instruccion extra del escenario
            ('eventos',    'keyword'),       # ← nuevo: disparador por palabra clave
            ('eventos',    'hora'),           # ← nuevo: hora del evento HH:MM (opcional)
            ('eventos',    'seguimiento'),    # ← nuevo: pregunta de seguimiento post-evento
        ]
        migraciones_int = [
            ('memoria_episodica', 'escenario_id'),
            ('memoria_episodica', 'evento_id'),
            ('eventos', 'consumido'),        # ← nuevo: estado consumido
            ('eventos', 'turns_after_fire'), # ← nuevo: contador de turnos post-disparo
            ('eventos', 'duracion_activa'),  # ← nuevo: cuántos turnos dura activo (default 6)
            ('eventos', 'aviso_dias'),         # ← nuevo: avisar N días antes (0 = no avisar)
            ('eventos', 'aviso_disparado'),    # ← nuevo: ya se envió el aviso previo
            ('eventos', 'seguimiento_disparado'), # ← nuevo: ya se envió el seguimiento post
            ('hilos_pendientes', 'importancia'),  # ← nuevo: prioridad del hilo (1-5)
        ]
        for tabla, columna in migraciones_text:
            try:
                cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} TEXT")
                print(f"✅ Migración TEXT: '{columna}' → '{tabla}'")
            except sqlite3.OperationalError:
                pass
        for tabla, columna in migraciones_int:
            if columna == 'duracion_activa':
                default = 6
            elif columna == 'importancia':
                default = 3
            else:
                default = 0
            try:
                cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} INTEGER DEFAULT {default}")
                print(f"✅ Migración INT: '{columna}' → '{tabla}'")
            except sqlite3.OperationalError:
                pass

        # Migraciones objetos — se ejecutan silenciosamente si la columna ya existe
        _obj_text = [
            ('objetos', 'estado',      "TEXT NOT NULL DEFAULT ''"),
            ('objetos', 'keyword',     "TEXT DEFAULT NULL"),
        ]
        _obj_int = [
            ('objetos', 'escenario_id', "INTEGER DEFAULT NULL"),
        ]
        for _t, _c, _def in _obj_text:
            try:
                cursor.execute(f"ALTER TABLE {_t} ADD COLUMN {_c} {_def}")
                print(f"✅ Migración: '{_c}' → '{_t}'")
            except sqlite3.OperationalError:
                pass
        for _t, _c, _def in _obj_int:
            try:
                cursor.execute(f"ALTER TABLE {_t} ADD COLUMN {_c} {_def}")
                print(f"✅ Migración: '{_c}' → '{_t}'")
            except sqlite3.OperationalError:
                pass
        try:
            cursor.execute("ALTER TABLE objetos ADD COLUMN poseedor TEXT NOT NULL DEFAULT 'usuario'")
        except Exception:
            pass

        # Garantizar que siempre exista la fila de relación.
        # INSERT OR REPLACE (en vez de OR IGNORE) para forzar la inserción
        # incluso si la tabla existe pero está vacía (caso de DBs legacy migradas).
        cursor.execute('SELECT COUNT(*) FROM relacion WHERE id = 1')
        if cursor.fetchone()[0] == 0:
            cursor.execute(
                'INSERT INTO relacion (id, primer_mensaje) VALUES (1, ?)',
                (now_argentina().isoformat(),)
            )
            print("✅ Fila de relación inicializada")

# ─────────────────────────────────────────────────────────────────────────────
# IMPORTAR / LISTAR PERSONAJES
# ─────────────────────────────────────────────────────────────────────────────

def _reparar_encoding(obj):
    """
    Recorre recursivamente un dict/list y repara strings con encoding latin-1 mal interpretado.
    Detecta el patrón específico: caracteres Ã seguidos de otro carácter (señal de doble-encoding).
    Solo repara si detecta el patrón; si ya está bien, no toca nada.
    Ej: 'CompaÃ±ero' → 'Compañero', 'mÃºsculo' → 'músculo'
    """
    if isinstance(obj, dict):
        return {k: _reparar_encoding(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_reparar_encoding(i) for i in obj]
    if isinstance(obj, str):
        if 'Ã' in obj or 'â€' in obj or 'Â' in obj:
            try:
                reparado = obj.encode('latin-1').decode('utf-8')
                return reparado
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
        return obj
    return obj

def importar_personaje_desde_json(json_data, imagen_bytes=None):
    """
    Instala un personaje nuevo desde un dict chara_card_v2.
    Crea su carpeta, guarda el JSON y la imagen si viene.
    Repara automáticamente encoding corrupto (latin-1 / utf-8 mixto).
    Devuelve el pid asignado.
    """
    json_data = _reparar_encoding(json_data)

    nombre = json_data.get('data', {}).get('name', 'personaje')
    pid    = f"{nombre.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    p      = paths(pid)
    os.makedirs(p['dir'], exist_ok=True)

    with open(p['json'], 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)

    avatar_b64 = (
        json_data.get('data', {}).get('avatar_image') or
        json_data.get('data', {}).get('avatar') or
        json_data.get('avatar_image', '')
    )
    if avatar_b64 and isinstance(avatar_b64, str) and len(avatar_b64) > 100:
        try:
            if ',' in avatar_b64:
                avatar_b64 = avatar_b64.split(',', 1)[1]
            with open(p['avatar'], 'wb') as f:
                f.write(base64.b64decode(avatar_b64))
        except Exception as e:
            print(f"⚠️  No se pudo guardar avatar base64: {e}")

    if imagen_bytes:
        with open(p['avatar'], 'wb') as f:
            f.write(imagen_bytes)

    init_database_personaje(pid)
    print(f"✅ Personaje importado: {nombre} → {pid}")
    return pid

# ─────────────────────────────────────────────────────────────────────────────
# CONEXIÓN SQLITE (compartida por todos los módulos)
# ─────────────────────────────────────────────────────────────────────────────

def _get_conn(db_path):
    """Abre una conexión SQLite con encoding UTF-8 forzado — evita corrupción en Windows."""
    conn = sqlite3.connect(db_path)
    conn.execute('PRAGMA encoding = "UTF-8"')
    conn.text_factory = str
    return conn


def listar_personajes():
    """Devuelve lista de todos los personajes instalados."""
    if not os.path.exists(PERSONAJES_DIR):
        return []
    personajes = []
    activo_id  = get_personaje_activo_id()
    for pid in os.listdir(PERSONAJES_DIR):
        pjson = os.path.join(PERSONAJES_DIR, pid, 'personaje.json')
        if os.path.exists(pjson):
            try:
                with open(pjson, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                personajes.append({
                    'id'          : pid,
                    'nombre'      : data.get('data', {}).get('name', pid),
                    'activo'      : pid == activo_id,
                    'tiene_avatar': os.path.exists(os.path.join(PERSONAJES_DIR, pid, 'avatar.jpg')),
                })
            except Exception:
                pass
    return personajes


def reparar_valor_db(valor):
    """
    Repara un string individual leído de SQLite que puede tener encoding corrupto.
    Versión liviana de _reparar_encoding() para usar en lecturas de DB punto a punto.
    Ejemplo: 'compaÃ±Ã­a' → 'compañía', '21 aÃ±os' → '21 años'
    """
    if not isinstance(valor, str):
        return valor
    if 'Ã' in valor or 'â€' in valor or 'Â' in valor:
        try:
            return valor.encode('latin-1').decode('utf-8')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
    return valor

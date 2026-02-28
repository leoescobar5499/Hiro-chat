# ═══════════════════════════════════════════════════════════════════════════
# ROUTES.PY — Todos los endpoints HTTP
# Separados en bloques por tema: personajes, chat, memoria,
# escenarios, eventos, objetos, export.
# El archivo que tocás cuando agregás o cambiás una API.
# ═══════════════════════════════════════════════════════════════════════════

import os, json, re, shutil, time
import mimetypes
from flask import Blueprint, render_template, request, jsonify, send_file, Response
from werkzeug.utils import secure_filename

from utils import (
    now_argentina, ARGENTINA_TZ,
    paths, get_personaje_activo_id,
    init_database_personaje,
    importar_personaje_desde_json, listar_personajes,
    _get_conn,
    llamada_mistral_segura,   # estaba siendo importada de memoria por accidente
)
from modelos_utils import (
    cargar_modelos_activos,
    cambiar_modelo,
    listar_modelos_mistral,
    listar_modelos_openrouter,
    probar_modelo,
    agregar_modelo_a_libreria,
    listar_modelos_libreria,
    obtener_modelo_libreria,
    eliminar_modelo_libreria,
    asignar_modelo_a_tarea,
    obtener_asignaciones,
    obtener_modelo_para_tarea,
    filtrar_modelos_por_tag,
    buscar_modelos_libreria,
    TAREAS_DISPONIBLES,
)
from memoria import (
    cargar_personaje,
    _ejecutar_sintesis,
    generar_perfil_narrativo, generar_resumen_relacion, generar_sintesis,
    limpiar_faiss_episodios,
)
from chat_engine import _procesar_mensaje, _procesar_continuar, verificar_eventos_automaticos

bp = Blueprint('main', __name__)

# ─────────────────────────────────────────────────────────────────────────────
# GESTOR DE APIs
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api_manager')
def api_manager():
    return render_template('api_manager.html')


@bp.route('/api/config/apis', methods=['GET'])
def get_api_config():
    """Obtener configuración actual de APIs"""
    try:
        from utils import cargar_config_apis
        config = cargar_config_apis()
        return jsonify(config)
    except Exception as e:
        print(f"❌ Error cargando config: {e}")
        from utils import obtener_config_predeterminada
        return jsonify(obtener_config_predeterminada()), 200


@bp.route('/api/config/apis', methods=['POST'])
def save_api_config():
    """Guardar configuración de APIs — también sincroniza modelos_activos.json"""
    try:
        from utils import guardar_config_apis
        from modelos_utils import guardar_modelos_activos, cargar_modelos_activos
        data = request.get_json()
        guardar_config_apis(data)

        # ── Sincronizar modelos_activos.json automáticamente ─────────────────
        # Así el gestor visual es la única fuente de verdad, sin tocar JSONs a mano.
        models   = data.get('models', {})
        provider = data.get('fallback', {}).get('primaryProvider', 'mistral')
        chat_model  = models.get('chat', '')
        small_model = models.get('extraction', '')

        activos = cargar_modelos_activos()
        activos['provider'] = provider
        if provider == 'openrouter':
            if chat_model:  activos['openrouter_chat']  = chat_model
            if small_model: activos['openrouter_small'] = small_model
        else:
            if chat_model:  activos['mistral_chat']  = chat_model
            if small_model: activos['mistral_small'] = small_model
        guardar_modelos_activos(activos)
        print(f"✅ modelos_activos.json sincronizado — provider={provider}, chat={chat_model}, small={small_model}")

        return jsonify({"ok": True, "mensaje": "Configuración guardada"})
    except Exception as e:
        print(f"❌ Error guardando config: {e}")
        return jsonify({"error": str(e)}), 400


@bp.route('/api/config/test-apis', methods=['POST'])
def test_api_connections():
    """Testear conexiones de APIs"""
    try:
        from utils import cargar_config_apis
        config = cargar_config_apis()
        results = {
            "mistral": {"ok": False, "error": "No configurado"},
            "openrouter": {"ok": False, "error": "No configurado"}
        }
        
        # Test Mistral
        if config.get('mistral', {}).get('enabled') and config.get('mistral', {}).get('apiKey'):
            try:
                from mistralai.client import MistralClient
                client = MistralClient(api_key=config['mistral']['apiKey'])
                response = client.embeddings(model="mistral-embed", input=["test"])
                results["mistral"] = {"ok": True}
            except Exception as e:
                results["mistral"]["error"] = str(e)[:100]
        
        # Test OpenRouter
        if config.get('openrouter', {}).get('enabled') and config.get('openrouter', {}).get('apiKey'):
            try:
                import requests
                headers = {
                    "Authorization": f"Bearer {config['openrouter']['apiKey']}",
                    "HTTP-Referer": "http://localhost"
                }
                response = requests.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=5)
                if response.status_code == 200:
                    results["openrouter"] = {"ok": True}
                else:
                    results["openrouter"]["error"] = f"HTTP {response.status_code}"
            except Exception as e:
                results["openrouter"]["error"] = str(e)[:100]
        
        return jsonify(results)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# ENDPOINTS DE GESTIÓN DE MODELOS DINÁMICOS
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/models/mistral', methods=['GET'])
def get_modelos_mistral():
    """Obtiene la lista de modelos disponibles en Mistral AI"""
    try:
        resultado = listar_modelos_mistral()
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Error obteniendo modelos Mistral: {e}")
        return jsonify({
            'error': str(e),
            'modelos': [
                {'id': 'mistral-large-latest', 'nombre': 'Mistral Large (recomendado)', 'tipo': 'chat'},
                {'id': 'mistral-small-latest', 'nombre': 'Mistral Small (rápido)', 'tipo': 'small'},
            ]
        }), 200


@bp.route('/api/models/openrouter', methods=['GET'])
def get_modelos_openrouter():
    """Obtiene la lista de modelos de OpenRouter (sin censura prioritariamente)"""
    try:
        sin_censura = request.args.get('uncensored', 'true').lower() == 'true'
        resultado = listar_modelos_openrouter(sin_censura_solo=sin_censura)
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Error obteniendo modelos OpenRouter: {e}")
        return jsonify({
            'error': str(e),
            'modelos': []
        }), 200


@bp.route('/api/models/activos', methods=['GET'])
def get_modelos_activos():
    """Obtiene los modelos activos actuales"""
    try:
        config = cargar_modelos_activos()
        return jsonify({
            'ok': True,
            'config': config
        })
    except Exception as e:
        print(f"❌ Error obteniendo modelos activos: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 400


@bp.route('/api/models/cambiar', methods=['POST'])
def cambiar_modelo_endpoint():
    """Cambia el modelo activo"""
    try:
        data = request.get_json()
        tipo = data.get('tipo')
        nuevo_modelo = data.get('modelo')
        
        if not tipo or not nuevo_modelo:
            return jsonify({'error': 'Faltan parámetros: tipo y modelo'}), 400
        
        config = cambiar_modelo(tipo, nuevo_modelo)
        
        return jsonify({
            'ok': True,
            'mensaje': f'Modelo {tipo} cambiado a {nuevo_modelo}',
            'config': config
        })
    except Exception as e:
        print(f"❌ Error cambiando modelo: {e}")
        return jsonify({'error': str(e)}), 400


@bp.route('/api/models/probar', methods=['POST'])
def probar_modelo_endpoint():
    """Prueba un modelo enviando una petición simple"""
    try:
        data = request.get_json()
        modelo_id = data.get('modelo')
        proveedor = data.get('proveedor', 'openrouter')
        
        if not modelo_id:
            return jsonify({'error': 'Falta el parámetro modelo'}), 400
        
        resultado = probar_modelo(modelo_id, proveedor)
        
        return jsonify(resultado)
    except Exception as e:
        print(f"❌ Error probando modelo: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 400

# NUEVO ENDPOINT
@bp.route('/api/models/search', methods=['POST'])
def search_modelos():
    """Busca modelos por query en OpenRouter"""
    query = request.json.get('query')
    resultado = buscar_modelos_openrouter(query)
    return jsonify(resultado)

# NUEVO ENDPOINT
@bp.route('/api/models/validate/<modelo_id>', methods=['GET'])
def validate_modelo(modelo_id):
    """Valida si un modelo existe"""
    existe = validar_modelo_openrouter(modelo_id)
    return jsonify({'existe': existe})

# NUEVO ENDPOINT
@bp.route('/api/models/info/<path:modelo_id>', methods=['GET'])
def get_modelo_info(modelo_id):
    """Obtiene info detallada de un modelo"""
    info = obtener_info_modelo_openrouter(modelo_id)
    return jsonify(info)


@bp.route('/api/models/all-for-tasks', methods=['GET'])
def get_all_models_for_tasks():
    """
    Obtiene TODOS los modelos disponibles (OpenRouter + Mistral + Librería)
    para llenar los dropdowns de "Modelos por Tarea"
    """
    try:
        from modelos_utils import listar_modelos_libreria
        
        # 1. Obtener modelos de OpenRouter
        openrouter_data = listar_modelos_openrouter(sin_censura_solo=True)
        openrouter_modelos = openrouter_data.get('modelos', [])
        
        # 2. Obtener modelos de Mistral
        mistral_data = listar_modelos_mistral()
        mistral_modelos = mistral_data.get('modelos', [])
        
        # 3. Obtener modelos de la librería
        libreria_data = listar_modelos_libreria()
        libreria_modelos = libreria_data.get('modelos', [])
        
        # 4. Convertir modelos de librería al formato esperado
        libreria_formateada = []
        for m in libreria_modelos:
            libreria_formateada.append({
                'id': m.get('id'),
                'nombre': m.get('nombre') or m.get('id'),
                'proveedor': m.get('proveedor'),
                'tipo': 'ambos',
                'es_libreria': True,
                'sin_censura': True
            })
        
        # 5. Combinar todos
        todos_modelos = openrouter_modelos + mistral_modelos + libreria_formateada
        
        return jsonify({
            'ok': True,
            'modelos': todos_modelos,
            'total': len(todos_modelos),
            'openrouter': len(openrouter_modelos),
            'mistral': len(mistral_modelos),
            'libreria': len(libreria_modelos)
        })
        
    except Exception as e:
        print(f"❌ Error obteniendo modelos para tareas: {e}")
        return jsonify({
            'ok': False,
            'error': str(e),
            'modelos': []
        }), 200

# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 9: PERSONAJES
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/')
def index():
    return render_template('index.html')


@bp.route('/sobre_vos')
def sobre_vos():
    return render_template('sobre_vos.html')


@bp.route('/api/personajes', methods=['GET'])
def api_listar_personajes():
    return jsonify(listar_personajes())


@bp.route('/api/personajes/activo', methods=['GET'])
def api_personaje_activo():
    pid = get_personaje_activo_id()
    p   = paths(pid)
    if os.path.exists(p['json']):
        with open(p['json'], 'r', encoding='utf-8') as f:
            data = json.load(f)
        return jsonify({'id': pid, 'nombre': data.get('data',{}).get('name', pid),
                        'tiene_avatar': os.path.exists(p['avatar'])})
    return jsonify({'id': pid, 'nombre': pid, 'tiene_avatar': False})


@bp.route('/api/personajes/cambiar', methods=['POST'])
def api_cambiar_personaje():
    data = request.json
    pid  = data.get('id')
    if not pid:
        return jsonify({'error': 'ID requerido'}), 400
    p = paths(pid)
    if not os.path.exists(p['json']):
        return jsonify({'error': 'Personaje no encontrado'}), 404
    cargar_personaje(pid)
    with open(p['json'], 'r', encoding='utf-8') as f:
        pdata = json.load(f)
    return jsonify({'success': True, 'nombre': pdata.get('data',{}).get('name', pid),
                    'tiene_avatar': os.path.exists(p['avatar'])})


@bp.route('/api/personajes/importar', methods=['POST'])
def api_importar_personaje():
    if 'json_file' not in request.files:
        return jsonify({'error': 'Se requiere un archivo JSON'}), 400
    json_file = request.files['json_file']
    try:
        json_data = json.loads(json_file.read().decode('utf-8'))
    except Exception:
        return jsonify({'error': 'JSON inválido'}), 400
    imagen_bytes = None
    if 'imagen' in request.files:
        img_file = request.files['imagen']
        if img_file.filename:
            imagen_bytes = img_file.read()
    try:
        pid   = importar_personaje_desde_json(json_data, imagen_bytes)
        p     = paths(pid)
        with open(p['json'], 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        return jsonify({'success': True, 'id': pid,
                        'nombre': pdata.get('data',{}).get('name', pid),
                        'tiene_avatar': os.path.exists(p['avatar'])})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/personajes/<pid>/avatar')
def api_avatar_personaje(pid):
    p    = paths(pid)
    ruta = p['avatar'] if os.path.exists(p['avatar']) else ('./static/Hiro.jpg' if os.path.exists('./static/Hiro.jpg') else None)
    if not ruta:
        return '', 404
    resp = send_file(ruta, mimetype='image/jpeg')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@bp.route('/api/personajes/activo/ficha', methods=['GET'])
def api_get_ficha_personaje():
    """Devuelve los campos editables de la ficha del personaje activo."""
    p = paths()
    if not os.path.exists(p['json']):
        return jsonify({'error': 'No se encontró la ficha del personaje'}), 404
    with open(p['json'], 'r', encoding='utf-8') as f:
        data = json.load(f)
    d = data.get('data', {})
    mes_example = d.get('mes_example', '')
    if isinstance(mes_example, list):
        partes = []
        for ex in mes_example:
            if isinstance(ex, dict):
                partes.append('\n'.join(f"{k}: {v}" for k, v in ex.items()))
            else:
                partes.append(str(ex))
        mes_example = '\n\n'.join(partes)
    return jsonify({
        'name'         : d.get('name', ''),
        'description'  : d.get('description', ''),
        'personality'  : d.get('personality', ''),
        'scenario'     : d.get('scenario', ''),
        'first_mes'    : d.get('first_mes', ''),
        'mes_example'  : mes_example,
        'tags'         : d.get('tags', []),
        'creator_notes': d.get('creator_notes', ''),
        'modo_memoria' : d.get('modo_memoria', 'roleplay'),
    })


@bp.route('/api/personajes/activo/ficha', methods=['PUT'])
def api_put_ficha_personaje():
    """Guarda cambios en la ficha del personaje activo."""
    p = paths()
    if not os.path.exists(p['json']):
        return jsonify({'error': 'No se encontró la ficha'}), 404
    try:
        with open(p['json'], 'r', encoding='utf-8') as f:
            card = json.load(f)
        data   = request.json
        campos = ['name', 'description', 'personality', 'scenario',
                  'first_mes', 'mes_example', 'tags', 'creator_notes', 'modo_memoria']
        for campo in campos:
            if campo in data:
                card['data'][campo] = data[campo]
        with open(p['json'], 'w', encoding='utf-8') as f:
            json.dump(card, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/personajes/activo/avatar', methods=['POST'])
def api_cambiar_avatar():
    """Reemplaza el avatar del personaje activo."""
    if 'imagen' not in request.files:
        return jsonify({'error': 'No se recibió imagen'}), 400
    img = request.files['imagen']
    if not img.filename:
        return jsonify({'error': 'Archivo vacío'}), 400
    p = paths()
    try:
        ext = os.path.splitext(secure_filename(img.filename))[1].lower() or '.jpg'
        avatar_path = os.path.join(p['dir'], f'avatar{ext}')
        img.save(avatar_path)
        if avatar_path != p['avatar']:
            if os.path.exists(p['avatar']):
                os.remove(p['avatar'])
            os.rename(avatar_path, p['avatar'])
        return jsonify({'success': True, 'url': f"/api/personajes/{p['id']}/avatar?t={int(time.time())}"})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/personajes/<pid>', methods=['DELETE'])
def api_eliminar_personaje(pid):
    if pid == get_personaje_activo_id():
        return jsonify({'error': 'No podés eliminar el personaje activo'}), 400
    p = paths(pid)
    if not os.path.exists(p['dir']):
        return jsonify({'error': 'Personaje no encontrado'}), 404
    shutil.rmtree(p['dir'])
    return jsonify({'success': True})

@bp.route('/editar_personaje')
def editar_personaje():
    return render_template('editar_personaje.html')

@bp.route('/escenarios')
def pagina_escenarios():
    return render_template('escenarios.html')

@bp.route('/eventos')
def pagina_eventos():
    return render_template('eventos.html')
    
@bp.route('/objetos')
def pagina_objetos():
    return render_template('objetos.html')
    


@bp.route('/api/diarios', methods=['GET'])
def listar_diarios():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT id, titulo, contenido, fecha, auto FROM diarios_personaje ORDER BY id DESC'
            )
            rows = cursor.fetchall()
        except Exception:
            return jsonify([])
    return jsonify([
        {'id': r[0], 'titulo': r[1], 'contenido': r[2], 'fecha': r[3], 'auto': bool(r[4])}
        for r in rows
    ])


@bp.route('/api/diarios', methods=['POST'])
def crear_diario():
    data    = request.json or {}
    generar = data.get('generar', False)

    if generar:
        from memoria import generar_diario_automatico
        contenido = generar_diario_automatico()
        if not contenido:
            return jsonify({'error': 'No hay datos suficientes aún'}), 400
        return jsonify({'success': True, 'mensaje': 'Generado automáticamente'})

    titulo    = (data.get('titulo') or '').strip() or \
                f"Entrada — {now_argentina().strftime('%d/%m/%Y')}"
    contenido = (data.get('contenido') or '').strip()
    if not contenido:
        return jsonify({'error': 'El contenido es requerido'}), 400

    fecha = now_argentina().isoformat()
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO diarios_personaje (titulo, contenido, fecha, auto) VALUES (?, ?, ?, 0)',
            (titulo, contenido, fecha)
        )
        new_id = cursor.lastrowid
    return jsonify({'success': True, 'id': new_id, 'titulo': titulo,
                    'contenido': contenido, 'fecha': fecha})


@bp.route('/api/diarios/<int:did>', methods=['PUT'])
def editar_diario(did):
    data      = request.json or {}
    contenido = (data.get('contenido') or '').strip()
    titulo    = (data.get('titulo') or '').strip()
    if not contenido:
        return jsonify({'error': 'Contenido requerido'}), 400
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        if titulo:
            cursor.execute(
                'UPDATE diarios_personaje SET contenido=?, titulo=? WHERE id=?',
                (contenido, titulo, did)
            )
        else:
            cursor.execute(
                'UPDATE diarios_personaje SET contenido=? WHERE id=?',
                (contenido, did)
            )
    return jsonify({'success': True})


@bp.route('/api/diarios/<int:did>', methods=['DELETE'])
def eliminar_diario(did):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM diarios_personaje WHERE id=?', (did,))
    return jsonify({'success': True})

# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN: EVOLUCIÓN DEL PERSONAJE POR FASE
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/evolucion', methods=['GET'])
def listar_evolucion():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                'SELECT fase, descripcion, personalidad, fecha_actualizacion FROM evolucion_fases ORDER BY fase ASC'
            )
            rows = cursor.fetchall()
        except Exception:
            return jsonify([])
    return jsonify([
        {'fase': r[0], 'descripcion': r[1], 'personalidad': r[2], 'fecha': r[3]}
        for r in rows
    ])


@bp.route('/api/evolucion/<int:fase>', methods=['PUT'])
def editar_evolucion(fase):
    data        = request.json or {}
    descripcion = (data.get('descripcion') or '').strip()
    personalidad= (data.get('personalidad') or '').strip()
    fecha       = now_argentina().isoformat()
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO evolucion_fases (fase, descripcion, personalidad, fecha_actualizacion)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(fase) DO UPDATE SET
                descripcion=excluded.descripcion,
                personalidad=excluded.personalidad,
                fecha_actualizacion=excluded.fecha_actualizacion
        ''', (fase, descripcion, personalidad, fecha))
    return jsonify({'success': True})


@bp.route('/api/evolucion/<int:fase>', methods=['DELETE'])
def eliminar_evolucion(fase):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM evolucion_fases WHERE fase=?', (fase,))
    return jsonify({'success': True})


@bp.route('/api/evolucion/generar', methods=['POST'])
def generar_evolucion_ia():
    """Auto-genera descripción + personalidad para la fase actual usando IA."""
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT fase, nivel_confianza, nivel_intimidad, dias_juntos FROM relacion WHERE id=1'
            )
            rel = cursor.fetchone()

        if not rel:
            return jsonify({'error': 'No hay datos de relación'}), 400

        fase, confianza, intimidad, dias = rel

        p         = paths()
        nombre_p  = 'Personaje'
        desc_orig = ''
        try:
            with open(p['json'], 'r', encoding='utf-8') as f:
                pdata    = json.load(f)
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

Y el estado actual de la relación:
- Fase: {fase}/4 ({fases_nombres.get(fase, '')})
- Confianza: {confianza}/100 — Intimidad: {intimidad}/100 — Días: {dias}

Escribí DOS textos breves que muestren cómo {nombre_p} ha evolucionado en ESTA fase:

1. DESCRIPCION (3-4 oraciones): Cómo es {nombre_p} AHORA — su presencia emocional, actitud hacia el usuario. Vívido y en presente.

2. PERSONALIDAD (3-4 oraciones): Cómo se comporta en esta fase — gestos, forma de hablar, hábitos con el usuario. Concreto y específico.

Respondé SOLO en JSON sin markdown:
{{"descripcion": "...", "personalidad": "..."}}"""

        response = llamada_mistral_segura(
            model="mistral-small-latest",
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=450
        )
        texto = response.choices[0].message.content.strip()

        # Parsear JSON de la respuesta
        from memoria._helpers import _limpiar_json
        datos = _limpiar_json(texto, esperar_array=False)
        if not datos:
            return jsonify({'error': 'No se pudo parsear la respuesta de IA'}), 500

        return jsonify({
            'success'     : True,
            'fase'        : fase,
            'descripcion' : datos.get('descripcion', ''),
            'personalidad': datos.get('personalidad', '')
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 10: CHAT
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/chat', methods=['POST'])
def chat():
    try:
        data    = request.json
        mensaje = data.get('message', '').strip()
        if not mensaje:
            return jsonify({'error': 'Mensaje vacío'}), 400
        if len(mensaje) > 2000:
            return jsonify({'error': 'Mensaje demasiado largo (máximo 2000 caracteres)'}), 400

        respuesta = _procesar_mensaje(mensaje)

        eventos_disparados = []
        try:
            eventos_disparados = verificar_eventos_automaticos()
        except Exception as e:
            print(f"⚠️ Error verificando eventos: {e}")

        return jsonify({'response': respuesta, 'eventos_disparados': eventos_disparados})
    except Exception as e:
        print(f"❌ Error en /api/chat: {e}")
        return jsonify({'error': f'Error interno: {str(e)}'}), 500


@bp.route('/api/mensaje', methods=['POST'])
def enviar_mensaje_legacy():
    """Endpoint legacy — reutiliza _procesar_mensaje."""
    try:
        data    = request.json
        mensaje = data.get('mensaje', '').strip()
        if not mensaje:
            return jsonify({'error': 'Mensaje vacío'}), 400
        respuesta = _procesar_mensaje(mensaje)
        return jsonify({'respuesta': respuesta})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/continuar', methods=['POST'])
def continuar():
    """El personaje continúa escribiendo sin input del usuario."""
    try:
        respuesta = _procesar_continuar()
        eventos_disparados = []
        try:
            eventos_disparados = verificar_eventos_automaticos()
        except Exception as e:
            print(f"⚠️ Error verificando eventos: {e}")
        return jsonify({'response': respuesta, 'eventos_disparados': eventos_disparados})
    except Exception as e:
        print(f"❌ Error en /api/continuar: {e}")
        return jsonify({'error': f'Error interno: {str(e)}'}), 500


@bp.route('/api/cancelar_ultimo', methods=['POST'])
def cancelar_ultimo():
    """
    Borra el último intercambio de la DB cuando el usuario presiona Stop.
    Lógica:
      - Si el último mensaje es 'assistant' → borra ese + el 'user' anterior (turno completo).
      - Si el último mensaje es 'user' (abort antes de que Mistral respondiera) → borra solo ese.
    No toca memoria episódica ni permanente porque el post-proceso corre en background
    y puede no haber llegado a guardar nada todavía.
    """
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id, rol FROM mensajes ORDER BY id DESC LIMIT 2')
            ultimos = cursor.fetchall()

            if not ultimos:
                return jsonify({'ok': True, 'borrados': 0})

            ids_a_borrar = []
            ultimo_id, ultimo_rol = ultimos[0]

            if ultimo_rol == 'assistant':
                # Turno completo: borrar respuesta del personaje + mensaje del usuario
                ids_a_borrar.append(ultimo_id)
                if len(ultimos) > 1:
                    prev_id, prev_rol = ultimos[1]
                    if prev_rol == 'user':
                        ids_a_borrar.append(prev_id)
            elif ultimo_rol == 'user':
                # Abort antes de la respuesta — solo borrar el mensaje del usuario
                ids_a_borrar.append(ultimo_id)

            if ids_a_borrar:
                placeholders = ','.join('?' * len(ids_a_borrar))
                cursor.execute(f'DELETE FROM mensajes WHERE id IN ({placeholders})', ids_a_borrar)

            print(f"🛑 Stop: borrados {len(ids_a_borrar)} mensaje(s) de DB")
            return jsonify({'ok': True, 'borrados': len(ids_a_borrar)})
    except Exception as e:
        print(f"⚠️ Error cancelar_ultimo: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 11: STATS, HISTORIAL, PERFIL
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/stats', methods=['GET'])
def obtener_estadisticas():
    from datetime import datetime
    import json as _json
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, fase, nivel_confianza, nivel_intimidad, dias_juntos, primer_mensaje, temas_frecuentes FROM relacion WHERE id = 1')
        relacion = cursor.fetchone()
        cursor.execute('SELECT COUNT(*) FROM mensajes')
        total_mensajes = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM mensajes WHERE rol='user'")
        total_user = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM memoria_permanente')
        total_hechos = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM memoria_episodica')
        total_episodios = cursor.fetchone()[0]
        cursor.execute('SELECT COUNT(*) FROM sintesis_conocimiento')
        total_sintesis = cursor.fetchone()[0]
        cursor.execute('SELECT contenido FROM backstory_aprendido WHERE id=1 LIMIT 1')
        bs_row = cursor.fetchone()

    dias_juntos = 1
    if relacion and relacion[5]:
        primer = datetime.fromisoformat(str(relacion[5]).replace(' ','T').split('.')[0])
        if primer.tzinfo is None:
            primer = primer.replace(tzinfo=ARGENTINA_TZ)
        dias_juntos = max(1, (now_argentina().date() - primer.date()).days + 1)

    temas = []
    if relacion and relacion[6]:
        try: temas = _json.loads(relacion[6])
        except Exception: pass

    fases = {1:"Primeras conversaciones",2:"Conociendo más",3:"Confianza construida",4:"Intimidad profunda"}
    return jsonify({
        'dias_juntos'               : dias_juntos,
        'total_mensajes'            : total_mensajes,
        'total_mensajes_usuario'    : total_user,
        'total_hechos_aprendidos'   : total_hechos,
        'total_memorias_episodicas' : total_episodios,
        'total_sintesis'            : total_sintesis,
        'fase'                      : relacion[1] if relacion else 1,
        'fase_nombre'               : fases.get(relacion[1] if relacion else 1),
        'nivel_confianza'           : relacion[2] if relacion else 0,
        'nivel_intimidad'           : relacion[3] if relacion else 0,
        'temas_frecuentes'          : temas,
        'tiene_backstory'           : bool(bs_row and bs_row[0]),
    })

@bp.route('/api/perfil', methods=['GET'])
def obtener_perfil():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, categoria, clave, valor, contexto, confianza FROM memoria_permanente ORDER BY categoria, ultima_actualizacion DESC')
        memoria = cursor.fetchall()
        cursor.execute('SELECT categoria, contenido FROM sintesis_conocimiento')
        sintesis = cursor.fetchall()

    perfil = {'hechos': {}, 'sintesis': {}, 'tiene_datos': len(memoria) > 0}
    for id_h, cat, clave, valor, contexto, conf in memoria:
        perfil['hechos'].setdefault(cat, []).append(
            {'id': id_h, 'clave': clave, 'valor': valor, 'contexto': contexto, 'confianza': conf})
    for cat, contenido in sintesis:
        perfil['sintesis'][cat] = contenido
    return jsonify(perfil)


@bp.route('/api/historial', methods=['GET'])
def obtener_historial():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, rol, contenido, timestamp FROM mensajes ORDER BY id ASC')
        msgs = cursor.fetchall()
    return jsonify({'mensajes': [{'id': r[0], 'rol': r[1], 'contenido': r[2], 'timestamp': r[3]} for r in msgs]})


@bp.route('/api/historial', methods=['DELETE'])
def limpiar_historial():
    try:
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM mensajes')
            cursor.execute('DELETE FROM memoria_episodica')
            cursor.execute('UPDATE relacion SET ultimo_mensaje = ? WHERE id = 1', (now_argentina().isoformat(),))

        pid_actual = get_personaje_activo_id()
        limpiar_faiss_episodios(pid_actual)
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 12: CRUD MENSAJES
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/mensaje/<int:msg_id>', methods=['GET'])
def obtener_mensaje(msg_id):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, rol, contenido FROM mensajes WHERE id = ?', (msg_id,))
        msg = cursor.fetchone()
    if msg:
        return jsonify({'id': msg[0], 'rol': msg[1], 'contenido': msg[2]})
    return jsonify({'error': 'No encontrado'}), 404


@bp.route('/api/mensaje/<int:msg_id>', methods=['PUT'])
def editar_mensaje(msg_id):
    data = request.json
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE mensajes SET contenido = ? WHERE id = ?', (data.get('contenido',''), msg_id))
    return jsonify({'success': True})


@bp.route('/api/mensaje/<int:msg_id>', methods=['DELETE'])
def eliminar_mensaje(msg_id):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM mensajes WHERE id = ?', (msg_id,))
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 13: CRUD MEMORIA
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/memoria/hecho/<int:hid>', methods=['GET'])
def obtener_hecho(hid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, categoria, clave, valor, contexto, confianza FROM memoria_permanente WHERE id = ?', (hid,))
        r = cursor.fetchone()
    if r:
        return jsonify({'id':r[0],'categoria':r[1],'clave':r[2],'valor':r[3],'contexto':r[4],'confianza':r[5]})
    return jsonify({'error': 'No encontrado'}), 404


@bp.route('/api/memoria/hecho/<int:hid>', methods=['PUT'])
def editar_hecho(hid):
    data = request.json
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('''UPDATE memoria_permanente
            SET categoria=?, clave=?, valor=?, contexto=?, confianza=?, ultima_actualizacion=?
            WHERE id=?''',
            (data['categoria'], data['clave'], data['valor'],
             data.get('contexto',''), data.get('confianza',100), now_argentina().isoformat(), hid))
    return jsonify({'success': True})


@bp.route('/api/memoria/hecho/<int:hid>', methods=['DELETE'])
def eliminar_hecho(hid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memoria_permanente WHERE id = ?', (hid,))
    return jsonify({'success': True})


@bp.route('/api/memoria/categoria/<cat>', methods=['DELETE'])
def eliminar_categoria(cat):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memoria_permanente WHERE categoria = ?', (cat,))
        n = cursor.rowcount
    return jsonify({'success': True, 'mensaje': f'{n} registros eliminados'})


@bp.route('/api/memoria/limpiar-todo', methods=['DELETE'])
def limpiar_memoria():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM memoria_permanente')
        cursor.execute('DELETE FROM sintesis_conocimiento')
    return jsonify({'success': True, 'mensaje': 'Memoria eliminada'})


@bp.route('/api/reset-total', methods=['DELETE'])
def reset_total():
    """
    Borra TODO excepto escenarios y objetos.
    Limpia: mensajes, memorias, síntesis, hilos, estado emocional, backstory.
    Resetea: relación completa (incluyendo primer_mensaje → ahora, para que
    dias_juntos vuelva a 1 en el cálculo dinámico de /api/stats),
    eventos disparados, y contadores AUTOINCREMENT.
    """
    try:
        ahora = now_argentina().isoformat()

        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()

            # ── Historial y memoria ───────────────────────────────────────────
            cursor.execute('DELETE FROM mensajes')
            cursor.execute('DELETE FROM memoria_episodica')
            cursor.execute('DELETE FROM memoria_permanente')
            cursor.execute('DELETE FROM sintesis_conocimiento')

            # ── Tablas auxiliares ─────────────────────────────────────────────
            cursor.execute('DELETE FROM hilos_pendientes')
            cursor.execute('DELETE FROM estado_emocional')
            try:
                cursor.execute('DELETE FROM backstory_aprendido')
            except Exception:
                pass
            try:
                cursor.execute('DELETE FROM diarios_personaje')
            except Exception:
                pass
            try:
                cursor.execute('DELETE FROM evolucion_fases')
            except Exception:
                pass
            try:
                cursor.execute('DELETE FROM objetos_cambios_pendientes')
            except Exception:
                pass

            # ── Resetear relación completa ────────────────────────────────────
            # primer_mensaje se pisa con ahora: el cálculo dinámico de dias_juntos
            # en /api/stats hace (hoy - primer_mensaje).days + 1, así que si
            # primer_mensaje = hoy el resultado es siempre 1.
            cursor.execute('''
                UPDATE relacion SET
                    fase             = 1,
                    nivel_confianza  = 0,
                    nivel_intimidad  = 0,
                    dias_juntos      = 0,
                    primer_mensaje   = ?,
                    ultimo_mensaje   = NULL,
                    temas_frecuentes = NULL
                WHERE id = 1
            ''', (ahora,))

            # ── Resetear eventos ──────────────────────────────────────────────
            cursor.execute('''
                UPDATE eventos SET
                    disparado        = 0,
                    consumido        = 0,
                    turns_after_fire = 0,
                    fecha_disparo    = NULL
            ''')

            # ── Resetear contadores AUTOINCREMENT ─────────────────────────────
            for tabla in [
                'mensajes', 'memoria_episodica', 'memoria_permanente',
                'sintesis_conocimiento', 'hilos_pendientes',
                'estado_emocional', 'backstory_aprendido',
                'diarios_personaje', 'evolucion_fases',
                'objetos_cambios_pendientes',
            ]:
                try:
                    cursor.execute(
                        "DELETE FROM sqlite_sequence WHERE name = ?", (tabla,)
                    )
                except Exception:
                    pass

        # ── Limpiar FAISS ─────────────────────────────────────────────────────
        try:
            limpiar_faiss_episodios(get_personaje_activo_id())
        except Exception as e:
            print(f"⚠️ Error limpiando FAISS en reset-total: {e}")

        return jsonify({'success': True, 'mensaje': 'Reset completo realizado'})

    except Exception as e:
        print(f"❌ Error en reset-total: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ─── CRUD SÍNTESIS ────────────────────────────────────────────────────────────

@bp.route('/api/sintesis', methods=['GET'])
def listar_sintesis():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, categoria, titulo, contenido FROM sintesis_conocimiento ORDER BY categoria')
        rows = cursor.fetchall()
        # Agregar backstory como entrada especial si existe
        try:
            cursor.execute('SELECT contenido, fecha_actualizacion FROM backstory_aprendido WHERE id=1 LIMIT 1')
            bs = cursor.fetchone()
        except Exception:
            bs = None
    result = [{'id': r[0], 'categoria': r[1], 'titulo': r[2], 'contenido': r[3]} for r in rows]
    if bs and bs[0]:
        result.append({'id': 'backstory', 'categoria': 'diario_personaje', 'titulo': 'Diario del personaje', 'contenido': bs[0], 'fecha': str(bs[1])})
    return jsonify(result)


@bp.route('/api/sintesis/<int:sid>', methods=['GET'])
def obtener_sintesis(sid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, categoria, titulo, contenido FROM sintesis_conocimiento WHERE id=?', (sid,))
        r = cursor.fetchone()
    if r:
        return jsonify({'id': r[0], 'categoria': r[1], 'titulo': r[2], 'contenido': r[3]})
    return jsonify({'error': 'No encontrado'}), 404


@bp.route('/api/sintesis/<int:sid>', methods=['PUT'])
def editar_sintesis(sid):
    data = request.json
    contenido = data.get('contenido', '').strip()
    if not contenido:
        return jsonify({'error': 'El contenido no puede estar vacío'}), 400
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE sintesis_conocimiento SET contenido=?, fecha_actualizacion=? WHERE id=?',
                       (contenido, now_argentina().isoformat(), sid))
    return jsonify({'success': True})


@bp.route('/api/sintesis/<int:sid>', methods=['DELETE'])
def eliminar_sintesis_endpoint(sid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM sintesis_conocimiento WHERE id=?', (sid,))
    return jsonify({'success': True})


@bp.route('/api/regenerar-sintesis', methods=['POST'])
def regenerar_sintesis():
    try:
        _ejecutar_sintesis("manual desde UI")
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 14: ESCENARIOS (historia + color de ambiente)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/escenarios', methods=['GET'])
def api_listar_escenarios():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, descripcion, historia, activo, color, tono, instruccion FROM escenarios ORDER BY id DESC')
        rows = cursor.fetchall()
    return jsonify([{
        'id': r[0], 'nombre': r[1], 'descripcion': r[2],
        'historia': r[3] or '', 'activo': bool(r[4]), 'color': r[5] or '',
        'tono': r[6] or '', 'instruccion': r[7] or ''
    } for r in rows])


@bp.route('/api/escenario-activo', methods=['GET'])
def api_escenario_activo():
    """Devuelve el escenario activo con color para que el frontend actualice el fondo."""
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, nombre, color FROM escenarios WHERE activo=1 LIMIT 1')
        row = cursor.fetchone()
    if row:
        return jsonify({'id': row[0], 'nombre': row[1], 'color': row[2] or ''})
    return jsonify({'id': None, 'nombre': '', 'color': ''})


@bp.route('/api/escenarios', methods=['POST'])
def api_crear_escenario():
    data        = request.json
    nombre      = data.get('nombre', '').strip()
    desc        = data.get('descripcion', '').strip()
    historia    = data.get('historia', '').strip()
    color       = data.get('color', '').strip()
    tono        = data.get('tono', '').strip()
    instruccion = data.get('instruccion', '').strip()
    if not nombre or not desc:
        return jsonify({'error': 'Nombre y descripción requeridos'}), 400
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO escenarios (nombre, descripcion, historia, color, tono, instruccion) VALUES (?, ?, ?, ?, ?, ?)',
            (nombre, desc, historia, color, tono, instruccion)
        )
        eid = cursor.lastrowid
    return jsonify({'success': True, 'id': eid})


@bp.route('/api/escenarios/<int:eid>', methods=['PUT'])
def api_editar_escenario(eid):
    data        = request.json
    nombre      = data.get('nombre', '').strip()
    desc        = data.get('descripcion', '').strip()
    historia    = data.get('historia', '').strip()
    color       = data.get('color', '').strip()
    tono        = data.get('tono', '').strip()
    instruccion = data.get('instruccion', '').strip()
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE escenarios SET nombre=?, descripcion=?, historia=?, color=?, tono=?, instruccion=? WHERE id=?',
            (nombre, desc, historia, color, tono, instruccion, eid)
        )
    return jsonify({'success': True})


@bp.route('/api/escenarios/<int:eid>/activar', methods=['POST'])
def api_activar_escenario(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE escenarios SET activo=0')
        color, nombre_esc = '', ''
        if eid != 0:
            cursor.execute('UPDATE escenarios SET activo=1 WHERE id=?', (eid,))
            cursor.execute('SELECT nombre, color FROM escenarios WHERE id=?', (eid,))
            row = cursor.fetchone()
            if row:
                nombre_esc, color = row[0], row[1] or ''
    return jsonify({'success': True, 'nombre': nombre_esc, 'color': color})


@bp.route('/api/escenarios/<int:eid>', methods=['DELETE'])
def api_eliminar_escenario(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM escenarios WHERE id=?', (eid,))
    return jsonify({'success': True})


@bp.route('/api/escenarios/<int:eid>/memorias', methods=['GET'])
def api_memorias_escenario(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT nombre FROM escenarios WHERE id=?', (eid,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Escenario no encontrado'}), 404
        cursor.execute('''SELECT id, fecha, resumen, emocion_detectada, temas
            FROM memoria_episodica WHERE escenario_id=? AND resumen IS NOT NULL
            ORDER BY fecha DESC LIMIT 20''', (eid,))
        eps = cursor.fetchall()
    return jsonify({
        'nombre': row[0], 'total': len(eps),
        'episodios': [{'id': r[0], 'fecha': r[1], 'resumen': r[2],
                       'emocion': r[3], 'temas': json.loads(r[4]) if r[4] else []} for r in eps]
    })


@bp.route('/api/escenarios/generar', methods=['POST'])
def api_generar_escenario_ia():
    """Genera descripción e historia de un escenario con IA."""
    data   = request.json
    nombre = data.get('nombre', '').strip()
    idea   = data.get('idea', '').strip()
    if not nombre or not idea:
        return jsonify({'error': 'Nombre e idea requeridos'}), 400

    nombre_personaje = 'el personaje'
    try:
        p = paths()
        with open(p['json'], 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        nombre_personaje = pdata['data'].get('name', 'el personaje')
    except Exception:
        pass

    prompt = f"""Estás creando un escenario para un chat de roleplay entre "{nombre_personaje}" y el usuario.

Nombre del escenario: "{nombre}"
Idea del usuario: "{idea}"

Generá CUATRO cosas:

1. DESCRIPCION (2-3 oraciones): El ambiente físico. Qué se ve, qué se siente, qué se huele.
   Presente, evocador, sensorial. Sin mencionar a los personajes.

2. HISTORIA (3-5 oraciones): Qué significa este lugar para los dos. Qué pasó aquí,
   qué recuerdos tiene, por qué es especial. Puede incluir un momento clave que vivieron juntos.

3. TONO (2-5 palabras): El tono emocional del escenario. Ejemplos: "oscuro y melancólico",
   "íntimo y cálido", "tenso y misterioso", "alegre y desenfadado".

4. INSTRUCCION (1-2 oraciones): Una instrucción concisa para el personaje sobre cómo
   comportarse o qué detalles ambientales mencionar en este lugar.

Respondé SOLO con JSON:
{{"descripcion": "...", "historia": "...", "tono": "...", "instruccion": "..."}}"""

    try:
        resp = llamada_mistral_segura(
            model="mistral-small-latest",
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=400
        )
        contenido = resp.choices[0].message.content.strip()
        match = re.search(r'\{[\s\S]*\}', contenido)
        resultado = json.loads(match.group(0) if match else contenido)
        return jsonify({'success': True,
                        'descripcion':  resultado.get('descripcion', ''),
                        'historia':     resultado.get('historia', ''),
                        'tono':         resultado.get('tono', ''),
                        'instruccion':  resultado.get('instruccion', '')})
    except Exception as e:
        print(f"❌ Error generando escenario: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 15: EVENTOS (con campo historia)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/eventos', methods=['GET'])
def api_listar_eventos():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('''SELECT id, nombre, descripcion, historia, tipo, valor,
                         activo, disparado, hora, aviso_dias, seguimiento,
                         aviso_disparado, seguimiento_disparado
                         FROM eventos ORDER BY id DESC''')
        rows = cursor.fetchall()
    return jsonify([{
        'id': r[0], 'nombre': r[1], 'descripcion': r[2], 'historia': r[3] or '',
        'tipo': r[4], 'valor': r[5] or '', 'activo': bool(r[6]), 'disparado': bool(r[7]),
        'hora': r[8] or '', 'aviso_dias': int(r[9] or 0), 'seguimiento': r[10] or '',
        'aviso_disparado': bool(r[11]), 'seguimiento_disparado': bool(r[12]),
    } for r in rows])


@bp.route('/api/eventos', methods=['POST'])
def api_crear_evento():
    data        = request.json
    nombre      = data.get('nombre', '').strip()
    desc        = data.get('descripcion', '').strip()
    historia    = data.get('historia', '').strip()
    tipo        = data.get('tipo', 'manual')
    valor       = data.get('valor') or None
    hora        = (data.get('hora') or '').strip() or None
    aviso_dias  = int(data.get('aviso_dias') or 0)
    seguimiento = (data.get('seguimiento') or '').strip() or None
    if not nombre or not desc:
        return jsonify({'error': 'Nombre y descripción requeridos'}), 400
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO eventos (nombre, descripcion, historia, tipo, valor, hora, aviso_dias, seguimiento) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
            (nombre, desc, historia, tipo, valor, hora, aviso_dias, seguimiento)
        )
        eid = cursor.lastrowid
    return jsonify({'success': True, 'id': eid})


@bp.route('/api/eventos/generar', methods=['POST'])
def api_generar_evento_ia():
    """Genera descripción e historia de un evento con IA."""
    data   = request.json
    nombre = data.get('nombre', '').strip()
    idea   = data.get('idea', '').strip()
    if not nombre or not idea:
        return jsonify({'error': 'Nombre e idea requeridos'}), 400

    nombre_personaje = 'el personaje'
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        nombre_personaje = pdata['data'].get('name', 'el personaje')
    except Exception:
        pass

    prompt = f"""Estás creando un evento especial para un chat de roleplay entre "{nombre_personaje}" y el usuario.

Nombre del evento: "{nombre}"
Idea del usuario: "{idea}"

Generá DOS cosas:

1. DESCRIPCION (1-2 oraciones): Qué es este evento. Concreto y directo.

2. HISTORIA (3-4 oraciones): Cómo fue ese momento. Qué pasó, cómo se sintieron,
   qué detalle lo hace inolvidable. Escribí con emoción y especificidad.

Respondé SOLO con JSON:
{{"descripcion": "...", "historia": "..."}}"""

    try:
        resp = llamada_mistral_segura(
            model="mistral-small-latest",
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300
        )
        contenido = resp.choices[0].message.content.strip()
        match = re.search(r'\{[\s\S]*\}', contenido)
        resultado = json.loads(match.group(0) if match else contenido)
        return jsonify({'success': True, 'descripcion': resultado.get('descripcion',''),
                        'historia': resultado.get('historia','')})
    except Exception as e:
        print(f"❌ Error generando evento: {e}")
        return jsonify({'error': str(e)}), 500


@bp.route('/api/eventos/<int:eid>/disparar', methods=['POST'])
def api_disparar_evento(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE eventos SET disparado=1, fecha_disparo=? WHERE id=?',
                       (now_argentina().isoformat(), eid))
        cursor.execute('SELECT nombre, descripcion FROM eventos WHERE id=?', (eid,))
        row = cursor.fetchone()
    if row:
        return jsonify({'success': True, 'nombre': row[0], 'descripcion': row[1]})
    return jsonify({'error': 'Evento no encontrado'}), 404


@bp.route('/api/eventos/<int:eid>/resetear', methods=['POST'])
def api_resetear_evento(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE eventos SET disparado=0, fecha_disparo=NULL, aviso_disparado=0, seguimiento_disparado=0 WHERE id=?',
            (eid,)
        )
    return jsonify({'success': True})


@bp.route('/api/eventos/<int:eid>', methods=['DELETE'])
def api_eliminar_evento(eid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM eventos WHERE id=?', (eid,))
    return jsonify({'success': True})


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 15b: OBJETOS (ítems con propiedades para el roleplay)
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/objetos', methods=['GET'])
def api_listar_objetos():
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, nombre, descripcion, propiedades, estado, poseedor, activo '
            'FROM objetos ORDER BY activo DESC, id DESC'
        )
        rows = cursor.fetchall()
    return jsonify([{
        'id'         : r[0],
        'nombre'     : r[1],
        'descripcion': r[2],
        'propiedades': r[3],
        'estado'     : r[4] or '',
        'poseedor'   : r[5] or 'usuario',
        'activo'     : bool(r[6]),
    } for r in rows])



@bp.route('/api/objetos', methods=['POST'])
def api_crear_objeto():
    data     = request.json
    nombre   = data.get('nombre', '').strip()
    desc     = data.get('descripcion', '').strip()
    props    = data.get('propiedades', '').strip()
    poseedor = data.get('poseedor', 'usuario').strip()
    estado   = data.get('estado', '').strip()
    if not nombre or not desc or not props:
        return jsonify({'error': 'Nombre, descripción y propiedades son requeridos'}), 400
    if poseedor not in ('usuario', 'personaje'):
        poseedor = 'usuario'
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO objetos (nombre, descripcion, propiedades, estado, poseedor) VALUES (?, ?, ?, ?, ?)',
            (nombre, desc, props, estado, poseedor)
        )
        oid = cursor.lastrowid
    return jsonify({'success': True, 'id': oid})


@bp.route('/api/objetos/<int:oid>', methods=['PUT'])
def api_editar_objeto(oid):
    data     = request.json
    nombre   = data.get('nombre', '').strip()
    desc     = data.get('descripcion', '').strip()
    props    = data.get('propiedades', '').strip()
    poseedor = data.get('poseedor', 'usuario').strip()
    estado   = data.get('estado', '').strip()
    activo   = int(data.get('activo', 1))
    if poseedor not in ('usuario', 'personaje'):
        poseedor = 'usuario'
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute(
            'UPDATE objetos SET nombre=?, descripcion=?, propiedades=?, estado=?, poseedor=?, activo=? WHERE id=?',
            (nombre, desc, props, estado, poseedor, activo, oid)
        )
    return jsonify({'success': True})



@bp.route('/api/objetos/<int:oid>/toggle', methods=['POST'])
def api_toggle_objeto(oid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT activo FROM objetos WHERE id=?', (oid,))
        row = cursor.fetchone()
        if not row:
            return jsonify({'error': 'Objeto no encontrado'}), 404
        nuevo = 0 if row[0] else 1
        cursor.execute('UPDATE objetos SET activo=? WHERE id=?', (nuevo, oid))
    return jsonify({'success': True, 'activo': bool(nuevo)})


@bp.route('/api/objetos/<int:oid>', methods=['DELETE'])
def api_eliminar_objeto(oid):
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM objetos WHERE id=?', (oid,))
    return jsonify({'success': True})


@bp.route('/api/objetos/generar', methods=['POST'])
def api_generar_objeto_ia():
    """Genera descripción y propiedades de un objeto con IA."""
    data   = request.json
    nombre = data.get('nombre', '').strip()
    idea   = data.get('idea', '').strip()
    if not nombre or not idea:
        return jsonify({'error': 'Nombre e idea requeridos'}), 400

    nombre_personaje = 'el personaje'
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            pdata = json.load(f)
        nombre_personaje = pdata['data'].get('name', 'el personaje')
    except Exception:
        pass

    prompt = f"""Estás creando un objeto para un roleplay entre "{nombre_personaje}" y el usuario.

Nombre del objeto: "{nombre}"
Idea del usuario: "{idea}"

Generá DOS cosas:

1. DESCRIPCION (1-2 oraciones): Cómo se ve, qué se siente al tocarlo. Concreto y sensorial.

2. PROPIEDADES (2-4 oraciones): Qué puede hacer exactamente, sus reglas, sus límites o condiciones.
   Sé específico: "puede explotar objetos tocándolos, pero necesita 10 minutos para recargarse",
   "tiene exactamente 3 balas y no acepta recarga", etc.

Respondé SOLO con JSON:
{{"descripcion": "...", "propiedades": "..."}}"""

    try:
        resp = llamada_mistral_segura(
            model="mistral-small-latest",
            messages=[{'role': 'user', 'content': prompt}],
            max_tokens=300
        )
        contenido = resp.choices[0].message.content.strip()
        match = re.search(r'\{[\s\S]*\}', contenido)
        resultado = json.loads(match.group(0) if match else contenido)
        return jsonify({'success': True,
                        'descripcion': resultado.get('descripcion', ''),
                        'propiedades': resultado.get('propiedades', '')})
    except Exception as e:
        print(f"❌ Error generando objeto: {e}")
        return jsonify({'error': str(e)}), 500


# ─────────────────────────────────────────────────────────────────────────────
# SECCIÓN 16: EXPORTAR / IMPORTAR CHAT Y MEMORIA
# ─────────────────────────────────────────────────────────────────────────────

@bp.route('/api/exportar/chat', methods=['GET'])
def exportar_chat():
    """Exporta el historial completo como JSON descargable."""
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, rol, contenido, timestamp FROM mensajes ORDER BY id ASC')
        mensajes = [{'id': r[0], 'rol': r[1], 'contenido': r[2], 'timestamp': r[3]} for r in cursor.fetchall()]
    pid    = get_personaje_activo_id()
    nombre = pid
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            nombre = json.load(f).get('data', {}).get('name', pid)
    except Exception:
        pass
    export = {
        'version'  : '1.0',
        'tipo'     : 'chat',
        'personaje': nombre,
        'exportado': now_argentina().isoformat(),
        'mensajes' : mensajes,
    }
    return Response(
        json.dumps(export, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="chat_{nombre}_{now_argentina().strftime("%Y%m%d")}.json"'}
    )


@bp.route('/api/exportar/memoria', methods=['GET'])
def exportar_memoria():
    """Exporta memoria permanente + síntesis como JSON descargable."""
    with _get_conn(paths()['db']) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT id, categoria, clave, valor, contexto, confianza, fecha_aprendido FROM memoria_permanente ORDER BY categoria, id')
        hechos = [{'id': r[0], 'categoria': r[1], 'clave': r[2], 'valor': r[3],
                   'contexto': r[4], 'confianza': r[5], 'fecha_aprendido': r[6]} for r in cursor.fetchall()]
        cursor.execute('SELECT id, categoria, titulo, contenido FROM sintesis_conocimiento ORDER BY categoria')
        sintesis = [{'id': r[0], 'categoria': r[1], 'titulo': r[2], 'contenido': r[3]} for r in cursor.fetchall()]
    pid    = get_personaje_activo_id()
    nombre = pid
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            nombre = json.load(f).get('data', {}).get('name', pid)
    except Exception:
        pass
    export = {
        'version'  : '1.0',
        'tipo'     : 'memoria',
        'personaje': nombre,
        'exportado': now_argentina().isoformat(),
        'hechos'   : hechos,
        'sintesis' : sintesis,
    }
    return Response(
        json.dumps(export, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="memoria_{nombre}_{now_argentina().strftime("%Y%m%d")}.json"'}
    )


@bp.route('/api/importar/chat', methods=['POST'])
def importar_chat():
    """Importa un historial de chat exportado previamente. Añade al existente."""
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se recibió archivo'}), 400
    try:
        data = json.loads(request.files['archivo'].read().decode('utf-8'))
        if data.get('tipo') != 'chat':
            return jsonify({'error': 'El archivo no es un export de chat'}), 400
        mensajes = data.get('mensajes', [])
        if not mensajes:
            return jsonify({'error': 'El archivo no contiene mensajes'}), 400
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            for m in mensajes:
                cursor.execute(
                    'INSERT INTO mensajes (rol, contenido, timestamp) VALUES (?, ?, ?)',
                    (m.get('rol', 'user'), m.get('contenido', ''), m.get('timestamp', now_argentina().isoformat()))
                )
        return jsonify({'success': True, 'importados': len(mensajes)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/api/importar/memoria', methods=['POST'])
def importar_memoria():
    """Importa memoria permanente + síntesis. Los hechos existentes se actualizan por (categoria, clave)."""
    if 'archivo' not in request.files:
        return jsonify({'error': 'No se recibió archivo'}), 400
    try:
        data     = json.loads(request.files['archivo'].read().decode('utf-8'))
        if data.get('tipo') != 'memoria':
            return jsonify({'error': 'El archivo no es un export de memoria'}), 400
        hechos   = data.get('hechos', [])
        sintesis = data.get('sintesis', [])
        with _get_conn(paths()['db']) as conn:
            cursor = conn.cursor()
            for h in hechos:
                cursor.execute('''
                    INSERT INTO memoria_permanente
                    (categoria, clave, valor, contexto, confianza, fecha_aprendido, ultima_actualizacion)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(categoria, clave) DO UPDATE SET
                        valor=excluded.valor, contexto=excluded.contexto,
                        confianza=excluded.confianza, ultima_actualizacion=excluded.ultima_actualizacion
                ''', (h.get('categoria','general'), h.get('clave',''), h.get('valor',''),
                      h.get('contexto',''), h.get('confianza', 100),
                      h.get('fecha_aprendido', now_argentina().isoformat()),
                      now_argentina().isoformat()))
            for s in sintesis:
                cursor.execute('''
                    INSERT INTO sintesis_conocimiento
                    (categoria, titulo, contenido, fecha_creacion, fecha_actualizacion)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(categoria, titulo) DO UPDATE SET
                        contenido=excluded.contenido, fecha_actualizacion=excluded.fecha_actualizacion
                ''', (s.get('categoria','general'), s.get('titulo',''), s.get('contenido',''),
                      now_argentina().isoformat(), now_argentina().isoformat()))
        return jsonify({'success': True, 'hechos': len(hechos), 'sintesis': len(sintesis)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ═════════════════════════════════════════════════════════════════════════════
# EXPORTAR / IMPORTAR — por tabla y backup completo
# ═════════════════════════════════════════════════════════════════════════════

def _nombre_personaje():
    """Devuelve el nombre del personaje activo para los nombres de archivo."""
    try:
        with open(paths()['json'], 'r', encoding='utf-8') as f:
            return json.load(f).get('data', {}).get('name', get_personaje_activo_id())
    except Exception:
        return get_personaje_activo_id()

def _json_response(data, filename):
    """Devuelve un JSON descargable."""
    return Response(
        json.dumps(data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )

def _fecha():
    return now_argentina().strftime('%Y%m%d_%H%M')


# ── EXPORTAR POR TABLA ────────────────────────────────────────────────────────

@bp.route('/api/exportar/episodica', methods=['GET'])
def exportar_episodica():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT id,fecha,contenido_usuario,contenido_hiro,resumen,temas,emocion_detectada,importancia FROM memoria_episodica ORDER BY id')
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'episodica','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'filas':rows},
                          f'episodica_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/relacion', methods=['GET'])
def exportar_relacion():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM relacion')
        rel = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
        c.execute('SELECT * FROM estado_emocional ORDER BY id')
        emocional = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
        c.execute('SELECT * FROM hilos_pendientes ORDER BY id')
        hilos = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'relacion','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),
                            'relacion':rel,'estado_emocional':emocional,'hilos_pendientes':hilos},
                          f'relacion_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/escenarios', methods=['GET'])
def exportar_escenarios():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM escenarios ORDER BY id')
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'escenarios','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'filas':rows},
                          f'escenarios_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/eventos', methods=['GET'])
def exportar_eventos():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM eventos ORDER BY id')
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'eventos','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'filas':rows},
                          f'eventos_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/objetos', methods=['GET'])
def exportar_objetos():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM objetos ORDER BY id')
        objs = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
        c.execute('SELECT * FROM objetos_cambios_pendientes ORDER BY id')
        cambios = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'objetos','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),
                            'objetos':objs,'cambios_pendientes':cambios},
                          f'objetos_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/diarios', methods=['GET'])
def exportar_diarios():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM diarios_personaje ORDER BY id')
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'diarios','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'filas':rows},
                          f'diarios_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/evolucion', methods=['GET'])
def exportar_evolucion():
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        c.execute('SELECT * FROM evolucion_fases ORDER BY fase')
        rows = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
    return _json_response({'version':'1.0','tipo':'evolucion','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'filas':rows},
                          f'evolucion_{_nombre_personaje()}_{_fecha()}.json')

@bp.route('/api/exportar/completo', methods=['GET'])
def exportar_completo():
    """Backup completo de todas las tablas."""
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        tablas = ['mensajes','memoria_permanente','memoria_episodica','sintesis_conocimiento',
                  'relacion','estado_emocional','hilos_pendientes','escenarios','eventos',
                  'objetos','objetos_cambios_pendientes','diarios_personaje','evolucion_fases']
        backup = {}
        for t in tablas:
            try:
                c.execute(f'SELECT * FROM {t} ORDER BY id' if t != 'relacion' else f'SELECT * FROM {t}')
                backup[t] = [dict(zip([d[0] for d in c.description], r)) for r in c.fetchall()]
            except Exception as e:
                backup[t] = []
    return _json_response({'version':'1.0','tipo':'completo','personaje':_nombre_personaje(),'exportado':now_argentina().isoformat(),'tablas':backup},
                          f'backup_completo_{_nombre_personaje()}_{_fecha()}.json')


# ── IMPORTAR POR TABLA ────────────────────────────────────────────────────────

def _leer_archivo_json(tipo_esperado=None):
    """Lee y parsea el archivo JSON del request. Valida tipo si se especifica."""
    if 'archivo' not in request.files:
        return None, (jsonify({'error': 'No se recibió archivo'}), 400)
    try:
        data = json.loads(request.files['archivo'].read().decode('utf-8'))
    except Exception as e:
        return None, (jsonify({'error': f'JSON inválido: {e}'}), 400)
    if tipo_esperado and data.get('tipo') != tipo_esperado:
        return None, (jsonify({'error': f'Archivo incorrecto: se esperaba tipo "{tipo_esperado}", recibido "{data.get("tipo")}"'}), 400)
    return data, None

@bp.route('/api/importar/episodica', methods=['POST'])
def importar_episodica():
    data, err = _leer_archivo_json('episodica')
    if err: return err
    filas = data.get('filas', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR IGNORE INTO memoria_episodica (fecha,contenido_usuario,contenido_hiro,resumen,temas,emocion_detectada,importancia) VALUES (?,?,?,?,?,?,?)',
                      (r.get('fecha'), r.get('contenido_usuario',''), r.get('contenido_hiro',''),
                       r.get('resumen',''), r.get('temas',''), r.get('emocion_detectada',''), r.get('importancia',5)))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/relacion', methods=['POST'])
def importar_relacion():
    data, err = _leer_archivo_json('relacion')
    if err: return err
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in data.get('relacion', []):
            c.execute('INSERT OR REPLACE INTO relacion (id,fase,nivel_confianza,nivel_intimidad,dias_juntos,primer_mensaje,ultimo_mensaje,temas_frecuentes) VALUES (?,?,?,?,?,?,?,?)',
                      (r.get('id',1), r.get('fase',1), r.get('nivel_confianza',0), r.get('nivel_intimidad',0),
                       r.get('dias_juntos',0), r.get('primer_mensaje'), r.get('ultimo_mensaje'), r.get('temas_frecuentes')))
        for r in data.get('hilos_pendientes', []):
            c.execute('INSERT OR IGNORE INTO hilos_pendientes (pregunta,tema,importancia,resuelto,fecha) VALUES (?,?,?,?,?)',
                      (r.get('pregunta',''), r.get('tema',''), r.get('importancia',3), r.get('resuelto',0), r.get('fecha')))
    return jsonify({'success': True})

@bp.route('/api/importar/escenarios', methods=['POST'])
def importar_escenarios():
    data, err = _leer_archivo_json('escenarios')
    if err: return err
    filas = data.get('filas', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR IGNORE INTO escenarios (nombre,descripcion,historia,tono,instruccion,color,activo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?)',
                      (r.get('nombre',''), r.get('descripcion',''), r.get('historia',''),
                       r.get('tono',''), r.get('instruccion',''), r.get('color',''),
                       r.get('activo',0), r.get('fecha_creacion')))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/eventos', methods=['POST'])
def importar_eventos():
    data, err = _leer_archivo_json('eventos')
    if err: return err
    filas = data.get('filas', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR IGNORE INTO eventos (nombre,descripcion,historia,tipo,valor,keyword,activo,disparado,consumido,turns_after_fire,duracion_activa,fecha_disparo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                      (r.get('nombre',''), r.get('descripcion',''), r.get('historia',''), r.get('tipo',''),
                       r.get('valor',''), r.get('keyword',''), r.get('activo',1), r.get('disparado',0),
                       r.get('consumido',0), r.get('turns_after_fire',0), r.get('duracion_activa',6),
                       r.get('fecha_disparo'), r.get('fecha_creacion')))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/objetos', methods=['POST'])
def importar_objetos():
    data, err = _leer_archivo_json('objetos')
    if err: return err
    filas = data.get('objetos', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR IGNORE INTO objetos (nombre,descripcion,propiedades,estado,poseedor,escenario_id,keyword,activo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?)',
                      (r.get('nombre',''), r.get('descripcion',''), r.get('propiedades',''),
                       r.get('estado',''), r.get('poseedor','usuario'), r.get('escenario_id'),
                       r.get('keyword',''), r.get('activo',1), r.get('fecha_creacion')))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/diarios', methods=['POST'])
def importar_diarios():
    data, err = _leer_archivo_json('diarios')
    if err: return err
    filas = data.get('filas', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR IGNORE INTO diarios_personaje (titulo,contenido,fecha,auto) VALUES (?,?,?,?)',
                      (r.get('titulo',''), r.get('contenido',''), r.get('fecha'), r.get('auto',0)))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/evolucion', methods=['POST'])
def importar_evolucion():
    data, err = _leer_archivo_json('evolucion')
    if err: return err
    filas = data.get('filas', [])
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        for r in filas:
            c.execute('INSERT OR REPLACE INTO evolucion_fases (fase,descripcion,personalidad,fecha_actualizacion) VALUES (?,?,?,?)',
                      (r.get('fase'), r.get('descripcion',''), r.get('personalidad',''), r.get('fecha_actualizacion')))
    return jsonify({'success': True, 'importados': len(filas)})

@bp.route('/api/importar/completo', methods=['POST'])
def importar_completo():
    """Restaura un backup completo. Inserta sin reemplazar (OR IGNORE) para no romper datos existentes."""
    data, err = _leer_archivo_json('completo')
    if err: return err
    tablas = data.get('tablas', {})
    totales = {}
    with _get_conn(paths()['db']) as conn:
        c = conn.cursor()
        # Mensajes
        for r in tablas.get('mensajes', []):
            try:
                c.execute('INSERT OR IGNORE INTO mensajes (rol,contenido,timestamp) VALUES (?,?,?)',
                          (r.get('rol','user'), r.get('contenido',''), r.get('timestamp')))
            except: pass
        totales['mensajes'] = len(tablas.get('mensajes',[]))
        # Memoria permanente
        for r in tablas.get('memoria_permanente', []):
            try:
                c.execute('INSERT OR IGNORE INTO memoria_permanente (categoria,clave,valor,confianza,contexto,fecha_aprendido,ultima_actualizacion) VALUES (?,?,?,?,?,?,?)',
                          (r.get('categoria','general'), r.get('clave',''), r.get('valor',''),
                           r.get('confianza',100), r.get('contexto',''), r.get('fecha_aprendido'), r.get('ultima_actualizacion')))
            except: pass
        totales['memoria_permanente'] = len(tablas.get('memoria_permanente',[]))
        # Síntesis
        for r in tablas.get('sintesis_conocimiento', []):
            try:
                c.execute('INSERT OR IGNORE INTO sintesis_conocimiento (categoria,titulo,contenido,fecha_creacion,fecha_actualizacion) VALUES (?,?,?,?,?)',
                          (r.get('categoria','general'), r.get('titulo',''), r.get('contenido',''),
                           r.get('fecha_creacion'), r.get('fecha_actualizacion')))
            except: pass
        totales['sintesis_conocimiento'] = len(tablas.get('sintesis_conocimiento',[]))
        # Episódica
        for r in tablas.get('memoria_episodica', []):
            try:
                c.execute('INSERT OR IGNORE INTO memoria_episodica (fecha,contenido_usuario,contenido_hiro,resumen,temas,emocion_detectada,importancia) VALUES (?,?,?,?,?,?,?)',
                          (r.get('fecha'), r.get('contenido_usuario',''), r.get('contenido_hiro',''),
                           r.get('resumen',''), r.get('temas',''), r.get('emocion_detectada',''), r.get('importancia',5)))
            except: pass
        totales['memoria_episodica'] = len(tablas.get('memoria_episodica',[]))
        # Relación
        for r in tablas.get('relacion', []):
            try:
                c.execute('INSERT OR REPLACE INTO relacion (id,fase,nivel_confianza,nivel_intimidad,dias_juntos,primer_mensaje,ultimo_mensaje,temas_frecuentes) VALUES (?,?,?,?,?,?,?,?)',
                          (r.get('id',1), r.get('fase',1), r.get('nivel_confianza',0), r.get('nivel_intimidad',0),
                           r.get('dias_juntos',0), r.get('primer_mensaje'), r.get('ultimo_mensaje'), r.get('temas_frecuentes')))
            except: pass
        # Escenarios
        for r in tablas.get('escenarios', []):
            try:
                c.execute('INSERT OR IGNORE INTO escenarios (nombre,descripcion,historia,tono,instruccion,color,activo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?)',
                          (r.get('nombre',''), r.get('descripcion',''), r.get('historia',''),
                           r.get('tono',''), r.get('instruccion',''), r.get('color',''),
                           r.get('activo',0), r.get('fecha_creacion')))
            except: pass
        totales['escenarios'] = len(tablas.get('escenarios',[]))
        # Eventos
        for r in tablas.get('eventos', []):
            try:
                c.execute('INSERT OR IGNORE INTO eventos (nombre,descripcion,historia,tipo,valor,keyword,activo,disparado,consumido,turns_after_fire,duracion_activa,fecha_disparo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                          (r.get('nombre',''), r.get('descripcion',''), r.get('historia',''), r.get('tipo',''),
                           r.get('valor',''), r.get('keyword',''), r.get('activo',1), r.get('disparado',0),
                           r.get('consumido',0), r.get('turns_after_fire',0), r.get('duracion_activa',6),
                           r.get('fecha_disparo'), r.get('fecha_creacion')))
            except: pass
        totales['eventos'] = len(tablas.get('eventos',[]))
        # Objetos
        for r in tablas.get('objetos', []):
            try:
                c.execute('INSERT OR IGNORE INTO objetos (nombre,descripcion,propiedades,estado,poseedor,escenario_id,keyword,activo,fecha_creacion) VALUES (?,?,?,?,?,?,?,?,?)',
                          (r.get('nombre',''), r.get('descripcion',''), r.get('propiedades',''),
                           r.get('estado',''), r.get('poseedor','usuario'), r.get('escenario_id'),
                           r.get('keyword',''), r.get('activo',1), r.get('fecha_creacion')))
            except: pass
        totales['objetos'] = len(tablas.get('objetos',[]))
        # Diarios
        for r in tablas.get('diarios_personaje', []):
            try:
                c.execute('INSERT OR IGNORE INTO diarios_personaje (titulo,contenido,fecha,auto) VALUES (?,?,?,?)',
                          (r.get('titulo',''), r.get('contenido',''), r.get('fecha'), r.get('auto',0)))
            except: pass
        totales['diarios_personaje'] = len(tablas.get('diarios_personaje',[]))
        # Evolución
        for r in tablas.get('evolucion_fases', []):
            try:
                c.execute('INSERT OR REPLACE INTO evolucion_fases (fase,descripcion,personalidad,fecha_actualizacion) VALUES (?,?,?,?)',
                          (r.get('fase'), r.get('descripcion',''), r.get('personalidad',''), r.get('fecha_actualizacion')))
            except: pass
        totales['evolucion_fases'] = len(tablas.get('evolucion_fases',[]))
    return jsonify({'success': True, 'totales': totales})


# ═════════════════════════════════════════════════════════════════════════════
# LIBRERÍA DE MODELOS PERSONALIZADOS
# Permite guardar y gestionar modelos propios, asignarlos a tareas
# ═════════════════════════════════════════════════════════════════════════════

@bp.route('/api/libreria/modelos', methods=['GET'])
def get_libreria_modelos():
    """Obtiene todos los modelos en la librería"""
    return jsonify(listar_modelos_libreria())


@bp.route('/api/libreria/agregar', methods=['POST'])
def agregar_modelo_libreria():
    """Agrega un modelo personalizado a la librería"""
    data = request.json or {}
    
    resultado = agregar_modelo_a_libreria(
        modelo_id=data.get('modelo_id'),
        nombre=data.get('nombre'),
        descripcion=data.get('descripcion', ''),
        proveedor=data.get('proveedor', 'openrouter'),
        tags=data.get('tags', [])
    )
    
    return jsonify(resultado)


@bp.route('/api/libreria/modelo/<path:modelo_id>', methods=['GET'])
def get_modelo_libreria(modelo_id):
    """Obtiene un modelo específico de la librería"""
    return jsonify(obtener_modelo_libreria(modelo_id))


@bp.route('/api/libreria/modelo/<path:modelo_id>', methods=['DELETE'])
def eliminar_de_libreria(modelo_id):
    """Elimina un modelo de la librería"""
    return jsonify(eliminar_modelo_libreria(modelo_id))


@bp.route('/api/libreria/asignaciones', methods=['GET'])
def get_asignaciones():
    """Obtiene todas las asignaciones de modelos a tareas"""
    return jsonify(obtener_asignaciones())


@bp.route('/api/libreria/asignar', methods=['POST'])
def asignar_tarea():
    """Asigna un modelo a una tarea específica"""
    data = request.json or {}
    tarea     = data.get('tarea')
    modelo_id = data.get('modelo_id')

    if not tarea or not modelo_id:
        return jsonify({'error': 'Faltan parámetros: tarea y modelo_id son obligatorios'}), 400

    resultado = asignar_modelo_a_tarea(tarea=tarea, modelo_id=modelo_id)
    return jsonify(resultado)


@bp.route('/api/libreria/tarea/<tarea>', methods=['GET'])
def get_modelo_tarea(tarea):
    """Obtiene el modelo asignado a una tarea"""
    resultado = obtener_modelo_para_tarea(tarea)
    return jsonify(resultado)


@bp.route('/api/libreria/buscar', methods=['GET'])
def buscar_libreria():
    """Busca modelos en la librería por query"""
    query = request.args.get('q', '')
    return jsonify(buscar_modelos_libreria(query))


@bp.route('/api/libreria/tag/<tag>', methods=['GET'])
def get_modelos_por_tag(tag):
    """Filtra modelos por tag"""
    return jsonify(filtrar_modelos_por_tag(tag))


@bp.route('/api/libreria/tareas', methods=['GET'])
def get_tareas_disponibles():
    """Obtiene la lista de tareas disponibles"""
    return jsonify({
        'ok': True,
        'tareas': TAREAS_DISPONIBLES,
        'total': len(TAREAS_DISPONIBLES)
    })
    
# ─────────────────────────────────────────────────────────────────────────────
# EXPRESIONES — almacenadas en JSON dentro de la carpeta del personaje
# Estructura: data/personajes/{pid}/expresiones/expresiones.json
#             data/personajes/{pid}/expresiones/1.jpg   (imágenes)
# ─────────────────────────────────────────────────────────────────────────────

def _expresiones_dir():
    """Devuelve la ruta absoluta de la carpeta de expresiones del personaje activo."""
    pid = get_personaje_activo_id()
    d = os.path.abspath(os.path.join('./data/personajes', pid, 'expresiones'))
    os.makedirs(d, exist_ok=True)
    return d

def _expresiones_json_path():
    return os.path.join(_expresiones_dir(), 'expresiones.json')

def _leer_expresiones():
    """Lee el JSON de expresiones. Devuelve lista vacía si no existe."""
    p = _expresiones_json_path()
    if not os.path.exists(p):
        return []
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _guardar_expresiones(lista):
    """Guarda la lista de expresiones en el JSON."""
    with open(_expresiones_json_path(), 'w', encoding='utf-8') as f:
        json.dump(lista, f, ensure_ascii=False, indent=2)

def _siguiente_id(lista):
    """Genera el próximo ID entero libre."""
    return max((e['id'] for e in lista), default=0) + 1

def _imagen_existe(expr):
    """Verifica si la imagen de una expresión existe en disco."""
    if not expr.get('imagen'):
        return False
    ruta = os.path.join(_expresiones_dir(), expr['imagen'])
    return os.path.exists(ruta)


@bp.route('/expresiones')
def pagina_expresiones():
    return render_template('expresiones.html')


@bp.route('/api/expresiones', methods=['GET'])
def api_listar_expresiones():
    lista = _leer_expresiones()
    result = []
    for e in lista:
        result.append({
            'id'          : e['id'],
            'nombre'      : e['nombre'],
            'patrones'    : e.get('patrones', []),
            'tiene_imagen': _imagen_existe(e),
            'es_default'  : bool(e.get('es_default', False)),
        })
    return jsonify(result)


@bp.route('/api/expresiones', methods=['POST'])
def api_crear_expresion():
    nombre     = request.form.get('nombre', '').strip()
    es_default = request.form.get('es_default', '0') == '1'
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400

    try:
        patrones = json.loads(request.form.get('patrones', '[]'))
    except Exception:
        patrones = []

    lista = _leer_expresiones()
    nuevo_id = _siguiente_id(lista)

    # Guardar imagen si viene
    imagen_nombre = None
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file and file.filename:
            ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.jpg'
            imagen_nombre = f'{nuevo_id}{ext}'
            file.save(os.path.join(_expresiones_dir(), imagen_nombre))

    # Si es default, quitar default de los demás
    if es_default:
        for e in lista:
            e['es_default'] = False

    lista.append({
        'id'        : nuevo_id,
        'nombre'    : nombre,
        'patrones'  : patrones,
        'imagen'    : imagen_nombre,
        'es_default': es_default,
    })
    _guardar_expresiones(lista)
    return jsonify({'success': True, 'id': nuevo_id})


@bp.route('/api/expresiones/<int:eid>', methods=['PUT'])
def api_editar_expresion(eid):
    nombre     = request.form.get('nombre', '').strip()
    es_default = request.form.get('es_default', '0') == '1'
    if not nombre:
        return jsonify({'error': 'Nombre requerido'}), 400

    try:
        patrones = json.loads(request.form.get('patrones', '[]'))
    except Exception:
        patrones = []

    lista = _leer_expresiones()
    idx = next((i for i, e in enumerate(lista) if e['id'] == eid), None)
    if idx is None:
        return jsonify({'error': 'No encontrado'}), 404

    # Guardar nueva imagen si viene
    if 'imagen' in request.files:
        file = request.files['imagen']
        if file and file.filename:
            # Borrar imagen anterior si existe
            img_ant = lista[idx].get('imagen')
            if img_ant:
                try:
                    os.remove(os.path.join(_expresiones_dir(), img_ant))
                except Exception:
                    pass
            ext = os.path.splitext(secure_filename(file.filename))[1].lower() or '.jpg'
            imagen_nombre = f'{eid}{ext}'
            file.save(os.path.join(_expresiones_dir(), imagen_nombre))
            lista[idx]['imagen'] = imagen_nombre

    if es_default:
        for e in lista:
            e['es_default'] = False

    lista[idx].update({
        'nombre'    : nombre,
        'patrones'  : patrones,
        'es_default': es_default,
    })
    _guardar_expresiones(lista)
    return jsonify({'success': True})


@bp.route('/api/expresiones/<int:eid>', methods=['DELETE'])
def api_eliminar_expresion(eid):
    lista = _leer_expresiones()
    idx = next((i for i, e in enumerate(lista) if e['id'] == eid), None)
    if idx is None:
        return jsonify({'error': 'No encontrado'}), 404

    # Borrar imagen del disco
    img = lista[idx].get('imagen')
    if img:
        try:
            os.remove(os.path.join(_expresiones_dir(), img))
        except Exception:
            pass

    lista.pop(idx)
    _guardar_expresiones(lista)
    return jsonify({'success': True})


@bp.route('/api/expresiones/<int:eid>/default', methods=['POST'])
def api_set_default_expresion(eid):
    lista = _leer_expresiones()
    for e in lista:
        e['es_default'] = (e['id'] == eid)
    _guardar_expresiones(lista)
    return jsonify({'success': True})


@bp.route('/api/expresiones/<int:eid>/imagen', methods=['GET'])
def api_imagen_expresion(eid):
    lista = _leer_expresiones()
    expr  = next((e for e in lista if e['id'] == eid), None)
    if not expr or not expr.get('imagen'):
        return '', 404

    ruta = os.path.join(_expresiones_dir(), expr['imagen'])
    ruta = os.path.abspath(ruta)
    if not os.path.exists(ruta):
        print(f'[EXPR] 404 — no existe: {ruta}')
        return '', 404

    ext  = os.path.splitext(ruta)[1].lower()
    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
            '.png': 'image/png',  '.gif':  'image/gif',
            '.webp': 'image/webp'}.get(ext, 'image/jpeg')

    # Leer y devolver directamente — más confiable que send_file
    # porque garantiza el Content-Type sin depender de mimetypes del SO
    try:
        with open(ruta, 'rb') as f:
            data = f.read()
        print(f'[EXPR] OK — {ruta} ({len(data)} bytes, {mime})')
        return Response(
            data,
            mimetype=mime,
            headers={'Cache-Control': 'no-cache, no-store'}
        )
    except Exception as e:
        print(f'[EXPR] ERROR leyendo {ruta}: {e}')
        return '', 500


// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_API_MANAGER.JS — Gestor de APIs
// Multi-proveedor: Mistral, OpenRouter, OpenAI, Cohere, Jina, Ollama
// ═══════════════════════════════════════════════════════════════════════════

// Dimensiones conocidas por modelo de embedding
const EMBEDDING_DIMS = {
    'mistral-embed':               1024,
    'text-embedding-3-small':      1536,
    'text-embedding-3-large':      3072,
    'text-embedding-ada-002':      1536,
    'embed-multilingual-v3.0':     1024,
    'embed-english-v3.0':          1024,
    'jina-embeddings-v3':          1024,
    'jina-embeddings-v2-base-es':   768,
    'mxbai-embed-large':           1024,
    'nomic-embed-text':             768,
    'all-minilm':                   384,
};
const MISTRAL_EMBED_DIM = 1024;

// ─────────────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    console.log('🔧 Inicializando Gestor de APIs...');
    await cargarModelosEnDropdowns();
    await loadConfig();
    updateStatusIndicators();
    adjustPaddingForFooter();
});

window.addEventListener('resize', adjustPaddingForFooter);

function adjustPaddingForFooter() {
    const footer = document.querySelector('.api-footer');
    const container = document.querySelector('.api-container');
    if (footer && container) {
        container.style.paddingBottom = footer.offsetHeight + 'px';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ALERTA DE DIMENSIONES DE EMBEDDING
// ─────────────────────────────────────────────────────────────────────────────

function actualizarOpcionesEmbedding() {
    const provider = document.getElementById('embedding-provider')?.value;
    const select   = document.getElementById('model-embeddings');
    const warning  = document.getElementById('embedding-dim-warning');
    if (!select || !warning) return;

    const modelo = select.value;
    const dims   = EMBEDDING_DIMS[modelo] ?? null;
    const diferente = dims !== null && dims !== MISTRAL_EMBED_DIM;

    warning.style.display = diferente ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
    const sel = document.getElementById('model-embeddings');
    if (sel) sel.addEventListener('change', actualizarOpcionesEmbedding);
});

// ═══════════════════════════════════════════════════════════════════════════
// CARGAR MODELOS DINÁMICAMENTE EN DROPDOWNS
// ═══════════════════════════════════════════════════════════════════════════

async function cargarModelosEnDropdowns() {
    console.log('📥 Cargando modelos dinámicamente en dropdowns...');
    try {
        const response = await fetch('/api/models/all-for-tasks');
        const data = await response.json();
        if (!data.ok) { console.warn('⚠️ Error cargando modelos:', data.error); return; }

        const modelos = data.modelos || [];
        const taskSelects = ['model-chat', 'model-extraction', 'model-synthesis', 'model-generation', 'model-enrichment'];

        for (const selectId of taskSelects) {
            const select = document.getElementById(selectId);
            if (!select) continue;

            const optionsExistentes = new Set(Array.from(select.querySelectorAll('option')).map(o => o.value));

            modelos.forEach(m => {
                if (!optionsExistentes.has(m.id) && m.es_libreria) {
                    const option = document.createElement('option');
                    option.value = m.id;
                    option.textContent = `${m.nombre} (${m.proveedor}) 📚`;
                    option.setAttribute('data-libreria', 'true');
                    select.appendChild(option);
                }
            });
        }
    } catch (error) {
        console.error('❌ Error cargando modelos en dropdowns:', error);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GESTIÓN DE TABS
// ─────────────────────────────────────────────────────────────────────────────

function switchTab(tabName) {
    if (!tabName) return;
    const tabElement = document.getElementById(`tab-${tabName}`);
    if (!tabElement) { console.error(`No se encontró tab-${tabName}`); return; }

    document.querySelectorAll('.api-tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.api-tab-btn').forEach(btn => btn.classList.remove('active'));

    document.getElementById(`tab-${tabName}`)?.classList.add('active');
    document.querySelector(`[data-tab="${tabName}"]`)?.classList.add('active');

    if (window.innerWidth <= 768) {
        document.querySelector(`.api-tab-btn.active`)?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    }

    if (tabName === 'libreria') {
        setTimeout(() => cargarLibreria(), 100);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PROVIDERS
// ─────────────────────────────────────────────────────────────────────────────

function toggleProvider(provider) {
    const checkbox = document.getElementById(`${provider}-enabled`);
    const keyInput = document.getElementById(`${provider}-key`);

    if (keyInput && checkbox.checked && !keyInput.value) {
        keyInput.focus();
        showToast(`⚠️ Ingresa la API Key para ${provider}`, 'error');
    }
    saveConfig();
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTRASEÑAS
// ─────────────────────────────────────────────────────────────────────────────

function togglePasswordField(fieldId) {
    const field = document.getElementById(fieldId);
    field.type = field.type === 'password' ? 'text' : 'password';
}

// ─────────────────────────────────────────────────────────────────────────────
// SENSIBILIDAD NSFW
// ─────────────────────────────────────────────────────────────────────────────

function updateSensitivityLabel(slider) {
    const value = parseInt(slider.value);
    const labels = [
        'Sensibilidad muy baja: Solo detecta contenido extremadamente explícito',
        'Sensibilidad baja: Detecta referencias sexuales muy claras',
        'Sensibilidad media: Detecta referencias explícitas claras',
        'Sensibilidad alta: Detecta alusiones sexuales moderadas',
        'Sensibilidad muy alta: Detecta cualquier referencia a temas adultos'
    ];
    document.getElementById('sensitivity-hint').textContent = labels[value - 1];
    saveConfig();
}

// ─────────────────────────────────────────────────────────────────────────────
// GUARDAR CONFIG — incluye todos los proveedores nuevos
// ─────────────────────────────────────────────────────────────────────────────

function _val(id, fallback = '') {
    return document.getElementById(id)?.value ?? fallback;
}
function _checked(id, fallback = false) {
    const el = document.getElementById(id);
    return el ? el.checked : fallback;
}

async function saveConfig() {
    try {
        const config = {
            // ── Proveedores de chat/LLM ──────────────────────────────────
            mistral: {
                enabled:  _checked('mistral-enabled'),
                apiKey:   _val('mistral-key'),
                endpoint: _val('mistral-endpoint') || 'https://api.mistral.ai/v1',
                rpmLimit: parseInt(_val('mistral-rpm-limit')) || 30
            },
            openrouter: {
                enabled: _checked('openrouter-enabled'),
                apiKey:  _val('openrouter-key'),
                rpmLimit: parseInt(_val('openrouter-rpm-limit')) || 60
            },
            // ── Proveedores de embeddings ─────────────────────────────────
            openai: {
                enabled:  _checked('openai-enabled'),
                apiKey:   _val('openai-key'),
                endpoint: _val('openai-endpoint') || 'https://api.openai.com/v1',
                rpmLimit: 60
            },
            cohere: {
                enabled: _checked('cohere-enabled'),
                apiKey:  _val('cohere-key'),
                rpmLimit: 100
            },
            jina: {
                enabled: _checked('jina-enabled'),
                apiKey:  _val('jina-key'),
                rpmLimit: 60
            },
            ollama: {
                enabled:  _checked('ollama-enabled'),
                endpoint: _val('ollama-endpoint') || 'http://localhost:11434',
                rpmLimit: 999
            },
            // ── Modelos por tarea ─────────────────────────────────────────
            models: {
                chat:               _val('model-chat'),
                embeddings:         _val('model-embeddings'),
                embedding_provider: _val('embedding-provider'),
                extraction:         _val('model-extraction'),
                synthesis:          _val('model-synthesis'),
                generation:         _val('model-generation'),
                enrichment:         _val('model-enrichment')
            },
            // ── NSFW ──────────────────────────────────────────────────────
            nsfw: {
                detectionEnabled: _checked('nsfw-detection-enabled'),
                sensitivity:      parseInt(_val('nsfw-sensitivity')) || 3,
                autoSwitch:       _checked('nsfw-auto-switch', true),
                logging:          _checked('nsfw-logging', true)
            },
            // ── Fallbacks ─────────────────────────────────────────────────
            fallback: {
                enabled:           _checked('fallback-enabled', true),
                primaryProvider:   _val('fallback-primary', 'mistral'),
                secondaryProvider: _val('fallback-secondary', 'openrouter'),
                retryEnabled:      _checked('retry-count', true),
                retryAttempts:     parseInt(_val('retry-attempts')) || 3
            },
            queueEnabled: _checked('queue-enabled', true),
            // ── Búsqueda en internet ──────────────────────────────────────
            search: {
                enabled:     _checked('search-enabled', false),
                serpapi_key: _val('search-serpapi-key'),
                brave_key:   _val('search-brave-key'),
                tavily_key:  _val('search-tavily-key'),
            }
        };

        const response = await fetch('/api/config/apis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(config)
        });

        if (!response.ok) throw new Error(`Error del servidor: ${response.status}`);
        console.log('✅ Configuración guardada');
        showToast('✅ Configuración guardada correctamente', 'success');
        updateStatusIndicators();

    } catch (error) {
        console.error('❌ Error al guardar:', error);
        showToast('❌ Error al guardar configuración', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR CONFIG
// ─────────────────────────────────────────────────────────────────────────────

async function loadConfig() {
    try {
        const response = await fetch('/api/config/apis');
        if (!response.ok) throw new Error('No se pudo cargar la configuración');
        const config = await response.json();

        // ── Mistral ───────────────────────────────────────────────────────
        document.getElementById('mistral-enabled').checked  = config.mistral?.enabled || false;
        document.getElementById('mistral-key').value        = config.mistral?.apiKey || '';
        document.getElementById('mistral-endpoint').value   = config.mistral?.endpoint || 'https://api.mistral.ai/v1';
        document.getElementById('mistral-rpm-limit').value  = config.mistral?.rpmLimit || 30;

        // ── OpenRouter ────────────────────────────────────────────────────
        document.getElementById('openrouter-enabled').checked  = config.openrouter?.enabled || false;
        document.getElementById('openrouter-key').value        = config.openrouter?.apiKey || '';
        document.getElementById('openrouter-rpm-limit').value  = config.openrouter?.rpmLimit || 60;

        // ── OpenAI ────────────────────────────────────────────────────────
        if (document.getElementById('openai-enabled'))
            document.getElementById('openai-enabled').checked = config.openai?.enabled || false;
        if (document.getElementById('openai-key'))
            document.getElementById('openai-key').value = config.openai?.apiKey || '';
        if (document.getElementById('openai-endpoint'))
            document.getElementById('openai-endpoint').value = config.openai?.endpoint || 'https://api.openai.com/v1';

        // ── Cohere ────────────────────────────────────────────────────────
        if (document.getElementById('cohere-enabled'))
            document.getElementById('cohere-enabled').checked = config.cohere?.enabled || false;
        if (document.getElementById('cohere-key'))
            document.getElementById('cohere-key').value = config.cohere?.apiKey || '';

        // ── Jina ──────────────────────────────────────────────────────────
        if (document.getElementById('jina-enabled'))
            document.getElementById('jina-enabled').checked = config.jina?.enabled || false;
        if (document.getElementById('jina-key'))
            document.getElementById('jina-key').value = config.jina?.apiKey || '';

        // ── Ollama ────────────────────────────────────────────────────────
        if (document.getElementById('ollama-enabled'))
            document.getElementById('ollama-enabled').checked = config.ollama?.enabled || false;
        if (document.getElementById('ollama-endpoint'))
            document.getElementById('ollama-endpoint').value = config.ollama?.endpoint || 'http://localhost:11434';

        // ── Modelos ───────────────────────────────────────────────────────
        document.getElementById('model-chat').value        = config.models?.chat || 'mistral-large-latest';
        document.getElementById('model-extraction').value  = config.models?.extraction || 'mistral-small-latest';
        document.getElementById('model-synthesis').value   = config.models?.synthesis || 'mistral-medium-latest';
        document.getElementById('model-generation').value  = config.models?.generation || 'mistral-medium-latest';
        document.getElementById('model-enrichment').value  = config.models?.enrichment || 'mistral-medium-latest';

        if (document.getElementById('embedding-provider'))
            document.getElementById('embedding-provider').value = config.models?.embedding_provider || 'mistral';
        if (document.getElementById('model-embeddings'))
            document.getElementById('model-embeddings').value = config.models?.embeddings || 'mistral-embed';

        // ── NSFW ──────────────────────────────────────────────────────────
        document.getElementById('nsfw-detection-enabled').checked = config.nsfw?.detectionEnabled || false;
        document.getElementById('nsfw-sensitivity').value         = config.nsfw?.sensitivity || 3;
        document.getElementById('nsfw-auto-switch').checked       = config.nsfw?.autoSwitch !== false;
        document.getElementById('nsfw-logging').checked           = config.nsfw?.logging !== false;

        // ── Fallbacks ─────────────────────────────────────────────────────
        document.getElementById('fallback-enabled').checked    = config.fallback?.enabled !== false;
        document.getElementById('fallback-primary').value      = config.fallback?.primaryProvider || 'mistral';
        document.getElementById('fallback-secondary').value    = config.fallback?.secondaryProvider || 'openrouter';
        document.getElementById('retry-count').checked         = config.fallback?.retryEnabled !== false;
        document.getElementById('retry-attempts').value        = config.fallback?.retryAttempts || 3;

        document.getElementById('queue-enabled').checked = config.queueEnabled !== false;

        // ── Búsqueda en internet ──────────────────────────────────────────
        if (document.getElementById('search-enabled'))
            document.getElementById('search-enabled').checked = config.search?.enabled || false;
        if (document.getElementById('search-serpapi-key'))
            document.getElementById('search-serpapi-key').value = config.search?.serpapi_key || '';
        if (document.getElementById('search-brave-key'))
            document.getElementById('search-brave-key').value = config.search?.brave_key || '';
        if (document.getElementById('search-tavily-key'))
            document.getElementById('search-tavily-key').value = config.search?.tavily_key || '';

        // ── Actualizar labels visuales (después de setear TODOS los campos) ──
        // IMPORTANTE: updateSensitivityLabel llama a saveConfig() internamente,
        // por eso debe ir al final — si va antes, guarda con los campos de
        // búsqueda vacíos y sobreescribe las API keys cada vez que se carga la página.
        updateSensitivityLabel(document.getElementById('nsfw-sensitivity'));

        actualizarOpcionesEmbedding();
        console.log('✅ Configuración cargada');

    } catch (error) {
        console.error('⚠️ Error al cargar configuración:', error);
        showToast('⚠️ Usando configuración predeterminada', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// TESTING DE CONEXIONES
// ─────────────────────────────────────────────────────────────────────────────

async function testearTodoslosModelos() {
    const loading = document.getElementById('api-loading');
    loading.classList.add('active');

    try {
        const response = await fetch('/api/config/test-apis', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        const results = await response.json();

        const proveedores = ['mistral', 'openrouter', 'openai', 'cohere', 'jina', 'ollama'];
        for (const p of proveedores) {
            const status = document.getElementById(`${p}-status`);
            if (!status || !results[p]) continue;
            if (results[p].ok) {
                status.className = 'api-status connected';
                status.innerHTML = '<span class="api-status-dot"></span>Conectado correctamente';
            } else {
                status.className = 'api-status error';
                status.innerHTML = `<span class="api-status-dot"></span>Error: ${results[p].error || 'Sin respuesta'}`;
            }
        }

        showToast('✅ Verificación completada', 'success');
    } catch (error) {
        console.error('Error al testear:', error);
        showToast('❌ Error al verificar conexiones', 'error');
    } finally {
        loading.classList.remove('active');
    }
}

function updateStatusIndicators() {
    const proveedoresConKey = ['mistral', 'openrouter', 'openai', 'cohere', 'jina'];

    for (const p of proveedoresConKey) {
        const keyEl    = document.getElementById(`${p}-key`);
        const statusEl = document.getElementById(`${p}-status`);
        if (!statusEl) continue;

        if (keyEl && keyEl.value) {
            statusEl.className = 'api-status';
            statusEl.innerHTML = '<span class="api-status-dot"></span>API Key configurada';
        } else {
            statusEl.innerHTML = '<span class="api-status-dot"></span>No configurado';
        }
    }

    // Ollama no tiene key, solo endpoint
    const ollamaEndpoint = document.getElementById('ollama-endpoint');
    const ollamaStatus   = document.getElementById('ollama-status');
    if (ollamaStatus) {
        const enabled = document.getElementById('ollama-enabled')?.checked;
        ollamaStatus.innerHTML = enabled
            ? `<span class="api-status-dot"></span>Endpoint: ${ollamaEndpoint?.value || 'localhost:11434'}`
            : '<span class="api-status-dot"></span>No configurado';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// RESET & EXPORT
// ─────────────────────────────────────────────────────────────────────────────

function resetConfig() {
    if (!confirm('⚠️ ¿Restablecer toda la configuración a valores predeterminados?')) return;

    // Mistral / OpenRouter
    document.getElementById('mistral-enabled').checked   = false;
    document.getElementById('mistral-key').value         = '';
    document.getElementById('mistral-endpoint').value    = 'https://api.mistral.ai/v1';
    document.getElementById('mistral-rpm-limit').value   = 30;
    document.getElementById('openrouter-enabled').checked = false;
    document.getElementById('openrouter-key').value      = '';
    document.getElementById('openrouter-rpm-limit').value = 60;

    // Nuevos proveedores
    const nulos = ['openai', 'cohere', 'jina'];
    for (const p of nulos) {
        const en = document.getElementById(`${p}-enabled`);
        const k  = document.getElementById(`${p}-key`);
        if (en) en.checked = false;
        if (k)  k.value    = '';
    }
    if (document.getElementById('openai-endpoint'))
        document.getElementById('openai-endpoint').value = 'https://api.openai.com/v1';
    if (document.getElementById('ollama-enabled'))
        document.getElementById('ollama-enabled').checked = false;
    if (document.getElementById('ollama-endpoint'))
        document.getElementById('ollama-endpoint').value = 'http://localhost:11434';

    // Modelos
    document.getElementById('model-chat').value       = 'mistral-large-latest';
    document.getElementById('model-extraction').value = 'mistral-small-latest';
    document.getElementById('model-synthesis').value  = 'mistral-medium-latest';
    document.getElementById('model-generation').value = 'mistral-medium-latest';
    document.getElementById('model-enrichment').value = 'mistral-medium-latest';
    if (document.getElementById('model-embeddings'))
        document.getElementById('model-embeddings').value = 'mistral-embed';
    if (document.getElementById('embedding-provider'))
        document.getElementById('embedding-provider').value = 'mistral';

    // NSFW / Fallbacks
    document.getElementById('nsfw-detection-enabled').checked = false;
    document.getElementById('nsfw-sensitivity').value         = 3;
    document.getElementById('nsfw-auto-switch').checked       = true;
    document.getElementById('nsfw-logging').checked           = true;
    document.getElementById('fallback-enabled').checked       = true;
    document.getElementById('fallback-primary').value         = 'mistral';
    document.getElementById('fallback-secondary').value       = 'openrouter';
    document.getElementById('retry-count').checked            = true;
    document.getElementById('retry-attempts').value           = 3;
    document.getElementById('queue-enabled').checked          = true;

    updateSensitivityLabel(document.getElementById('nsfw-sensitivity'));
    actualizarOpcionesEmbedding();
    saveConfig();
}

async function exportConfig() {
    try {
        const response = await fetch('/api/config/apis');
        const config = await response.json();
        const dataBlob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `api-config-${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        URL.revokeObjectURL(url);
        showToast('✅ Configuración exportada', 'success');
    } catch (error) {
        showToast('❌ Error al exportar configuración', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SAVE & CLOSE
// ─────────────────────────────────────────────────────────────────────────────

async function saveAndClose() {
    await saveConfig();
    setTimeout(() => { window.location.href = '/'; }, 1000);
}

// ─────────────────────────────────────────────────────────────────────────────
// TOAST NOTIFICATIONS
// ─────────────────────────────────────────────────────────────────────────────

function showToast(message, type = 'info') {
    const toast = document.getElementById('api-toast');
    toast.textContent = message;
    toast.className = `api-toast ${type} visible`;
    setTimeout(() => { toast.classList.remove('visible'); }, 3000);
}

console.log('🔧 Gestor de APIs cargado');


// ═══════════════════════════════════════════════════════════════════════════
// GESTIÓN DE TABS DE MODELOS DINÁMICOS
// ═══════════════════════════════════════════════════════════════════════════

function switchModelosTab(tabName) {
    document.querySelectorAll('.modelos-tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.modelos-tab-btn').forEach(btn => btn.classList.remove('active'));

    const tab = document.getElementById(`tab-${tabName}`);
    if (tab) tab.classList.add('active');
    event.target.classList.add('active');

    if (tabName === 'openrouter-chat') cargarModelosOpenRouter('chat');
    if (tabName === 'mistral-chat')    cargarModelosMistral('chat');
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR MODELOS DE OPENROUTER
// ─────────────────────────────────────────────────────────────────────────────

function cargarModelosOpenRouter(tipo) {
    const container = document.getElementById(`openrouter-${tipo}-lista`);
    if (!container) return;
    container.innerHTML = '<p class="cargando">⏳ Cargando modelos sin censura...</p>';

    Promise.all([
        fetch('/api/models/openrouter?uncensored=true').then(r => r.json()),
        fetch('/api/libreria/modelos').then(r => r.json())
    ])
    .then(([dataOpenRouter, dataLibreria]) => {
        let modelos = (dataOpenRouter.modelos || []).filter(m => m.tipo === tipo);

        if (dataLibreria.ok && dataLibreria.modelos) {
            const modelosLibreria = dataLibreria.modelos
                .filter(m => m.proveedor === 'openrouter')
                .map(m => ({ id: m.id, nombre: m.nombre || m.id, proveedor: 'OpenRouter', tipo, sin_censura: true, es_libreria: true }));
            modelos = [...modelos, ...modelosLibreria];
        }

        if (modelos.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:#999;padding:2rem;">No hay modelos disponibles</p>';
            return;
        }
        renderizarModelos(container, modelos, 'openrouter', tipo);
        cargarModeloActual();
    })
    .catch(err => {
        console.error('❌ Error cargando modelos:', err);
        container.innerHTML = `<p style="color:#f44336;text-align:center;padding:2rem;">❌ Error de conexión</p>`;
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR MODELOS DE MISTRAL
// ─────────────────────────────────────────────────────────────────────────────

function cargarModelosMistral(tipo) {
    const container = document.getElementById(`mistral-${tipo}-lista`);
    if (!container) return;
    container.innerHTML = '<p class="cargando">⏳ Cargando modelos de Mistral...</p>';

    Promise.all([
        fetch('/api/models/mistral').then(r => r.json()),
        fetch('/api/libreria/modelos').then(r => r.json())
    ])
    .then(([dataMistral, dataLibreria]) => {
        let filtrados = (dataMistral.modelos || [
            {id:'mistral-large-latest',  nombre:'Mistral Large', tipo:'chat'},
            {id:'mistral-medium-latest', nombre:'Mistral Medium', tipo:'chat'},
            {id:'open-mistral-nemo',     nombre:'Open Mistral Nemo', tipo:'chat'},
            {id:'mistral-small-latest',  nombre:'Mistral Small', tipo:'small'},
        ]).filter(m => m.tipo === tipo);

        if (dataLibreria.ok && dataLibreria.modelos) {
            const modelosLibreria = dataLibreria.modelos
                .filter(m => m.proveedor === 'mistral')
                .map(m => ({ id: m.id, nombre: m.nombre || m.id, proveedor: 'Mistral', tipo, es_libreria: true }));
            filtrados = [...filtrados, ...modelosLibreria];
        }

        if (filtrados.length === 0) {
            container.innerHTML = '<p style="text-align:center;color:#999;padding:2rem;">No hay modelos disponibles</p>';
            return;
        }
        renderizarModelos(container, filtrados, 'mistral', tipo);
        cargarModeloActual();
    })
    .catch(err => {
        container.innerHTML = `<p style="color:#f44336;text-align:center;padding:2rem;">❌ Error de conexión</p>`;
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDERIZAR MODELOS EN GRID
// ─────────────────────────────────────────────────────────────────────────────

function renderizarModelos(container, modelos, proveedor, tipo) {
    const html = modelos.map(m => {
        const badges = [];
        if (m.sin_censura)                           badges.push('<span class="modelo-item-badge uncensored">✨ Sin censura</span>');
        if (m.precio_input?.includes('GRATIS'))      badges.push('<span class="modelo-item-badge free">💰 GRATIS</span>');
        if (m.es_libreria)                           badges.push('<span class="modelo-item-badge libreria" style="background:#4CAF50;color:white;">📚 Librería</span>');

        return `
            <div class="modelo-item" data-id="${m.id}" onclick="seleccionarModelo('${m.id}', '${proveedor}_${tipo}')">
                <div class="modelo-item-nombre">${m.nombre || m.id}</div>
                <div class="modelo-item-id">${m.id}</div>
                <div class="modelo-item-tags">
                    ${m.proveedor ? `<span class="modelo-item-proveedor">${m.proveedor}</span>` : ''}
                    ${badges.join('')}
                </div>
                ${m.precio_input ? `<div class="modelo-item-detalles"><strong>Entrada:</strong> ${m.precio_input}<br/><strong>Salida:</strong> ${m.precio_output || 'N/A'}</div>` : ''}
                ${m.contexto     ? `<div class="modelo-item-detalles"><strong>Contexto:</strong> ${m.contexto}</div>` : ''}
                <button class="modelo-item-btn" onclick="event.stopPropagation(); seleccionarModelo('${m.id}', '${proveedor}_${tipo}')">Seleccionar</button>
            </div>
        `;
    }).join('');
    container.innerHTML = html;
}

// ─────────────────────────────────────────────────────────────────────────────
// SELECCIONAR MODELO
// ─────────────────────────────────────────────────────────────────────────────

function seleccionarModelo(modeloId, tipo) {
    const btn = event.target;
    if (!btn.classList.contains('modelo-item-btn')) return;

    btn.disabled = true;
    btn.innerHTML = '⏳ Cambiando...';

    fetch('/api/models/cambiar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tipo, modelo: modeloId })
    })
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
        if (data.ok) {
            mostrarNotificacion(`✅ Modelo cambiado a ${modeloId}`, 'success');
            cargarModeloActual();
            document.querySelectorAll('.modelo-item').forEach(el => {
                el.classList.toggle('active', el.dataset.id === modeloId);
            });
        } else {
            mostrarNotificacion(`❌ Error: ${data.error}`, 'error');
        }
    })
    .catch(err => mostrarNotificacion('❌ Error de conexión al servidor', 'error'))
    .finally(() => { btn.disabled = false; btn.innerHTML = 'Seleccionar'; });
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR MODELO ACTUAL
// ─────────────────────────────────────────────────────────────────────────────

function cargarModeloActual() {
    fetch('/api/models/activos')
    .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then(data => {
        if (data.ok && data.config) {
            const chatActual = data.config.openrouter_chat || data.config.mistral_chat || 'N/A';
            const inputChat  = document.getElementById('modelo-chat-actual');
            if (inputChat) inputChat.value = chatActual;

            document.querySelectorAll('.modelo-item').forEach(item => {
                item.classList.toggle('active', item.dataset.id === chatActual);
            });
        }
    })
    .catch(err => console.error('❌ Error cargando modelo actual:', err));
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICACIONES
// ─────────────────────────────────────────────────────────────────────────────

function mostrarNotificacion(mensaje, tipo = 'info') {
    const notif = document.createElement('div');
    notif.className = `notificacion ${tipo}`;
    notif.textContent = mensaje;
    document.body.appendChild(notif);
    setTimeout(() => {
        notif.style.animation = 'slideOutRight 0.3s ease';
        setTimeout(() => notif.remove(), 300);
    }, 4000);
}

// ─────────────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN DEL MÓDULO DE MODELOS DINÁMICOS
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    cargarModeloActual();
    setTimeout(() => {
        cargarModelosOpenRouter('chat');
        cargarModelosMistral('chat');
    }, 500);
});

// ─────────────────────────────────────────────────────────────────────────────
// PROBAR MODELO
// ─────────────────────────────────────────────────────────────────────────────

function probarModelo(modeloId, proveedor = 'openrouter') {
    const btn = event.target;
    btn.disabled = true;
    btn.innerHTML = '⏳ Probando...';

    fetch('/api/models/probar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modelo: modeloId, proveedor })
    })
    .then(r => r.json())
    .then(data => {
        if (data.ok) mostrarNotificacion(`✅ "${data.respuesta.substring(0, 30)}..."`, 'success');
        else         mostrarNotificacion(`❌ Error: ${data.error}`, 'error');
    })
    .catch(err => mostrarNotificacion('❌ Error al probar modelo', 'error'))
    .finally(() => { btn.disabled = false; btn.innerHTML = 'Probar'; });
}

// ─────────────────────────────────────────────────────────────────────────────
// BÚSQUEDA PERSONALIZADA DE MODELOS
// ─────────────────────────────────────────────────────────────────────────────

async function buscarModeloPersonalizado(tipo) {
    const inputId    = `openrouter-${tipo}-search-input`;
    const resultadoId = `openrouter-${tipo}-custom`;
    const input      = document.getElementById(inputId);
    const resultadoDiv = document.getElementById(resultadoId);

    if (!input || !resultadoDiv) {
        mostrarNotificacion(`Error: elementos UI no encontrados`, 'error');
        return;
    }

    const modeloId = input.value.trim();
    if (!modeloId) { mostrarNotificacion('⚠️ Ingresa un ID de modelo', 'warning'); return; }

    resultadoDiv.innerHTML = `<div class="modelo-item"><p class="cargando">⏳ Buscando ${modeloId}...</p></div>`;

    try {
        const response = await fetch('/api/models/probar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modelo: modeloId, proveedor: 'openrouter' })
        });

        const resultado = await response.json();

        if (resultado.ok) {
            renderizarModeloPersonalizado(resultadoDiv, {
                id: modeloId, nombre: modeloId.split('/').pop() || modeloId,
                tipo, proveedor: 'OpenRouter', funciona: true
            }, tipo);
            mostrarNotificacion('✅ Modelo encontrado y validado', 'success');
        } else {
            resultadoDiv.innerHTML = `
                <div class="modelo-item" style="border-color:#ff9999;background:#fff5f5;">
                    <h4 style="color:#cc0000;margin:0 0 0.5rem 0;">⚠️ Modelo no encontrado</h4>
                    <p style="color:#666;margin:0;font-size:0.85rem;">ID: <strong>${modeloId}</strong> — ${resultado.error || 'Verifica que sea correcto'}</p>
                </div>`;
            mostrarNotificacion('❌ Modelo no encontrado', 'error');
        }
    } catch (error) {
        resultadoDiv.innerHTML = `<div class="modelo-item" style="border-color:#ff9999;"><h4 style="color:#cc0000;">❌ Error: ${error.message}</h4></div>`;
        mostrarNotificacion('❌ Error: ' + error.message, 'error');
    }
}

function renderizarModeloPersonalizado(contenedor, modelo, tipo) {
    contenedor.innerHTML = `
        <div class="modelo-item">
            <div class="modelo-item-nombre">🔍 ${modelo.nombre}</div>
            <div class="modelo-item-id">${modelo.id}</div>
            <div class="modelo-item-tags">
                <span class="modelo-item-proveedor">${modelo.proveedor}</span>
                <span class="modelo-item-badge uncensored">✓ Funciona</span>
            </div>
            <button class="modelo-item-btn" onclick="seleccionarModelo('${modelo.id.replace(/'/g,"\\'")}', '${tipo}')">
                ✓ Seleccionar este modelo
            </button>
        </div>`;
}

function limpiarBusqueda(tipo) {
    const input  = document.getElementById(`openrouter-${tipo}-search-input`);
    const result = document.getElementById(`openrouter-${tipo}-custom`);
    if (input)  input.value = '';
    if (result) result.innerHTML = '';
}

console.log('✅ Funciones de búsqueda personalizada cargadas');

// ─────────────────────────────────────────────────────────────────────────────
// AUTO-DETECCIÓN DE PROVEEDOR POR MODEL ID
// ─────────────────────────────────────────────────────────────────────────────

const PROVEEDOR_RULES = [
    // Mistral — modelos propios sin "/" en el ID
    { test: id => /^(mistral|codestral|voxtral|ministral|pixtral|open-mistral|open-codestral|open-mixtral)/i.test(id) && !id.includes('/'), proveedor: 'mistral', label: '🟠 Mistral' },
    // OpenAI Embeddings
    { test: id => /^text-embedding|^gpt-/i.test(id), proveedor: 'openai', label: '🟢 OpenAI' },
    // Cohere
    { test: id => /^embed-|^command-/i.test(id), proveedor: 'cohere', label: '🔵 Cohere' },
    // Jina
    { test: id => /^jina-/i.test(id), proveedor: 'jina', label: '🟣 Jina AI' },
    // Ollama — sin "/" y nombres de modelos locales conocidos
    { test: id => /^(llama|phi|gemma|qwen|deepseek|falcon|orca|tinyllama|nomic|mxbai|all-minilm)[\d:-]/i.test(id) && !id.includes('/'), proveedor: 'ollama', label: '🖥️ Ollama' },
    // OpenRouter — formato org/modelo o contiene "/"
    { test: id => id.includes('/'), proveedor: 'openrouter', label: '🌐 OpenRouter' },
];

function detectarProveedorDesdId(modeloId) {
    const id = (modeloId || '').trim().toLowerCase();
    if (!id) return null;
    for (const rule of PROVEEDOR_RULES) {
        if (rule.test(id)) return rule;
    }
    return null;
}

function detectarProveedorAuto() {
    const id     = document.getElementById('lib-modelo-id')?.value || '';
    const badge  = document.getElementById('lib-proveedor-badge');
    const select = document.getElementById('lib-modelo-proveedor');
    if (!badge) return;

    const match = detectarProveedorDesdId(id);
    if (match) {
        badge.textContent = match.label;
        badge.style.display = 'inline-block';
        // Solo actualiza el select si sigue en "auto"
        if (select && select.value === 'auto') {
            // No cambiamos el select para no confundir, solo mostramos el badge
        }
    } else {
        badge.style.display = 'none';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// LIBRERÍA DE MODELOS
// ─────────────────────────────────────────────────────────────────────────────

function cargarLibreria() {
    cargarListaModelos();
}

async function cargarListaModelos() {
    try {
        const response = await fetch('/api/libreria/modelos');
        const data = await response.json();
        const contenedor = document.getElementById('libreria-modelos-lista');

        if (!data.ok || data.modelos.length === 0) {
            contenedor.innerHTML = '<p style="color:#999;">No hay modelos en la librería. Agrega uno nuevo.</p>';
            return;
        }

        let html = '<div style="display:grid;gap:1rem;">';
        data.modelos.forEach(modelo => {
            const tagHTML = modelo.tags.map(tag =>
                `<span style="display:inline-block;background:#e0e0e0;padding:0.3rem 0.7rem;border-radius:4px;font-size:0.8rem;margin-right:0.5rem;">${tag}</span>`
            ).join('');

            html += `
                <div style="background:#f9f9f9;border:2px solid #e0e0e0;border-radius:10px;padding:1.2rem;">
                    <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:0.8rem;">
                        <div>
                            <h4 style="margin:0;color:#222;">${modelo.nombre}</h4>
                            <code style="color:#666;font-size:0.85rem;">${modelo.id}</code>
                        </div>
                        <button onclick="eliminarModeloLibreria('${modelo.id}')" class="api-btn api-btn-secondary" style="padding:0.5rem 1rem;font-size:0.85rem;">🗑️ Eliminar</button>
                    </div>
                    ${modelo.descripcion ? `<p style="color:#666;margin:0.5rem 0;font-size:0.9rem;">${modelo.descripcion}</p>` : ''}
                    <div style="margin-top:0.8rem;">
                        <span style="background:#e1f5fe;color:#0277bd;padding:0.3rem 0.7rem;border-radius:4px;font-size:0.75rem;margin-right:0.5rem;">${modelo.proveedor}</span>
                        ${tagHTML}
                    </div>
                </div>`;
        });
        html += '</div>';
        contenedor.innerHTML = html;
    } catch (error) {
        document.getElementById('libreria-modelos-lista').innerHTML =
            `<p style="color:#cc0000;">Error al cargar modelos: ${error.message}</p>`;
    }
}

async function agregarModeloLibreria() {
    const modeloId    = document.getElementById('lib-modelo-id').value.trim();
    const nombre      = document.getElementById('lib-modelo-nombre').value.trim();
    const descripcion = document.getElementById('lib-modelo-descripcion').value.trim();
    const tagsStr     = document.getElementById('lib-modelo-tags').value.trim();

    if (!modeloId) { mostrarNotificacion('⚠️ Ingresa el ID del modelo', 'warning'); return; }

    // Resolver proveedor: manual o auto-detectado
    const selectVal = document.getElementById('lib-modelo-proveedor').value;
    let proveedor;
    if (selectVal === 'auto' || !selectVal) {
        const match = detectarProveedorDesdId(modeloId);
        proveedor = match ? match.proveedor : 'openrouter'; // fallback a openrouter
    } else {
        proveedor = selectVal;
    }

    const tags = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : [];

    try {
        const response = await fetch('/api/libreria/agregar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ modelo_id: modeloId, nombre: nombre || undefined, descripcion, proveedor, tags })
        });
        const resultado = await response.json();

        if (resultado.ok) {
            mostrarNotificacion(`✅ ${resultado.mensaje}`, 'success');
            document.getElementById('lib-modelo-id').value          = '';
            document.getElementById('lib-modelo-nombre').value      = '';
            document.getElementById('lib-modelo-descripcion').value = '';
            document.getElementById('lib-modelo-tags').value        = '';
            document.getElementById('lib-modelo-proveedor').value   = 'auto';
            const badge = document.getElementById('lib-proveedor-badge');
            if (badge) badge.style.display = 'none';
            cargarListaModelos();
            cargarModelosOpenRouter('chat');
            cargarModelosMistral('chat');
            cargarModelosEnDropdowns();
        } else {
            mostrarNotificacion(`❌ ${resultado.mensaje}`, 'error');
        }
    } catch (error) {
        mostrarNotificacion(`Error: ${error.message}`, 'error');
    }
}

async function eliminarModeloLibreria(modeloId) {
    if (!confirm(`¿Eliminar modelo ${modeloId} de la librería?`)) return;
    try {
        const response = await fetch(`/api/libreria/modelo/${modeloId}`, { method: 'DELETE' });
        const resultado = await response.json();
        if (resultado.ok) {
            mostrarNotificacion(`✅ ${resultado.mensaje}`, 'success');
            cargarListaModelos();
            cargarModelosOpenRouter('chat');
            cargarModelosMistral('chat');
            cargarModelosEnDropdowns();
        } else {
            mostrarNotificacion(`❌ ${resultado.mensaje}`, 'error');
        }
    } catch (error) {
        mostrarNotificacion(`Error: ${error.message}`, 'error');
    }
}

function copiarModeloId(modeloId) {
    navigator.clipboard.writeText(modeloId).then(() => mostrarNotificacion(`✅ Copiado: ${modeloId}`, 'success'));
}

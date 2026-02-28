// ═══════════════════════════════════════════════════════════════════════════
// HIRO CHAT — Frontend
// Mejoras: /api/chat en lugar de /api/mensaje, avatar dinámico,
// sin monkey-patch de fetch, sin funciones duplicadas, sin console.log
// ═══════════════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────────────────
// ELEMENTOS DEL DOM
// ─────────────────────────────────────────────────────────────────────────────

const chatContainer   = document.getElementById('chatContainer');
const messageInput    = document.getElementById('messageInput');
const sendButton      = document.getElementById('sendButton');
const typingIndicator = document.getElementById('typingIndicator');
const daysCounter     = document.getElementById('daysCounter');
const settingsButton  = document.getElementById('settingsButton');
const settingsDropdown= document.getElementById('settingsDropdown');

// ─────────────────────────────────────────────────────────────────────────────
// ESTADO GLOBAL
// ─────────────────────────────────────────────────────────────────────────────
// Expresiones
let _expresionesCache = null;
let _expresionAbierta = false;

let isWaiting          = false;
let messageIdCounter   = 0;
let currentOpenMenu    = null;
let personajeActualId  = 'hiro';
let personajeNombre    = 'Personaje';

// Control de generación
let stopController     = null;  // AbortController activo durante fetch
let typewriterStop     = false; // flag para cortar el typewriter mid-animation

function getAvatarUrl() {
    return `/api/personajes/${personajeActualId}/avatar`;
}

// ─────────────────────────────────────────────────────────────────────────────
// SISTEMA DE TEMAS
// ─────────────────────────────────────────────────────────────────────────────

function initTheme() {
    const savedTheme = localStorage.getItem('hiro-theme') || 'gold';
    applyTheme(savedTheme);
}

function applyTheme(themeName) {
    document.documentElement.setAttribute('data-theme', themeName);
    localStorage.setItem('hiro-theme', themeName);
    document.querySelectorAll('.color-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.color === themeName);
    });
}

document.querySelectorAll('.color-option').forEach(button => {
    button.addEventListener('click', e => applyTheme(e.currentTarget.dataset.color));
});

// ─────────────────────────────────────────────────────────────────────────────
// MENÚ DE CONFIGURACIÓN
// ─────────────────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────────────────
// MENÚ DE CONFIGURACIÓN — 3 paneles
// ─────────────────────────────────────────────────────────────────────────────

settingsButton.addEventListener('click', e => {
    e.stopPropagation();
    const yaAbiertoPanel = document.querySelector('.smenu-panel.open');
    if (yaAbiertoPanel) {
        cerrarPaneles();
        return;
    }
    settingsDropdown.classList.toggle('open');
});

function _cerrarSettingsDropdown(e) {
    const dentroDropdown = settingsDropdown.contains(e.target);
    const dentroPanel    = [...document.querySelectorAll('.smenu-panel')].some(p => p.contains(e.target));
    const dentroBoton    = settingsButton.contains(e.target);

    if (!dentroDropdown && !dentroPanel && !dentroBoton) {
        settingsDropdown.classList.remove('open');
        cerrarPaneles();
    }
    if (currentOpenMenu && !currentOpenMenu.contains(e.target)) {
        const btn = currentOpenMenu.previousElementSibling;
        if (btn && !btn.contains(e.target)) closeMessageMenu();
    }
}

document.addEventListener('click',      _cerrarSettingsDropdown);
document.addEventListener('touchstart', _cerrarSettingsDropdown, { passive: true });

// ─────────────────────────────────────────────────────────────────────────────
// SISTEMA DE PANELES
// ─────────────────────────────────────────────────────────────────────────────

const _PANELES_IDS = ['panelConfiguracion', 'panelMensajes', 'panelPersonajes'];
let   _panelPersonajeSeleccionado = null;

function cerrarPaneles() {
    _PANELES_IDS.forEach(id => document.getElementById(id)?.classList.remove('open'));
}

function abrirPanel(nombre) {
    // Cerrar dropdown
    settingsDropdown.classList.remove('open');

    const mapeo = {
        'configuracion': 'panelConfiguracion',
        'mensajes':      'panelMensajes',
        'personajes':    'panelPersonajes',
    };
    const panelId = mapeo[nombre];
    if (!panelId) return;

    // Cerrar todos, abrir solo el pedido (sin superposición)
    _PANELES_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (id === panelId) {
            el.classList.toggle('open');  // toggle: si ya estaba abierto, lo cierra
        } else {
            el.classList.remove('open');
        }
    });

    // Cargar contenido dinámico del panel si está abriéndose
    if (document.getElementById(panelId)?.classList.contains('open')) {
        if (nombre === 'personajes') _cargarPanelPersonajes();
    }
}

// ── Panel Personajes ──────────────────────────────────────────────────────────

async function _cargarPanelPersonajes() {
    const container = document.getElementById('panelListaPersonajes');
    if (!container) return;
    container.innerHTML = '<p class="smenu-lista-cargando">Cargando...</p>';
    _panelPersonajeSeleccionado = personajeActualId;

    try {
        const resp = await fetch('/api/personajes');
        const lista = await resp.json();

        if (!lista.length) {
            container.innerHTML = '<p class="smenu-lista-cargando">No hay personajes instalados.</p>';
            return;
        }

        container.innerHTML = '';
        lista.forEach(p => {
            const card = document.createElement('div');
            card.className = `smenu-personaje-card${p.activo ? ' seleccionado activo-actual' : ''}`;
            card.dataset.pid = p.id;
            card.innerHTML = `
                <img class="smenu-personaje-avatar"
                     src="/api/personajes/${p.id}/avatar"
                     onerror="this.style.display='none'">
                <div class="smenu-personaje-info">
                    <div class="smenu-personaje-nombre">${p.nombre}</div>
                    <div class="smenu-personaje-id">${p.id}</div>
                </div>
                ${p.activo ? '<span class="smenu-personaje-badge">● activo</span>' : ''}
            `;
            card.addEventListener('click', () => _seleccionarPersonajePanel(p.id));
            container.appendChild(card);
        });
    } catch {
        container.innerHTML = '<p class="smenu-lista-cargando">Error cargando personajes.</p>';
    }
}

function _seleccionarPersonajePanel(pid) {
    _panelPersonajeSeleccionado = pid;
    document.querySelectorAll('#panelListaPersonajes .smenu-personaje-card').forEach(card => {
        card.classList.toggle('seleccionado', card.dataset.pid === pid);
    });
}

async function aplicarPersonajeSeleccionado() {
    if (!_panelPersonajeSeleccionado) { cerrarPaneles(); return; }
    if (_panelPersonajeSeleccionado === personajeActualId) { cerrarPaneles(); return; }
    cerrarPaneles();
    await cambiarAPersonaje(_panelPersonajeSeleccionado);
}

// ─────────────────────────────────────────────────────────────────────────────
// MENÚ CONTEXTUAL DE MENSAJES
// ─────────────────────────────────────────────────────────────────────────────

function createMessageMenu(messageWrapper, messageId, isHiro) {
    const menuButton = document.createElement('button');
    menuButton.className = 'message-menu-button';
    menuButton.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="1"></circle>
            <circle cx="12" cy="5" r="1"></circle>
            <circle cx="12" cy="19" r="1"></circle>
        </svg>`;

    const menu = document.createElement('div');
    menu.className = 'message-menu';
    const yaDestacado = mensajesDestacados.some(d => d.id === messageId);
    menu.innerHTML = `
        <button class="message-menu-item star${yaDestacado ? ' active' : ''}" data-action="star" data-star="${messageId}">
            <svg viewBox="0 0 24 24" fill="${yaDestacado ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2">
                <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"></polygon>
            </svg>
            ${yaDestacado ? 'Quitar destacado' : 'Destacar'}
        </button>
        <button class="message-menu-item" data-action="edit">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
                <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
            </svg>
            Editar
        </button>
        ${isHiro ? `
        <button class="message-menu-item" data-action="regenerate">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="23 4 23 10 17 10"></polyline>
                <polyline points="1 20 1 14 7 14"></polyline>
                <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path>
            </svg>
            Regenerar
        </button>
        <button class="message-menu-item" data-action="continuar">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="13 17 18 12 13 7"></polyline>
                <polyline points="6 17 11 12 6 7"></polyline>
            </svg>
            Continuar
        </button>` : ''}
        <button class="message-menu-item danger" data-action="delete">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <polyline points="3 6 5 6 21 6"></polyline>
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
            </svg>
            Eliminar
        </button>`;

    menuButton.addEventListener('click', e => {
        e.stopPropagation();
        if (currentOpenMenu && currentOpenMenu !== menu) closeMessageMenu();
        menu.classList.toggle('open');
        currentOpenMenu = menu.classList.contains('open') ? menu : null;
    });

    menu.querySelectorAll('.message-menu-item').forEach(item => {
        item.addEventListener('click', e => {
            e.stopPropagation();
            const action = e.currentTarget.dataset.action;
            if (action === 'star') {
                const bubble = messageWrapper.querySelector('.message-bubble');
                const texto  = bubble?.textContent || '';
                toggleDestacado(messageId, texto, isHiro);
                // Refresh menu label
                const starBtn = menu.querySelector('[data-action="star"]');
                const ahora   = mensajesDestacados.some(d => d.id === messageId);
                if (starBtn) {
                    starBtn.querySelector('svg').setAttribute('fill', ahora ? 'currentColor' : 'none');
                    starBtn.classList.toggle('active', ahora);
                    starBtn.childNodes[starBtn.childNodes.length - 1].textContent = ahora ? ' Quitar destacado' : ' Destacar';
                }
            }
            if (action === 'edit')       editMessage(messageWrapper, messageId);
            if (action === 'regenerate') regenerateResponse(messageId);
            if (action === 'continuar')  continuarRespuesta();
            if (action === 'delete')     deleteMessage(messageId, messageWrapper);
            closeMessageMenu();
        });
    });

    return { menuButton, menu };
}

function closeMessageMenu() {
    if (currentOpenMenu) {
        currentOpenMenu.classList.remove('open');
        currentOpenMenu = null;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTROL DEL BOTÓN STOP
// ─────────────────────────────────────────────────────────────────────────────

function _setEstadoGenerando(generando) {
    const stopBtn = document.getElementById('stopButton');
    const sendBtn = document.getElementById('sendButton');
    if (stopBtn) stopBtn.style.display = generando ? 'flex' : 'none';
    if (sendBtn) sendBtn.style.display = generando ? 'none' : 'flex';
}

function stopGeneration() {
    // Abortar el fetch si todavía está en curso
    if (stopController) {
        stopController.abort();
        stopController = null;
    }
    // Detener el typewriter inmediatamente
    typewriterStop = true;

    // Borrar el último intercambio de la DB (fire & forget)
    fetch('/api/cancelar_ultimo', { method: 'POST' })
        .then(r => r.json())
        .then(d => { if (d.borrados > 0) console.log(`🛑 Stop: ${d.borrados} mensaje(s) eliminados de DB`); })
        .catch(() => {});
}

// ─────────────────────────────────────────────────────────────────────────────
// FORMATEO DE MENSAJES
// ─────────────────────────────────────────────────────────────────────────────

function formatHiroMessage(text) {
    if (!text) return '';
    let escaped = text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
    // "diálogo" va PRIMERO para no matchear los class="..." de los spans siguientes
    return escaped
        .replace(/"([^"]+)"/g,       '<span class="dialogue">"$1"</span>')
        .replace(/\*([^*]+)\*/g,     '<span class="action">*$1*</span>')
        .replace(/\(\(([^)]+)\)\)/g, '<span class="thought">(($1))</span>')
        .replace(/\n/g,              '<br>');
}

function formatTime() {
    return new Date().toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    textarea.style.height = textarea.scrollHeight + 'px';
}

function scrollToBottom() {
    chatContainer.scrollTo({ top: chatContainer.scrollHeight, behavior: 'smooth' });
}

// ─────────────────────────────────────────────────────────────────────────────
// RENDERIZADO DE MENSAJES
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Crea un mensaje del asistente vacío en el chat y escribe el texto
 * palabra por palabra. Devuelve una Promise que resuelve cuando termina.
 */
function renderMessageTypewriter(contenido, messageId = null) {
    const msgId = messageId || ++messageIdCounter;

    const wrapper = document.createElement('div');
    wrapper.className = 'message-wrapper hiro-message';
    wrapper.dataset.messageId = msgId;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    avatar.innerHTML = `
        <img src="${getAvatarUrl()}" alt="${personajeNombre}"
             class="avatar-image" onerror="handleImageError(this)">
        <div class="avatar-fallback">${personajeNombre.charAt(0).toUpperCase()}</div>`;

    const content = document.createElement('div');
    content.className = 'message-content';

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble hiro-bubble';

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = formatTime();

    content.appendChild(bubble);
    content.appendChild(time);

    const { menuButton, menu } = createMessageMenu(wrapper, msgId, true);

    wrapper.appendChild(avatar);
    wrapper.appendChild(content);
    wrapper.appendChild(menuButton);
    wrapper.appendChild(menu);

    chatContainer.appendChild(wrapper);
    scrollToBottom();

    // Efecto typewriter palabra por palabra
    return new Promise(resolve => {
        const formatted = formatHiroMessage(contenido);
        const words = contenido.split(' ');
        let current = '';
        let i = 0;
        const delay = Math.max(30, Math.min(80, 1800 / words.length));

        function writeNext() {
            // Si se pidió stop, mostrar el texto completo de una y resolver
            if (typewriterStop) {
                bubble.innerHTML = formatted;
                resolve(wrapper);
                return;
            }
            if (i < words.length) {
                current += (i === 0 ? '' : ' ') + words[i];
                bubble.innerHTML = formatHiroMessage(current);
                scrollToBottom();
                i++;
                setTimeout(writeNext, delay);
            } else {
                bubble.innerHTML = formatted;
                resolve(wrapper);
            }
        }
        writeNext();
    });
}

function renderMessage(rol, contenido, messageId = null) {
    const msgId  = messageId || ++messageIdCounter;
    const isHiro = rol === 'assistant';

    const wrapper = document.createElement('div');
    wrapper.className = `message-wrapper ${isHiro ? 'hiro-message' : 'user-message'}`;
    wrapper.dataset.messageId = msgId;

    const avatar = document.createElement('div');
    avatar.className = 'avatar';
    if (isHiro) {
        avatar.innerHTML = `
            <img src="${getAvatarUrl()}" alt="${personajeNombre}"
                 class="avatar-image" onerror="handleImageError(this)">
            <div class="avatar-fallback">${personajeNombre.charAt(0).toUpperCase()}</div>`;
    } else {
        avatar.textContent = 'U';
    }

    const content = document.createElement('div');
    content.className = 'message-content';

    const bubble = document.createElement('div');
    bubble.className = `message-bubble ${isHiro ? 'hiro-bubble' : 'user-bubble'}`;
    bubble.innerHTML = formatHiroMessage(contenido);

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = formatTime();

    content.appendChild(bubble);
    content.appendChild(time);

    const { menuButton, menu } = createMessageMenu(wrapper, msgId, isHiro);

    if (isHiro) {
        wrapper.appendChild(avatar);
        wrapper.appendChild(content);
        wrapper.appendChild(menuButton);
        wrapper.appendChild(menu);
    } else {
        wrapper.appendChild(menuButton);
        wrapper.appendChild(menu);
        wrapper.appendChild(content);
        wrapper.appendChild(avatar);  // avatar al final = derecha en flex row
    }

    chatContainer.appendChild(wrapper);
    scrollToBottom();
    return wrapper;
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTROL DE MENSAJES (editar / eliminar / regenerar)
// ─────────────────────────────────────────────────────────────────────────────

async function deleteMessage(messageId, messageElement) {
    if (!confirm('¿Eliminar este mensaje?')) return;
    try {
        const resp = await fetch(`/api/mensaje/${messageId}`, { method: 'DELETE' });
        if (resp.ok) {
            messageElement.style.opacity = '0';
            messageElement.style.transform = 'translateX(20px)';
            setTimeout(() => messageElement.remove(), 300);
        }
    } catch {
        mostrarNotificacion('Error al eliminar el mensaje', 'error');
    }
}

async function editMessage(messageWrapper, messageId) {
    const bubble = messageWrapper.querySelector('.message-bubble');
    const originalContent = bubble.innerHTML;
    const originalText = bubble.textContent.trim();

    const textarea = document.createElement('textarea');
    textarea.className = 'message-input';
    textarea.value = originalText;
    textarea.style.cssText = 'width:100%;min-height:60px';

    const btns = document.createElement('div');
    btns.style.cssText = 'display:flex;gap:8px;margin-top:8px';

    const saveBtn   = document.createElement('button');
    saveBtn.textContent = 'Guardar';
    saveBtn.className   = 'icon-button';
    saveBtn.style.cssText = 'width:auto;padding:8px 16px';

    const cancelBtn = document.createElement('button');
    cancelBtn.textContent = 'Cancelar';
    cancelBtn.className   = 'icon-button';
    cancelBtn.style.cssText = 'width:auto;padding:8px 16px';

    bubble.innerHTML = '';
    bubble.appendChild(textarea);
    btns.appendChild(saveBtn);
    btns.appendChild(cancelBtn);
    bubble.appendChild(btns);
    autoResize(textarea);
    textarea.focus();

    saveBtn.onclick = async () => {
        const newText = textarea.value.trim();
        if (!newText || newText === originalText) {
            bubble.innerHTML = originalContent;
            return;
        }
        try {
            const resp = await fetch(`/api/mensaje/${messageId}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ contenido: newText }),
            });
            if (resp.ok) {
                bubble.innerHTML = formatHiroMessage(newText);
                // Si es mensaje del usuario → regenerar respuesta siguiente
                if (messageWrapper.classList.contains('user-message')) {
                    const nextMsg = messageWrapper.nextElementSibling;
                    if (nextMsg && nextMsg.classList.contains('hiro-message')) {
                        const hiroMsgId = nextMsg.dataset.messageId;
                        await fetch(`/api/mensaje/${hiroMsgId}`, { method: 'DELETE' });
                        nextMsg.remove();
                        await sendExistingMessage(newText);
                    }
                }
            }
        } catch {
            mostrarNotificacion('Error al editar el mensaje', 'error');
            bubble.innerHTML = originalContent;
        }
    };

    cancelBtn.onclick = () => { bubble.innerHTML = originalContent; };
}

async function regenerateResponse(messageId) {
    if (isWaiting) return;
    const hiroMessage = document.querySelector(`[data-message-id="${messageId}"]`);
    if (!hiroMessage) return;
    hiroMessage.style.opacity = '0.5';

    try {
        await fetch(`/api/mensaje/${messageId}`, { method: 'DELETE' });

        let prevMsg = hiroMessage.previousElementSibling;
        while (prevMsg && !prevMsg.classList.contains('user-message')) {
            prevMsg = prevMsg.previousElementSibling;
        }
        if (!prevMsg) { hiroMessage.style.opacity = '1'; return; }

        const resp = await fetch(`/api/mensaje/${prevMsg.dataset.messageId}`);
        const data = await resp.json();
        hiroMessage.remove();
        await sendExistingMessage(data.contenido);
    } catch {
        hiroMessage.style.opacity = '1';
        mostrarNotificacion('Error al regenerar la respuesta', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTINUAR — el personaje sigue escribiendo sin input del usuario
// ─────────────────────────────────────────────────────────────────────────────

async function continuarRespuesta() {
    if (isWaiting) return;

    isWaiting = true;
    typewriterStop = false;
    stopController = new AbortController();
    sendButton.disabled = true;
    messageInput.disabled = true;
    _setEstadoGenerando(true);
    chatContainer.appendChild(typingIndicator);
    typingIndicator.style.display = 'flex';
    scrollToBottom();

    try {
        const resp = await fetch('/api/continuar', {
            method: 'POST',
            signal: stopController.signal,
        });
        const data = await resp.json();

        typingIndicator.style.opacity = '0';
        await new Promise(r => setTimeout(r, 200));
        typingIndicator.style.display = 'none';
        typingIndicator.style.opacity = '1';

        if (data.error) {
            renderMessage('assistant', `❌ Error: ${data.error}`);
        } else {
            await renderMessageTypewriter(data.response);
            await detectarYMostrarExpresion(data.response);
            _procesarEventosDisparados(data.eventos_disparados);
        }
    } catch(e) {
        typingIndicator.style.display = 'none';
        if (e.name !== 'AbortError') {
            renderMessage('assistant', '❌ Error de conexión.');
        }
    } finally {
        isWaiting = false;
        typewriterStop = false;
        stopController = null;
        _setEstadoGenerando(false);
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ENVÍO DE MENSAJES
// ─────────────────────────────────────────────────────────────────────────────

async function _callChatAPI(mensaje) {
    const resp = await fetch('/api/chat', {
        method : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body   : JSON.stringify({ message: mensaje }),
        signal : stopController ? stopController.signal : undefined,
    });
    return await resp.json();
}

async function sendExistingMessage(mensaje) {
    isWaiting = true;
    typewriterStop = false;
    stopController = new AbortController();
    sendButton.disabled = true;
    messageInput.disabled = true;
    _setEstadoGenerando(true);
    chatContainer.appendChild(typingIndicator);
    typingIndicator.style.display = 'flex';
    scrollToBottom();

    try {
        const data = await _callChatAPI(mensaje);
        typingIndicator.style.opacity = '0';
        await new Promise(r => setTimeout(r, 200));
        typingIndicator.style.display = 'none';
        typingIndicator.style.opacity = '1';
        if (data.error) {
            renderMessage('assistant', `❌ Error: ${data.error}`);
        } else {
            await renderMessageTypewriter(data.response);
            await detectarYMostrarExpresion(data.response);
            _procesarEventosDisparados(data.eventos_disparados);
        }
    } catch(e) {
        typingIndicator.style.display = 'none';
        typingIndicator.style.opacity = '1';
        if (e.name !== 'AbortError') {
            renderMessage('assistant', '❌ Error de conexión.');
        }
    } finally {
        isWaiting = false;
        typewriterStop = false;
        stopController = null;
        _setEstadoGenerando(false);
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
    }
}

async function sendMessage() {
    if (isWaiting) return;
    const mensaje = messageInput.value.trim();
    if (!mensaje) return;

    messageInput.value = '';
    messageInput.style.height = 'auto';
    isWaiting = true;
    typewriterStop = false;
    stopController = new AbortController();
    sendButton.disabled = true;
    messageInput.disabled = true;
    _setEstadoGenerando(true);

    renderMessage('user', mensaje);
    chatContainer.appendChild(typingIndicator);
    typingIndicator.style.display = 'flex';
    scrollToBottom();

    try {
        const data = await _callChatAPI(mensaje);
        typingIndicator.style.opacity = '0';
        await new Promise(r => setTimeout(r, 200));
        typingIndicator.style.display = 'none';
        typingIndicator.style.opacity = '1';
        if (data.error) {
            renderMessage('assistant', `❌ Error: ${data.error}`);
        } else {
            await renderMessageTypewriter(data.response);
            await detectarYMostrarExpresion(data.response); 
            _procesarEventosDisparados(data.eventos_disparados);
            loadStats();
        }
    } catch(e) {
        typingIndicator.style.display = 'none';
        typingIndicator.style.opacity = '1';
        if (e.name !== 'AbortError') {
            renderMessage('assistant', '❌ Error de conexión. Asegurate de que el servidor esté corriendo.');
        }
    } finally {
        isWaiting = false;
        typewriterStop = false;
        stopController = null;
        _setEstadoGenerando(false);
        sendButton.disabled = false;
        messageInput.disabled = false;
        messageInput.focus();
    }
}

function _procesarEventosDisparados(eventos) {
    if (!eventos || !eventos.length) return;
    eventos.forEach((ev, i) => {
        setTimeout(() => mostrarNotificacionEvento(ev.nombre, ev.descripcion), 1200 + i * 500);
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// HISTORIAL / STATS / PERFIL
// ─────────────────────────────────────────────────────────────────────────────

async function loadHistory() {
    try {
        const resp = await fetch('/api/historial');
        const data = await resp.json();
        if (data.mensajes && data.mensajes.length > 0) {
            chatContainer.innerHTML = '';
            data.mensajes.forEach(msg => renderMessage(msg.rol, msg.contenido, msg.id));
            // messageIdCounter refleja el ID real más alto de la DB
            messageIdCounter = Math.max(...data.mensajes.map(m => m.id));
        }
    } catch { /* silencioso — el chat de bienvenida permanece */ }
}

async function loadStats() {
    try {
        const resp = await fetch('/api/stats');
        const data = await resp.json();
        if (data.dias_juntos !== undefined) {
            daysCounter.textContent = `Día ${data.dias_juntos}`;
        }
    } catch { /* no crítico */ }
}


// ─────────────────────────────────────────────────────────────────────────────
// EDICIÓN INLINE DE SÍNTESIS
// ─────────────────────────────────────────────────────────────────────────────

function activarEdicionSintesisInline(sid) {
    const textoEl = document.getElementById(`sintesis-texto-${sid}`);
    if (!textoEl || textoEl.dataset.editando === '1') return;
    textoEl.dataset.editando = '1';

    const textoOriginal = textoEl.textContent.trim();

    // Reemplazar el div de texto por un textarea + botones inline
    textoEl.innerHTML = `
        <textarea id="sintesis-inline-${sid}"
            style="width:100%;min-height:80px;background:var(--bg-void);
                   border:1px solid var(--accent);border-radius:6px;
                   color:var(--text-bright);font-family:var(--font-serif);
                   font-size:0.85rem;line-height:1.6;padding:8px 10px;
                   resize:vertical;outline:none;box-sizing:border-box;
                   box-shadow:0 0 0 3px var(--accent-glow)"
            >${textoOriginal}</textarea>
        <div style="display:flex;justify-content:flex-end;gap:6px;margin-top:6px">
            <button onclick="cancelarEdicionSintesisInline(${sid}, \`${textoOriginal.replace(/`/g,'\\`')}\`)"
                style="background:none;border:1px solid var(--border);color:var(--text-secondary);
                       cursor:pointer;font-size:0.72rem;font-family:monospace;padding:3px 10px;
                       border-radius:4px;transition:all 0.2s">
                Cancelar
            </button>
            <button onclick="guardarEdicionSintesisInline(${sid})"
                style="background:var(--accent);border:none;color:var(--bg-void);
                       cursor:pointer;font-size:0.72rem;font-family:monospace;padding:3px 10px;
                       border-radius:4px;font-weight:600;transition:all 0.2s">
                Guardar
            </button>
        </div>`;

    const ta = document.getElementById(`sintesis-inline-${sid}`);
    ta.focus();
    ta.setSelectionRange(ta.value.length, ta.value.length);

    // Ctrl+Enter o Cmd+Enter para guardar rápido
    ta.addEventListener('keydown', e => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            e.preventDefault();
            guardarEdicionSintesisInline(sid);
        }
        if (e.key === 'Escape') {
            cancelarEdicionSintesisInline(sid, textoOriginal);
        }
    });
}

function cancelarEdicionSintesisInline(sid, textoOriginal) {
    const textoEl = document.getElementById(`sintesis-texto-${sid}`);
    if (!textoEl) return;
    textoEl.innerHTML = textoOriginal;
    delete textoEl.dataset.editando;
}

async function guardarEdicionSintesisInline(sid) {
    const ta = document.getElementById(`sintesis-inline-${sid}`);
    if (!ta) return;
    const nuevoContenido = ta.value.trim();
    if (!nuevoContenido) { mostrarNotificacion('El contenido no puede estar vacío', 'error'); return; }

    try {
        const resp = await fetch(`/api/sintesis/${sid}`, {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ contenido: nuevoContenido }),
        });
        const r = await resp.json();
        if (r.success) {
            const textoEl = document.getElementById(`sintesis-texto-${sid}`);
            if (textoEl) {
                textoEl.innerHTML = nuevoContenido;
                delete textoEl.dataset.editando;
            }
            mostrarNotificacion('Síntesis actualizada', 'success');
        } else {
            mostrarNotificacion('Error: ' + r.error, 'error');
        }
    } catch {
        mostrarNotificacion('Error al guardar', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// PERSONAJE ACTIVO — carga dinámica de nombre y avatar
// ─────────────────────────────────────────────────────────────────────────────

async function cargarPersonajeActivo() {
    try {
        const resp = await fetch('/api/personajes/activo');
        const data = await resp.json();
        personajeActualId = data.id;
        personajeNombre   = data.nombre;
        actualizarUIPersonaje();
        await actualizarModoBadge();
        aplicarColoresPersonaje(personajeActualId); // ← aplica colores DESPUÉS de saber el ID real
    } catch { /* usa defaults */ }
}

async function actualizarModoBadge() {
    try {
        const resp = await fetch('/api/personajes/activo/ficha');
        const data = await resp.json();
        const modo  = data.modo_memoria || 'roleplay';
        const badge = document.getElementById('headerModoBadge');
        if (!badge) return;
        if (modo === 'compañero') {
            badge.textContent = '· Compañero';
            badge.classList.add('companion');
        } else {
            badge.textContent = '· Roleplay';
            badge.classList.remove('companion');
        }
    } catch { /* silencioso */ }
}

function _setImgSrc(img, fallback, url, alt, inicial) {
    if (!img) return;
    // Resetear display por si un onerror previo lo había ocultado
    img.style.display = '';
    if (fallback) fallback.style.display = 'none';
    img.alt    = alt;
    img.onerror = () => handleImageError(img);
    img.src    = url;
}

function actualizarUIPersonaje() {
    const avatarUrl = getAvatarUrl();
    const inicial   = personajeNombre.charAt(0).toUpperCase();

    // Header
    _setImgSrc(
        document.getElementById('headerHiroImage'),
        document.getElementById('headerHiroFallback'),
        avatarUrl, personajeNombre, inicial
    );
    const headerFallback = document.getElementById('headerHiroFallback');
    if (headerFallback) headerFallback.textContent = inicial;
    const headerNameEl = document.querySelector('.hiro-name');
    if (headerNameEl) headerNameEl.textContent = personajeNombre;

    // Sidebar
    _setImgSrc(
        document.getElementById('sidebarHiroImage'),
        document.getElementById('sidebarHiroFallback'),
        avatarUrl, personajeNombre, inicial
    );
    const sidebarFallback = document.getElementById('sidebarHiroFallback');
    if (sidebarFallback) sidebarFallback.textContent = inicial;
    const sidebarName = document.querySelector('.sidebar-avatar-name');
    if (sidebarName) sidebarName.textContent = personajeNombre;

    // Typing indicator
    _setImgSrc(
        document.querySelector('.typing-indicator .avatar-image'),
        document.querySelector('.typing-indicator .avatar-fallback'),
        avatarUrl, personajeNombre, inicial
    );
    const typingFallback = document.querySelector('.typing-indicator .avatar-fallback');
    if (typingFallback) typingFallback.textContent = inicial;

    // Título de pestaña
    document.title = personajeNombre;

    // Sidebar header label
    const sidebarH3 = document.querySelector('.sidebar-header h3');
    if (sidebarH3) sidebarH3.textContent = `Lo que ${personajeNombre} sabe`;
}

function handleImageError(img) {
    img.style.display = 'none';
    const fallback = img.nextElementSibling;
    if (fallback && fallback.classList.contains('avatar-fallback')) {
        fallback.style.display = 'flex';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SIDEBAR
// ─────────────────────────────────────────────────────────────────────────────

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const isOpen  = sidebar.classList.toggle('open');
    if (overlay) overlay.classList.toggle('active', isOpen);
}

function closeSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    sidebar.classList.remove('open');
    if (overlay) overlay.classList.remove('active');
}

document.getElementById('openSidebar').addEventListener('click', toggleSidebar);
document.getElementById('closeSidebar').addEventListener('click', closeSidebar);

// El sidebar solo se cierra con el botón X

// ─────────────────────────────────────────────────────────────────────────────
// ACCIONES: LIMPIAR CHAT, IMPORTAR, CREAR, CAMBIAR PERSONAJE
// ─────────────────────────────────────────────────────────────────────────────

async function clearChat() {
    if (isWaiting) { mostrarNotificacion('La IA está generando. Esperá a que termine.', 'error'); return; }
    if (!confirm('¿Eliminar toda la conversación? Esta acción no se puede deshacer.')) return;
    try {
        const resp = await fetch('/api/historial', { method: 'DELETE' });
        if (resp.ok) {
            chatContainer.innerHTML = `
                <div class="message-wrapper hiro-message">
                    <div class="avatar">
                        <img src="${getAvatarUrl()}" alt="${personajeNombre}"
                             class="avatar-image" onerror="handleImageError(this)">
                        <div class="avatar-fallback">${personajeNombre.charAt(0).toUpperCase()}</div>
                    </div>
                    <div class="message-content">
                        <div class="message-bubble hiro-bubble">
                            <span class="action">*${personajeNombre} está listo para comenzar de nuevo.*</span>
                        </div>
                        <div class="message-time">Ahora</div>
                    </div>
                </div>`;
            messageIdCounter = 0;
        }
    } catch {
        mostrarNotificacion('Error al limpiar la conversación', 'error');
    }
}

document.getElementById('clearChatFromSettings').addEventListener('click', () => {
    clearChat();
    settingsDropdown.classList.remove('open');
});

document.getElementById('importarPersonajeBtn').addEventListener('click', abrirModalImportar);
document.getElementById('crearPersonajeBtn').addEventListener('click', () => {
    window.location.href = '/crear-personaje';
});
document.getElementById('cambiarPersonajeBtn').addEventListener('click', abrirModalCambiar);
document.getElementById('objetosBtn').addEventListener('click', () => {
    abrirModalObjetos();
    settingsDropdown.classList.remove('open');
});

// ─────────────────────────────────────────────────────────────────────────────
// MODAL: IMPORTAR PERSONAJE
// ─────────────────────────────────────────────────────────────────────────────

function abrirModalImportar() {
    if (isWaiting) { mostrarNotificacion('La IA está generando. Esperá a que termine.', 'error'); return; }
    document.getElementById('modalImportar').style.display = 'flex';
    settingsDropdown.classList.remove('open');
    document.getElementById('importJsonFile').addEventListener('change', previsualizarPersonaje, { once: true });
    document.getElementById('importImageFile').addEventListener('change', previsualizarImagenSuelta, { once: true });
}

function cerrarModalImportar() {
    document.getElementById('modalImportar').style.display = 'none';
    document.getElementById('importJsonFile').value  = '';
    document.getElementById('importImageFile').value = '';
    document.getElementById('importPreview').style.display = 'none';
}

function previsualizarPersonaje(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        try {
            const data   = JSON.parse(ev.target.result);
            const nombre = data.data?.name || 'Personaje';
            const img    = data.data?.avatar_image || data.data?.avatar || '';
            document.getElementById('importPreviewNombre').textContent = nombre;
            const previewImg = document.getElementById('importPreviewImg');
            if (img) {
                previewImg.src = img.startsWith('data:') ? img : `data:image/jpeg;base64,${img}`;
                previewImg.style.display = 'block';
            } else {
                previewImg.style.display = 'none';
            }
            document.getElementById('importPreview').style.display = 'block';
        } catch { /* JSON inválido, silencioso */ }
    };
    reader.readAsText(file);
}

function previsualizarImagenSuelta(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = ev => {
        const previewImg = document.getElementById('importPreviewImg');
        previewImg.src   = ev.target.result;
        previewImg.style.display = 'block';
        document.getElementById('importPreview').style.display = 'block';
    };
    reader.readAsDataURL(file);
}

async function confirmarImportacion() {
    const jsonFile = document.getElementById('importJsonFile').files[0];
    if (!jsonFile) { mostrarNotificacion('Seleccioná un archivo JSON', 'error'); return; }

    const formData = new FormData();
    formData.append('json_file', jsonFile);
    const imgFile = document.getElementById('importImageFile').files[0];
    if (imgFile) formData.append('imagen', imgFile);

    try {
        const resp = await fetch('/api/personajes/importar', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.success) {
            mostrarNotificacion(`✅ ${data.nombre} importado`, 'success');
            cerrarModalImportar();
        } else {
            mostrarNotificacion(data.error || 'Error al importar', 'error');
        }
    } catch {
        mostrarNotificacion('Error de conexión', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL: CAMBIAR PERSONAJE
// ─────────────────────────────────────────────────────────────────────────────

function abrirModalCambiar() {
    if (isWaiting) { mostrarNotificacion('La IA está generando. Esperá a que termine.', 'error'); return; }
    document.getElementById('modalCambiar').style.display = 'flex';
    settingsDropdown.classList.remove('open');
    cargarListaPersonajes();
}

function cerrarModalCambiar() {
    document.getElementById('modalCambiar').style.display = 'none';
}

async function cargarListaPersonajes() {
    try {
        const resp = await fetch('/api/personajes');
        const lista= await resp.json();
        const el   = document.getElementById('listaPersonajes');

        if (!lista.length) {
            el.innerHTML = '<p style="color:var(--text-secondary)">No hay personajes instalados.</p>';
            return;
        }

        el.innerHTML = lista.map(p => `
            <div class="personaje-card${p.activo ? ' activo' : ''}" style="
                display:flex;align-items:center;gap:12px;padding:12px;
                background:var(--bg-secondary);border-radius:10px;
                border:2px solid ${p.activo ? 'var(--accent)' : 'var(--border)'};
                cursor:${p.activo ? 'default' : 'pointer'};transition:border-color 0.2s"
                ${p.activo ? '' : `onclick="cambiarAPersonaje('${p.id}')"`}>
                <img src="/api/personajes/${p.id}/avatar"
                     style="width:44px;height:44px;border-radius:50%;object-fit:cover;border:2px solid var(--border)"
                     onerror="this.style.display='none'">
                <div style="flex:1">
                    <div style="font-weight:600">${p.nombre}</div>
                    <div style="font-size:0.75rem;color:var(--text-secondary);font-family:monospace">${p.id}</div>
                </div>
                ${p.activo ? '<span style="font-size:0.7rem;color:var(--accent);font-family:monospace">● ACTIVO</span>' : ''}
                ${!p.activo ? `
                    <button onclick="event.stopPropagation();eliminarPersonaje('${p.id}','${p.nombre}')"
                        style="background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:4px">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"></polyline>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                        </svg>
                    </button>` : ''}
            </div>`).join('');
    } catch {
        mostrarNotificacion('Error cargando personajes', 'error');
    }
}

async function cambiarAPersonaje(pid) {
    if (isWaiting) {
        mostrarNotificacion('La IA está generando una respuesta. Esperá a que termine.', 'error');
        return;
    }
    try {
        const resp = await fetch('/api/personajes/cambiar', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ id: pid }),
        });
        const data = await resp.json();
        if (data.success) {
            personajeActualId = pid;
            personajeNombre   = data.nombre;
            actualizarUIPersonaje();
            aplicarColoresPersonaje(pid);   // ← aplicar colores del nuevo personaje
            cerrarModalCambiar();
            chatContainer.innerHTML = '';
            messageIdCounter = 0;
            // Resetear fondo de escenario y luego cargar el del nuevo personaje
            aplicarFondoEscenario('', '');
            await cargarEscenarioActivo();
            await loadHistory();
            await loadStats();
            await actualizarModoBadge();
            // Recargar expresiones del nuevo personaje y actualizar el widget
            _expresionAbierta = false;
            document.getElementById('expresionPanel')?.classList.remove('abierto');
            document.getElementById('expresionToggle')?.classList.remove('abierto');
            document.getElementById('expresionWidget')?.classList.remove('sin-expresion');
            const _eImg = document.getElementById('expresionImg');
            if (_eImg) { _eImg.removeAttribute('src'); _eImg.style.display = 'none'; }
            await cargarExpresionesCache();
            await mostrarExpresionDefault();
            mostrarNotificacion(`Cambiado a ${data.nombre}`, 'success');
        } else {
            mostrarNotificacion(data.error || 'Error al cambiar', 'error');
        }
    } catch {
        mostrarNotificacion('Error de conexión', 'error');
    }
}

async function eliminarPersonaje(pid, nombre) {
    if (!confirm(`¿Eliminar a ${nombre}? Se borrarán todos sus datos.`)) return;
    try {
        const resp = await fetch(`/api/personajes/${pid}`, { method: 'DELETE' });
        const data = await resp.json();
        if (data.success) {
            mostrarNotificacion(`${nombre} eliminado`, 'success');
            cargarListaPersonajes();
        } else {
            mostrarNotificacion(data.error || 'Error al eliminar', 'error');
        }
    } catch {
        mostrarNotificacion('Error de conexión', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MEMORIA: EDITAR / ELIMINAR HECHOS
// ─────────────────────────────────────────────────────────────────────────────

async function editarHecho(hechoId) {
    try {
        const resp  = await fetch(`/api/memoria/hecho/${hechoId}`);
        const hecho = await resp.json();
        if (hecho.error) { mostrarNotificacion('No se pudo cargar el hecho', 'error'); return; }

        const modal = document.createElement('div');
        modal.className = 'modal-edicion';
        modal.innerHTML = `
            <div class="modal-contenido">
                <div class="modal-header">
                    <h3>Editar información</h3>
                    <button class="modal-cerrar" onclick="cerrarModalEdicion()">×</button>
                </div>
                <div class="modal-body">
                    <div class="form-group">
                        <label>Categoría:</label>
                        <input type="text" id="edit-categoria" value="${hecho.categoria}">
                    </div>
                    <div class="form-group">
                        <label>Etiqueta:</label>
                        <input type="text" id="edit-clave" value="${hecho.clave}">
                    </div>
                    <div class="form-group">
                        <label>Valor:</label>
                        <input type="text" id="edit-valor" value="${hecho.valor}">
                    </div>
                    <div class="form-group">
                        <label>Contexto (opcional):</label>
                        <textarea id="edit-contexto" rows="3">${hecho.contexto || ''}</textarea>
                    </div>
                    <div class="form-group">
                        <label>Confianza (1-100):</label>
                        <input type="number" id="edit-confianza" value="${hecho.confianza}" min="1" max="100">
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn-cancelar" onclick="cerrarModalEdicion()">Cancelar</button>
                    <button class="btn-guardar" onclick="guardarEdicionHecho(${hechoId})">Guardar</button>
                </div>
            </div>`;
        document.body.appendChild(modal);
        modal.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModalEdicion(); });
        setTimeout(() => document.getElementById('edit-categoria').focus(), 100);
    } catch {
        mostrarNotificacion('Error al cargar el hecho', 'error');
    }
}

async function guardarEdicionHecho(hechoId) {
    const datos = {
        categoria: document.getElementById('edit-categoria').value.trim(),
        clave    : document.getElementById('edit-clave').value.trim(),
        valor    : document.getElementById('edit-valor').value.trim(),
        contexto : document.getElementById('edit-contexto').value.trim(),
        confianza: parseInt(document.getElementById('edit-confianza').value),
    };
    if (!datos.categoria || !datos.clave || !datos.valor) {
        mostrarNotificacion('Categoría, etiqueta y valor son obligatorios', 'error');
        return;
    }
    try {
        const resp = await fetch(`/api/memoria/hecho/${hechoId}`, {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify(datos),
        });
        const r = await resp.json();
        if (r.success) {
            mostrarNotificacion('Información actualizada', 'success');
            cerrarModalEdicion();
            loadPerfil();
        } else {
            mostrarNotificacion('Error al guardar: ' + r.error, 'error');
        }
    } catch {
        mostrarNotificacion('Error al guardar los cambios', 'error');
    }
}

function cerrarModalEdicion() {
    const modal = document.querySelector('.modal-edicion');
    if (modal) modal.remove();
}

async function eliminarHecho(hechoId) {
    if (!confirm('¿Eliminar esta información?')) return;
    try {
        const resp = await fetch(`/api/memoria/hecho/${hechoId}`, { method: 'DELETE' });
        const r    = await resp.json();
        if (r.success) { mostrarNotificacion('Información eliminada', 'success'); loadPerfil(); }
    } catch {
        mostrarNotificacion('Error al eliminar', 'error');
    }
}

async function eliminarCategoria(categoria) {
    if (!confirm(`¿Eliminar TODA la categoría "${categoria}"?`)) return;
    try {
        const resp = await fetch(`/api/memoria/categoria/${encodeURIComponent(categoria)}`, { method: 'DELETE' });
        const r    = await resp.json();
        if (r.success) { mostrarNotificacion(r.mensaje, 'success'); loadPerfil(); }
    } catch {
        mostrarNotificacion('Error al eliminar la categoría', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// SÍNTESIS: ELIMINAR (la edición ahora es inline — ver activarEdicionSintesisInline)
// ─────────────────────────────────────────────────────────────────────────────

// Alias por compatibilidad con cualquier referencia antigua
function editarSintesis(sid) { activarEdicionSintesisInline(sid); }

async function eliminarSintesis(sid) {
    if (!confirm('¿Eliminar esta síntesis? Se puede regenerar después.')) return;
    try {
        const resp = await fetch(`/api/sintesis/${sid}`, { method: 'DELETE' });
        const r    = await resp.json();
        if (r.success) { mostrarNotificacion('Síntesis eliminada', 'success'); loadPerfil(); }
    } catch {
        mostrarNotificacion('Error al eliminar', 'error');
    }
}

function confirmarLimpiarTodo() {
    const conf = prompt('Esta acción eliminará TODA la información.\nEscribí "ELIMINAR TODO" para confirmar:');
    if (conf === 'ELIMINAR TODO') limpiarTodaMemoria();
    else if (conf !== null) mostrarNotificacion('Texto de confirmación incorrecto. No se eliminó nada.', 'info');
}

async function limpiarTodaMemoria() {
    try {
        const resp = await fetch('/api/memoria/limpiar-todo', { method: 'DELETE' });
        const r    = await resp.json();
        if (r.success) { mostrarNotificacion(r.mensaje, 'success'); loadPerfil(); }
    } catch {
        mostrarNotificacion('Error al limpiar la memoria', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// NOTIFICACIONES
// ─────────────────────────────────────────────────────────────────────────────

function mostrarNotificacion(mensaje, tipo = 'info') {
    const notif = document.createElement('div');
    notif.className = `notificacion notificacion-${tipo}`;
    notif.textContent = mensaje;
    document.body.appendChild(notif);
    setTimeout(() => notif.classList.add('mostrar'), 10);
    setTimeout(() => {
        notif.classList.remove('mostrar');
        setTimeout(() => notif.remove(), 300);
    }, 4000);
}

function mostrarNotificacionEvento(nombre, descripcion) {
    const notif = document.createElement('div');
    notif.style.cssText = `
        position:fixed;top:80px;left:50%;transform:translateX(-50%) translateY(-10px);
        background:var(--bg-card);border:2px solid var(--accent);border-radius:12px;
        padding:16px 24px;z-index:1000;box-shadow:0 8px 32px rgba(201,168,76,0.2);
        display:flex;align-items:center;gap:12px;
        opacity:0;transition:all 0.3s ease;max-width:90vw;`;
    notif.innerHTML = `
        <span style="font-size:1.4rem">✦</span>
        <div>
            <div style="font-weight:600;color:var(--accent);font-size:0.95rem">${nombre}</div>
            <div style="font-size:0.82rem;color:var(--text-secondary);margin-top:2px">${descripcion}</div>
        </div>
        <button onclick="this.parentElement.remove()" style="
            background:none;border:none;color:var(--text-secondary);
            cursor:pointer;font-size:1.2rem;padding:0 0 0 8px">×</button>`;
    document.body.appendChild(notif);
    setTimeout(() => {
        notif.style.opacity = '1';
        notif.style.transform = 'translateX(-50%) translateY(0)';
    }, 10);
    setTimeout(() => {
        notif.style.opacity = '0';
        setTimeout(() => notif.remove(), 300);
    }, 8000);
}

// ─────────────────────────────────────────────────────────────────────────────
// FONDO DE ESCENARIO
// ─────────────────────────────────────────────────────────────────────────────

function aplicarFondoEscenario(color, nombre) {
    const bg       = document.getElementById('sceneBg');
    const slot     = document.getElementById('headerEscenarioSlot');
    const nombreEl = document.getElementById('headerEscenarioNombre');

    if (!bg) return;

    if (!color || !nombre) {
        bg.style.opacity = '0';
        bg.style.backgroundColor = 'transparent';
        if (slot) slot.style.display = 'none';
        return;
    }

    bg.style.backgroundColor = color;
    bg.style.opacity = '0.22';

    if (slot && nombreEl) {
        nombreEl.textContent = ` ${nombre}`;
        slot.style.display = 'inline-flex';
    }
}

async function cargarEscenarioActivo() {
    try {
        const resp = await fetch('/api/escenario-activo');
        const data = await resp.json();
        if (data.color) aplicarFondoEscenario(data.color, data.nombre);
    } catch { /* silencioso */ }
}

// ─────────────────────────────────────────────────────────────────────────────
// MENSAJES DESTACADOS
// ─────────────────────────────────────────────────────────────────────────────

let mensajesDestacados = [];
try { mensajesDestacados = JSON.parse(localStorage.getItem('hiro-destacados') || '[]'); } catch { mensajesDestacados = []; }

function guardarDestacados() {
    try { localStorage.setItem('hiro-destacados', JSON.stringify(mensajesDestacados)); } catch {}
}

function toggleDestacado(msgId, texto, esHiro) {
    const idx = mensajesDestacados.findIndex(d => d.id === msgId);
    if (idx >= 0) {
        mensajesDestacados.splice(idx, 1);
        guardarDestacados();
        mostrarNotificacion('Destacado quitado', 'info');
    } else {
        mensajesDestacados.push({
            id: msgId, texto: texto.substring(0, 300),
            esHiro, fecha: new Date().toLocaleString('es-AR')
        });
        guardarDestacados();
        mostrarNotificacion('⭐ Mensaje destacado', 'success');
    }
}

function abrirDestacados() {
    document.getElementById('modalDestacados').style.display = 'flex';
    settingsDropdown.classList.remove('open');
    const lista = document.getElementById('listaDestacados');
    if (!mensajesDestacados.length) {
        lista.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">Todavía no hay mensajes destacados. Abrí el menú ⋮ de cualquier mensaje y elegí ⭐ Destacar.</p>';
        return;
    }
    lista.innerHTML = mensajesDestacados.slice().reverse().map(d => `
        <div style="background:var(--bg-secondary);border-radius:8px;padding:10px 12px;
            border-left:3px solid ${d.esHiro ? 'var(--accent)' : 'var(--border)'}">
            <div style="font-size:0.7rem;color:var(--text-secondary);font-family:monospace;margin-bottom:4px">
                ${d.esHiro ? personajeNombre : 'Vos'} · ${d.fecha}
            </div>
            <div style="font-size:0.88rem">${d.texto}${d.texto.length >= 300 ? '...' : ''}</div>
            <button onclick="quitarDestacadoPorId(${d.id})"
                style="margin-top:6px;background:none;border:none;color:var(--text-secondary);
                cursor:pointer;font-size:0.72rem;font-family:monospace">✕ quitar</button>
        </div>`).join('');
}

function quitarDestacadoPorId(id) {
    mensajesDestacados = mensajesDestacados.filter(d => d.id !== id);
    guardarDestacados();
    abrirDestacados();
}

// ─────────────────────────────────────────────────────────────────────────────
// BUSCAR MENSAJES
// ─────────────────────────────────────────────────────────────────────────────

function abrirBuscar() {
    document.getElementById('modalBuscar').style.display = 'flex';
    settingsDropdown.classList.remove('open');
    setTimeout(() => document.getElementById('buscarInput').focus(), 100);
}

function buscarMensajes() {
    const query = document.getElementById('buscarInput').value.toLowerCase().trim();
    const container = document.getElementById('buscarResultados');

    if (!query) {
        container.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">Escribí algo para buscar...</p>';
        return;
    }

    const wrappers = document.querySelectorAll('#chatContainer .message-wrapper');
    const resultados = [];
    wrappers.forEach(wrapper => {
        const bubble = wrapper.querySelector('.message-bubble');
        if (!bubble) return;
        const texto = bubble.textContent;
        if (texto.toLowerCase().includes(query)) {
            resultados.push({
                texto,
                esHiro: wrapper.classList.contains('hiro-message'),
                tiempo: wrapper.querySelector('.message-time')?.textContent || '',
                el: wrapper
            });
        }
    });

    window._buscarEls = resultados.map(r => r.el);

    if (!resultados.length) {
        container.innerHTML = `<p style="color:var(--text-secondary);font-size:0.85rem">Sin resultados para "${query}"</p>`;
        return;
    }

    const esc = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    container.innerHTML = resultados.map((r, i) => `
        <div onclick="irAMensaje(${i})" style="
            background:var(--bg-secondary);border-radius:8px;padding:10px 12px;cursor:pointer;
            border-left:3px solid ${r.esHiro ? 'var(--accent)' : 'var(--border)'};
            transition:background 0.15s"
            onmouseover="this.style.background='var(--bg-card)'"
            onmouseout="this.style.background='var(--bg-secondary)'">
            <div style="font-size:0.7rem;color:var(--text-secondary);font-family:monospace;margin-bottom:3px">
                ${r.esHiro ? personajeNombre : 'Vos'} · ${r.tiempo}
            </div>
            <div style="font-size:0.88rem">${
                r.texto.substring(0, 200).replace(
                    new RegExp(`(${esc})`, 'gi'),
                    '<mark>$1</mark>'
                )
            }${r.texto.length > 200 ? '...' : ''}</div>
        </div>`).join('');
}

function irAMensaje(idx) {
    const el = window._buscarEls?.[idx];
    if (!el) return;
    document.getElementById('modalBuscar').style.display = 'none';
    setTimeout(() => {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.style.outline = '2px solid var(--accent)';
        el.style.borderRadius = '8px';
        setTimeout(() => { el.style.outline = ''; el.style.borderRadius = ''; }, 2000);
    }, 200);
}

// ─────────────────────────────────────────────────────────────────────────────
// EVENT LISTENERS DE INPUT
// ─────────────────────────────────────────────────────────────────────────────

sendButton.addEventListener('click', sendMessage);

messageInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

messageInput.addEventListener('input', () => autoResize(messageInput));

// ─────────────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', async () => {
    initTheme();
    await cargarPersonajeActivo();
    await loadHistory();
    await loadStats();
    await cargarEscenarioActivo();
    await cargarExpresionesCache();
    await mostrarExpresionDefault();
    messageInput.focus();
    setInterval(loadStats, 30000);

    document.getElementById('buscarMensajesBtn')?.addEventListener('click', abrirBuscar);
    document.getElementById('destacadosBtn')?.addEventListener('click', abrirDestacados);
    document.getElementById('nuevo-escenario-color')?.addEventListener('input', function() {
        document.getElementById('esc-color-preview').style.background = this.value;
    });

    document.getElementById('exportarChatBtn')?.addEventListener('click', () => {
        exportarChat(); settingsDropdown.classList.remove('open');
    });
    document.getElementById('exportarMemoriaBtn')?.addEventListener('click', () => {
        exportarMemoria(); settingsDropdown.classList.remove('open');
    });
    document.getElementById('importarChatBtn')?.addEventListener('click', () => {
        abrirModalImportarChat(); settingsDropdown.classList.remove('open');
    });
    document.getElementById('importarMemoriaBtn')?.addEventListener('click', () => {
        abrirModalImportarMemoria(); settingsDropdown.classList.remove('open');
    });

    // El avatar del sidebar ahora es un <a> que navega a /editar_personaje
    // document.getElementById('editarFichaBtn') ya no existe en index.html
});

// ─────────────────────────────────────────────────────────────────────────────
// FICHA Y AVATAR — movidos a /editar_personaje
// ─────────────────────────────────────────────────────────────────────────────
// Toda la lógica de cargarFicha, abrirModalEditarFicha, guardarFicha,
// abrirModalAvatar, cerrarModalAvatar, verImagenCompleta y subirNuevoAvatar
// vive ahora en editar_personaje.html para mantener index.html liviano.

// ─────────────────────────────────────────────────────────────────────────────
// EXPORTAR / IMPORTAR CHAT Y MEMORIA
// ─────────────────────────────────────────────────────────────────────────────

function exportarChat() {
    const a = document.createElement('a');
    a.href = '/api/exportar/chat';
    a.click();
}

function exportarMemoria() {
    const a = document.createElement('a');
    a.href = '/api/exportar/memoria';
    a.click();
}

// — Importar chat —

function abrirModalImportarChat() {
    document.getElementById('importChatFile').value = '';
    document.getElementById('modalImportarChat').style.display = 'flex';
}

function cerrarModalImportarChat() {
    document.getElementById('modalImportarChat').style.display = 'none';
}

async function confirmarImportarChat() {
    const file = document.getElementById('importChatFile').files[0];
    if (!file) { mostrarNotificacion('Seleccioná un archivo primero', 'error'); return; }

    const formData = new FormData();
    formData.append('archivo', file);

    try {
        const resp = await fetch('/api/importar/chat', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.success) {
            mostrarNotificacion(`✅ ${data.importados} mensajes importados`, 'success');
            cerrarModalImportarChat();
            // Recargar el chat para mostrar los mensajes nuevos
            chatContainer.innerHTML = '';
            messageIdCounter = 0;
            await loadHistory();
        } else {
            mostrarNotificacion('Error: ' + data.error, 'error');
        }
    } catch {
        mostrarNotificacion('Error al importar el chat', 'error');
    }
}

// — Importar memoria —

function abrirModalImportarMemoria() {
    document.getElementById('importMemoriaFile').value = '';
    document.getElementById('modalImportarMemoria').style.display = 'flex';
}

function cerrarModalImportarMemoria() {
    document.getElementById('modalImportarMemoria').style.display = 'none';
}

async function confirmarImportarMemoria() {
    const file = document.getElementById('importMemoriaFile').files[0];
    if (!file) { mostrarNotificacion('Seleccioná un archivo primero', 'error'); return; }

    const formData = new FormData();
    formData.append('archivo', file);

    try {
        const resp = await fetch('/api/importar/memoria', { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.success) {
            mostrarNotificacion(
                `✅ ${data.hechos} hechos y ${data.sintesis} síntesis importados`, 'success'
            );
            cerrarModalImportarMemoria();
        } else {
            mostrarNotificacion('Error: ' + data.error, 'error');
        }
    } catch {
        mostrarNotificacion('Error al importar la memoria', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL OBJETOS
// ─────────────────────────────────────────────────────────────────────────────

function abrirModalObjetos() {
    document.getElementById('modalObjetos').style.display = 'flex';
    cargarObjetos();
}

function cerrarModalObjetos() {
    document.getElementById('modalObjetos').style.display = 'none';
}

async function cargarObjetos() {
    try {
        const resp    = await fetch('/api/objetos');
        const objetos = await resp.json();
        const lista   = document.getElementById('listaObjetos');

        if (!objetos.length) {
            lista.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">No hay objetos creados todavía.</p>';
            return;
        }

        const iconoPoseedor = { usuario: '🧑', personaje: '🤖' };
        const labelPoseedor = { usuario: 'Usuario', personaje: 'Personaje' };

        lista.innerHTML = objetos.map(o => `
            <div style="background:var(--bg-secondary);border-radius:10px;
                border:2px solid ${o.activo ? 'var(--accent)' : 'var(--border)'};overflow:hidden">
                <div style="display:flex;align-items:flex-start;gap:10px;padding:12px">
                    <span style="font-size:1.2rem;flex-shrink:0">${iconoPoseedor[o.poseedor] || '📦'}</span>
                    <div style="flex:1;min-width:0">
                        <div style="font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                            ${o.nombre}
                            <span style="font-size:0.68rem;font-family:monospace;color:var(--text-secondary);
                                background:var(--bg-primary);padding:2px 8px;border-radius:4px">
                                ${labelPoseedor[o.poseedor] || o.poseedor}
                            </span>
                            ${o.activo ? '<span style="font-size:0.68rem;color:var(--accent);font-family:monospace">● EN ESCENA</span>' : '<span style="font-size:0.68rem;color:var(--text-secondary);font-family:monospace">○ inactivo</span>'}
                        </div>
                        <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:3px">${o.descripcion}</div>
                        <div style="font-size:0.8rem;color:var(--text-soft,var(--text-secondary));margin-top:4px;
                            font-style:italic;border-left:2px solid var(--border);padding-left:8px">
                            ${o.propiedades}
                        </div>
                    </div>
                    <div style="display:flex;gap:6px;flex-shrink:0">
                        <button onclick="toggleObjeto(${o.id}, this)"
                            title="${o.activo ? 'Sacar de escena' : 'Poner en escena'}"
                            style="padding:5px 10px;background:${o.activo ? 'var(--bg-primary)' : 'var(--accent-dim)'};
                            border:1px solid ${o.activo ? 'var(--border)' : 'var(--accent)'};
                            color:${o.activo ? 'var(--text-secondary)' : 'var(--accent)'};
                            border-radius:6px;cursor:pointer;font-size:0.72rem;font-family:monospace">
                            ${o.activo ? '○ Quitar' : '● Activar'}
                        </button>
                        <button onclick="eliminarObjeto(${o.id})" style="
                            background:none;border:none;color:var(--text-secondary);cursor:pointer;padding:4px">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
            </div>`).join('');
    } catch { mostrarNotificacion('Error cargando objetos', 'error'); }
}

async function toggleObjeto(oid, btn) {
    try {
        const resp = await fetch(`/api/objetos/${oid}/toggle`, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            cargarObjetos();
            mostrarNotificacion(data.activo ? '📦 Objeto en escena' : 'Objeto quitado de escena', 'success');
        }
    } catch { mostrarNotificacion('Error al cambiar objeto', 'error'); }
}

async function eliminarObjeto(oid) {
    if (!confirm('¿Eliminar este objeto?')) return;
    try {
        await fetch(`/api/objetos/${oid}`, { method: 'DELETE' });
        cargarObjetos();
        mostrarNotificacion('Objeto eliminado', 'success');
    } catch { mostrarNotificacion('Error al eliminar', 'error'); }
}

async function generarObjetoIA() {
    const nombre = document.getElementById('nuevo-objeto-nombre').value.trim();
    const idea   = document.getElementById('nuevo-objeto-desc').value.trim();
    if (!nombre || !idea) {
        mostrarNotificacion('Completá el nombre y tu idea primero', 'error');
        return;
    }
    const btn = document.getElementById('btn-generar-objeto');
    btn.textContent = '⏳ Generando...';
    btn.disabled = true;
    try {
        const resp = await fetch('/api/objetos/generar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, idea }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-objeto-desc').value  = data.descripcion;
            document.getElementById('nuevo-objeto-props').value = data.propiedades;
            mostrarNotificacion('✨ Objeto generado — editalo si querés', 'success');
        } else {
            mostrarNotificacion(data.error || 'Error generando', 'error');
        }
    } catch { mostrarNotificacion('Error de conexión', 'error'); }
    finally {
        btn.textContent = '✨ Generar con IA';
        btn.disabled = false;
    }
}

async function crearObjeto() {
    const nombre   = document.getElementById('nuevo-objeto-nombre').value.trim();
    const desc     = document.getElementById('nuevo-objeto-desc').value.trim();
    const props    = document.getElementById('nuevo-objeto-props').value.trim();
    const poseedor = document.querySelector('input[name="nuevo-obj-poseedor"]:checked')?.value || 'usuario';
    if (!nombre || !desc || !props) {
        mostrarNotificacion('Completá nombre, descripción y propiedades', 'error');
        return;
    }
    try {
        const resp = await fetch('/api/objetos', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ nombre, descripcion: desc, propiedades: props, poseedor }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-objeto-nombre').value = '';
            document.getElementById('nuevo-objeto-desc').value   = '';
            document.getElementById('nuevo-objeto-props').value  = '';
            document.querySelector('input[name="nuevo-obj-poseedor"][value="usuario"]').checked = true;
            cargarObjetos();
            mostrarNotificacion('📦 Objeto creado', 'success');
        }
    } catch { mostrarNotificacion('Error al crear objeto', 'error'); }
}

// ═══════════════════════════════════════════════════════════════════════════
// PERSONALIZAR CHAT — Colores de burbujas + acento por personaje o global
// ═══════════════════════════════════════════════════════════════════════════

const PC_DEFAULTS = {
    iaBg       : '#1a1230',
    iaBorder   : '#c9a84c',
    iaText     : '#f0f0f5',
    userBg     : '#1c1c23',
    userBorder : '#2e2e3e',
    userText   : '#c8c8d8',
    accent     : 'gold',
    fmtDialogue: '#f0f0f5',
    fmtAction  : '#8888a0',
    fmtThought : '#55556a',
};

function _pcStorageKey(scope) {
    return scope === 'personaje'
        ? `hiro-colors-pid-${personajeActualId}`
        : 'hiro-colors-general';
}

function _pcLoad(scope) {
    try {
        const raw = localStorage.getItem(_pcStorageKey(scope));
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function _pcSave(scope, data) {
    localStorage.setItem(_pcStorageKey(scope), JSON.stringify(data));
}

/** Aplica las variables CSS de burbujas y el tema de acento */
function _pcAplicar(cfg) {
    if (!cfg) return;
    const root = document.documentElement;
    if (cfg.iaBg)        root.style.setProperty('--bubble-ia-bg',      cfg.iaBg);
    if (cfg.iaBorder)    root.style.setProperty('--bubble-ia-border',  cfg.iaBorder);
    if (cfg.iaText)      root.style.setProperty('--bubble-ia-text',    cfg.iaText);
    if (cfg.userBg)      root.style.setProperty('--bubble-user-bg',    cfg.userBg);
    if (cfg.userBorder)  root.style.setProperty('--bubble-user-border',cfg.userBorder);
    if (cfg.userText)    root.style.setProperty('--bubble-user-text',  cfg.userText);
    if (cfg.fmtDialogue) root.style.setProperty('--format-dialogue',   cfg.fmtDialogue);
    if (cfg.fmtAction)   root.style.setProperty('--format-action',     cfg.fmtAction);
    if (cfg.fmtThought)  root.style.setProperty('--format-thought',    cfg.fmtThought);
    if (cfg.accent)      applyTheme(cfg.accent);
}

/**
 * Carga y aplica los colores del personaje activo.
 * Primero busca colores específicos del personaje; si no hay, usa los generales.
 * Se llama al iniciar y al cambiar de personaje.
 */
function aplicarColoresPersonaje(pid) {
    const porPersonaje = _pcLoad('personaje');  // usa personajeActualId actual
    const general      = _pcLoad('general');
    _pcAplicar(porPersonaje || general || PC_DEFAULTS);
}

/** Actualiza las previsualizaciones en vivo del modal */
function _pcActualizarPreviews() {
    const iaBg       = document.getElementById('pc-ia-bg')?.value;
    const iaBorder   = document.getElementById('pc-ia-border')?.value;
    const iaText     = document.getElementById('pc-ia-text')?.value;
    const userBg     = document.getElementById('pc-user-bg')?.value;
    const userBorder = document.getElementById('pc-user-border')?.value;
    const userText   = document.getElementById('pc-user-text')?.value;

    const iaBgPrev = document.getElementById('pc-ia-bg-preview');
    if (iaBgPrev) {
        iaBgPrev.style.background  = iaBg;
        iaBgPrev.style.borderColor = iaBorder;
        iaBgPrev.style.color       = iaText;
    }
    const iaBorderPrev = document.getElementById('pc-ia-border-preview');
    if (iaBorderPrev) {
        iaBorderPrev.style.background  = iaBg;
        iaBorderPrev.style.borderColor = iaBorder;
        iaBorderPrev.style.color       = iaText;
    }
    const userBgPrev = document.getElementById('pc-user-bg-preview');
    if (userBgPrev) {
        userBgPrev.style.background  = userBg;
        userBgPrev.style.borderColor = userBorder;
        userBgPrev.style.color       = userText;
    }
    const userBorderPrev = document.getElementById('pc-user-border-preview');
    if (userBorderPrev) {
        userBorderPrev.style.background  = userBg;
        userBorderPrev.style.borderColor = userBorder;
        userBorderPrev.style.color       = userText;
    }

    // Live preview de colores de formato
    const dlg = document.getElementById('pc-fmt-dialogue')?.value;
    const act = document.getElementById('pc-fmt-action')?.value;
    const tho = document.getElementById('pc-fmt-thought')?.value;
    const dlgPrev = document.getElementById('pc-fmt-dialogue-preview');
    const actPrev = document.getElementById('pc-fmt-action-preview');
    const thoPrev = document.getElementById('pc-fmt-thought-preview');
    if (dlgPrev && dlg) dlgPrev.style.color = dlg;
    if (actPrev && act) actPrev.style.color = act;
    if (thoPrev && tho) thoPrev.style.color = tho;
}

function abrirPersonalizarChat() {
    // Cerrar el dropdown de settings
    document.getElementById('settingsDropdown')?.classList.remove('open');

    // Determinar qué config mostrar: personaje > general > defaults
    const cfg = _pcLoad('personaje') || _pcLoad('general') || PC_DEFAULTS;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val; };
    set('pc-ia-bg',       cfg.iaBg       || PC_DEFAULTS.iaBg);
    set('pc-ia-border',   cfg.iaBorder   || PC_DEFAULTS.iaBorder);
    set('pc-ia-text',     cfg.iaText     || PC_DEFAULTS.iaText);
    set('pc-user-bg',     cfg.userBg     || PC_DEFAULTS.userBg);
    set('pc-user-border', cfg.userBorder || PC_DEFAULTS.userBorder);
    set('pc-user-text',   cfg.userText   || PC_DEFAULTS.userText);
    set('pc-fmt-dialogue', cfg.fmtDialogue || PC_DEFAULTS.fmtDialogue);
    set('pc-fmt-action',   cfg.fmtAction   || PC_DEFAULTS.fmtAction);
    set('pc-fmt-thought',  cfg.fmtThought  || PC_DEFAULTS.fmtThought);

    // Marcar el color de acento activo
    const accentActual = localStorage.getItem('hiro-theme') || 'gold';
    document.querySelectorAll('.color-option').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.color === accentActual);
    });

    // Conectar live previews
    ['pc-ia-bg','pc-ia-border','pc-ia-text','pc-user-bg','pc-user-border','pc-user-text',
     'pc-fmt-dialogue','pc-fmt-action','pc-fmt-thought'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener('input', _pcActualizarPreviews);
    });

    _pcActualizarPreviews();
    document.getElementById('modalPersonalizarChat').style.display = 'flex';
}

function cerrarPersonalizarChat() {
    document.getElementById('modalPersonalizarChat').style.display = 'none';
}

function guardarColoresChat(scope) {
    const accentActual = localStorage.getItem('hiro-theme') || 'gold';
    const cfg = {
        iaBg       : document.getElementById('pc-ia-bg')?.value       || PC_DEFAULTS.iaBg,
        iaBorder   : document.getElementById('pc-ia-border')?.value    || PC_DEFAULTS.iaBorder,
        iaText     : document.getElementById('pc-ia-text')?.value      || PC_DEFAULTS.iaText,
        userBg     : document.getElementById('pc-user-bg')?.value      || PC_DEFAULTS.userBg,
        userBorder : document.getElementById('pc-user-border')?.value  || PC_DEFAULTS.userBorder,
        userText   : document.getElementById('pc-user-text')?.value    || PC_DEFAULTS.userText,
        fmtDialogue: document.getElementById('pc-fmt-dialogue')?.value || PC_DEFAULTS.fmtDialogue,
        fmtAction  : document.getElementById('pc-fmt-action')?.value   || PC_DEFAULTS.fmtAction,
        fmtThought : document.getElementById('pc-fmt-thought')?.value  || PC_DEFAULTS.fmtThought,
        accent     : accentActual,
    };
    _pcSave(scope, cfg);
    _pcAplicar(cfg);
    cerrarPersonalizarChat();
    const msg = scope === 'personaje'
        ? `✅ Colores guardados para ${personajeNombre}`
        : '✅ Colores guardados en general';
    mostrarNotificacion(msg, 'success');
}
// ─────────────────────────────────────────────────────────────────────────────
// SISTEMA DE EXPRESIONES
// ─────────────────────────────────────────────────────────────────────────────

async function cargarExpresionesCache() {
    try {
        const resp = await fetch('/api/expresiones');
        if (!resp.ok) throw new Error();
        _expresionesCache = await resp.json();
    } catch {
        _expresionesCache = [];
    }
}

/**
 * Núcleo del sistema. texto=null → mostrar default sin detectar patrones.
 * texto=string → buscar patrón coincidente, fallback a default.
 */
async function _mostrarExpresion(texto) {
    const widget = document.getElementById('expresionWidget');
    const img    = document.getElementById('expresionImg');
    const sinImg = document.getElementById('expresionSinImg');
    const nombre = document.getElementById('expresionNombre');

    // Sin ninguna expresión configurada → ocultar widget completo
    if (!_expresionesCache || !_expresionesCache.length) {
        widget.classList.add('sin-expresion');
        return;
    }

    let encontrada = null;

    // Solo buscar por patrón si viene con texto de mensaje
    if (texto) {
        const textoLower = texto.toLowerCase();
        for (const ex of _expresionesCache) {
            if (!ex.tiene_imagen) continue;
            const patrones = ex.patrones || [];
            if (patrones.length && patrones.some(p => textoLower.includes(p.toLowerCase()))) {
                encontrada = ex;
                break;
            }
        }
    }

    // Fallback: default (con o sin imagen), o la primera disponible
    if (!encontrada) {
        encontrada = _expresionesCache.find(e => e.es_default)
                  || _expresionesCache[0]
                  || null;
    }

    if (!encontrada) {
        widget.classList.add('sin-expresion');
        return;
    }

    // Widget visible y panel abierto siempre
    widget.classList.remove('sin-expresion');
    nombre.textContent = encontrada.nombre;

    if (!_expresionAbierta) {
        _expresionAbierta = true;
        document.getElementById('expresionPanel').classList.add('abierto');
        document.getElementById('expresionToggle').classList.add('abierto');
    }

    // Sin imagen → mostrar placeholder "Sin img"
    if (!encontrada.tiene_imagen) {
        img.removeAttribute('src');
        img.style.display    = 'none';
        sinImg.style.display = 'flex';
        return;
    }

    // Con imagen → cargar normalmente
    img.style.display    = 'block';
    sinImg.style.display = 'none';

    const url = `/api/expresiones/${encontrada.id}/imagen?t=${Date.now()}`;
    img.onerror = () => {
        console.error('[EXPR] img.onerror para:', img.src);
        img.onerror = null;
        img.removeAttribute('src');
        img.style.display    = 'none';
        sinImg.style.display = 'flex';
    };
    img.onload = () => { img.onerror = null; img.onload = null; };
    img.src = url;
}

/** Llamada al arrancar: muestra la expresión default sin analizar texto. */
async function mostrarExpresionDefault() {
    await _mostrarExpresion(null);
}

/** Llamada después de cada respuesta del personaje. */
async function detectarYMostrarExpresion(texto) {
    await _mostrarExpresion(texto);
}

function toggleExpresion() {
    _expresionAbierta = !_expresionAbierta;
    document.getElementById('expresionPanel').classList.toggle('abierto', _expresionAbierta);
    document.getElementById('expresionToggle').classList.toggle('abierto', _expresionAbierta);
}
// Los colores se aplican desde cargarPersonajeActivo() al iniciar
// y desde el cambio de personaje — no se necesita IIFE prematuro aquí.

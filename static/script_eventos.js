// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_EVENTOS.JS — Página de gestión de eventos
// ═══════════════════════════════════════════════════════════════════════════

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

function mostrarNotificacionEvento(nombre, descripcion, subtipo = 'evento') {
    const colores = {
        evento:      { border: 'var(--accent)',  icon: '✦',  glow: 'rgba(212,175,55,0.2)' },
        aviso:       { border: '#f59e0b',         icon: '⏰', glow: 'rgba(245,158,11,0.2)' },
        seguimiento: { border: '#60a5fa',          icon: '💬', glow: 'rgba(96,165,250,0.2)' },
    };
    const c = colores[subtipo] || colores.evento;

    const notif = document.createElement('div');
    notif.style.cssText = `
        position:fixed;top:80px;left:50%;transform:translateX(-50%) translateY(-10px);
        background:var(--bg-secondary,#1a1a20);border:2px solid ${c.border};border-radius:12px;
        padding:16px 24px;z-index:1000;box-shadow:0 8px 32px ${c.glow};
        display:flex;align-items:center;gap:12px;
        opacity:0;transition:all 0.3s ease;max-width:90vw;`;
    notif.innerHTML = `
        <span style="font-size:1.4rem">${c.icon}</span>
        <div>
            <div style="font-weight:600;color:${c.border};font-size:0.95rem">${nombre}</div>
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
// TEMA
// ─────────────────────────────────────────────────────────────────────────────

function initTheme() {
    const saved = localStorage.getItem('hiro-theme') || 'gold';
    document.documentElement.setAttribute('data-theme', saved);
}

// ─────────────────────────────────────────────────────────────────────────────
// CAMPO DISPARADOR DINÁMICO
// ─────────────────────────────────────────────────────────────────────────────

function actualizarCampoEvento() {
    const tipo  = document.getElementById('nuevo-evento-tipo').value;
    const input = document.getElementById('nuevo-evento-valor');
    if (tipo === 'fecha') {
        input.style.display = 'block';
        input.placeholder   = 'DD-MM (ej: 14-02)';
    } else if (tipo === 'mensajes') {
        input.style.display = 'block';
        input.placeholder   = 'Cantidad de mensajes (ej: 100)';
    } else {
        input.style.display = 'none';
        input.value = '';
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR EVENTOS
// ─────────────────────────────────────────────────────────────────────────────

async function cargarEventos() {
    try {
        const resp   = await fetch('/api/eventos');
        const eventos = await resp.json();
        const lista  = document.getElementById('listaEventos');

        if (!eventos.length) {
            lista.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">No hay eventos creados todavía. ¡Creá el primero abajo!</p>';
            return;
        }

        const iconoTipo = { fecha: '📅', mensajes: '💬', manual: '⚡' };
        const labelTipo = { fecha: 'Fecha', mensajes: 'Mensajes', manual: 'Manual' };

        lista.innerHTML = eventos.map(e => {
            const labelValor = e.valor ? `: ${e.valor}` : '';
            const labelHora  = e.hora  ? ` ${e.hora}` : '';
            const badgesExtra = [
                e.disparado         ? '<span class="badge-activo">✦ ACTIVO</span>' : '',
                e.aviso_disparado && !e.disparado ? '<span class="badge-aviso">⏰ Aviso enviado</span>' : '',
                e.seguimiento_disparado ? '<span class="badge-seguimiento">💬 Seguimiento enviado</span>' : '',
            ].join('');

            return `
            <div class="card-evento ${e.disparado ? 'disparado' : ''}">
                <div class="card-inner">
                    <span style="font-size:1.2rem;flex-shrink:0">${iconoTipo[e.tipo] || '⚡'}</span>
                    <div style="flex:1">
                        <div style="font-weight:600;display:flex;align-items:center;gap:8px;flex-wrap:wrap">
                            ${e.nombre}
                            <span class="badge-tipo">${labelTipo[e.tipo]}${labelValor}${labelHora}</span>
                            ${badgesExtra}
                        </div>
                        <div style="font-size:0.85rem;color:var(--text-secondary);margin-top:3px">${e.descripcion}</div>
                        ${e.aviso_dias > 0 || e.seguimiento ? `
                        <div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:6px">
                            ${e.aviso_dias > 0 ? `<span style="font-size:0.72rem;color:var(--text-secondary);font-family:var(--font-mono)">⏰ aviso ${e.aviso_dias}d antes</span>` : ''}
                            ${e.seguimiento  ? `<span style="font-size:0.72rem;color:var(--text-secondary);font-family:var(--font-mono)">💬 con seguimiento</span>` : ''}
                        </div>` : ''}
                    </div>
                    <div style="display:flex;gap:6px;flex-shrink:0;align-items:center">
                        ${!e.disparado
                            ? `<button class="btn-activar btn-disparar-ev"
                                data-eid="${e.id}"
                                data-nombre="${e.nombre.replace(/&/g,'&amp;').replace(/"/g,'&quot;')}">
                                ▶ Activar
                              </button>`
                            : `<button class="btn-reset" onclick="resetearEvento(${e.id})">↺ Reset</button>`
                        }
                        <button class="btn-delete" onclick="eliminarEvento(${e.id})">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                ${e.historia ? `<div class="card-historia">
                    💭 ${e.historia.substring(0,160)}${e.historia.length > 160 ? '...' : ''}
                </div>` : ''}
            </div>`;
        }).join('');

        lista.querySelectorAll('.btn-disparar-ev').forEach(btn => {
            btn.addEventListener('click', () => {
                dispararEvento(parseInt(btn.dataset.eid), btn.dataset.nombre);
            });
        });
    } catch {
        mostrarNotificacion('Error cargando eventos', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CREAR EVENTO
// ─────────────────────────────────────────────────────────────────────────────

async function generarEventoIA() {
    const nombre = document.getElementById('nuevo-evento-nombre').value.trim();
    const idea   = document.getElementById('nuevo-evento-desc').value.trim();
    if (!nombre || !idea) {
        mostrarNotificacion('Completá el nombre y escribí tu idea primero', 'error');
        return;
    }
    const btn = document.getElementById('btn-generar-evento');
    btn.textContent = '⏳ Generando...';
    btn.disabled = true;
    try {
        const resp = await fetch('/api/eventos/generar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, idea }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-evento-desc').value     = data.descripcion;
            document.getElementById('nuevo-evento-historia').value = data.historia;
            mostrarNotificacion('✨ Evento generado — editalo si querés', 'success');
        } else {
            mostrarNotificacion(data.error || 'Error generando', 'error');
        }
    } catch {
        mostrarNotificacion('Error de conexión', 'error');
    } finally {
        btn.textContent = '✨ Generar con IA';
        btn.disabled = false;
    }
}

async function crearEvento() {
    const nombre      = document.getElementById('nuevo-evento-nombre').value.trim();
    const desc        = document.getElementById('nuevo-evento-desc').value.trim();
    const historia    = document.getElementById('nuevo-evento-historia').value.trim();
    const tipo        = document.getElementById('nuevo-evento-tipo').value;
    const valor       = document.getElementById('nuevo-evento-valor').value.trim() || null;
    const hora        = document.getElementById('nuevo-evento-hora')?.value.trim()        || '';
    const aviso_dias  = parseInt(document.getElementById('nuevo-evento-aviso')?.value || '0');
    const seguimiento = document.getElementById('nuevo-evento-seguimiento')?.value.trim() || '';

    if (!nombre || !desc) { mostrarNotificacion('Completá nombre y descripción', 'error'); return; }
    if ((tipo === 'fecha' || tipo === 'mensajes') && !valor) {
        mostrarNotificacion('Completá el valor del disparador', 'error'); return;
    }

    try {
        const resp = await fetch('/api/eventos', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ nombre, descripcion: desc, historia, tipo, valor, hora, aviso_dias, seguimiento }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-evento-nombre').value       = '';
            document.getElementById('nuevo-evento-desc').value         = '';
            document.getElementById('nuevo-evento-historia').value     = '';
            document.getElementById('nuevo-evento-valor').value        = '';
            document.getElementById('nuevo-evento-tipo').value         = 'manual';
            if (document.getElementById('nuevo-evento-hora'))        document.getElementById('nuevo-evento-hora').value        = '';
            if (document.getElementById('nuevo-evento-aviso'))       document.getElementById('nuevo-evento-aviso').value       = '0';
            if (document.getElementById('nuevo-evento-seguimiento')) document.getElementById('nuevo-evento-seguimiento').value = '';
            actualizarCampoEvento();
            cargarEventos();
            mostrarNotificacion('✅ Evento creado', 'success');
        }
    } catch {
        mostrarNotificacion('Error al crear evento', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// DISPARAR / RESETEAR / ELIMINAR
// ─────────────────────────────────────────────────────────────────────────────

async function dispararEvento(eid, nombre) {
    try {
        const resp = await fetch(`/api/eventos/${eid}/disparar`, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            cargarEventos();
            mostrarNotificacionEvento(nombre, data.descripcion || '', 'evento');
        }
    } catch {
        mostrarNotificacion('Error al activar evento', 'error');
    }
}

async function resetearEvento(eid) {
    try {
        await fetch(`/api/eventos/${eid}/resetear`, { method: 'POST' });
        cargarEventos();
        mostrarNotificacion('Evento reseteado', 'success');
    } catch {
        mostrarNotificacion('Error al resetear', 'error');
    }
}

async function eliminarEvento(eid) {
    if (!confirm('¿Eliminar este evento?')) return;
    try {
        await fetch(`/api/eventos/${eid}`, { method: 'DELETE' });
        cargarEventos();
        mostrarNotificacion('Evento eliminado', 'success');
    } catch {
        mostrarNotificacion('Error al eliminar', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// INICIALIZACIÓN
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    cargarEventos();
});

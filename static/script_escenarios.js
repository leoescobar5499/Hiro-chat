// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_ESCENARIOS.JS — Gestión de escenarios
// ═══════════════════════════════════════════════════════════════════════════

'use strict';

let _editandoEid = null;

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS UI
// ─────────────────────────────────────────────────────────────────────────────

function mostrarNotificacion(mensaje, tipo = 'info') {
    const notif = document.createElement('div');
    notif.className = `notificacion notificacion-${tipo}`;
    const icon = tipo === 'success' ? '✅' : tipo === 'error' ? '❌' : 'ℹ️';
    notif.innerHTML = `<span>${icon}</span><span>${mensaje}</span>`;
    document.body.appendChild(notif);
    setTimeout(() => notif.classList.add('mostrar'), 10);
    setTimeout(() => {
        notif.classList.remove('mostrar');
        setTimeout(() => notif.remove(), 300);
    }, 3500);
}

function actualizarColorPreview(previewId, color) {
    const el = document.getElementById(previewId);
    if (!el) return;
    el.style.background  = color;
    el.style.boxShadow   = `0 0 14px ${color}50`;
}

function toggleAvanzado(btn) {
    btn.classList.toggle('open');
    const sec = document.getElementById('avanzado-section');
    if (sec) sec.classList.toggle('open');
}

function _esc(str) {
    return (str || '')
        .replace(/&/g, '&amp;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR ESCENARIOS
// ─────────────────────────────────────────────────────────────────────────────

async function cargarEscenarios() {
    const lista   = document.getElementById('listaEscenarios');
    const badgeD  = document.getElementById('badge-default');
    const defCard = document.getElementById('escenario-default-card');

    lista.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-muted);font-size:.85rem">Cargando...</div>';

    let escenas = [];
    try {
        const resp = await fetch('/api/escenarios');
        if (!resp.ok) throw new Error('API error');
        escenas = await resp.json();
    } catch {
        mostrarNotificacion('Error cargando escenarios', 'error');
        lista.innerHTML = '';
        return;
    }

    const hayActivo = escenas.some(e => e.activo);

    if (badgeD)  badgeD.style.display = hayActivo ? 'none' : 'inline-flex';
    if (defCard) defCard.classList.toggle('activo', !hayActivo);

    if (!escenas.length) {
        lista.innerHTML = `<div class="empty-state">Sin escenarios personalizados aún. ¡Creá el primero abajo!</div>`;
        return;
    }

    lista.innerHTML = escenas.map(e => `
        <div class="card-escenario ${e.activo ? 'activo' : ''}">
            <div class="card-inner">
                <div class="card-info" onclick="activarEscenario(${e.id})">
                    <div class="card-header-row">
                        ${e.color ? `<div class="color-dot" style="background:${e.color};box-shadow:0 0 8px ${e.color}80"></div>` : ''}
                        <div class="card-title-group">
                            ${_esc(e.nombre)}
                            ${e.activo ? '<span class="badge-activo">ACTIVO</span>' : ''}
                            ${e.tono   ? `<span class="badge-tono">${_esc(e.tono)}</span>` : ''}
                        </div>
                    </div>
                    <div class="card-desc">${_esc(e.descripcion)}</div>
                </div>
                <div class="card-actions">
                    <button class="btn-accion" title="Ver recuerdos" onclick="verMemorias(${e.id}, '${_esc(e.nombre)}')">💭</button>
                    <button class="btn-accion btn-editar-esc"
                        title="Editar"
                        data-eid="${e.id}"
                        data-nombre="${_esc(e.nombre)}"
                        data-desc="${_esc(e.descripcion)}"
                        data-historia="${_esc(e.historia || '')}"
                        data-tono="${_esc(e.tono || '')}"
                        data-instruccion="${_esc(e.instruccion || '')}"
                        data-color="${_esc(e.color || '')}">✏️</button>
                    <button class="btn-delete" title="Eliminar" onclick="eliminarEscenario(${e.id})">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polyline points="3 6 5 6 21 6"/>
                            <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                        </svg>
                    </button>
                </div>
            </div>
            ${e.historia ? `<div class="card-historia">«${_esc(e.historia.substring(0, 180))}${e.historia.length > 180 ? '…' : ''}»</div>` : ''}
        </div>`
    ).join('');

    lista.querySelectorAll('.btn-editar-esc').forEach(btn => {
        btn.addEventListener('click', ev => {
            ev.stopPropagation();
            abrirModalEditar(
                parseInt(btn.dataset.eid),
                btn.dataset.nombre,
                btn.dataset.desc,
                btn.dataset.historia    || '',
                btn.dataset.tono        || '',
                btn.dataset.instruccion || '',
                btn.dataset.color       || ''
            );
        });
    });
}

// ─────────────────────────────────────────────────────────────────────────────
// ACTIVAR
// ─────────────────────────────────────────────────────────────────────────────

async function activarEscenario(eid) {
    try {
        const resp = await fetch(`/api/escenarios/${eid}/activar`, { method: 'POST' });
        if (!resp.ok) throw new Error();
        const data = await resp.json();
        mostrarNotificacion(data.nombre ? `Activo: ${data.nombre}` : 'Volviendo al escenario base', 'success');
    } catch {
        mostrarNotificacion('Error al activar escenario', 'error');
    }
    cargarEscenarios();
}

// ─────────────────────────────────────────────────────────────────────────────
// GENERAR CON IA
// ─────────────────────────────────────────────────────────────────────────────

async function generarEscenarioIA() {
    const nombre = document.getElementById('nuevo-escenario-nombre').value.trim();
    const idea   = document.getElementById('nuevo-escenario-desc').value.trim();

    if (!nombre && !idea) {
        mostrarNotificacion('Escribí al menos un nombre o una idea', 'error');
        return;
    }

    const btn = document.getElementById('btn-generar-escenario');
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation:spin 1s linear infinite"><path d="M21 12a9 9 0 1 1-6.219-8.56"/></svg> Generando...';
    btn.disabled = true;

    try {
        const resp = await fetch('/api/escenarios/generar', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre: nombre || 'Lugar misterioso', idea: idea || nombre }),
        });
        if (!resp.ok) throw new Error();
        const data = await resp.json();
        if (data.success) {
            if (data.descripcion) document.getElementById('nuevo-escenario-desc').value      = data.descripcion;
            if (data.historia)    document.getElementById('nuevo-escenario-historia').value  = data.historia;
            if (data.tono) {
                document.getElementById('nuevo-escenario-tono').value = data.tono;
                // abrir sección avanzada si estaba cerrada
                const toggle = document.getElementById('btn-avanzado-toggle');
                const sec    = document.getElementById('avanzado-section');
                if (sec && !sec.classList.contains('open')) {
                    toggle?.classList.add('open');
                    sec.classList.add('open');
                }
            }
            if (data.instruccion) document.getElementById('nuevo-escenario-instruccion').value = data.instruccion;
            mostrarNotificacion('Escenario generado — editalo si querés', 'success');
        } else {
            mostrarNotificacion(data.error || 'Error generando', 'error');
        }
    } catch {
        mostrarNotificacion('Error de conexión', 'error');
    } finally {
        btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"/></svg> Generar con IA';
        btn.disabled = false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CREAR
// ─────────────────────────────────────────────────────────────────────────────

async function crearEscenario() {
    const nombre      = document.getElementById('nuevo-escenario-nombre').value.trim();
    const desc        = document.getElementById('nuevo-escenario-desc').value.trim();
    const historia    = document.getElementById('nuevo-escenario-historia').value.trim();
    const tono        = document.getElementById('nuevo-escenario-tono')?.value.trim() || '';
    const instruccion = document.getElementById('nuevo-escenario-instruccion')?.value.trim() || '';
    const color       = document.getElementById('nuevo-escenario-color')?.value || '#8b5cf6';

    if (!nombre || !desc) {
        mostrarNotificacion('Nombre y descripción son obligatorios', 'error');
        return;
    }

    try {
        const resp = await fetch('/api/escenarios', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ nombre, descripcion: desc, historia, tono, instruccion, color }),
        });
        if (!resp.ok) throw new Error();
        const data = await resp.json();
        if (!data.success) throw new Error(data.error || 'Error creando');
    } catch (err) {
        mostrarNotificacion(err.message || 'Error al crear escenario', 'error');
        return;
    }

    // Limpiar form
    ['nuevo-escenario-nombre', 'nuevo-escenario-desc', 'nuevo-escenario-historia',
     'nuevo-escenario-tono', 'nuevo-escenario-instruccion'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
    });
    const colorEl = document.getElementById('nuevo-escenario-color');
    if (colorEl) { colorEl.value = '#8b5cf6'; actualizarColorPreview('esc-color-preview', '#8b5cf6'); }

    // Cerrar sección avanzada
    document.getElementById('btn-avanzado-toggle')?.classList.remove('open');
    document.getElementById('avanzado-section')?.classList.remove('open');

    cargarEscenarios();
    mostrarNotificacion('Escenario creado', 'success');
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL EDITAR
// ─────────────────────────────────────────────────────────────────────────────

function abrirModalEditar(eid, nombre, desc, historia, tono, instruccion, color) {
    _editandoEid = eid;
    const c = color || '#8b5cf6';
    document.getElementById('edit-esc-nombre').value      = nombre;
    document.getElementById('edit-esc-desc').value        = desc;
    document.getElementById('edit-esc-historia').value    = historia;
    document.getElementById('edit-esc-tono').value        = tono;
    document.getElementById('edit-esc-instruccion').value = instruccion;
    document.getElementById('edit-esc-color').value       = c;
    actualizarColorPreview('edit-esc-preview', c);
    document.getElementById('modalEditarEscenario').classList.add('open');
}

function cerrarModalEditar() {
    document.getElementById('modalEditarEscenario').classList.remove('open');
    _editandoEid = null;
}

async function guardarEdicionEscenario() {
    if (!_editandoEid) return;
    const nombre      = document.getElementById('edit-esc-nombre').value.trim();
    const desc        = document.getElementById('edit-esc-desc').value.trim();
    const historia    = document.getElementById('edit-esc-historia').value.trim();
    const tono        = document.getElementById('edit-esc-tono')?.value.trim() || '';
    const instruccion = document.getElementById('edit-esc-instruccion')?.value.trim() || '';
    const color       = document.getElementById('edit-esc-color')?.value || '';

    if (!nombre || !desc) {
        mostrarNotificacion('Nombre y descripción son obligatorios', 'error');
        return;
    }

    const btn = document.getElementById('btn-guardar-edicion');
    btn.textContent = 'Guardando...';
    btn.disabled = true;

    try {
        const resp = await fetch(`/api/escenarios/${_editandoEid}`, {
            method:  'PUT',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ nombre, descripcion: desc, historia, tono, instruccion, color }),
        });
        if (!resp.ok) throw new Error();
        cerrarModalEditar();
        cargarEscenarios();
        mostrarNotificacion('Escenario actualizado', 'success');
    } catch {
        mostrarNotificacion('Error al guardar', 'error');
    } finally {
        btn.textContent = 'Guardar';
        btn.disabled = false;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// ELIMINAR
// ─────────────────────────────────────────────────────────────────────────────

async function eliminarEscenario(eid) {
    if (!confirm('¿Eliminar este escenario?')) return;
    try {
        const resp = await fetch(`/api/escenarios/${eid}`, { method: 'DELETE' });
        if (!resp.ok) throw new Error();
        cargarEscenarios();
        mostrarNotificacion('Escenario eliminado', 'success');
    } catch {
        mostrarNotificacion('Error al eliminar', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MEMORIAS
// ─────────────────────────────────────────────────────────────────────────────

async function verMemorias(eid, nombre) {
    const bodyDiv = document.getElementById('modalMemoriasBody');
    document.getElementById('modalMemoriasTitle').innerHTML =
        `💭 Recuerdos en <span style="color:var(--accent);margin-left:4px">${nombre}</span>`;
    bodyDiv.innerHTML = '<div style="text-align:center;padding:24px;color:var(--text-muted)">Cargando...</div>';
    document.getElementById('modalMemorias').classList.add('open');

    try {
        const resp = await fetch(`/api/escenarios/${eid}/memorias`);
        if (!resp.ok) throw new Error();
        const data = await resp.json();
        const eps  = data.episodios || [];

        if (!eps.length) {
            bodyDiv.innerHTML = '<p style="color:var(--text-secondary);text-align:center;padding:16px 0;font-size:.88rem">Todavía no hay recuerdos aquí. Activá el escenario y empezá a charlar.</p>';
            return;
        }

        bodyDiv.innerHTML =
            `<p style="font-size:.8rem;color:var(--text-muted);margin:0 0 14px">${data.total} recuerdo${data.total !== 1 ? 's' : ''}</p>` +
            eps.map(ep => `
                <div class="memoria-item">
                    <div class="memoria-meta">
                        ${(ep.fecha || '').substring(0, 16)}${ep.emocion ? ' · ' + ep.emocion : ''}
                    </div>
                    <div class="memoria-resumen">${ep.resumen || ''}</div>
                </div>`
            ).join('');
    } catch {
        bodyDiv.innerHTML = '<p style="color:var(--danger);text-align:center;padding:16px 0;font-size:.88rem">Error cargando recuerdos.</p>';
    }
}

function cerrarModalMemorias() {
    document.getElementById('modalMemorias').classList.remove('open');
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    // Sincronizar tema si existe
    const savedTheme = localStorage.getItem('hiro-theme');
    if (savedTheme) document.documentElement.setAttribute('data-theme', savedTheme);

    cargarEscenarios();

    // Cerrar modales al click fuera
    document.querySelectorAll('.modal-overlay').forEach(modal => {
        modal.addEventListener('click', e => {
            if (e.target === modal) {
                modal.classList.remove('open');
                _editandoEid = null;
            }
        });
    });

    // Cerrar modales con Escape
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            document.querySelectorAll('.modal-overlay.open').forEach(m => {
                m.classList.remove('open');
                _editandoEid = null;
            });
        }
    });
});

// CSS de animación de spin para el loader del botón IA
const _spinStyle = document.createElement('style');
_spinStyle.textContent = '@keyframes spin { to { transform: rotate(360deg) } }';
document.head.appendChild(_spinStyle);

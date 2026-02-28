// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_OBJETOS.JS — Gestión de objetos / inventario del roleplay
// Endpoints usados (todos en routes.py):
//   GET    /api/objetos              → listar todos
//   POST   /api/objetos              → crear
//   PUT    /api/objetos/<id>         → editar completo
//   POST   /api/objetos/<id>/toggle  → activar / desactivar
//   PATCH  /api/objetos/<id>/estado  → actualizar solo el estado
//   POST   /api/objetos/<id>/poseedor → cambiar poseedor
//   DELETE /api/objetos/<id>         → eliminar
//   POST   /api/objetos/generar      → generar desc + props con IA
// ═══════════════════════════════════════════════════════════════════════════

const MAX_ACTIVOS = 3;
let _editandoOid  = null;
let _objetosCache = [];

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
    }, 3500);
}

function initTheme() {
    const saved = localStorage.getItem('hiro-theme') || 'gold';
    document.documentElement.setAttribute('data-theme', saved);
}

// ─────────────────────────────────────────────────────────────────────────────
// CONTADOR DE ACTIVOS
// ─────────────────────────────────────────────────────────────────────────────

function actualizarContador(objetos) {
    const activos = objetos.filter(o => o.activo).length;
    for (let i = 1; i <= MAX_ACTIVOS; i++) {
        const dot = document.getElementById(`dot${i}`);
        if (dot) dot.classList.toggle('lleno', i <= activos);
    }
    const aviso = document.getElementById('avisoLimite');
    if (aviso) aviso.classList.toggle('visible', activos >= MAX_ACTIVOS);
}

// ─────────────────────────────────────────────────────────────────────────────
// ICONO POR NOMBRE (heurística simple)
// ─────────────────────────────────────────────────────────────────────────────

function _icono(nombre) {
    const n = nombre.toLowerCase();
    if (/arma|pistol|revólver|revolver|cuchillo|espada|rifle|fusil|bala/.test(n)) return '🔫';
    if (/carta|papel|nota|mapa|libro|documento/.test(n)) return '📜';
    if (/llave|cerradura/.test(n)) return '🗝️';
    if (/poción|pocima|bebida|líquido/.test(n)) return '🧪';
    if (/anillo|collar|medallón|joya/.test(n)) return '💍';
    if (/escudo|armadura/.test(n)) return '🛡️';
    if (/bolso|mochila|maletín|bolsa/.test(n)) return '🎒';
    if (/teléfono|celular|radio/.test(n)) return '📱';
    if (/linterna|luz|vela/.test(n)) return '🔦';
    return '📦';
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGAR OBJETOS
// ─────────────────────────────────────────────────────────────────────────────

async function cargarObjetos() {
    try {
        const resp    = await fetch('/api/objetos');
        const objetos = await resp.json();
        _objetosCache = objetos;

        actualizarContador(objetos);

        const lista = document.getElementById('listaObjetos');

        if (!objetos.length) {
            lista.innerHTML = '<p style="color:var(--text-secondary);font-size:0.85rem">Sin objetos todavía. Creá el primero abajo.</p>';
            return;
        }

        // Activos primero, luego inactivos
        const ordenados = [
            ...objetos.filter(o => o.activo),
            ...objetos.filter(o => !o.activo),
        ];

        lista.innerHTML = ordenados.map(o => {
            const poseedor    = o.poseedor || 'usuario';
            const poseedorLabel = poseedor === 'usuario' ? '👤 Usuario' : '🤖 Personaje';
            const estadoVal   = o.estado || '';

            return `
            <div class="card-objeto ${o.activo ? 'activo' : ''}" id="card-obj-${o.id}">
                <div class="card-top">
                    <div class="obj-icon">${_icono(o.nombre)}</div>
                    <div class="obj-info">
                        <div class="obj-nombre">
                            ${o.nombre}
                            <span class="badge-poseedor ${poseedor}"
                                  onclick="cambiarPoseedor(${o.id}, '${poseedor}')"
                                  title="Click para cambiar poseedor">
                                ${poseedorLabel}
                            </span>
                            ${o.activo ? '<span class="badge-activo-pill">● ACTIVO</span>' : ''}
                        </div>
                        <div class="obj-desc">${_esc(o.descripcion)}</div>
                        ${o.propiedades
                            ? `<div class="obj-props">${_esc(o.propiedades)}</div>`
                            : ''}
                    </div>
                    <div class="card-actions">
                        <button class="btn-toggle ${o.activo ? 'activado' : 'desactivado'}"
                                onclick="toggleObjeto(${o.id})">
                            ${o.activo ? '⏏ Guardar' : '▶ Sacar'}
                        </button>
                        <button class="btn-accion" onclick="abrirModal(${o.id})" title="Editar">✎</button>
                        <button class="btn-delete" onclick="eliminarObjeto(${o.id})" title="Eliminar">
                            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="3 6 5 6 21 6"></polyline>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>
                            </svg>
                        </button>
                    </div>
                </div>
                <!-- Barra de estado (siempre visible, útil durante el roleplay) -->
                <div class="card-estado">
                    <span class="estado-label">Estado</span>
                    <input class="estado-input"
                           id="estado-input-${o.id}"
                           type="text"
                           value="${_esc(estadoVal)}"
                           placeholder="sin estado especial"
                           onkeydown="if(event.key==='Enter')guardarEstado(${o.id})">
                    <button class="btn-estado-save" onclick="guardarEstado(${o.id})">✓</button>
                </div>
            </div>`;
        }).join('');

    } catch (e) {
        mostrarNotificacion('Error cargando objetos', 'error');
        console.error(e);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// TOGGLE ACTIVO / INACTIVO
// ─────────────────────────────────────────────────────────────────────────────

async function toggleObjeto(oid) {
    const obj    = _objetosCache.find(o => o.id === oid);
    const activos = _objetosCache.filter(o => o.activo).length;

    // Bloquear si ya hay 3 activos y este está inactivo
    if (obj && !obj.activo && activos >= MAX_ACTIVOS) {
        mostrarNotificacion('⚠ Límite de 3 objetos activos. Guardá uno primero.', 'error');
        return;
    }

    try {
        const resp = await fetch(`/api/objetos/${oid}/toggle`, { method: 'POST' });
        const data = await resp.json();
        if (data.success) {
            const label = data.activo ? 'Objeto sacado a escena' : 'Objeto guardado en inventario';
            mostrarNotificacion(label, 'success');
            cargarObjetos();
        }
    } catch {
        mostrarNotificacion('Error al cambiar estado', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CAMBIAR POSEEDOR (click en el badge)
// ─────────────────────────────────────────────────────────────────────────────

async function cambiarPoseedor(oid, poseedorActual) {
    const nuevo   = poseedorActual === 'usuario' ? 'personaje' : 'usuario';
    const obj     = _objetosCache.find(o => o.id === oid);
    if (!obj) return;

    try {
        const resp = await fetch(`/api/objetos/${oid}`, {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({
                nombre      : obj.nombre,
                descripcion : obj.descripcion,
                propiedades : obj.propiedades,
                estado      : obj.estado || '',
                poseedor    : nuevo,
                activo      : obj.activo ? 1 : 0,
            })
        });
        const data = await resp.json();
        if (data.success) {
            const label = nuevo === 'usuario' ? '👤 Usuario' : '🤖 Personaje';
            mostrarNotificacion(`Poseedor → ${label}`, 'success');
            cargarObjetos();
        }
    } catch {
        mostrarNotificacion('Error cambiando poseedor', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GUARDAR ESTADO RÁPIDO
// ─────────────────────────────────────────────────────────────────────────────

async function guardarEstado(oid) {
    const input   = document.getElementById(`estado-input-${oid}`);
    if (!input) return;
    const estado = input.value.trim();
    const obj    = _objetosCache.find(o => o.id === oid);
    if (!obj) return;

    try {
        const resp = await fetch(`/api/objetos/${oid}`, {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({
                nombre      : obj.nombre,
                descripcion : obj.descripcion,
                propiedades : obj.propiedades,
                estado      : estado,
                poseedor    : obj.poseedor,
                activo      : obj.activo ? 1 : 0,
            })
        });
        const data = await resp.json();
        if (data.success) {
            // Actualizar cache local sin recargar todo
            obj.estado = estado;
            mostrarNotificacion('Estado actualizado', 'success');
        }
    } catch {
        mostrarNotificacion('Error guardando estado', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GENERAR CON IA
// ─────────────────────────────────────────────────────────────────────────────

async function generarObjetoIA() {
    const nombre = document.getElementById('nuevo-obj-nombre').value.trim();
    const idea   = document.getElementById('nuevo-obj-desc').value.trim();
    if (!nombre || !idea) {
        mostrarNotificacion('Completá el nombre y la idea primero', 'error');
        return;
    }
    const btn = document.getElementById('btn-generar-obj');
    btn.textContent = '⏳ Generando...';
    btn.disabled = true;
    try {
        const resp = await fetch('/api/objetos/generar', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ nombre, idea }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-obj-desc').value  = data.descripcion;
            document.getElementById('nuevo-obj-props').value = data.propiedades;
            mostrarNotificacion('✨ Objeto generado — editalo si querés', 'success');
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

// ─────────────────────────────────────────────────────────────────────────────
// CREAR OBJETO
// ─────────────────────────────────────────────────────────────────────────────

async function crearObjeto() {
    const nombre   = document.getElementById('nuevo-obj-nombre').value.trim();
    const desc     = document.getElementById('nuevo-obj-desc').value.trim();
    const props    = document.getElementById('nuevo-obj-props').value.trim();
    const poseedor = document.getElementById('nuevo-obj-poseedor').value;
    const estado   = document.getElementById('nuevo-obj-estado').value.trim();

    if (!nombre || !desc || !props) {
        mostrarNotificacion('Nombre, descripción y propiedades son requeridos', 'error');
        return;
    }

    try {
        const resp = await fetch('/api/objetos', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ nombre, descripcion: desc, propiedades: props, poseedor, estado }),
        });
        const data = await resp.json();
        if (data.success) {
            document.getElementById('nuevo-obj-nombre').value  = '';
            document.getElementById('nuevo-obj-desc').value    = '';
            document.getElementById('nuevo-obj-props').value   = '';
            document.getElementById('nuevo-obj-estado').value  = '';
            document.getElementById('nuevo-obj-poseedor').value = 'usuario';
            cargarObjetos();
            mostrarNotificacion('✅ Objeto creado', 'success');
        }
    } catch {
        mostrarNotificacion('Error al crear objeto', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// MODAL EDITAR
// ─────────────────────────────────────────────────────────────────────────────

function abrirModal(oid) {
    const obj = _objetosCache.find(o => o.id === oid);
    if (!obj) return;
    _editandoOid = oid;
    document.getElementById('edit-nombre').value   = obj.nombre || '';
    document.getElementById('edit-desc').value     = obj.descripcion || '';
    document.getElementById('edit-props').value    = obj.propiedades || '';
    document.getElementById('edit-estado').value   = obj.estado || '';
    document.getElementById('edit-poseedor').value = obj.poseedor || 'usuario';
    document.getElementById('modalEditar').classList.add('open');
}

function cerrarModal() {
    document.getElementById('modalEditar').classList.remove('open');
    _editandoOid = null;
}

async function guardarEdicion() {
    if (!_editandoOid) return;
    const obj = _objetosCache.find(o => o.id === _editandoOid);

    const nombre   = document.getElementById('edit-nombre').value.trim();
    const desc     = document.getElementById('edit-desc').value.trim();
    const props    = document.getElementById('edit-props').value.trim();
    const estado   = document.getElementById('edit-estado').value.trim();
    const poseedor = document.getElementById('edit-poseedor').value;

    if (!nombre || !desc || !props) {
        mostrarNotificacion('Nombre, descripción y propiedades son requeridos', 'error');
        return;
    }

    const btn = document.getElementById('btn-guardar-edit');
    btn.textContent = 'Guardando...';
    btn.disabled = true;

    try {
        const resp = await fetch(`/api/objetos/${_editandoOid}`, {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({
                nombre, descripcion: desc, propiedades: props,
                estado, poseedor, activo: obj ? (obj.activo ? 1 : 0) : 0,
            }),
        });
        const data = await resp.json();
        if (data.success) {
            cerrarModal();
            cargarObjetos();
            mostrarNotificacion('✅ Objeto actualizado', 'success');
        }
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

async function eliminarObjeto(oid) {
    const obj = _objetosCache.find(o => o.id === oid);
    if (!confirm(`¿Eliminar "${obj?.nombre || 'este objeto'}"?`)) return;
    try {
        await fetch(`/api/objetos/${oid}`, { method: 'DELETE' });
        cargarObjetos();
        mostrarNotificacion('Objeto eliminado', 'success');
    } catch {
        mostrarNotificacion('Error al eliminar', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// HELPER ESCAPE HTML
// ─────────────────────────────────────────────────────────────────────────────

function _esc(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    cargarObjetos();
});

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') cerrarModal();
});

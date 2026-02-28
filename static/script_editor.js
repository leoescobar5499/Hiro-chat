// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_EDITOR.JS — Lógica de editar_personaje.html
// ═══════════════════════════════════════════════════════════════════════════

// ─────────────────────────────────────────────────────────────────────────────
// TEMA
// ─────────────────────────────────────────────────────────────────────────────

const savedTheme = localStorage.getItem('hiro-theme') || 'gold';
document.documentElement.setAttribute('data-theme', savedTheme);

// ─────────────────────────────────────────────────────────────────────────────
// ESTADO
// ─────────────────────────────────────────────────────────────────────────────

let cambiosPendientes = false;
let personajeId       = null; // se resuelve en init() desde /api/personajes/activo

function avatarUrl() {
    // GET de avatar requiere el ID real: /api/personajes/<pid>/avatar
    // POST de avatar usa:                /api/personajes/activo/avatar
    return `/api/personajes/${personajeId}/avatar?t=${Date.now()}`;
}

// ─────────────────────────────────────────────────────────────────────────────
// TOAST
// ─────────────────────────────────────────────────────────────────────────────

function toast(msg, tipo = 'info') {
    const el = document.getElementById('toast');
    el.textContent = msg;
    el.className = `ep-toast ${tipo} show`;
    setTimeout(() => el.classList.remove('show'), 3000);
}

// ─────────────────────────────────────────────────────────────────────────────
// CAMBIOS PENDIENTES
// ─────────────────────────────────────────────────────────────────────────────

function marcarCambio() {
    cambiosPendientes = true;
    const st = document.getElementById('saveStatus');
    st.textContent = 'Cambios sin guardar';
    st.className = 'ep-save-status';
}

document.querySelectorAll('.ep-input, .ep-textarea').forEach(el => {
    el.addEventListener('input', marcarCambio);
});
document.querySelectorAll('input[name="f-modo"]').forEach(el => {
    el.addEventListener('change', marcarCambio);
});

// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────

async function init() {
    try {
        // 1. Obtener el ID real del personaje activo
        const activo = await fetch('/api/personajes/activo').then(r => r.json());
        personajeId = activo.id;

        // 2. Avatar — ahora sí tenemos el ID correcto
        const img = document.getElementById('avatarImg');
        img.src = avatarUrl();
        img.onerror = () => {
            img.style.display = 'none';
            document.getElementById('avatarFallback').style.display = 'flex';
        };

        // 3. Stats de relación
        const stats = await fetch('/api/stats').then(r => r.json());
        document.getElementById('statDias').textContent     = `Día ${stats.dias_juntos ?? 0}`;
        document.getElementById('statMensajes').textContent = `${stats.total_mensajes ?? 0} mensajes`;
        document.getElementById('statFase').textContent     = `Fase ${stats.fase ?? 1}`;

        // 4. Ficha
        const ficha = await fetch('/api/personajes/activo/ficha').then(r => r.json());
        const nombre = ficha.name || '';
        document.getElementById('headerName').textContent     = nombre;
        document.getElementById('avatarName').textContent     = nombre;
        document.getElementById('avatarFallback').textContent = nombre.charAt(0).toUpperCase() || '?';
        document.title = `Editar — ${nombre}`;

        // Normalizar mes_example
        let ejemplos = ficha.mes_example || '';
        if (Array.isArray(ejemplos)) {
            ejemplos = ejemplos.map(ex => {
                if (typeof ex === 'object' && ex !== null) {
                    return Object.entries(ex).map(([k, v]) => `${k}: ${v}`).join('\n');
                }
                return String(ex);
            }).join('\n\n');
        }

        document.getElementById('f-nombre').value         = ficha.name          || '';
        document.getElementById('f-descripcion').value    = ficha.description   || '';
        document.getElementById('f-personalidad').value   = ficha.personality   || '';
        document.getElementById('f-escenario').value      = ficha.scenario      || '';
        document.getElementById('f-primer-mensaje').value = ficha.first_mes     || '';
        document.getElementById('f-ejemplos').value       = ejemplos;
        document.getElementById('f-tags').value           = (ficha.tags || []).join(', ');
        document.getElementById('f-notas').value          = ficha.creator_notes || '';

        const modo = ficha.modo_memoria || 'roleplay';
        document.querySelectorAll('input[name="f-modo"]').forEach(r => {
            r.checked = (r.value === modo);
        });

        cambiosPendientes = false;

    } catch (e) {
        toast('Error al cargar datos', 'error');
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// GUARDAR FICHA
// ─────────────────────────────────────────────────────────────────────────────

const SVG_SAVE = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"></path>
    <polyline points="17 21 17 13 7 13 7 21"></polyline>
    <polyline points="7 3 7 8 15 8"></polyline>
</svg> Guardar cambios`;

const SVG_SAVING = `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
    <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83"/>
</svg> Guardando...`;

async function guardarFicha() {
    const btn = document.getElementById('btnGuardar');
    const st  = document.getElementById('saveStatus');
    btn.disabled  = true;
    btn.innerHTML = SVG_SAVING;

    const tags = document.getElementById('f-tags').value
        .split(',').map(t => t.trim()).filter(Boolean);

    const payload = {
        name          : document.getElementById('f-nombre').value.trim(),
        description   : document.getElementById('f-descripcion').value.trim(),
        personality   : document.getElementById('f-personalidad').value.trim(),
        scenario      : document.getElementById('f-escenario').value.trim(),
        first_mes     : document.getElementById('f-primer-mensaje').value.trim(),
        mes_example   : document.getElementById('f-ejemplos').value.trim(),
        tags,
        creator_notes : document.getElementById('f-notas').value.trim(),
        modo_memoria  : document.querySelector('input[name="f-modo"]:checked')?.value || 'roleplay',
    };

    try {
        const resp = await fetch('/api/personajes/activo/ficha', {
            method : 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify(payload),
        });
        const r = await resp.json();
        if (r.success) {
            toast('Ficha guardada correctamente', 'success');
            st.textContent = 'Guardado';
            st.className   = 'ep-save-status guardado';
            cambiosPendientes = false;
            if (payload.name) {
                document.getElementById('headerName').textContent = payload.name;
                document.getElementById('avatarName').textContent  = payload.name;
                document.title = `Editar — ${payload.name}`;
            }
        } else {
            toast('Error: ' + r.error, 'error');
            st.textContent = 'Error al guardar';
            st.className   = 'ep-save-status error';
        }
    } catch {
        toast('Error de conexión', 'error');
        st.textContent = 'Error al guardar';
        st.className   = 'ep-save-status error';
    } finally {
        btn.disabled  = false;
        btn.innerHTML = SVG_SAVE;
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// AVATAR — subir imagen y ver completa
// ─────────────────────────────────────────────────────────────────────────────

document.getElementById('avatarInput').addEventListener('change', async function () {
    const file = this.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('imagen', file);

    try {
        // POST usa /activo/avatar (sí existe)
        const resp = await fetch('/api/personajes/activo/avatar', {
            method: 'POST',
            body  : formData,
        });
        const data = await resp.json();
        if (data.success) {
            const img = document.getElementById('avatarImg');
            img.style.display = '';
            document.getElementById('avatarFallback').style.display = 'none';
            img.src = avatarUrl(); // usa el ID resuelto en init()
            toast('Imagen actualizada', 'success');
        } else {
            toast('Error: ' + data.error, 'error');
        }
    } catch {
        toast('Error al subir la imagen', 'error');
    }
    this.value = '';
});

// Clic en el avatar dispara el file input
document.getElementById('avatarWrap').addEventListener('click', () => {
    document.getElementById('avatarInput').click();
});

function verImagenCompleta() {
    window.open(`/api/personajes/${personajeId}/avatar`, '_blank');
}

// ─────────────────────────────────────────────────────────────────────────────
// ATAJOS Y SALIDA
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('keydown', e => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        guardarFicha();
    }
});

window.addEventListener('beforeunload', e => {
    if (cambiosPendientes) {
        e.preventDefault();
        e.returnValue = '';
    }
});

// ─────────────────────────────────────────────────────────────────────────────
// ARRANQUE
// ─────────────────────────────────────────────────────────────────────────────

init();

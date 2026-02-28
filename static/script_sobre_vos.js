// ═══════════════════════════════════════════════════════════════════════════
// SCRIPT_SOBRE_VOS.JS
// Endpoints usados:
//   GET  /api/stats                       → fase, confianza, intimidad, mensajes
//   GET  /api/perfil                      → hechos + síntesis
//   GET  /api/sintesis                    → lista de síntesis con id
//   GET  /api/personajes/activo/ficha     → nombre del personaje
//   GET  /api/diarios                     → entradas del diario del personaje
//   POST /api/diarios                     → crear/generar entrada de diario
//   PUT  /api/diarios/<id>               → editar entrada
//   DELETE /api/diarios/<id>             → eliminar entrada
//   GET  /api/evolucion                   → descripción de evolución por fase
//   POST /api/evolucion/generar           → generar con IA para fase actual
//   PUT  /api/evolucion/<fase>           → guardar descripción de fase
//   DELETE /api/evolucion/<fase>         → eliminar descripción de fase
//   PUT  /api/memoria/hecho/<id>          → editar un hecho
//   PUT  /api/sintesis/<id>              → editar una síntesis
//   DELETE /api/memoria/hecho/<id>        → eliminar un hecho
//   DELETE /api/memoria/categoria/<cat>   → eliminar categoría entera
//   DELETE /api/sintesis/<id>            → eliminar una síntesis
//   DELETE /api/memoria/limpiar-todo      → borrar toda la memoria
//   GET  /api/exportar/memoria            → descarga JSON
//   POST /api/importar/memoria            → sube JSON
// ═══════════════════════════════════════════════════════════════════════════

let personajeNombre = 'Personaje';
let hechoActualEdit = null; // { id, tipo: 'hecho' | 'sintesis' | 'diario' | 'evolucion' }

// ─────────────────────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────────────────────

function _escHtml(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function _formatFecha(isoStr) {
    if (!isoStr) return '—';
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString('es-AR', { day: '2-digit', month: '2-digit', year: 'numeric' });
    } catch {
        return String(isoStr).substring(0, 10);
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// CARGA PRINCIPAL
// ─────────────────────────────────────────────────────────────────────────────

async function cargarPagina() {
    // Nombre del personaje
    try {
        const ficha = await fetch('/api/personajes/activo/ficha').then(r => r.json());
        personajeNombre = ficha.name || 'Personaje';
        document.getElementById('personajeName').textContent = personajeNombre;
        document.title = `${personajeNombre} — Sobre vos`;
    } catch { /* silencioso */ }

    const el = document.getElementById('perfilContent');
    let html = '';

    // Cargar todo en paralelo
    const [statsRes, perfilRes, sintesisRes, diariosRes, evolucionRes] = await Promise.allSettled([
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/perfil').then(r => r.json()),
        fetch('/api/sintesis').then(r => r.json()),
        fetch('/api/diarios').then(r => r.json()),
        fetch('/api/evolucion').then(r => r.json()),
    ]);

    const stats     = statsRes.status     === 'fulfilled' ? statsRes.value     : null;
    const perfil    = perfilRes.status    === 'fulfilled' ? perfilRes.value    : null;
    const sintesis  = sintesisRes.status  === 'fulfilled' ? sintesisRes.value  : [];
    const diarios   = diariosRes.status   === 'fulfilled' ? diariosRes.value   : [];
    const evolucion = evolucionRes.status === 'fulfilled' ? evolucionRes.value : [];

    // ── 0. ESTADO DE LA RELACIÓN ────────────────────────────────────────────
    if (stats && stats.fase !== undefined) {
        const colores = {
            1: { color: '#60a5fa', nombre: 'Fase 1/4 — Conocimiento' },
            2: { color: '#8b5cf6', nombre: 'Fase 2/4 — Apertura' },
            3: { color: '#f59e0b', nombre: 'Fase 3/4 — Intimidad' },
            4: { color: '#ef4444', nombre: 'Fase 4/4 — Profundidad' },
        };
        const { color, nombre: nombreFase } = colores[stats.fase] || colores[1];
        const confianza = stats.nivel_confianza  ?? 0;
        const intimidad = stats.nivel_intimidad  ?? 0;
        const dias      = stats.dias_juntos      ?? 1;
        const mensajes  = stats.total_mensajes   ?? 0;
        const hechos    = stats.total_hechos_aprendidos ?? 0;
        const episodios = stats.total_memorias_episodicas ?? 0;
        const nSintesis = stats.total_sintesis   ?? 0;
        const temas     = stats.temas_frecuentes || [];

        const descripcionesFase = {
            1: "Están conociéndose. La relación es cordial y cautelosa. El personaje es formal y guarda distancia.",
            2: "La relación comienza a florecer. Hay más apertura y confianza. El personaje se vuelve más amigable.",
            3: "Profunda intimidad emocional. Han superado barreras. Hay complicidad y conexión auténtica.",
            4: "La relación es intensamente devota. Máxima confianza e intimidad. El personaje es completamente auténtico."
        };

        const temasHtml = temas.length > 0
            ? `<div class="sv-temas"><div class="sv-temas-label">Temas frecuentes</div><div class="sv-temas-chips">${temas.map(t => `<span class="sv-chip">${t}</span>`).join('')}</div></div>`
            : '';

        html += `
        <div class="sv-relacion-card" style="--fase-color:${color}">
            <h2 class="sv-section-title" style="margin-bottom:24px">💝 Estado de la Relación</h2>
            <div class="sv-metrics">
                <div class="sv-metric" style="border-color:${color}">
                    <div class="sv-metric-label" style="color:${color}">Fase Actual</div>
                    <div class="sv-metric-value" style="color:${color}">${nombreFase}</div>
                    <div class="sv-metric-sub">Día ${dias}</div>
                </div>
                <div class="sv-metric sv-metric-bar" style="border-color:rgba(96,165,250,0.3)">
                    <div class="sv-metric-label" style="color:#60a5fa">🔐 Confianza</div>
                    <div class="sv-bar-track"><div class="sv-bar-fill" style="width:${confianza}%;background:linear-gradient(90deg,#60a5fa,#8b5cf6)"></div></div>
                    <div class="sv-metric-value" style="color:#60a5fa;font-size:1.1rem">${confianza}/100</div>
                </div>
                <div class="sv-metric sv-metric-bar" style="border-color:rgba(239,68,68,0.3)">
                    <div class="sv-metric-label" style="color:#ef4444">💗 Intimidad</div>
                    <div class="sv-bar-track"><div class="sv-bar-fill" style="width:${intimidad}%;background:linear-gradient(90deg,#f59e0b,#ef4444)"></div></div>
                    <div class="sv-metric-value" style="color:#ef4444;font-size:1.1rem">${intimidad}/100</div>
                </div>
                <div class="sv-metric" style="border-color:rgba(16,185,129,0.3)">
                    <div class="sv-metric-label" style="color:#10b981">💬 Mensajes</div>
                    <div class="sv-metric-value" style="color:#10b981">${mensajes}</div>
                    <div class="sv-metric-sub">totales (${stats.total_mensajes_usuario ?? 0} tuyos)</div>
                </div>
                <div class="sv-metric" style="border-color:rgba(251,191,36,0.3)">
                    <div class="sv-metric-label" style="color:#fbbf24">🧠 Memoria</div>
                    <div class="sv-metric-value" style="color:#fbbf24">${hechos}</div>
                    <div class="sv-metric-sub">${episodios} episodios · ${nSintesis} síntesis</div>
                </div>
            </div>
            <div class="sv-fase-desc" style="border-left-color:${color}">
                <div class="sv-fase-desc-label" style="color:${color}">Significado de esta fase</div>
                <div>${descripcionesFase[stats.fase] || ''}</div>
            </div>
            ${temasHtml}
        </div>`;
    }

    // ── 1. HECHOS APRENDIDOS ─────────────────────────────────────────────────
    if (perfil && perfil.tiene_datos && perfil.hechos && Object.keys(perfil.hechos).length > 0) {
        html += `<h2 class="sv-section-title" style="margin-top:40px">👤 Hechos Aprendidos</h2>`;

        for (const [categoria, hechos] of Object.entries(perfil.hechos)) {
            const catEnc = encodeURIComponent(categoria);
            html += `
            <div class="sv-cat-box">
                <div class="sv-cat-titulo">
                    <span>${categoria.toUpperCase()}</span>
                    <button class="sv-btn-danger-small" onclick="eliminarCategoria('${catEnc}')">✕ todo</button>
                </div>
                <div class="sv-items-grid">`;

            hechos.forEach(h => {
                const claveLabel = h.clave.replace(/_/g, ' ').toUpperCase();
                html += `
                <div class="sv-item-card" data-id="${h.id}">
                    <div class="sv-item-label">${claveLabel}</div>
                    <div class="sv-item-value">${_escHtml(h.valor)}</div>
                    <div class="sv-item-buttons">
                        <button class="sv-btn-edit" onclick="abrirEdicionHecho(${h.id}, ${JSON.stringify(claveLabel)}, ${JSON.stringify(h.valor || '')})">✎ Editar</button>
                        <button class="sv-btn-del"  onclick="eliminarHecho(${h.id})">✕</button>
                    </div>
                </div>`;
            });

            html += `</div></div>`;
        }
    } else if (perfil && !perfil.tiene_datos) {
        html += `<p class="sv-empty">${personajeNombre} todavía no te conoce bien. Contale sobre vos.</p>`;
    }

    // ── 2. SÍNTESIS Y DIARIO (backstory) ────────────────────────────────────
    if (sintesis && sintesis.length > 0) {
        const backstory    = sintesis.find(s => s.categoria === 'diario_personaje');
        const restoSintesis = sintesis.filter(s => s.categoria !== 'diario_personaje');

        if (backstory) {
            html += `<h2 class="sv-section-title" style="margin-top:40px">📖 Diario del personaje</h2>`;
            html += `<div class="sv-sintesis-box sv-diario-box">
                <div class="sv-sintesis-item sv-diario-item">
                    <div class="sv-sintesis-label">Lo que ${personajeNombre} piensa de vos</div>
                    <div class="sv-sintesis-valor sv-diario-texto">${_escHtml(backstory.contenido)}</div>
                </div>
            </div>`;
        }

        if (restoSintesis.length > 0) {
            html += `<h2 class="sv-section-title" style="margin-top:40px">📊 Síntesis</h2>`;
            html += `<div class="sv-sintesis-box">`;
            restoSintesis.forEach(s => {
                const titulo = s.titulo || s.categoria;
                html += `
                <div class="sv-sintesis-item">
                    <div class="sv-sintesis-label">${_escHtml(titulo.toUpperCase())}</div>
                    <div class="sv-sintesis-valor">${_escHtml(s.contenido)}</div>
                    <div class="sv-item-buttons">
                        <button class="sv-btn-edit" onclick="abrirEdicionSintesis(${s.id}, ${JSON.stringify(titulo)}, ${JSON.stringify(s.contenido || '')})">✎ Editar</button>
                        <button class="sv-btn-del"  onclick="eliminarSintesis(${s.id})">✕</button>
                    </div>
                </div>`;
            });
            html += `</div>`;
        }
    }

    // ── 3. DIARIOS DEL PERSONAJE (nuevo) ────────────────────────────────────
    html += `<div class="sv-nueva-seccion" style="margin-top:40px">
        <div class="sv-section-header-row">
            <h2 class="sv-section-title" style="margin:0">📔 Diarios de ${personajeNombre}</h2>
            <button class="sv-btn-generar" id="btnGenerarDiario" onclick="generarDiario()">✨ Generar nuevo</button>
        </div>`;

    if (diarios && diarios.length > 0) {
        diarios.forEach(d => {
            const fechaFmt = _formatFecha(d.fecha);
            html += `
            <div class="sv-diario-entrada" data-id="${d.id}">
                <div class="sv-diario-meta">
                    <span class="sv-diario-fecha">📅 ${fechaFmt}</span>
                    ${d.auto ? '<span class="sv-badge-ia">✦ IA</span>' : ''}
                </div>
                <div class="sv-diario-titulo">${_escHtml(d.titulo)}</div>
                <div class="sv-diario-body">${_escHtml(d.contenido)}</div>
                <div class="sv-item-buttons" style="margin-top:10px">
                    <button class="sv-btn-edit" onclick="abrirEdicionDiario(${d.id}, ${JSON.stringify(d.titulo || '')}, ${JSON.stringify(d.contenido || '')})">✎ Editar</button>
                    <button class="sv-btn-del"  onclick="eliminarDiario(${d.id})">✕ Eliminar</button>
                </div>
            </div>`;
        });
    } else {
        html += `<p class="sv-empty" style="margin-top:16px">Sin entradas aún. Generá el primer diario de ${personajeNombre}.</p>`;
    }
    html += `</div>`;

    // ── 4. EVOLUCIÓN DEL PERSONAJE (nuevo) ──────────────────────────────────
    const faseActual        = stats ? stats.fase : 1;
    const evFaseActual      = (evolucion || []).find(e => e.fase === faseActual) || null;

    const faseNombres = { 1: 'Conocimiento', 2: 'Apertura', 3: 'Intimidad', 4: 'Profundidad' };
    const faseColores = { 1: '#60a5fa',       2: '#8b5cf6',  3: '#f59e0b',  4: '#ef4444' };
    const faseIcons   = { 1: '⚡',            2: '🌿',       3: '🔥',       4: '💎' };
    const colorFase   = faseColores[faseActual] || '#60a5fa';

    html += `<div class="sv-nueva-seccion" style="margin-top:40px">
        <div class="sv-section-header-row">
            <h2 class="sv-section-title" style="margin:0">🌱 Evolución del Personaje</h2>
            <button class="sv-btn-generar" id="btnGenerarEvolucion" onclick="generarEvolucion()">✨ Generar con IA</button>
        </div>

        <div class="sv-evolucion-card" style="--fase-color:${colorFase};border-color:${colorFase}30">
            <div class="sv-evolucion-header">
                <span class="sv-fase-badge" style="background:${colorFase}18;border:1px solid ${colorFase};color:${colorFase}">
                    ${faseIcons[faseActual]} FASE ${faseActual} — ${faseNombres[faseActual] || ''}
                </span>
                ${evFaseActual
                    ? `<span class="sv-evolucion-actualizado">Actualizado: ${_formatFecha(evFaseActual.fecha)}</span>`
                    : ''}
            </div>

            <div class="sv-evolucion-bloque">
                <div class="sv-evolucion-label">Descripción</div>
                <div class="sv-evolucion-texto">
                    ${evFaseActual && evFaseActual.descripcion
                        ? _escHtml(evFaseActual.descripcion)
                        : '<em style="color:var(--text-secondary)">Sin descripción todavía. Generá una con IA.</em>'}
                </div>
                <button class="sv-btn-edit" style="margin-top:8px"
                    onclick="abrirEdicionEvolucion(${faseActual}, 'descripcion', ${JSON.stringify(evFaseActual?.descripcion || '')})">
                    ✎ Editar
                </button>
            </div>

            <div class="sv-evolucion-bloque" style="margin-top:20px;padding-top:20px;border-top:1px solid var(--border)">
                <div class="sv-evolucion-label">Personalidad en esta fase</div>
                <div class="sv-evolucion-texto">
                    ${evFaseActual && evFaseActual.personalidad
                        ? _escHtml(evFaseActual.personalidad)
                        : '<em style="color:var(--text-secondary)">Sin datos todavía.</em>'}
                </div>
                <button class="sv-btn-edit" style="margin-top:8px"
                    onclick="abrirEdicionEvolucion(${faseActual}, 'personalidad', ${JSON.stringify(evFaseActual?.personalidad || '')})">
                    ✎ Editar
                </button>
            </div>

            ${evFaseActual
                ? `<div style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px">
                       <button class="sv-btn-danger-small"
                           onclick="eliminarEvolucion(${faseActual})">
                           ✕ Eliminar fase ${faseActual}
                       </button>
                   </div>`
                : ''}
        </div>
    </div>`;

    // Sin datos en absoluto
    if (!html.trim()) {
        html = `
        <div class="sv-empty-state">
            <div class="sv-empty-icon">🌱</div>
            <p>${personajeNombre} todavía no te conoce. Cuanto más hables, más aprenderá.</p>
        </div>`;
    }

    el.innerHTML = html;
}


// ─────────────────────────────────────────────────────────────────────────────
// MODAL
// ─────────────────────────────────────────────────────────────────────────────

function abrirEdicionHecho(id, label, valorActual) {
    hechoActualEdit = { id, tipo: 'hecho' };
    _abrirModal(`Editar: ${label}`, valorActual);
}

function abrirEdicionSintesis(id, titulo, valorActual) {
    hechoActualEdit = { id, tipo: 'sintesis' };
    _abrirModal(`Editar síntesis: ${titulo}`, valorActual);
}

function abrirEdicionDiario(id, titulo, contenidoActual) {
    hechoActualEdit = { id, tipo: 'diario' };
    _abrirModal(`Editar diario: ${titulo}`, contenidoActual);
}

function abrirEdicionEvolucion(fase, campo, valorActual) {
    // campo: 'descripcion' | 'personalidad'
    hechoActualEdit = { fase, campo, tipo: 'evolucion' };
    const label = campo === 'descripcion' ? 'Descripción' : 'Personalidad en esta fase';
    _abrirModal(`Editar evolución — ${label}`, valorActual);
}

function _abrirModal(titulo, valor) {
    document.getElementById('editModalTitle').textContent = titulo;
    document.getElementById('editValor').value = valor;
    document.getElementById('editModal').classList.add('active');
    document.getElementById('editValor').focus();
}

function cerrarModal() {
    document.getElementById('editModal').classList.remove('active');
    hechoActualEdit = null;
}

async function guardarEdicion() {
    if (!hechoActualEdit) return;
    const valor = document.getElementById('editValor').value.trim();
    if (!valor) { mostrarToast('El valor no puede estar vacío', 'error'); return; }

    try {
        let resp;
        if (hechoActualEdit.tipo === 'hecho') {
            resp = await fetch(`/api/memoria/hecho/${hechoActualEdit.id}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ valor })
            });
        } else if (hechoActualEdit.tipo === 'sintesis') {
            resp = await fetch(`/api/sintesis/${hechoActualEdit.id}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ contenido: valor })
            });
        } else if (hechoActualEdit.tipo === 'diario') {
            resp = await fetch(`/api/diarios/${hechoActualEdit.id}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ contenido: valor })
            });
        } else if (hechoActualEdit.tipo === 'evolucion') {
            // Primero traer los datos actuales de esa fase para no pisar el otro campo
            let dataActual = {};
            try {
                const r = await fetch('/api/evolucion');
                const lista = await r.json();
                dataActual = lista.find(e => e.fase === hechoActualEdit.fase) || {};
            } catch { /* silencioso */ }

            const body = {
                descripcion : hechoActualEdit.campo === 'descripcion'  ? valor : (dataActual.descripcion  || ''),
                personalidad: hechoActualEdit.campo === 'personalidad' ? valor : (dataActual.personalidad || ''),
            };
            resp = await fetch(`/api/evolucion/${hechoActualEdit.fase}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify(body)
            });
        }

        if (resp && resp.ok) {
            cerrarModal();
            mostrarToast('Guardado', 'success');
            cargarPagina();
        } else {
            mostrarToast('Error al guardar', 'error');
        }
    } catch (e) {
        mostrarToast('Error: ' + e.message, 'error');
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// ACCIONES SOBRE HECHOS
// ─────────────────────────────────────────────────────────────────────────────

async function eliminarHecho(id) {
    if (!confirm('¿Eliminar este dato?')) return;
    try {
        const r = await fetch(`/api/memoria/hecho/${id}`, { method: 'DELETE' });
        if ((await r.json()).success) {
            mostrarToast('Dato eliminado', 'success');
            cargarPagina();
        }
    } catch { mostrarToast('Error eliminando', 'error'); }
}

async function eliminarCategoria(catEnc) {
    const categoria = decodeURIComponent(catEnc);
    if (!confirm(`¿Eliminar toda la categoría "${categoria}"?`)) return;
    try {
        const r = await fetch(`/api/memoria/categoria/${catEnc}`, { method: 'DELETE' });
        const d = await r.json();
        if (d.success) {
            mostrarToast(d.mensaje || 'Categoría eliminada', 'success');
            cargarPagina();
        }
    } catch { mostrarToast('Error eliminando', 'error'); }
}

async function eliminarSintesis(id) {
    if (!confirm('¿Eliminar esta síntesis?')) return;
    try {
        const r = await fetch(`/api/sintesis/${id}`, { method: 'DELETE' });
        if ((await r.json()).success) {
            mostrarToast('Síntesis eliminada', 'success');
            cargarPagina();
        }
    } catch { mostrarToast('Error eliminando', 'error'); }
}


// ─────────────────────────────────────────────────────────────────────────────
// DIARIOS — GENERAR Y ELIMINAR
// ─────────────────────────────────────────────────────────────────────────────

async function generarDiario() {
    const btn = document.getElementById('btnGenerarDiario');
    if (btn) { btn.textContent = '⏳ Generando...'; btn.disabled = true; }
    try {
        const r = await fetch('/api/diarios', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({ generar: true })
        });
        const d = await r.json();
        if (d.success) {
            mostrarToast('✨ Nuevo diario generado', 'success');
            cargarPagina();
        } else {
            mostrarToast(d.error || 'Error generando diario', 'error');
        }
    } catch { mostrarToast('Error de conexión', 'error'); }
    finally {
        if (btn) { btn.textContent = '✨ Generar nuevo'; btn.disabled = false; }
    }
}

async function eliminarDiario(id) {
    if (!confirm('¿Eliminar esta entrada del diario?')) return;
    try {
        const r = await fetch(`/api/diarios/${id}`, { method: 'DELETE' });
        if ((await r.json()).success) {
            mostrarToast('Entrada eliminada', 'success');
            cargarPagina();
        }
    } catch { mostrarToast('Error eliminando', 'error'); }
}


// ─────────────────────────────────────────────────────────────────────────────
// EVOLUCIÓN — GENERAR Y ELIMINAR
// ─────────────────────────────────────────────────────────────────────────────

async function generarEvolucion() {
    const btn = document.getElementById('btnGenerarEvolucion');
    if (btn) { btn.textContent = '⏳ Generando...'; btn.disabled = true; }
    try {
        const r = await fetch('/api/evolucion/generar', {
            method : 'POST',
            headers: { 'Content-Type': 'application/json' },
            body   : JSON.stringify({})
        });
        const d = await r.json();
        if (d.success) {
            // Guardar automáticamente lo generado
            const rSave = await fetch(`/api/evolucion/${d.fase}`, {
                method : 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body   : JSON.stringify({ descripcion: d.descripcion, personalidad: d.personalidad })
            });
            if ((await rSave.json()).success) {
                mostrarToast('✨ Evolución generada y guardada', 'success');
                cargarPagina();
            }
        } else {
            mostrarToast(d.error || 'Error generando', 'error');
        }
    } catch { mostrarToast('Error de conexión', 'error'); }
    finally {
        if (btn) { btn.textContent = '✨ Generar con IA'; btn.disabled = false; }
    }
}

async function eliminarEvolucion(fase) {
    if (!confirm(`¿Eliminar la descripción de la fase ${fase}?`)) return;
    try {
        const r = await fetch(`/api/evolucion/${fase}`, { method: 'DELETE' });
        if ((await r.json()).success) {
            mostrarToast('Fase eliminada', 'success');
            cargarPagina();
        }
    } catch { mostrarToast('Error eliminando', 'error'); }
}


// ─────────────────────────────────────────────────────────────────────────────
// MODAL IMPORTAR / EXPORTAR
// ─────────────────────────────────────────────────────────────────────────────

function abrirModalImpExp() {
    document.getElementById('modalImpExp').classList.add('active');
}

function cerrarModalImpExp() {
    document.getElementById('modalImpExp').classList.remove('active');
}

function impExpExportar(tabla) {
    window.location.href = `/api/exportar/${tabla}`;
}

async function impExpImportar(tabla, inputEl) {
    const archivo = inputEl.files[0];
    if (!archivo) return;

    const formData = new FormData();
    formData.append('archivo', archivo);

    try {
        const r = await fetch(`/api/importar/${tabla}`, { method: 'POST', body: formData });
        const d = await r.json();
        if (d.success) {
            const info = d.importados !== undefined ? ` (${d.importados} registros)` : '';
            mostrarToast(`✅ ${tabla} importado${info}`, 'success');
            cargarPagina();
        } else {
            mostrarToast('❌ ' + (d.error || 'Error desconocido'), 'error');
        }
    } catch (e) {
        mostrarToast('❌ Error: ' + e.message, 'error');
    }

    inputEl.value = '';
}

// Mantener compatibilidad con el borrar todo (que sigue en el menú)
function exportarMemoria() { impExpExportar('memoria'); }

async function borrarTodaMemoria() {
    cerrarMenuOpciones();

    const primera = confirm(
        `⚠️ RESET COMPLETO — ¿Borrar todo lo relacionado a ${personajeNombre}?\n\n` +
        `Se eliminarán:\n` +
        `• Todo el historial de chat\n` +
        `• Toda la memoria episódica\n` +
        `• Todos los hechos aprendidos sobre vos\n` +
        `• Todas las síntesis\n` +
        `• El progreso de la relación (fase, confianza, intimidad, días)\n` +
        `• Los hilos pendientes y el estado emocional\n` +
        `• Los eventos se resetearán (podrán volver a dispararse)\n\n` +
        `Los escenarios y objetos NO se borran.\n\n` +
        `Esta acción NO se puede deshacer.`
    );
    if (!primera) return;

    const segunda = confirm(
        `Última oportunidad.\n\n¿Confirmar reset total de ${personajeNombre}?\n` +
        `Se perderá absolutamente todo el historial y la memoria.`
    );
    if (!segunda) return;

    try {
        const r = await fetch('/api/reset-total', { method: 'DELETE' });
        const d = await r.json();
        if (d.success) {
            mostrarToast('✅ Reset completo. Todo fue borrado.', 'success');
            setTimeout(() => cargarPagina(), 800);
        } else {
            mostrarToast('Error: ' + (d.error || 'desconocido'), 'error');
        }
    } catch (e) {
        mostrarToast('Error: ' + e.message, 'error');
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// MENÚ DE OPCIONES
// ─────────────────────────────────────────────────────────────────────────────

function cerrarMenuOpciones() {
    document.getElementById('menuOpciones')?.classList.remove('visible');
    document.getElementById('btnOpciones')?.classList.remove('active');
}

function inicializarMenu() {
    const btn  = document.getElementById('btnOpciones');
    const menu = document.getElementById('menuOpciones');
    if (!btn || !menu) return;

    btn.addEventListener('click', (e) => {
        e.stopPropagation();
        menu.classList.toggle('visible');
        btn.classList.toggle('active');
    });

    menu.addEventListener('click', e => e.stopPropagation());

    document.addEventListener('click', () => {
        menu.classList.remove('visible');
        btn.classList.remove('active');
    });
}


// ─────────────────────────────────────────────────────────────────────────────
// TOAST
// ─────────────────────────────────────────────────────────────────────────────

function mostrarToast(msg, tipo = 'success') {
    const t = document.getElementById('toast');
    t.textContent = msg;
    t.className = `sv-toast sv-toast--${tipo} sv-toast--visible`;
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.remove('sv-toast--visible'), 2800);
}


// ─────────────────────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
    cargarPagina();
    inicializarMenu();
});

document.addEventListener('keydown', e => { if (e.key === 'Escape') cerrarModal(); });

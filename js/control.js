let estadoGlobal = {};
let timerLogs = null;
let carpetaSubidaObjetivo = null;

async function cargarEstado() {
  try {
    const res = await fetch('/api/estado');
    if (!res.ok) return;
    estadoGlobal = await res.json();
    renderizarEstado();
  } catch (e) {
    console.warn("Servidor local no disponible:", e);
  }
}

function renderizarEstado() {
  // 1. Tesis activa y selector de carpeta de subida
  const boxTesis = document.getElementById('tesis-actual');
  const boxLista = document.getElementById('tesis-lista-box');
  const selCarpetaSubida = document.getElementById('select-carpeta-tesis');

  if (selCarpetaSubida) {
    const carpetas = estadoGlobal.carpetas_tesis || [];
    selCarpetaSubida.innerHTML =
      `<option value="">Nueva carpeta según archivo</option>` +
      carpetas.map(c => `<option value="${c}">${c}</option>`).join('');
    if (carpetaSubidaObjetivo !== null && (carpetaSubidaObjetivo === "" || carpetas.includes(carpetaSubidaObjetivo))) {
      selCarpetaSubida.value = carpetaSubidaObjetivo;
    } else if (estadoGlobal.tesis && estadoGlobal.tesis.carpeta) {
      selCarpetaSubida.value = estadoGlobal.tesis.carpeta;
      carpetaSubidaObjetivo = estadoGlobal.tesis.carpeta;
    }
    const subDrop = document.getElementById('drop-tesis-sub');
    if (subDrop) {
      subDrop.textContent = selCarpetaSubida.value
        ? `Se guardará en: 1-MI-TESIS/${selCarpetaSubida.value}/`
        : 'Creará una carpeta nueva según el nombre del archivo .docx';
    }
  }

  if (estadoGlobal.tesis) {
    const t = estadoGlobal.tesis;
    boxTesis.innerHTML = `
      <div class="file-pill">
        <div class="file-pill-left">
          <svg class="file-icon-svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline></svg>
          <div>
            <div class="file-name" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
              <span>${t.nombre}</span>
              <span class="badge-activa">Activa</span>
              ${t.tiene_resultados ? `<a href="${t.panel_url}" target="_blank" class="badge-res">Ver panel</a>` : ''}
            </div>
            <div class="file-meta" style="margin-top:2px">
              Carpeta: <code>1-MI-TESIS/${t.carpeta || t.slug}/</code> · ${t.tamano} · ${t.modificado}
            </div>
          </div>
        </div>
        <button class="btn-sec danger" style="font-size:11px" onclick="eliminarTesis('${t.ruta_relativa || t.nombre}')">Eliminar</button>
      </div>
    `;
  } else {
    boxTesis.innerHTML = `
      <div class="file-pill" style="background:var(--bad-bg);border-color:var(--bad-bd)">
        <div class="file-pill-left">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--bad)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>
          <div>
            <div class="file-name" style="color:var(--bad-tx)">No se encontró ningún archivo .docx en 1-MI-TESIS</div>
            <div class="file-meta">Sube tu tesis o crea una carpeta de tesis a continuación.</div>
          </div>
        </div>
      </div>
    `;
  }

  // Lista agrupada por carpeta de tesis
  const tesisLista = estadoGlobal.tesis_lista || [];
  const carpetasVacias = (estadoGlobal.carpetas_tesis || []).filter(
    c => !tesisLista.some(t => t.carpeta === c)
  );
  if (tesisLista.length > 0 || carpetasVacias.length > 0) {
    const grupos = {};
    tesisLista.forEach(t => {
      const k = t.carpeta || "(Sin carpeta)";
      if (!grupos[k]) grupos[k] = [];
      grupos[k].push(t);
    });
    carpetasVacias.forEach(c => { if (!grupos[c]) grupos[c] = []; });

    boxLista.innerHTML = `
      <div style="font-size:12px;font-weight:700;margin-top:6px;color:var(--mut)">
        Carpetas de tesis y versiones (${Object.keys(grupos).length} tesis · ${tesisLista.length} docs):
      </div>
      <div class="tesis-multi-container">
        ${Object.entries(grupos).map(([carpeta, docs]) => {
          const conPanel = docs.find(d => d.tiene_resultados);
          return `
            <div class="tesis-grupo">
              <div class="tesis-grupo-hdr">
                <span>Tesis: ${carpeta} (${docs.length} doc${docs.length === 1 ? '' : 's'})</span>
                ${conPanel ? `<a href="${conPanel.panel_url}" target="_blank" class="badge-res">Ver panel</a>` : ''}
              </div>
              ${docs.length === 0
                ? `<div class="tesis-row" style="color:var(--mut);font-style:italic">Carpeta vacía — sube un .docx seleccionándola abajo.</div>`
                : docs.map(t => `
                  <div class="tesis-row ${t.activa ? 'activa' : ''}">
                    <div style="display:flex;align-items:center;gap:8px;min-width:0">
                      <span style="font-weight:${t.activa ? '700' : '400'};overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${t.nombre}">${t.nombre}</span>
                      ${t.activa ? '<span class="badge-activa">En uso</span>' : ''}
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;flex-shrink:0">
                      <span style="font-size:11.5px;color:var(--mut)">${t.tamano}</span>
                      ${!t.activa ? `<button class="btn-sec" style="font-size:11px;padding:3px 8px" onclick="seleccionarTesis('${t.ruta_relativa || t.nombre}')">Seleccionar</button>` : ''}
                      <button class="btn-del" onclick="eliminarTesis('${t.ruta_relativa || t.nombre}')">Eliminar</button>
                    </div>
                  </div>
                `).join('')}
            </div>
          `;
        }).join('')}
      </div>
    `;
  } else {
    boxLista.innerHTML = '';
  }

  // 2. Fuentes y conjunto seleccionable
  const selFuentes = document.getElementById('select-fuentes');
  const carpetasF = estadoGlobal.fuentes_carpetas || [];
  const fAct = estadoGlobal.fuente_seleccionada || '__todas__';
  if (selFuentes) {
    selFuentes.innerHTML = carpetasF.map(c =>
      `<option value="${c.id}" ${c.id === fAct ? 'selected' : ''}>${c.nombre} (${c.total})</option>`
    ).join('');
  }
  document.getElementById('total-fuentes-txt').textContent = `Fuentes en este conjunto: ${estadoGlobal.total_fuentes || 0}`;
  renderizarFuentes(estadoGlobal.fuentes || []);

  // Resumen de emparejamiento en Paso 3
  const boxEmp = document.getElementById('emparejamiento-box');
  if (boxEmp) {
    const fObj = carpetasF.find(c => c.id === fAct);
    const fLbl = fObj ? fObj.nombre : 'Todas las fuentes';
    if (estadoGlobal.tesis) {
      boxEmp.style.display = 'block';
      boxEmp.innerHTML = `<b>Cruce seleccionado:</b> <code>${estadoGlobal.tesis.carpeta || estadoGlobal.tesis.slug}</code> (${estadoGlobal.tesis.nombre}) <b>↔</b> <code>${fLbl}</code> (${estadoGlobal.total_fuentes || 0} archivos)`;
    } else {
      boxEmp.style.display = 'none';
    }
  }

  // 3. Resultados
  const resBox = document.getElementById('resultados-box');
  if (estadoGlobal.resultados && estadoGlobal.resultados.existe) {
    const r = estadoGlobal.resultados;
    const res = r.resumen || {};
    const numInv = res.invisibles || 0;
    const tAct = estadoGlobal.tesis || {};

    const panelHref = r.panel_url || '3-RESULTADOS/panel.html';
    const cTot = res.citas_totales ?? ((res.citas_din || 0) + (res.citas_mano || 0));

    resBox.innerHTML = `
      <div style="margin-bottom:14px">
        <div style="font-size:13px;color:var(--mut);margin-bottom:8px">
          Resultados de: <b>${r.archivo || tAct.nombre}</b>${r.fuentes_usadas ? ` · Fuentes: <b>${r.fuentes_usadas}</b>` : ''} · Carpeta: <code>3-RESULTADOS/${tAct.slug || ''}/</code> · ${r.fecha || 'Reciente'}
        </div>
        <div class="kpi-mini-grid">
          <a href="${panelHref}#sec-fuentes" target="_blank" class="kpi-mini" style="text-decoration:none;color:inherit">
            <div class="kpi-mini-val" style="color:${(res.max_sim < 5) ? 'var(--ok)' : 'var(--warn)'}">${res.max_sim || 0} %</div>
            <div class="kpi-mini-lbl">Similitud máx →</div>
          </a>
          <a href="${panelHref}#sec-similitud" target="_blank" class="kpi-mini" style="text-decoration:none;color:inherit">
            <div class="kpi-mini-val" style="color:${(res.sin_comillas == 0) ? 'var(--ok)' : 'var(--bad)'}">${res.sin_comillas || 0}</div>
            <div class="kpi-mini-lbl">Sin comillas →</div>
          </a>
          <a href="${panelHref}#sec-citas" target="_blank" class="kpi-mini" style="text-decoration:none;color:inherit">
            <div class="kpi-mini-val" style="color:${(cTot > 0 && res.citas_mal == 0 && (res.citas_mano || 0) == 0) ? 'var(--ok)' : (res.citas_mal > 0 || cTot == 0 ? 'var(--bad)' : 'var(--warn)')}">${cTot}</div>
            <div class="kpi-mini-lbl">Citas (${res.citas_din || 0} Word · ${res.citas_mano || 0} mano) →</div>
          </a>
        </div>
      </div>

      <a href="${panelHref}" target="_blank" class="btn-abrir-panel">
        <span>Abrir Panel de esta Tesis (${tAct.slug || 'panel.html'})</span>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
      </a>

      ${numInv > 0 ? `
        <div class="clean-alert">
          <div class="clean-alert-header">
            <span>Se detectaron ${numInv} caracteres invisibles</span>
          </div>
          <div class="clean-alert-desc">
            Existen espacios de ancho cero o marcas residuales de copiar/pegar. Puedes eliminarlos creando una copia limpia segura.
          </div>
          <button class="btn-act btn-limpiar" style="padding:10px 14px;font-size:13px" onclick="ejecutarAccion('limpiar')">
            <div>
              <span>Limpiar Caracteres Invisibles Ahora</span>
              <span class="btn-desc">Crea una copia limpia en 3-RESULTADOS sin tocar citas ni estilos.</span>
            </div>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m18 15-6-6-6 6"></path></svg>
          </button>
        </div>
      ` : `
        <div class="clean-ok-msg">
          Documento libre de caracteres invisibles (no requiere limpieza).
        </div>
      `}

      ${estadoGlobal.limpieza ? `
        <div style="padding:10px 14px;background:var(--ok-bg);border:1px solid var(--ok-bd);border-radius:6px;font-size:12.5px;display:flex;justify-content:space-between;align-items:center;margin-top:10px">
          <div>
            <b style="color:var(--ok-tx)">Copia limpia disponible:</b>
            <div style="font-size:11.5px;color:var(--mut)">${estadoGlobal.limpieza.nombre} (${estadoGlobal.limpieza.tamano})</div>
          </div>
          <button class="btn-sec" onclick="abrirCarpeta('3-RESULTADOS')">Abrir en Word</button>
        </div>
      ` : ''}
    `;
  } else {
    const tAct = estadoGlobal.tesis;
    resBox.innerHTML = `
      <div style="text-align:center;padding:28px 16px;color:var(--mut)">
        <div style="font-weight:700;font-size:14px;color:var(--tx)">
          ${tAct ? `No hay diagnóstico generado aún para "${tAct.carpeta || tAct.nombre}"` : 'No hay diagnóstico generado aún'}
        </div>
        <p style="font-size:12.5px;margin:6px 0 0">
          ${tAct ? `Sus resultados se guardarán en <code>3-RESULTADOS/${tAct.slug}/</code>. Selecciona <b>Revisión Completa</b> o <b>Revisión Rápida</b> en el Paso 3.` : 'Coloca tu tesis en el Paso 1 y ejecuta el análisis.'}
        </p>
      </div>
    `;
  }

  // Estado de ejecución
  if (estadoGlobal.ejecutando) {
    document.getElementById('btn-detener').style.display = 'inline-block';
    document.getElementById('terminal-dot').className = 'status-dot active';
    document.getElementById('terminal-status-text').textContent = estadoGlobal.accion_actual || 'Ejecutando...';
    document.getElementById('prog-box').style.display = 'block';
  } else {
    document.getElementById('btn-detener').style.display = 'none';
    document.getElementById('terminal-dot').className = 'status-dot';
    document.getElementById('terminal-status-text').textContent = 'Listo';
  }
}

function renderizarFuentes(fuentes) {
  const list = document.getElementById('lista-fuentes');
  if (!fuentes || fuentes.length === 0) {
    list.innerHTML = '<div style="padding:14px;text-align:center;color:var(--mut);font-size:12.5px">No hay fuentes en el conjunto seleccionado</div>';
    return;
  }
  list.innerHTML = fuentes.map(f => `
    <div class="fuente-row">
      <div style="display:flex;align-items:center;gap:8px;min-width:0">
        <span class="fuente-badge">${f.tipo}</span>
        <span title="${f.nombre}" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${f.nombre}</span>
      </div>
      <div style="display:flex;align-items:center;gap:10px;flex-shrink:0">
        <span style="font-size:11.5px;color:var(--mut)">${f.tamano}</span>
        <button class="btn-del" onclick="eliminarFuente('${f.nombre}')">Eliminar</button>
      </div>
    </div>
  `).join('');
}

function filtrarFuentes() {
  const q = document.getElementById('filtro-fuentes').value.toLowerCase();
  const fuentes = (estadoGlobal.fuentes || []).filter(f => f.nombre.toLowerCase().includes(q));
  renderizarFuentes(fuentes);
}

async function crearCarpetaTesis() {
  const nombre = prompt("Nombre de la carpeta para esta tesis (ej: Juan Perez):");
  if (!nombre || !nombre.trim()) return;
  try {
    const res = await fetch('/api/crear-carpeta-tesis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: nombre.trim() })
    });
    const data = await res.json();
    if (data.ok) {
      carpetaSubidaObjetivo = data.nombre;
      mostrarToast(`Carpeta "${data.nombre}" seleccionada para subir archivo`, "ok");
      await cargarEstado();
      const dz = document.getElementById('drop-tesis');
      if (dz) dz.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } else {
      mostrarToast(data.error || "No se pudo crear", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión", "bad");
  }
}

async function crearCarpetaFuentes() {
  const nombre = prompt("Nombre del nuevo conjunto de fuentes en 2-FUENTES (ej: Fuentes Rocio):");
  if (!nombre || !nombre.trim()) return;
  try {
    const res = await fetch('/api/crear-carpeta-fuentes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre: nombre.trim() })
    });
    const data = await res.json();
    if (data.ok) {
      mostrarToast(`Conjunto de fuentes creado: ${data.nombre}`, "ok");
      cargarEstado();
    } else {
      mostrarToast(data.error || "No se pudo crear", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión", "bad");
  }
}

async function seleccionarFuente(fuentes) {
  try {
    const res = await fetch('/api/seleccionar-fuente', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ fuentes })
    });
    const data = await res.json();
    if (data.ok) {
      cargarEstado();
    } else {
      mostrarToast("No se pudo cambiar de fuentes", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión", "bad");
  }
}

async function subirTesis(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith('.docx')) {
    mostrarToast("Solo se admiten archivos Word (.docx)", "bad");
    return;
  }
  const sel = document.getElementById('select-carpeta-tesis');
  const carpeta = sel ? sel.value : '';
  const qs = carpeta ? '?carpeta=' + encodeURIComponent(carpeta) : '';

  const fd = new FormData();
  fd.append('file', file);
  mostrarToast("Subiendo tesis...", "info");
  try {
    const res = await fetch('/api/subir-tesis' + qs, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.ok) {
      mostrarToast("Tesis guardada con éxito", "ok");
      cargarEstado();
    } else {
      mostrarToast("No se pudo guardar la tesis", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión al subir", "bad");
  }
}

async function subirFuentes(files) {
  if (!files || files.length === 0) return;
  const carpeta = estadoGlobal.fuente_seleccionada || '';
  const qs = (carpeta && carpeta !== '__todas__' && carpeta !== '__raiz__')
    ? '?carpeta=' + encodeURIComponent(carpeta)
    : '';

  const fd = new FormData();
  for (let i = 0; i < files.length; i++) {
    fd.append('file_' + i, files[i]);
  }
  mostrarToast(`Subiendo ${files.length} archivo(s)...`, "info");
  try {
    const res = await fetch('/api/subir-fuentes' + qs, { method: 'POST', body: fd });
    const data = await res.json();
    if (data.ok) {
      mostrarToast(`${data.total} fuente(s) agregada(s)`, "ok");
      cargarEstado();
    } else {
      mostrarToast("Error al procesar fuentes", "bad");
    }
  } catch (e) {
    mostrarToast("Error de red al subir", "bad");
  }
}

async function seleccionarTesis(nombre) {
  try {
    const res = await fetch('/api/seleccionar-tesis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre })
    });
    const data = await res.json();
    if (data.ok) {
      carpetaSubidaObjetivo = null;
      mostrarToast(`Documento seleccionado`, "ok");
      cargarEstado();
    } else {
      mostrarToast("No se pudo seleccionar la tesis", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión", "bad");
  }
}

async function eliminarTesis(nombre) {
  if (!confirm(`¿Eliminar "${nombre}" de 1-MI-TESIS?`)) return;
  try {
    const res = await fetch('/api/eliminar-tesis', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre })
    });
    const data = await res.json();
    if (data.ok) {
      mostrarToast("Tesis eliminada", "ok");
      cargarEstado();
    } else {
      mostrarToast("Error al eliminar", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión", "bad");
  }
}

async function vaciarTesis() {
  if (!confirm("¿Seguro que deseas vaciar TODA la carpeta 1-MI-TESIS?\nSe eliminarán todas las carpetas y archivos .docx allí guardados.")) return;
  try {
    const res = await fetch('/api/vaciar-tesis', { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      mostrarToast(`Carpeta 1-MI-TESIS vaciada (${data.borrados} elementos)`, "ok");
      cargarEstado();
    } else {
      mostrarToast("Error al vaciar carpeta", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión al vaciar", "bad");
  }
}

async function vaciarFuentes() {
  const carp = estadoGlobal.fuente_seleccionada || '__todas__';
  const msg = (carp === '__todas__')
    ? "¿Seguro que deseas vaciar TODA la carpeta 2-FUENTES?"
    : `¿Seguro que deseas vaciar las fuentes de "${carp === '__raiz__' ? 'General (raíz)' : carp}"?`;
  if (!confirm(msg)) return;
  try {
    const res = await fetch('/api/vaciar-fuentes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ carpeta: carp })
    });
    const data = await res.json();
    if (data.ok) {
      mostrarToast(`Fuentes vaciadas (${data.borrados} elementos)`, "ok");
      cargarEstado();
    } else {
      mostrarToast("Error al vaciar fuentes", "bad");
    }
  } catch (e) {
    mostrarToast("Error de conexión al vaciar", "bad");
  }
}

async function eliminarFuente(nombre) {
  if (!confirm(`¿Eliminar la fuente "${nombre}"?`)) return;
  try {
    const res = await fetch('/api/eliminar-fuente', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre })
    });
    const data = await res.json();
    if (data.ok) {
      mostrarToast("Fuente eliminada", "ok");
      cargarEstado();
    }
  } catch (e) {
    mostrarToast("Error al eliminar", "bad");
  }
}

async function ejecutarAccion(accion) {
  if (estadoGlobal.ejecutando) {
    mostrarToast("Ya existe un proceso en ejecución", "bad");
    return;
  }
  deshabilitarBotones(true);
  limpiarTerminal();
  document.getElementById('prog-box').style.display = 'block';
  document.getElementById('prog-bar-fill').style.width = '5%';
  document.getElementById('prog-pct-text').textContent = '5%';
  document.getElementById('prog-step-text').textContent = 'Iniciando ' + accion + '...';
  mostrarToast("Iniciando análisis...", "info");

  const fuentes = estadoGlobal.fuente_seleccionada || '__todas__';
  const tesis = estadoGlobal.tesis ? estadoGlobal.tesis.ruta_relativa : null;

  try {
    const res = await fetch('/api/ejecutar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accion, tesis, fuentes })
    });
    const data = await res.json();
    if (data.ok) {
      iniciarPollingLogs();
    } else {
      mostrarToast("No fue posible iniciar el análisis", "bad");
      deshabilitarBotones(false);
      document.getElementById('prog-box').style.display = 'none';
    }
  } catch (e) {
    mostrarToast("Error de conexión al ejecutar", "bad");
    deshabilitarBotones(false);
    document.getElementById('prog-box').style.display = 'none';
  }
}

async function detenerAccion() {
  try {
    await fetch('/api/detener', { method: 'POST' });
    mostrarToast("Proceso cancelado", "bad");
  } catch (e) {}
}

function iniciarPollingLogs() {
  if (timerLogs) clearInterval(timerLogs);
  timerLogs = setInterval(async () => {
    try {
      const res = await fetch('/api/logs');
      const data = await res.json();
      const term = document.getElementById('terminal-body');

      if (data.progreso !== undefined) {
        const pct = Math.max(0, Math.min(100, data.progreso));
        document.getElementById('prog-bar-fill').style.width = pct + '%';
        document.getElementById('prog-pct-text').textContent = pct + '%';
      }
      if (data.paso) {
        document.getElementById('prog-step-text').textContent = data.paso;
      }

      if (data.logs && data.logs.length) {
        term.textContent = data.logs.join('\n');
        term.scrollTop = term.scrollHeight;
      }

      if (!data.ejecutando) {
        clearInterval(timerLogs);
        timerLogs = null;
        deshabilitarBotones(false);
        document.getElementById('btn-detener').style.display = 'none';
        document.getElementById('terminal-dot').className = 'status-dot';
        document.getElementById('terminal-status-text').textContent =
          (data.codigo_salida === 0) ? 'Completado con éxito' : 'Finalizado con observaciones';

        document.getElementById('prog-bar-fill').style.width = '100%';
        document.getElementById('prog-pct-text').textContent = (data.codigo_salida === 0) ? '100%' : 'Listo';

        cargarEstado();
        mostrarToast("Ejecución finalizada", (data.codigo_salida === 0) ? "ok" : "warn");
      }
    } catch (e) {}
  }, 250);
}

function deshabilitarBotones(flag) {
  const bRev = document.getElementById('btn-revisar');
  const bRap = document.getElementById('btn-revisar-rapido');
  const bLim = document.getElementById('btn-limpiar');
  if (bRev) bRev.disabled = flag;
  if (bRap) bRap.disabled = flag;
  if (bLim) bLim.disabled = flag;
}

function limpiarTerminal() {
  document.getElementById('terminal-body').textContent = '';
}

async function abrirCarpeta(ruta) {
  try {
    await fetch('/api/abrir-archivo?ruta=' + encodeURIComponent(ruta));
  } catch (e) {}
}

function mostrarToast(msg, tipo = "ok") {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.className = tipo;
  t.style.display = 'block';
  setTimeout(() => { t.style.display = 'none'; }, 3500);
}

['drop-tesis', 'drop-fuentes'].forEach(id => {
  const el = document.getElementById(id);
  el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('dragover'); });
  el.addEventListener('dragleave', () => { el.classList.remove('dragover'); });
  el.addEventListener('drop', e => {
    e.preventDefault();
    el.classList.remove('dragover');
    if (id === 'drop-tesis') {
      if (e.dataTransfer.files.length) subirTesis(e.dataTransfer.files[0]);
    } else {
      if (e.dataTransfer.files.length) subirFuentes(e.dataTransfer.files);
    }
  });
});

cargarEstado();
setInterval(cargarEstado, 4000);

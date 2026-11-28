"""Panel HTML autocontenido con diagnóstico, exposición antiplagio y visualizaciones SVG."""
from html import escape as e
from pathlib import Path
from urllib.parse import quote


def _estado(ok, warn=False):
    return "ok" if ok else ("warn" if warn else "bad")


def _fmt_num(n):
    return f"{int(n):,}".replace(",", ".")


def _fmt_pct(v):
    return f"{v:.2f}".replace(".", ",") + " %"


def _tabla(cabeceras, filas, vacio="Nada para mostrar.", clase=""):
    if not filas:
        return (
            '<div class="caja-vacio">'
            '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            f'<span>{e(vacio)}</span></div>'
        )
    th = "".join(f'<th{" class=\"n\"" if c.startswith("#") else ""}>{e(c.lstrip("#"))}</th>' for c in cabeceras)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    cls_attr = f' class="{e(clase)}"' if clase else ""
    return f'<div class="tabla-wrap"><table{cls_attr}><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _svg_exposicion(exp):
    """Barra apilada horizontal 100% para texto expuesto (no citas) vs citas textuales."""
    p_prop = exp.get("pct_redaccion_propia", 0.0)
    p_paraf = exp.get("pct_parafrasis_citada", 0.0)
    p_citas = exp.get("pct_citas", 0.0)
    total = p_prop + p_paraf + p_citas
    if total <= 0:
        return '<div class="chart-empty">Ejecuta una nueva revisión para calcular la exposición antiplagio.</div>'

    w1 = max(0.0, p_prop)
    w2 = max(0.0, p_paraf)
    w3 = max(0.0, p_citas)
    x2 = w1
    x3 = w1 + w2

    return f"""
    <svg class="svg-chart" viewBox="0 0 600 44" height="44" role="img" aria-label="Distribución de texto expuesto a antiplagio">
      <rect x="0" y="6" width="{w1 * 6:.2f}" height="24" fill="var(--chart-1)" rx="3">
        <title>Redacción propia sin cita: {_fmt_pct(p_prop)}</title>
      </rect>
      <rect x="{x2 * 6:.2f}" y="6" width="{w2 * 6:.2f}" height="24" fill="var(--chart-3)">
        <title>Paráfrasis con cita: {_fmt_pct(p_paraf)}</title>
      </rect>
      <rect x="{x3 * 6:.2f}" y="6" width="{w3 * 6:.2f}" height="24" fill="var(--chart-2)" rx="3">
        <title>Citas textuales: {_fmt_pct(p_citas)}</title>
      </rect>
      <line x1="{x3 * 6:.2f}" y1="2" x2="{x3 * 6:.2f}" y2="34" stroke="var(--surface)" stroke-width="2" />
      <text x="0" y="42" font-size="11" fill="var(--muted)">0 %</text>
      <text x="300" y="42" font-size="11" fill="var(--muted)" text-anchor="middle">Expuesto (no citas): {_fmt_pct(exp.get("pct_no_citas", 0))}</text>
      <text x="600" y="42" font-size="11" fill="var(--muted)" text-anchor="end">100 %</text>
    </svg>
    """


def _svg_ring(pct_ok, label, sub):
    """Anillo SVG limpio de salud general."""
    r = 32
    c = 2 * 3.14159265 * r
    fill_len = max(0.0, min(1.0, pct_ok / 100.0)) * c
    color = "var(--ok)" if pct_ok >= 80 else ("var(--warn)" if pct_ok >= 55 else "var(--bad)")
    return f"""
    <div class="health-top">
      <svg width="80" height="80" viewBox="0 0 80 80" role="img" aria-label="{e(label)}: {pct_ok:.0f}%">
        <circle cx="40" cy="40" r="{r}" fill="none" stroke="var(--raised)" stroke-width="7" />
        <circle cx="40" cy="40" r="{r}" fill="none" stroke="{color}" stroke-width="7"
          stroke-dasharray="{fill_len:.2f} {c:.2f}" stroke-linecap="butt" transform="rotate(-90 40 40)" />
        <text x="40" y="44" text-anchor="middle" font-size="15" font-weight="600" fill="var(--text)">{pct_ok:.0f}%</text>
      </svg>
      <div class="health-summary">
        <strong>{e(label)}</strong>
        <span>{e(sub)}</span>
      </div>
    </div>
    """


def _svg_barras_fuentes(fuentes):
    """Gráfico de barras horizontales SVG para las 10 fuentes con mayor similitud."""
    top = [f for f in fuentes if f.get("porcentaje", 0) > 0][:10]
    if not top:
        return '<div class="chart-empty">No se detectaron coincidencias con las fuentes evaluadas.</div>'

    max_pct = max(max(f.get("porcentaje", 0) for f in top), 5.0)
    # Redondear tope a múltiplo limpio
    ceil_pct = 5.0 if max_pct <= 5 else (10.0 if max_pct <= 10 else float(int(max_pct // 5 + 1) * 5))
    row_h = 28
    pad_l = 230
    pad_r = 56
    bar_w = 600 - pad_l - pad_r
    h = len(top) * row_h + 26

    lines = []
    # Gridlines verticales (0, mitad, tope) y línea umbral 5%
    for tick in [0, ceil_pct / 2, ceil_pct]:
        tx = pad_l + (tick / ceil_pct) * bar_w
        lines.append(f'<line x1="{tx:.1f}" y1="0" x2="{tx:.1f}" y2="{h - 20}" stroke="var(--grid)" stroke-width="1" />')
        lines.append(f'<text x="{tx:.1f}" y="{h - 5}" font-size="11" fill="var(--muted)" text-anchor="middle">{tick:.0f}%</text>')

    if 5.0 < ceil_pct:
        ux = pad_l + (5.0 / ceil_pct) * bar_w
        lines.append(f'<line x1="{ux:.1f}" y1="0" x2="{ux:.1f}" y2="{h - 20}" stroke="var(--warn)" stroke-width="1" stroke-dasharray="3 3" />')

    for idx, f in enumerate(top):
        pct = f.get("porcentaje", 0.0)
        nom = f.get("fuente", "")
        short = nom if len(nom) <= 34 else nom[:31] + "…"
        y = idx * row_h + 6
        bw = max(2.0, (pct / ceil_pct) * bar_w)
        col = "var(--bad)" if pct >= 15 else ("var(--warn)" if pct >= 5 else "var(--chart-1)")
        comp = e(f.get("comparacion", ""))
        lines.append(
            f'<g>'
            f'<text x="{pad_l - 10}" y="{y + 13}" font-size="12" fill="var(--text)" text-anchor="end">'
            f'<title>{e(nom)}</title>{e(short)}</text>'
            f'<a href="{comp}" target="_blank">'
            f'<rect x="{pad_l}" y="{y + 2}" width="{bw:.1f}" height="15" fill="{col}" rx="2">'
            f'<title>{e(nom)}: {pct:.2f}%</title></rect>'
            f'</a>'
            f'<text x="{pad_l + bw + 6:.1f}" y="{y + 13}" font-size="12" font-weight="500" fill="var(--text)">{pct:.2f}%</text>'
            f'</g>'
        )

    return f'<svg class="svg-chart" viewBox="0 0 600 {h}" role="img" aria-label="Top fuentes por porcentaje de similitud">{"".join(lines)}</svg>'


def _svg_barra_proporcion(segmentos, titulo_aria):
    """Barra segmentada compacta para citas o enlaces web."""
    total = sum(v for _, v, _ in segmentos)
    if total == 0:
        return '<div class="chart-empty">Sin elementos registrados.</div>'
    rects = []
    x = 0.0
    for label, val, color in segmentos:
        if val <= 0:
            continue
        w = (val / total) * 400.0
        rects.append(f'<rect x="{x:.2f}" y="0" width="{w:.2f}" height="14" fill="{color}"><title>{e(label)}: {val}</title></rect>')
        x += w
    return f'<svg class="svg-chart" viewBox="0 0 400 14" height="14" style="border-radius:4px;overflow:hidden;margin:8px 0 12px" role="img" aria-label="{e(titulo_aria)}">{"".join(rects)}</svg>'


def _svg_historial(hist):
    """Gráfico de línea SVG de evolución de similitud máxima en el historial."""
    pts = hist[-12:]
    if len(pts) < 2:
        return '<div class="chart-empty">Se necesitan al menos 2 revisiones para graficar la tendencia histórica.</div>'

    w, h = 600, 150
    pad_l, pad_r, pad_t, pad_b = 42, 16, 16, 26
    pw = w - pad_l - pad_r
    ph = h - pad_t - pad_b
    vals = [float(p.get("max_sim", 0)) for p in pts]
    ymax = max(max(vals) * 1.25, 5.0)

    elems = []
    for t in [0, ymax / 2, ymax]:
        yy = pad_t + ph - (t / ymax) * ph
        elems.append(f'<line x1="{pad_l}" y1="{yy:.1f}" x2="{w - pad_r}" y2="{yy:.1f}" stroke="var(--grid)" stroke-width="1" />')
        elems.append(f'<text x="{pad_l - 8}" y="{yy + 4:.1f}" font-size="11" fill="var(--muted)" text-anchor="end">{t:.1f}%</text>')

    coords = []
    n = len(pts)
    for i, p in enumerate(pts):
        xx = pad_l + (i / (n - 1)) * pw
        yy = pad_t + ph - (float(p.get("max_sim", 0)) / ymax) * ph
        coords.append((xx, yy, p))

    path_d = " ".join(("M" if i == 0 else "L") + f"{x:.1f},{y:.1f}" for i, (x, y, _) in enumerate(coords))
    elems.append(f'<path d="{path_d}" fill="none" stroke="var(--chart-1)" stroke-width="2" />')

    for i, (xx, yy, p) in enumerate(coords):
        fecha_corta = p.get("fecha", "")[:10]
        elems.append(f'<circle cx="{xx:.1f}" cy="{yy:.1f}" r="3.5" fill="var(--chart-1)"><title>{e(p.get("fecha", ""))}: {p.get("max_sim", 0):.2f}% · {p.get("sin_comillas", 0)} sin comillas</title></circle>')
        if i == 0 or i == n - 1 or n <= 5:
            elems.append(f'<text x="{xx:.1f}" y="{h - 6}" font-size="11" fill="var(--muted)" text-anchor="middle">{e(fecha_corta)}</text>')

    return f'<svg class="svg-chart" viewBox="0 0 {w} {h}" role="img" aria-label="Evolución de similitud máxima">{"".join(elems)}</svg>'


def _ubicacion_pasaje(p):
    pag = p.get("pagina")
    tit = p.get("titulo", "")
    sub = p.get("subtitulo", "")
    partes = []
    if pag:
        partes.append(f'<span class="badge-pag">Pág. {pag}</span>')
    if tit:
        partes.append(f'<span class="loc-tit" title="{e(tit)}">{e(tit)}</span>')
    elif pag and pag <= 10:
        partes.append('<span class="loc-tit">Páginas preliminares</span>')
    if sub:
        partes.append(f'<span class="loc-sub" title="{e(sub)}">› {e(sub)}</span>')
    return " ".join(partes) if partes else '<span class="loc-sub">No ubicado</span>'


def _instruccion_pasaje(estado, palabras=0):
    if estado == "Sin comillas":
        if palabras >= 40:
            return "<b>Cita larga en bloque (≥ 40 pal.):</b> Párrafo aparte con sangría de 1.27 cm, sin comillas, citando autor, año y pág. O parafrasear."
        return '<b>Cita corta (&lt; 40 pal.):</b> Encerrar entre comillas dobles <code>""</code> y citar autor, año y pág. O parafrasear.'
    if estado == "Entre comillas":
        return "<b>Conforme:</b> Cita entre comillas. Verifica que incluya autor, año y página."
    if estado == "En bloque":
        return "<b>Conforme:</b> Cita en bloque. Verifica sangría de 1.27 cm y referencia final."
    return "<b>Revisar:</b> Confirmar si es redacción propia o cita omitida."


def _card_pasaje(p):
    st = p.get("estado", "")
    tag_cls = "bad" if st == "Sin comillas" else ("warn" if st == "No ubicado" else "ok")
    n_pal = p.get("palabras", 0)
    pag = p.get("pagina")
    fuente = p.get("fuente", "")
    frag = p.get("fragmento", "")
    parr = p.get("parrafo", "")
    loc_html = _ubicacion_pasaje(p)
    inst = _instruccion_pasaje(st, n_pal)

    return (
        f'<div class="pasaje-card {tag_cls}" data-estado="{e(st)}">'
        f'<div class="pasaje-header">'
        f'<div class="pasaje-meta"><span class="pill {tag_cls}">{e(st)}</span>{loc_html}</div>'
        f'<div class="pasaje-fte-meta"><span>Fuente: <b>{e(fuente)}</b></span><span class="pill">{n_pal} pal.</span></div>'
        f'</div>'
        f'<div class="pasaje-accion {tag_cls}">{inst}</div>'
        f'<div class="pasaje-grid-comparativa">'
        f'<div><div class="col-head">Fragmento idéntico detectado</div><div class="frag-caja">{e(frag)}</div></div>'
        f'<div><div class="col-head">Párrafo en tu tesis ({("Pág. " + str(pag)) if pag else "Cuerpo"})</div><div class="parr-caja">{e(parr)}</div></div>'
        f'</div></div>'
    )


def generar(d):
    sim = d.get("similitud", {})
    cit = d.get("citas", {})
    inv = d.get("invisibles", {})
    est = d.get("estructura", {})
    exp = est.get("exposicion", {})
    w = d.get("web", [])
    hist = d.get("historial", [])

    pasajes_raw = sim.get("pasajes", [])
    sin_comillas = [p for p in pasajes_raw if p.get("estado") == "Sin comillas"]
    fuentes_sim = sim.get("fuentes", [])
    max_sim = fuentes_sim[0]["porcentaje"] if fuentes_sim else 0.0

    citas_din = cit.get("campos_cita", 0)
    citas_mano = len(cit.get("texto_plano", []))
    citas_totales = citas_din + citas_mano
    citas_mal = len(cit.get("sin_fuente", [])) + len(cit.get("sin_citar", [])) + (0 if cit.get("hay_almacen") else 1)
    citas_estado = "bad" if (citas_totales == 0 or citas_mal > 0) else ("warn" if citas_mano > 0 else "ok")

    enlaces_mal = [x for x in w if x.get("estado") != "OK"]
    enlaces_ok = len(w) - len(enlaces_mal)
    inv_tot = inv.get("total", 0)
    homoglifos = len(inv.get("sustituidos", []))
    prob_est = len(est.get("problemas", []))

    # Exposición antiplagio
    has_exp = bool(exp and exp.get("palabras_cuerpo", 0) > 0)
    pct_no_citas_str = _fmt_pct(exp.get("pct_no_citas", 0)) if has_exp else "—"
    pct_citas_str = _fmt_pct(exp.get("pct_citas", 0)) if has_exp else "—"
    pal_no_citas_str = f'{_fmt_num(exp.get("palabras_no_citas", 0))} pal.' if has_exp else "Vuelve a revisar"
    pal_citas_str = f'{_fmt_num(exp.get("palabras_citas", 0))} pal.' if has_exp else "Vuelve a revisar"

    # Salud general (6 criterios clave)
    checks = [
        ("Pasajes sin comillas", len(sin_comillas) == 0, f"{len(sin_comillas)} pendientes", "sec-similitud", "bad" if sin_comillas else "ok"),
        ("Similitud máxima < 5 %", max_sim < 5.0, f"{max_sim:.2f} %", "sec-fuentes", _estado(max_sim < 5, max_sim < 15)),
        ("Citas y almacén Word", citas_mal == 0 and citas_mano == 0, f"{citas_mal} errores · {citas_mano} a mano", "sec-citas", citas_estado),
        ("Fuentes web accesibles", len(enlaces_mal) == 0, f"{enlaces_ok}/{len(w)} OK" if w else "Sin URLs", "sec-web", "warn" if enlaces_mal else "ok"),
        ("Invisibles y homoglifos", inv_tot == 0 and homoglifos == 0, f"{inv_tot} inv. · {homoglifos} camufl.", "sec-invisibles", "bad" if homoglifos else ("warn" if inv_tot else "ok")),
        ("Numeración tablas/figuras", prob_est == 0, f"{prob_est} problemas", "sec-tablas", "warn" if prob_est else "ok"),
    ]
    passed = sum(1 for _, ok, _, _, _ in checks if ok)
    health_pct = (passed / len(checks)) * 100.0
    health_label = f"{passed} de {len(checks)} criterios en orden"
    health_sub = "Lista para entrega" if passed == len(checks) else "Revisa los puntos marcados en ámbar o rojo"

    health_rows = "".join(
        f'<div class="health-item">'
        f'<a href="#{sec}" onclick="irASeccion(\'{sec}\')">{e(nom)}</a>'
        f'<span class="pill {st}">{e(det)}</span>'
        f'</div>'
        for nom, _, det, sec, st in checks
    )

    # Hallazgo principal en 1 línea
    hallazgos = []
    if sin_comillas:
        hallazgos.append(f"{len(sin_comillas)} pasajes sin comillas")
    if citas_mal:
        hallazgos.append(f"{citas_mal} errores de citas")
    elif citas_mano:
        hallazgos.append(f"{citas_mano} citas escritas a mano")
    if enlaces_mal:
        hallazgos.append(f"{len(enlaces_mal)} enlaces web con problema")
    finding_line = " · ".join(hallazgos) if hallazgos else "Sin hallazgos críticos: citas, similitud e integridad en orden."

    # Alertas críticas
    alertas_html_items = []
    if not cit.get("hay_almacen"):
        alertas_html_items.append("El documento no contiene el almacén de fuentes de Word (<code>customXml/item.xml</code>).")
    if not cit.get("hay_bibliografia"):
        alertas_html_items.append("No se encontró el campo automático de Referencias (<code>BIBLIOGRAPHY</code>) de Word.")
    if sim.get("error"):
        alertas_html_items.append(e(sim["error"]))
    if sim.get("ilegibles"):
        links = []
        for arch in sim["ilegibles"]:
            nom_arch = Path(arch).name
            links.append(
                f'<a href="https://www.google.com/search?q={quote(nom_arch)}" target="_blank" rel="noopener noreferrer">'
                f'<code>{e(arch)}</code></a>'
            )
        alertas_html_items.append(
            f"Archivos sin texto extraíble en <code>2-FUENTES</code>: {', '.join(links)}. "
            '<a href="https://www.ilovepdf.com/es/ocr-pdf" target="_blank" rel="noopener noreferrer">Aplicar OCR</a>.'
        )
    alerta_html = "".join(
        f'<div class="alerta"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">'
        f'<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>'
        f'<div><b>Atención:</b> {a}</div></div>'
        for a in alertas_html_items
    )

    # Pasajes coincidentes
    cards_pasajes = "".join(_card_pasaje(p) for p in pasajes_raw) if pasajes_raw else (
        '<div class="caja-vacio">'
        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>'
        '<span>No se encontraron párrafos con coincidencias largas con tus fuentes.</span></div>'
    )
    filas_pasajes = [
        [
            f'<span class="pill {"bad" if p.get("estado") == "Sin comillas" else "ok"}">{e(p.get("estado", ""))}</span> '
            f'{_ubicacion_pasaje(p)}<div class="panel-meta">{e(p.get("fuente", ""))} · {p.get("palabras", 0)} pal.</div>',
            _instruccion_pasaje(p.get("estado", ""), p.get("palabras", 0)),
            f'<div class="frag-caja">{e(p.get("fragmento", ""))}</div>',
            f'<div class="parr-caja">{e(p.get("parrafo", ""))}</div>',
        ]
        for p in pasajes_raw
    ]
    tabla_pasajes = _tabla(["Detección y ubicación", "Qué hacer", "Fragmento idéntico", "Párrafo en tu tesis"], filas_pasajes)

    # Fuentes tabla
    filas_fuentes = [
        [
            e(f.get("fuente", "")),
            f'<span class="pill {_estado(f.get("porcentaje", 0) < 1.0, f.get("porcentaje", 0) < 5.0)}">{f.get("porcentaje", 0):.2f} %</span>',
            f'<a href="{e(f.get("comparacion", ""))}" target="_blank" class="btn-comp">Comparar lado a lado</a>',
        ]
        for f in fuentes_sim
    ]
    tabla_fuentes = _tabla(["Fuente analizada (2-FUENTES)", "#Coincidencia", "Comparación"], filas_fuentes, "Sin fuentes analizadas.")

    # Citas tablas
    filas_sin_fuente = [[f'<span class="pill bad">Sin fuente</span>', f'<code>{e(t)}</code>', 'Agregar en Word > Referencias > Administrar fuentes.'] for t in cit.get("sin_fuente", [])]
    t_sin_fuente = _tabla(["Estado", "Etiqueta", "Qué hacer"], filas_sin_fuente, "Todas las citas están registradas en la bibliografía.")

    filas_sin_citar = [[f'<span class="pill warn">No citada</span>', f'<code>{e(t)}</code>', e(ti), 'Eliminar de Word si no se usó en el cuerpo.'] for t, ti in cit.get("sin_citar", [])]
    t_sin_citar = _tabla(["Estado", "Etiqueta", "Obra", "Qué hacer"], filas_sin_citar, "Todas las fuentes registradas se citan en la tesis.")

    filas_plano = []
    for item in cit.get("texto_plano", []):
        cita_str = item.get("cita", "") if isinstance(item, dict) else str(item)
        ctx_str = item.get("contexto", "") if isinstance(item, dict) else ""
        loc_cell = _ubicacion_pasaje(item) if isinstance(item, dict) else "En el texto"
        filas_plano.append([f'<span class="pill warn">A mano</span>', f'<code>{e(cita_str)}</code>', loc_cell, e(ctx_str)])
    t_plano = _tabla(["Tipo", "Cita detectada", "Ubicación", "Contexto"], filas_plano, "No hay citas escritas a mano; todas usan campos de Word.")

    # Web tabla
    filas_web = []
    for x in sorted(w, key=lambda it: it.get("estado") == "OK"):
        st = x.get("estado", "")
        tag_st = "ok" if st == "OK" else ("warn" if st in ("Redirige", "Bloqueado") else "bad")
        filas_web.append([
            f'<span class="pill {tag_st}">{e(st)}</span>',
            f'<b>{e(x.get("titulo") or x.get("tag", ""))}</b>',
            f'<a href="{e(x.get("url", ""))}" target="_blank" style="color:var(--info)">{e(x.get("url", "")[:55])}…</a>',
            e(x.get("detalle", "") or x.get("metodo", "")),
        ])
    t_web = _tabla(["Estado", "Título / Etiqueta", "URL", "Detalle / Método"], filas_web, "No hay referencias con URL o DOI.")

    # Invisibles & Estructura & Historial
    filas_inv_ej = [[e(ej[0]), f'<code>{e(ej[1])}</code>', e(ej[2])] for ej in inv.get("ejemplos", [])[:40] if len(ej) >= 3]
    t_inv_ej = _tabla(["Ubicación", "Tipo", "Contexto"], filas_inv_ej, "Documento libre de caracteres invisibles.")

    filas_sust = [[e(su[0]), f'<b>{e(su[1])}</b>', e(su[2])] for su in inv.get("sustituidos", [])[:40] if len(su) >= 3]
    t_sust = _tabla(["Ubicación", "Palabra", "Contexto"], filas_sust, "No se detectaron letras camufladas de otros alfabetos.")

    filas_est = [['<span class="pill warn">Numeración</span>', e(prob)] for prob in est.get("problemas", [])]
    t_est = _tabla(["Tipo", "Detalle"], filas_est, f"Numeración correlativa correcta ({est.get('tablas', 0)} tablas · {est.get('figuras', 0)} figuras).")

    filas_hist = [
        [
            f'<b>{e(h.get("fecha", ""))}</b>',
            e(h.get("archivo", "")),
            f'<span class="pill {_estado(h.get("max_sim", 0) < 5, h.get("max_sim", 0) < 15)}">{h.get("max_sim", 0):.2f} %</span>',
            f'<span class="pill {_estado(h.get("sin_comillas", 0) == 0)}">{h.get("sin_comillas", 0)}</span>',
            f'<span class="pill {_estado(h.get("citas_mal", 0) == 0)}">{h.get("citas_mal", 0)}</span>',
            f'<span class="pill {_estado(h.get("enlaces_mal", 0) == 0, True)}">{h.get("enlaces_mal", 0)}</span>',
        ]
        for h in reversed(hist[-10:])
    ]
    t_hist = _tabla(["Fecha", "Archivo", "#Similitud máx.", "#Sin comillas", "#Citas err.", "#Enlaces mal"], filas_hist, "Sin revisiones previas.")

    tesis_titulo = d.get("carpeta_tesis") or d.get("archivo", "Tesis")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnóstico de Tesis: {e(tesis_titulo)}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/css/panel.css">
</head>
<body>

<div class="mobile-bar">
  <strong>Diagnóstico · {e(tesis_titulo)}</strong>
  <button type="button" class="btn" onclick="document.getElementById('sidebar').classList.toggle('open')">Menú</button>
</div>

<div class="app-shell">
  <aside class="sidebar" id="sidebar">
    <div class="brand">
      <div class="brand-mark" aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      </div>
      <div class="brand-text">
        <div class="brand-name">Kit Revisión</div>
        <div class="brand-scope" title="{e(tesis_titulo)}">{e(tesis_titulo)}</div>
      </div>
    </div>

    <div class="nav-group-label">Lectura del diagnóstico</div>
    <a class="nav-link active" href="#sec-exposicion" onclick="irASeccion('sec-exposicion', this)">
      <span class="nav-link-left">Exposición antiplagio</span>
    </a>
    <a class="nav-link" href="#sec-similitud" onclick="irASeccion('sec-similitud', this)">
      <span class="nav-link-left">Similitud y pasajes</span>
      <span class="nav-count {"bad" if sin_comillas else ""}">{len(sin_comillas)}</span>
    </a>
    <a class="nav-link" href="#sec-citas" onclick="irASeccion('sec-citas', this)">
      <span class="nav-link-left">Citas y web</span>
      <span class="nav-count {"warn" if (citas_mal + citas_mano + len(enlaces_mal)) else ""}">{citas_mal + citas_mano + len(enlaces_mal)}</span>
    </a>
    <a class="nav-link" href="#sec-invisibles" onclick="irASeccion('sec-invisibles', this)">
      <span class="nav-link-left">Integridad del documento</span>
    </a>
    <a class="nav-link" href="#sec-historial" onclick="irASeccion('sec-historial', this)">
      <span class="nav-link-left">Evolución de revisiones</span>
    </a>

    <div class="sidebar-bottom">
      <a class="btn" href="/index.html">← Centro de Control</a>
    </div>
  </aside>

  <main class="canvas">
    <div class="container">
      <div class="title-row">
        <div>
          <h1>Diagnóstico: {e(tesis_titulo)}</h1>
          <p class="title-finding">{e(finding_line)}</p>
          <p class="title-meta">Archivo: {e(d.get("archivo", ""))} · Fuentes: {e(d.get("fuentes_usadas", "Todas"))} · {e(d.get("fecha", ""))}</p>
        </div>
        <div class="title-actions">
          <button type="button" class="btn" onclick="window.print()">Imprimir / PDF</button>
          <a href="/index.html" class="btn primary">Centro de Control</a>
        </div>
      </div>

      {alerta_html}

      <!-- KPI Strip -->
      <section class="kpi-strip" aria-label="Indicadores principales">
        <a href="#sec-exposicion" class="kpi-cell lead">
          <span class="kpi-label">Texto que no es cita textual</span>
          <span class="kpi-value">{e(pct_no_citas_str)}</span>
          <span class="kpi-sub">{e(pal_no_citas_str)} del cuerpo</span>
        </a>
        <a href="#sec-exposicion" class="kpi-cell">
          <span class="kpi-label">Citas textuales</span>
          <span class="kpi-value">{e(pct_citas_str)}</span>
          <span class="kpi-sub ok">{e(pal_citas_str)} entrecomilladas/bloque</span>
        </a>
        <a href="#sec-fuentes" class="kpi-cell">
          <span class="kpi-label">Similitud máxima</span>
          <span class="kpi-value">{max_sim:.2f} <small>%</small></span>
          <span class="kpi-sub" title="{e(fuentes_sim[0]["fuente"] if fuentes_sim else "")}">{e(fuentes_sim[0]["fuente"][:28] if fuentes_sim else "Sin fuentes")}</span>
        </a>
        <a href="#sec-similitud" class="kpi-cell">
          <span class="kpi-label">Coincidencias sin comillas</span>
          <span class="kpi-value">{len(sin_comillas)}</span>
          <span class="kpi-sub {"bad" if sin_comillas else "ok"}">de {len(pasajes_raw)} coincidencias</span>
        </a>
      </section>

      <!-- Capítulo 0: Exposición y Salud -->
      <section id="sec-exposicion" class="grid-12">
        <div class="panel col-7">
          <div class="panel-head">
            <h3>Distribución del texto analizado</h3>
            <span class="panel-meta">{_fmt_num(exp.get("palabras_cuerpo", est.get("palabras", 0)))} palabras en cuerpo</span>
          </div>
          <div class="exp-bar-wrap">
            <div class="exp-legend">
              <span class="exp-leg-item"><span class="swatch propia"></span>No citas: redacción sin cita</span>
              <span class="exp-leg-item"><span class="swatch paraf"></span>No citas: paráfrasis con cita</span>
              <span class="exp-leg-item"><span class="swatch cita"></span>Son citas textuales</span>
            </div>
            {_svg_exposicion(exp)}
          </div>
          <p class="exp-context"><b>Cómo leerlo:</b> el bloque que no es cita textual incluye redacción propia y paráfrasis con referencia. No equivale por sí solo a plagio; muestra qué parte del cuerpo podría producir coincidencias literales.</p>
          <div class="exp-rows">
            <div class="exp-row">
              <div class="exp-row-label"><span class="swatch propia"></span><span>Redacción propia sin cita <span class="exp-row-sub">(expuesta a similitud)</span></span></div>
              <div class="exp-row-words">{_fmt_num(exp.get("palabras_redaccion_propia", 0))} pal.</div>
              <div class="exp-row-pct">{_fmt_pct(exp.get("pct_redaccion_propia", 0)) if has_exp else "—"}</div>
            </div>
            <div class="exp-row">
              <div class="exp-row-label"><span class="swatch paraf"></span><span>Paráfrasis con cita APA <span class="exp-row-sub">(expuesta si copia literal)</span></span></div>
              <div class="exp-row-words">{_fmt_num(exp.get("palabras_parafrasis_citada", 0))} pal.</div>
              <div class="exp-row-pct">{_fmt_pct(exp.get("pct_parafrasis_citada", 0)) if has_exp else "—"}</div>
            </div>
            <div class="exp-row">
              <div class="exp-row-label"><span class="swatch cita"></span><span>Citas textuales <span class="exp-row-sub">(comillas / bloque)</span></span></div>
              <div class="exp-row-words">{_fmt_num(exp.get("palabras_citas", 0))} pal.</div>
              <div class="exp-row-pct">{e(pct_citas_str)}</div>
            </div>
          </div>
        </div>

        <div class="panel col-5">
          <div class="panel-head">
            <h3>Salud general del documento</h3>
            <span class="panel-meta">{_fmt_num(est.get("palabras", 0))} pal. totales</span>
          </div>
          {_svg_ring(health_pct, health_label, health_sub)}
          <div class="health-list">{health_rows}</div>
        </div>
      </section>

      <!-- Capítulo 1: Similitud y Pasajes -->
      <section class="chapter" id="sec-similitud">
        <div class="chapter-head">
          <h2>1. Coincidencias y pasajes</h2>
          <span class="chapter-desc">Fuentes con mayor solapamiento y fragmentos detectados sin comillas</span>
        </div>

        <div class="panel" id="sec-fuentes">
          <div class="panel-head">
            <h3>Top fuentes por porcentaje de similitud</h3>
            <span class="panel-meta">{len(fuentes_sim)} fuentes comparadas · umbral sugerido 5 %</span>
          </div>
          {_svg_barras_fuentes(fuentes_sim)}
          <details class="panel-details">
            <summary>Ver tabla completa de las {len(fuentes_sim)} fuentes y enlaces de comparación</summary>
            <div style="margin-top:12px">{tabla_fuentes}</div>
          </details>
        </div>

        <div class="panel">
          <div class="panel-head">
            <h3>Pasajes coincidentes ({len(pasajes_raw)})</h3>
            <span class="pill {"bad" if sin_comillas else "ok"}">{len(sin_comillas)} sin comillas</span>
          </div>
          <div class="toolbar">
            <div class="segmented" role="group" aria-label="Filtrar pasajes">
              <button type="button" class="activo" onclick="filtrarPasajes('todos', this)">Todos ({len(pasajes_raw)})</button>
              <button type="button" onclick="filtrarPasajes('Sin comillas', this)">Sin comillas ({len(sin_comillas)})</button>
              <button type="button" onclick="filtrarPasajes('Entre comillas', this)">Con comillas ({sum(1 for p in pasajes_raw if p.get('estado') != 'Sin comillas')})</button>
            </div>
            <div class="segmented" role="group" aria-label="Modo de vista">
              <button type="button" class="btn-vista activo" onclick="setVistaPasajes('cards', this)">Comparativa</button>
              <button type="button" class="btn-vista" onclick="setVistaPasajes('tabla', this)">Tabla</button>
            </div>
          </div>

          <details class="panel-details" style="margin-top:0;margin-bottom:14px;padding-top:0;border-top:0">
            <summary>Guía rápida APA: cómo corregir cada tipo de coincidencia</summary>
            <div class="guia-grid">
              <div class="guia-item"><b>Cita larga (≥ 40 pal.)</b>Párrafo aparte con sangría de 1.27 cm, sin comillas y con autor, año y pág.</div>
              <div class="guia-item"><b>Cita corta (&lt; 40 pal.)</b>Dentro del párrafo entre comillas dobles <code>""</code> con autor, año y pág.</div>
              <div class="guia-item"><b>Paráfrasis</b>Redactar con palabras propias conservando la cita del autor.</div>
            </div>
          </details>

          <div id="pasajes-cards-container">{cards_pasajes}</div>
          <div id="pasajes-tabla-container" style="display:none">{tabla_pasajes}</div>
        </div>
      </section>

      <!-- Capítulo 2: Citas y Fuentes Web -->
      <section class="chapter" id="sec-citas">
        <div class="chapter-head">
          <h2>2. Citas, bibliografía y fuentes web</h2>
          <span class="chapter-desc">Consistencia del gestor de Word y accesibilidad de URLs/DOI</span>
        </div>

        <div class="grid-12">
          <div class="panel col-6">
            <div class="panel-head">
              <h3>Citas en el documento ({citas_totales})</h3>
              <span class="pill {citas_estado}">{citas_din} Word · {citas_mano} a mano</span>
            </div>
            {_svg_barra_proporcion([("Dinámicas Word", citas_din, "var(--chart-1)"), ("Escritas a mano", citas_mano, "var(--warn)")], "Proporción de citas")}
            <div class="panel-meta">{cit.get("fuentes_registradas", 0)} fuentes registradas en Word ({cit.get("fuentes_citadas", 0)} citadas en texto)</div>
          </div>

          <div class="panel col-6" id="sec-web">
            <div class="panel-head">
              <h3>Fuentes web evaluadas ({len(w)})</h3>
              <span class="pill {"warn" if enlaces_mal else "ok"}">{enlaces_ok} OK · {len(enlaces_mal)} con problema</span>
            </div>
            {_svg_barra_proporcion([("OK", enlaces_ok, "var(--ok)"), ("Con problema", len(enlaces_mal), "var(--warn)")], "Estado de enlaces web")}
            <div class="panel-meta">Enlaces descargados para comparar similitud con fuentes en línea.</div>
          </div>
        </div>

        <div class="panel" style="margin-top:16px">
          <div class="subseccion" style="margin-top:0">
            <h4>Citas sin fuente en Word ({len(cit.get("sin_fuente", []))})</h4>
            {t_sin_fuente}
          </div>
          <div class="subseccion">
            <h4>Fuentes registradas nunca citadas ({len(cit.get("sin_citar", []))})</h4>
            {t_sin_citar}
          </div>
          <div class="subseccion" id="sec-citas-mano">
            <h4>Citas escritas a mano ({citas_mano})</h4>
            {t_plano}
          </div>
          <div class="subseccion">
            <h4>Detalle de fuentes web ({len(w)})</h4>
            <details class="panel-details" style="margin-top:0;padding-top:0;border-top:0" {"open" if enlaces_mal else ""}>
              <summary>Ver listado de {len(w)} enlaces evaluados</summary>
              <div style="margin-top:10px">{t_web}</div>
            </details>
          </div>
        </div>
      </section>

      <!-- Capítulo 3: Integridad e Historial -->
      <section class="chapter" id="sec-invisibles">
        <div class="chapter-head">
          <h2>3. Integridad del documento e historial</h2>
          <span class="chapter-desc">Caracteres ocultos, numeración de elementos y evolución entre revisiones</span>
        </div>

        <div class="grid-12">
          <div class="panel col-6">
            <div class="panel-head">
              <h3>Caracteres invisibles y homoglifos</h3>
              <span class="pill {"bad" if homoglifos else ("warn" if inv_tot else "ok")}">{inv_tot} invisibles · {homoglifos} camufladas</span>
            </div>
            <div class="subseccion" style="margin-top:0">{t_inv_ej}</div>
            <div class="subseccion" id="sec-homoglifos">
              <h4>Letras de otros alfabetos ({homoglifos})</h4>
              {t_sust}
            </div>
          </div>

          <div class="panel col-6" id="sec-tablas">
            <div class="panel-head">
              <h3>Tablas y figuras</h3>
              <span class="pill {"warn" if prob_est else "ok"}">{est.get("tablas", 0)} tablas · {est.get("figuras", 0)} figuras</span>
            </div>
            {t_est}
          </div>
        </div>

        <div class="panel" id="sec-historial" style="margin-top:16px">
          <div class="panel-head">
            <h3>Evolución de revisiones ({len(hist)})</h3>
            <span class="panel-meta">Similitud máxima histórica</span>
          </div>
          {_svg_historial(hist)}
          <div style="margin-top:14px">{t_hist}</div>
        </div>
      </section>
    </div>
  </main>
</div>

<script>
function setVistaPasajes(vista, btn) {{
  var cards = document.getElementById('pasajes-cards-container');
  var tabla = document.getElementById('pasajes-tabla-container');
  if (!cards || !tabla) return;
  document.querySelectorAll('.btn-vista').forEach(function(b) {{ b.classList.remove('activo'); }});
  if (btn) btn.classList.add('activo');
  cards.style.display = vista === 'tabla' ? 'none' : 'block';
  tabla.style.display = vista === 'tabla' ? 'block' : 'none';
}}

function filtrarPasajes(filtro, btn) {{
  if (btn && btn.parentElement) {{
    btn.parentElement.querySelectorAll('button').forEach(function(b) {{ b.classList.remove('activo'); }});
    btn.classList.add('activo');
  }}
  document.querySelectorAll('#pasajes-cards-container .pasaje-card').forEach(function(c) {{
    var st = c.getAttribute('data-estado') || '';
    if (filtro === 'todos') {{
      c.style.display = '';
    }} else if (filtro === 'Sin comillas') {{
      c.style.display = st === 'Sin comillas' ? '' : 'none';
    }} else {{
      c.style.display = st !== 'Sin comillas' ? '' : 'none';
    }}
  }});
}}

function irASeccion(id, linkEl) {{
  var el = document.getElementById(id);
  if (linkEl) {{
    document.querySelectorAll('.nav-link').forEach(function(a) {{ a.classList.remove('active'); }});
    linkEl.classList.add('active');
  }}
  var sb = document.getElementById('sidebar');
  if (sb) sb.classList.remove('open');
  if (!el) return;
  el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
}}
</script>
</body>
</html>"""

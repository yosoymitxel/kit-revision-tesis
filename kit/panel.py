"""Panel HTML autocontenido con los resultados y diagnóstico detallado de la tesis."""
from html import escape as e
from pathlib import Path
from urllib.parse import quote


# Sistema de colores: rojo (bad), ámbar (warn), verde (ok), azul (neutral)
def _estado(ok, warn=False):
    return "ok" if ok else ("warn" if warn else "bad")


def _kpi(titulo, valor, estado, detalle=""):
    svgs = {
        "ok": '<svg class="kpi-svg ok" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>',
        "warn": '<svg class="kpi-svg warn" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>',
        "bad": '<svg class="kpi-svg bad" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>',
        "neutral": '<svg class="kpi-svg neutral" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>',
    }
    svg_icon = svgs.get(estado, svgs["neutral"])
    return (f'<div class="kpi {estado}">'
            f'<div class="kv"><span class="kpi-icon">{svg_icon}</span> {e(str(valor))}</div>'
            f'<div class="kt">{e(titulo)}</div>'
            f'<div class="kd">{e(detalle)}</div>'
            f'</div>')


def _tabla(cabeceras, filas, vacio="Nada para mostrar.", clase=""):
    if not filas:
        return (f'<div class="caja-vacio">'
                f'<svg class="vacio-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>'
                f'<p class="vacio">{e(vacio)}</p></div>')
    th = "".join(f"<th>{e(c)}</th>" for c in cabeceras)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    cls_attr = f' class="{e(clase)}"' if clase else ""
    return f'<div class="tabla-contenedor"><table{cls_attr}><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table></div>'


def _ubicacion_pasaje(p):
    """Genera HTML destacado con la ubicación del problema (página, título y subtítulo)."""
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

    if not partes:
        return '<span class="loc-none">No ubicado</span>'
    return f'<div class="loc-box">{" ".join(partes)}</div>'


def _instruccion_pasaje(estado, palabras=0):
    """Instrucciones concisas para corregir un pasaje según norma APA / académica."""
    if estado == "Sin comillas":
        if palabras >= 40:
            return (
                '<div class="inst-box bad">'
                '<div class="inst-tit">Cita larga en bloque</div>'
                '<div class="inst-desc">Poner en párrafo aparte con sangría de 1.27 cm, sin comillas, y citar autor, año y pág. O parafrasear.</div>'
                '</div>'
            )
        else:
            return (
                '<div class="inst-box bad">'
                '<div class="inst-tit">Cita corta literal</div>'
                '<div class="inst-desc">Encerrar entre comillas dobles <code>""</code> y citar autor, año y pág. O parafrasear con redacción propia.</div>'
                '</div>'
            )
    elif estado == "Entre comillas":
        return (
            '<div class="inst-box ok">'
            '<div class="inst-tit">Cita entre comillas</div>'
            '<div class="inst-desc">Verificar que incluya el número de página o artículo de la fuente.</div>'
            '</div>'
        )
    elif estado == "En bloque":
        return (
            '<div class="inst-box ok">'
            '<div class="inst-tit">Cita en bloque</div>'
            '<div class="inst-desc">Verificar sangría reglamentaria de 1.27 cm y cita al final.</div>'
            '</div>'
        )
    else:
        return (
            '<div class="inst-box warn">'
            '<div class="inst-tit">Revisar contexto</div>'
            '<div class="inst-desc">Confirmar si corresponde a redacción propia o cita omitida.</div>'
            '</div>'
        )


def _ubicacion_cita_plana(item):
    """Ubicación de cita escrita a mano."""
    if isinstance(item, dict):
        pag = item.get("pagina")
        tit = item.get("titulo", "")
        sub = item.get("subtitulo", "")
        partes = []
        if pag:
            partes.append(f'<span class="badge-pag">Pág. {pag}</span>')
        if tit:
            partes.append(f'<span class="loc-tit">{e(tit)}</span>')
        if sub:
            partes.append(f'<span class="loc-sub">› {e(sub)}</span>')
        return f'<div class="loc-box">{" ".join(partes)}</div>' if partes else "No ubicado"
    return '<span class="loc-none">En el texto</span>'


def _card_pasaje(p):
    """Genera una tarjeta comparativa lado a lado con distribución balanceada."""
    st = p.get("estado", "")
    tag_cls = "bad" if st == "Sin comillas" else ("warn" if st == "No ubicado" else "ok")
    n_pal = p.get("palabras", 0)
    pag = p.get("pagina")
    tit = p.get("titulo", "")
    sub = p.get("subtitulo", "")
    fuente = p.get("fuente", "")
    frag = p.get("fragmento", "")
    parr = p.get("parrafo", "")

    partes = []
    if pag:
        partes.append(f'<span class="badge-pag">Pág. {pag}</span>')
    if tit:
        partes.append(f'<span class="loc-tit" title="{e(tit)}">{e(tit)}</span>')
    elif pag and pag <= 10:
        partes.append('<span class="loc-tit">Páginas preliminares</span>')
    if sub:
        partes.append(f'<span class="loc-sub" title="{e(sub)}">› {e(sub)}</span>')
    loc_html = " ".join(partes) if partes else '<span class="loc-none">En el cuerpo del texto</span>'

    if st == "Sin comillas":
        if n_pal >= 40:
            accion_html = (
                '<div class="pasaje-accion bad">'
                '<div class="pasaje-accion-tit">Acción requerida: Cita larga en bloque (≥ 40 palabras)</div>'
                '<div class="pasaje-accion-desc">'
                'Poner en párrafo aparte con sangría izquierda de 1.27 cm (0.5"), sin comillas, interlineado doble '
                'e indicar autor, año y página al final. O redactar la idea íntegramente con tus palabras (paráfrasis).'
                '</div>'
                '</div>'
            )
        else:
            accion_html = (
                '<div class="pasaje-accion bad">'
                '<div class="pasaje-accion-tit">Acción requerida: Cita corta literal (&lt; 40 palabras)</div>'
                '<div class="pasaje-accion-desc">'
                'Encerrar el fragmento idéntico entre comillas dobles <code>""</code> e indicar autor, año y número de página. '
                'O redactar con redacción propia citando la fuente.'
                '</div>'
                '</div>'
            )
    elif st == "Entre comillas":
        accion_html = (
            '<div class="pasaje-accion ok">'
            '<div class="pasaje-accion-tit">Conforme: Cita entre comillas</div>'
            '<div class="pasaje-accion-desc">El fragmento está entrecomillado. Verifica que tenga la cita de autor, año y página al final.</div>'
            '</div>'
        )
    elif st == "En bloque":
        accion_html = (
            '<div class="pasaje-accion ok">'
            '<div class="pasaje-accion-tit">Conforme: Cita en bloque</div>'
            '<div class="pasaje-accion-desc">Párrafo formateado en bloque con sangría. Confirma que la fuente esté registrada en Referencias.</div>'
            '</div>'
        )
    else:
        accion_html = (
            '<div class="pasaje-accion warn">'
            '<div class="pasaje-accion-tit">Revisar contexto del fragmento</div>'
            '<div class="pasaje-accion-desc">Confirma si este fragmento es de autoría propia o requiere citar la fuente bibliográfica.</div>'
            '</div>'
        )

    return (
        f'<div class="pasaje-card {tag_cls}">'
        f'<div class="pasaje-header">'
        f'<div class="pasaje-meta">'
        f'<span class="tag {tag_cls}">{e(st)}</span>'
        f'{loc_html}'
        f'</div>'
        f'<div class="pasaje-fte-meta">'
        f'<span class="pasaje-fuente-nom" title="{e(fuente)}">Fuente: <b>{e(fuente)}</b></span>'
        f'<span class="palabras-meta-badge">{n_pal} palabras idénticas</span>'
        f'</div>'
        f'</div>'
        f'{accion_html}'
        f'<div class="pasaje-grid-comparativa">'
        f'<div class="pasaje-col">'
        f'<div class="col-head">'
        f'<span class="col-dot {tag_cls}"></span>'
        f'<span>Fragmento idéntico detectado</span>'
        f'</div>'
        f'<div class="frag-caja">{e(frag)}</div>'
        f'</div>'
        f'<div class="pasaje-col">'
        f'<div class="col-head">'
        f'<span class="col-dot neutral"></span>'
        f'<span>Párrafo en tu tesis ({("Pág. " + str(pag)) if pag else "En el cuerpo"})</span>'
        f'</div>'
        f'<div class="parr-caja">{e(parr)}</div>'
        f'</div>'
        f'</div>'
        f'</div>'
    )


def generar(d):
    sim = d.get("similitud", {})
    cit = d.get("citas", {})
    inv = d.get("invisibles", {})
    est = d.get("estructura", {})
    w = d.get("web", [])

    enlaces_mal = [x for x in w if x.get("estado") != "OK"]
    sin_comillas = [p for p in sim.get("pasajes", []) if p.get("estado") == "Sin comillas"]
    max_sim = sim["fuentes"][0]["porcentaje"] if sim.get("fuentes") else 0
    citas_mal = len(cit.get("sin_fuente", [])) + len(cit.get("sin_citar", [])) + (0 if cit.get("hay_almacen") else 1)

    # Resumen de métricas
    kpis = "".join([
        _kpi("Palabras en Tesis", f'{est.get("palabras", 0):,}'.replace(",", "."), "neutral",
             f'{est.get("tablas", 0)} tablas · {est.get("figuras", 0)} figuras'),
        _kpi("Similitud Máxima", f"{max_sim:.1f} %", _estado(max_sim < 5, max_sim < 15),
             sim["fuentes"][0]["fuente"] if sim.get("fuentes") else "sin fuentes"),
        _kpi("Párrafos Sin Comillas", len(sin_comillas), _estado(not sin_comillas),
             f'de {len(sim.get("pasajes", []))} coincidencias detectadas'),
        _kpi("Problemas de Citas", citas_mal, _estado(citas_mal == 0),
             f'{cit.get("campos_cita", 0)} citas · {cit.get("fuentes_registradas", 0)} fuentes'),
        _kpi("Citas a Mano", len(cit.get("texto_plano", [])), _estado(not cit.get("texto_plano"), True),
             "no vinculadas a la bibliografía"),
        _kpi("Caracteres Invisibles", inv.get("total", 0), _estado(inv.get("total", 0) == 0, True),
             "espacios o marcas de copiar/pegar"),
        _kpi("Letras de Otro Alfabeto", len(inv.get("sustituidos", [])), _estado(not inv.get("sustituidos")),
             "cirílico/griego camuflado"),
        _kpi("Enlaces con Problema", len(enlaces_mal), _estado(not enlaces_mal, True),
             f'{len(w)} fuentes web evaluadas'),
        _kpi("Tablas y Figuras", len(est.get("problemas", [])), _estado(not est.get("problemas"), True),
             "errores de numeración"),
    ])

    # Alertas críticas
    alertas_html_items = []
    if not cit.get("hay_almacen"):
        alertas_html_items.append("El documento no contiene el almacén de fuentes de Word (<code>customXml/item.xml</code>). "
                                 "Las citas automáticas no funcionarán correctamente. Si limpiaste el documento con una herramienta externa, vuelve a una copia previa.")
    if not cit.get("hay_bibliografia"):
        alertas_html_items.append("No se encontró el campo automático de Referencias (campo <code>BIBLIOGRAPHY</code> de Word). Recuerda insertar la bibliografía desde la pestaña Referencias.")
    if sim.get("error"):
        alertas_html_items.append(e(sim["error"]))
    if sim.get("ilegibles"):
        links_ilegibles = []
        for arch in sim["ilegibles"]:
            nom_arch = Path(arch).name
            query = quote(nom_arch)
            link = (
                f'<a href="https://www.google.com/search?q={query}" target="_blank" rel="noopener noreferrer" '
                f'class="enlace-busqueda-pdf" title="Buscar en Google: {e(nom_arch)}">'
                f'<code>{e(arch)}</code> '
                f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>'
                f'</a>'
            )
            links_ilegibles.append(link)

        ocr_link = '<a href="https://www.ilovepdf.com/es/ocr-pdf" target="_blank" rel="noopener noreferrer" class="enlace-ocr-pdf">conviértelos con OCR en iLovePDF</a>'
        alertas_html_items.append(
            f"No se pudo extraer texto de los siguientes archivos en <code>2-FUENTES</code>: {', '.join(links_ilegibles)}. "
            f"Pueden ser PDF escaneados; {ocr_link} o consigue la versión digital con texto seleccionable."
        )

    alerta_html = "".join(f'<div class="alerta">'
                           f'<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polygon points="7.86 2 16.14 2 22 7.86 22 16.14 16.14 22 7.86 22 2 16.14 2 7.86 7.86 2"></polygon><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>'
                           f'<div><b>Atención requerida:</b> {a}</div></div>' for a in alertas_html_items)

    # Pasajes coincidentes
    pasajes_raw = sim.get("pasajes", [])
    if pasajes_raw:
        cards_pasajes = "".join(_card_pasaje(p) for p in pasajes_raw)
    else:
        cards_pasajes = (
            '<div class="caja-vacio">'
            '<svg class="vacio-svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>'
            '<p class="vacio">No se encontraron párrafos con coincidencias largas no citadas con tus fuentes.</p>'
            '</div>'
        )

    filas_pasajes = []
    for p in pasajes_raw:
        st = p.get("estado", "")
        tag_cls = "bad" if st == "Sin comillas" else ("warn" if st == "No ubicado" else "ok")
        n_pal = p.get("palabras", 0)
        col_det = (
            f'<div class="tb-det">'
            f'<span class="tag {tag_cls}">{e(st)}</span>'
            f'<div class="tb-loc">{_ubicacion_pasaje(p)}</div>'
            f'<div class="tb-fte" title="{e(p.get("fuente", ""))}">{e(p.get("fuente", ""))}</div>'
            f'<div class="palabras-meta">{n_pal} palabras coincidentes</div>'
            f'</div>'
        )
        col_accion = _instruccion_pasaje(st, n_pal)
        col_frag = f'<div class="frag-caja">{e(p.get("fragmento", ""))}</div>'
        col_parr = f'<div class="parr-caja">{e(p.get("parrafo", ""))}</div>'
        filas_pasajes.append([col_det, col_accion, col_frag, col_parr])

    s_pasajes = _tabla(
        ["Detección y Ubicación", "Qué hacer", "Fragmento idéntico", "Párrafo en tu tesis"],
        filas_pasajes,
        "No se encontraron párrafos con coincidencias largas no citadas con tus fuentes.",
        clase="tabla-pasajes"
    )

    guia_solucion = """
    <div class="guia-solucion-citas">
      <div class="guia-sol-card bad">
        <div class="guia-sol-tit">Cita textual larga (≥ 40 palabras)</div>
        <div class="guia-sol-txt">Poner en párrafo aparte con sangría izquierda de 1.27 cm (0.5"), sin comillas, interlineado doble y citar autor, año y pág. al final.</div>
      </div>
      <div class="guia-sol-card warn">
        <div class="guia-sol-tit">Cita textual corta (&lt; 40 palabras)</div>
        <div class="guia-sol-txt">Incorporar dentro del párrafo entre comillas dobles <code>""</code> indicando autor, año y número de página de la fuente.</div>
      </div>
      <div class="guia-sol-card ok">
        <div class="guia-sol-tit">Paráfrasis (Recomendado)</div>
        <div class="guia-sol-txt">Redactar la idea íntegramente con tus propias palabras y conservar la cita del autor para respaldar la afirmación.</div>
      </div>
    </div>
    """

    # Similitud por fuente
    filas_fuentes = []
    for f in sim.get("fuentes", []):
        pct = f.get("porcentaje", 0.0)
        st_pct = _estado(pct < 1.0, pct < 5.0)
        filas_fuentes.append([
            f'<span class="nombre-archivo">{e(f.get("fuente", ""))}</span>',
            f'<span class="tag {st_pct}">{pct:.2f} %</span>',
            f'<a href="{e(f.get("comparacion", ""))}" target="_blank" class="btn-comp">Ver comparación lado a lado</a>'
        ])

    s_fuentes = _tabla(
        ["Fuente analizada (en 2-FUENTES)", "Porcentaje de coincidencia", "Comparación visual"],
        filas_fuentes,
        "Coloca tus archivos fuente (PDF, DOCX, TXT) en la carpeta 2-FUENTES para comparar."
    )

    # Citas y referencias
    filas_sin_fuente = [[f'<span class="tag bad">Sin fuente</span>', f'<code>{e(t)}</code>',
                         'Esta cita existe en el cuerpo de tu tesis pero no figura en el almacén de referencias de Word. Agrégala desde "Referencias > Administrar fuentes".']
                        for t in cit.get("sin_fuente", [])]
    t_sin_fuente = _tabla(["Estado", "Etiqueta citada", "Qué hacer"], filas_sin_fuente, "Todas las citas en el texto están registradas en la bibliografía.")

    filas_sin_citar = [[f'<span class="tag warn">No citada</span>', f'<code>{e(t)}</code>', e(ti),
                        'Registraste esta fuente en Word pero nunca la citas en ningún párrafo. Si no la utilizaste, elimínala de la bibliografía final.']
                       for t, ti in cit.get("sin_citar", [])]
    t_sin_citar = _tabla(["Estado", "Etiqueta", "Título de la obra", "Qué hacer"], filas_sin_citar, "Todas las fuentes registradas se citan en la tesis.")

    filas_plano = []
    for item in cit.get("texto_plano", []):
        if isinstance(item, dict):
            cita_str = item.get("cita", "")
            ctx_str = item.get("contexto", "")
            loc_cell = _ubicacion_cita_plana(item)
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            cita_str = item[0]
            ctx_str = item[1]
            loc_cell = '<span class="loc-none">En el texto</span>'
        else:
            cita_str, ctx_str, loc_cell = str(item), "", "—"

        filas_plano.append([
            f'<span class="tag warn">Escrita a mano</span>',
            f'<code>{e(cita_str)}</code>',
            loc_cell,
            f'<span class="ctx-texto">{e(ctx_str)}</span>',
            '<b>Reemplazar:</b> Elimina este texto tipeado manualmente e inserta la cita con la herramienta oficial de Word (<i>Referencias > Insertar cita</i>) para que alimente el índice y bibliografía automática.'
        ])

    t_plano = _tabla(["Tipo", "Cita detectada", "Dónde está", "Contexto en el párrafo", "Qué hacer"],
                     filas_plano, "No hay citas escritas a mano. Todas usan los campos de Word.")

    s_citas = f"""
    <div class="subseccion">
        <h4>1. Citas en el texto cuya fuente no existe en Word ({len(cit.get("sin_fuente", []))})</h4>
        {t_sin_fuente}
    </div>
    <div class="subseccion">
        <h4>2. Fuentes registradas que nunca se citan en el texto ({len(cit.get("sin_citar", []))})</h4>
        {t_sin_citar}
    </div>
    <div class="subseccion">
        <h4>3. Citas escritas a mano (texto plano no dinámico) ({len(cit.get("texto_plano", []))})</h4>
        <p class="nota">Estas citas fueron escritas a máquina entre paréntesis y no usan el gestor de Word. Si no las reemplazas, la bibliografía automática no las incluirá.</p>
        {t_plano}
    </div>
    """

    # Fuentes web
    def _web_instruccion(x):
        st = x.get("estado", "")
        if st == "Caído":
            return '<b>Enlace roto:</b> El enlace devuelve error o 404. Busca el documento en el archivo histórico <a href="https://web.archive.org" target="_blank">Wayback Machine</a> o actualiza la URL en la bibliografía.'
        elif st == "Redirige":
            return '<b>URL desactualizada:</b> El enlace redirige a otra dirección. Modifica la referencia en Word colocando la URL final para evitar advertencias de enlaces no vigentes.'
        elif st == "Bloqueado":
            return '<b>Protegido contra descargas:</b> El portal bloqueó la lectura automatizada (Cloudflare/Captcha). Descarga el PDF o guarda la página como PDF y colócala en <code>2-FUENTES/web</code>.'
        elif st == "Sin texto":
            return '<b>Página interactiva sin texto estático:</b> El sitio carga vía JavaScript. Guarda la versión para imprimir en PDF en <code>2-FUENTES/web</code> para que pueda compararse.'
        return '<span class="txt-ok">Contenido descargado e incluido en la comparación de similitud.</span>'

    filas_web = []
    for x in sorted(w, key=lambda it: it.get("estado") == "OK"):
        st = x.get("estado", "")
        tag_st = "ok" if st == "OK" else ("warn" if st in ("Redirige", "Bloqueado") else "bad")
        filas_web.append([
            f'<span class="tag {tag_st}">{e(st)}</span>',
            f'<div class="inst-web">{_web_instruccion(x)}</div>',
            f'<b>{e(x.get("titulo") or x.get("tag", ""))}</b>',
            f'<a href="{e(x.get("url", ""))}" target="_blank" class="enlace-web">{e(x.get("url", "")[:60])}…</a>',
            f'<span class="detalle-web">{e(x.get("detalle", ""))}</span>',
            f'<code>{e(x.get("metodo", ""))}</code>'
        ])

    s_web = _tabla(
        ["Estado", "Qué hacer con este enlace", "Título / Etiqueta", "Dirección URL", "Detalle técnico", "Método"],
        filas_web,
        "La bibliografía de Word no contiene referencias con URL o código DOI."
    )

    # Invisibles y caracteres sustituidos
    filas_inv_tipo = [[f'<code>{e(k)}</code>', f'<span class="badge-num">{v}</span>',
                       'Espacios de ancho cero o guiones suaves que entran al copiar texto desde páginas web, navegadores o chats.']
                      for k, v in inv.get("por_tipo", {}).items()]
    t_inv_tipo = _tabla(["Tipo de carácter invisible", "Cantidad encontrada", "Descripción"], filas_inv_tipo, "No hay caracteres invisibles.")

    filas_inv_ej = []
    for ej in inv.get("ejemplos", [])[:60]:
        if len(ej) == 3:
            donde, tipo, ctx = ej
        else:
            donde, tipo, ctx = str(ej[0]), "Invisible", str(ej[-1])
        filas_inv_ej.append([
            f'<span class="loc-tit">{e(donde)}</span>',
            f'<code>{e(tipo)}</code>',
            f'<div class="ctx-inv">{e(ctx)}</div>',
            'Usa el botón <b>Limpiar Invisibles</b> en el Centro de Control para eliminarlos automáticamente sin dañar citas ni estilos.'
        ])
    t_inv_ej = _tabla(["Dónde se encuentra (Pág / Título)", "Tipo", "Contexto (⟦·⟧ = invisible)", "Acción recomendada"],
                      filas_inv_ej, "Documento libre de caracteres invisibles.")

    filas_sust = []
    for su in inv.get("sustituidos", [])[:60]:
        if len(su) == 3:
            donde, pal, ctx = su
        else:
            donde, pal, ctx = str(su[0]), str(su[1]), str(su[-1])
        filas_sust.append([
            f'<span class="loc-tit">{e(donde)}</span>',
            f'<b class="bad-text">{e(pal)}</b>',
            f'<div class="ctx-inv">{e(ctx)}</div>',
            '<b class="bad-text">Corregir obligatoriamente:</b> Reemplaza la palabra tipeándola normalmente en español. El software de control antiplagio de universidades penaliza las letras camufladas.'
        ])
    t_sust = _tabla(["Dónde se encuentra (Pág / Título)", "Palabra afectada", "Contexto en tu tesis", "Acción recomendada"],
                    filas_sust, "No se detectaron letras de otros alfabetos camufladas.")

    s_inv = f"""
    <div class="subseccion">
        <h4>1. Frecuencia por tipo de carácter invisible ({inv.get("total", 0)} detectados)</h4>
        {t_inv_tipo}
    </div>
    <div class="subseccion">
        <h4>2. Ubicaciones de caracteres invisibles (primeras ocurrencias)</h4>
        {t_inv_ej}
    </div>
    <div class="subseccion">
        <h4>3. Letras de otros alfabetos camufladas ({len(inv.get("sustituidos", []))} encontradas)</h4>
        <p class="nota bad-nota"><b>Observación reglamentaria:</b> Letras griegas o cirílicas que se ven idénticas a letras latinas (ej. 'а', 'е', 'о'). Se consideran intento de engaño por los comités evaluadores. Cámbialas manualmente en Word.</p>
        {t_sust}
    </div>
    """

    # Tablas y figuras
    filas_est = []
    for prob in est.get("problemas", []):
        filas_est.append([
            '<span class="tag warn">Numeración</span>',
            e(prob),
            'Revisa los títulos de tablas y figuras en Word. Verifica que los números sean consecutivos (Tabla 1, Tabla 2...) y que cada tabla mencionada en el cuerpo exista efectivamente.'
        ])
    s_est = _tabla(["Tipo de problema", "Detalle detectado", "Qué hacer"], filas_est, "La numeración de tablas y figuras es completamente correlativa y consistente.")

    # Historial de revisiones
    hist = d.get("historial", [])
    filas_hist = []
    for h in reversed(hist[-10:]):
        m_sim = h.get("max_sim", 0)
        s_com = h.get("sin_comillas", 0)
        c_mal = h.get("citas_mal", 0)
        i_tot = h.get("invisibles", 0)
        e_mal = h.get("enlaces_mal", 0)
        filas_hist.append([
            f'<b>{e(h.get("fecha", ""))}</b>',
            e(h.get("archivo", "")),
            f'<span class="tag {_estado(m_sim < 5, m_sim < 15)}">{m_sim:.1f} %</span>',
            f'<span class="tag {_estado(s_com == 0)}">{s_com}</span>',
            f'<span class="tag {_estado(c_mal == 0)}">{c_mal}</span>',
            f'<span class="tag {_estado(i_tot == 0, True)}">{i_tot}</span>',
            f'<span class="tag {_estado(e_mal == 0, True)}">{e_mal}</span>'
        ])
    hist_html = _tabla(["Fecha de revisión", "Archivo evaluado", "Similitud máx.", "Sin comillas", "Citas con problema", "Invisibles", "Enlaces rotos"],
                       filas_hist, "Aún no hay revisiones históricas registradas.")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Diagnóstico y Revisión de Tesis: {e(d.get("archivo", "Tesis"))}</title>
<style>
:root {{
  --bg: #f8fafc;
  --card: #ffffff;
  --tx: #0f172a;
  --mut: #64748b;
  --bd: #e2e8f0;
  --bd-focus: #cbd5e1;

  /* Paleta unificada */
  --ok: #0f766e;
  --ok-bg: #f0fdfa;
  --ok-bd: #99f6e4;
  --ok-tx: #115e59;

  --warn: #b45309;
  --warn-bg: #fffbeb;
  --warn-bd: #fde68a;
  --warn-tx: #92400e;

  --bad: #b91c1c;
  --bad-bg: #fef2f2;
  --bad-bd: #fecaca;
  --bad-tx: #991b1b;

  --info: #1d4ed8;
  --info-bg: #eff6ff;
  --info-bd: #bfdbfe;
  --info-tx: #1e40af;
}}

@media (prefers-color-scheme: dark) {{
  :root {{
    --bg: #0b0f17;
    --card: #151b26;
    --tx: #f1f5f9;
    --mut: #94a3b8;
    --bd: #242e42;
    --bd-focus: #334155;

    --ok-bg: #042f2e;
    --ok-bd: #115e59;
    --ok-tx: #5eead4;

    --warn-bg: #451a03;
    --warn-bd: #78350f;
    --warn-tx: #fcd34d;

    --bad-bg: #450a0a;
    --bad-bd: #7f1d1d;
    --bad-tx: #fca5a5;

    --info-bg: #172554;
    --info-bd: #1e40af;
    --info-tx: #93c5fd;
  }}
}}

* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  font: 14.5px/1.6 system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
  background: var(--bg);
  color: var(--tx);
}}

/* ── Encabezado y Barra Superior ── */
header {{
  background: var(--card);
  border-bottom: 1px solid var(--bd);
  padding: 18px 32px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.header-titles h1 {{
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.3px;
}}
.header-titles .sub {{
  color: var(--mut);
  font-size: 13.5px;
  margin-top: 3px;
}}
.header-actions {{
  display: flex;
  gap: 12px;
  align-items: center;
}}
.btn-control {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 15px;
  background: var(--info-bg);
  color: var(--info);
  border: 1px solid var(--info-bd);
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  text-decoration: none;
  transition: all 0.15s ease;
}}
.btn-control:hover {{
  background: var(--info);
  color: #fff;
  border-color: var(--info);
}}

main {{
  padding: 24px 32px 64px;
  max-width: 1480px;
  margin: 0 auto;
}}

/* ── Guía Unificada de Colores ── */
.guia-colores {{
  background: var(--card);
  border: 1px solid var(--bd);
  border-radius: 12px;
  padding: 14px 20px;
  margin-bottom: 24px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}}
.guia-header {{
  font-weight: 700;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  color: var(--mut);
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.guia-items {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}}
.guia-item {{
  display: flex;
  align-items: flex-start;
  gap: 10px;
  font-size: 13px;
  line-height: 1.4;
}}
.guia-bullet {{
  width: 14px;
  height: 14px;
  border-radius: 4px;
  flex-shrink: 0;
  margin-top: 2px;
}}
.guia-bullet.bad {{ background: var(--bad); }}
.guia-bullet.warn {{ background: var(--warn); }}
.guia-bullet.ok {{ background: var(--ok); }}
.guia-bullet.info {{ background: var(--info); }}

/* ── Alertas Críticas ── */
.alerta {{
  background: var(--bad-bg);
  color: var(--bad-tx);
  border: 1px solid var(--bad-bd);
  border-radius: 10px;
  padding: 12px 18px;
  margin-bottom: 20px;
  font-size: 14px;
  display: flex;
  align-items: flex-start;
  gap: 12px;
}}

/* ── KPIs (Métricas Principales) ── */
.kpis {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(215px, 1fr));
  gap: 14px;
  margin-bottom: 28px;
}}
.kpi {{
  background: var(--card);
  border: 1px solid var(--bd);
  border-left: 5px solid var(--mut);
  border-radius: 10px;
  padding: 16px 18px;
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}}
.kpi:hover {{
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0,0,0,0.05);
}}
.kpi.bad {{ border-left-color: var(--bad); background: var(--bad-bg); }}
.kpi.warn {{ border-left-color: var(--warn); background: var(--warn-bg); }}
.kpi.ok {{ border-left-color: var(--ok); background: var(--ok-bg); }}
.kpi.neutral {{ border-left-color: var(--info); background: var(--info-bg); }}

.kv {{
  font-size: 26px;
  font-weight: 800;
  line-height: 1.2;
  display: flex;
  align-items: center;
  gap: 6px;
}}
.kpi-icon {{ font-size: 20px; }}
.kt {{
  font-weight: 700;
  font-size: 13.5px;
  margin-top: 6px;
}}
.kd {{
  color: var(--mut);
  font-size: 12.5px;
  margin-top: 2px;
}}

/* ── Secciones Plegables (Details) ── */
details {{
  background: var(--card);
  border: 1px solid var(--bd);
  border-radius: 12px;
  margin: 16px 0;
  padding: 8px 20px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.02);
}}
details[open] {{
  border-color: var(--bd-focus);
}}
summary {{
  cursor: pointer;
  font-weight: 700;
  font-size: 16px;
  padding: 12px 0;
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
}}
summary::-webkit-details-marker {{ display: none; }}
summary .sum-left {{
  display: flex;
  align-items: center;
  gap: 10px;
}}
summary::after {{
  content: "";
  display: inline-block;
  width: 7px;
  height: 7px;
  border-right: 2px solid var(--mut);
  border-bottom: 2px solid var(--mut);
  transform: rotate(45deg);
  transition: transform 0.2s ease;
  margin-right: 6px;
}}
details[open] summary::after {{
  transform: rotate(-135deg);
}}

/* ── Badges y Etiquetas ── */
.badge {{
  padding: 3px 10px;
  border-radius: 99px;
  font-size: 12px;
  font-weight: 700;
  color: #fff;
  display: inline-block;
}}
.badge.bad {{ background: var(--bad); }}
.badge.warn {{ background: var(--warn); }}
.badge.ok {{ background: var(--ok); }}

.tag {{
  display: inline-block;
  padding: 3px 9px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.3px;
  white-space: nowrap;
}}
.tag.bad {{ background: var(--bad-bg); color: var(--bad-tx); border: 1px solid var(--bad-bd); }}
.tag.warn {{ background: var(--warn-bg); color: var(--warn-tx); border: 1px solid var(--warn-bd); }}
.tag.ok {{ background: var(--ok-bg); color: var(--ok-tx); border: 1px solid var(--ok-bd); }}

.badge-pag {{
  display: inline-block;
  background: #3b82f6;
  color: #fff;
  font-weight: 800;
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 4px;
  margin-right: 4px;
}}
.badge-num {{
  font-weight: 700;
  font-size: 13px;
  color: var(--tx);
}}

/* ── Cajas de Ubicación Exacta ── */
.loc-box {{
  font-size: 12px;
  line-height: 1.45;
  display: flex;
  flex-direction: column;
  gap: 3px;
}}
.loc-tit {{
  font-weight: 700;
  color: var(--tx);
}}
.loc-sub {{
  color: var(--mut);
  font-style: italic;
}}
.loc-none {{
  color: var(--mut);
}}

/* Cajas de Instrucciones Claras */
.inst-box {{
  font-size: 11.5px;
  line-height: 1.45;
  padding: 8px 10px;
  border-radius: 6px;
  border-left: 3px solid;
}}
.inst-box.bad {{
  background: var(--bad-bg);
  border-color: var(--bad);
  color: var(--bad-tx);
}}
.inst-box.warn {{
  background: var(--warn-bg);
  border-color: var(--warn);
  color: var(--warn-tx);
}}
.inst-box.ok {{
  background: var(--ok-bg);
  border-color: var(--ok);
  color: var(--ok-tx);
}}
.inst-tit {{
  font-weight: 700;
  margin-bottom: 2px;
}}
.inst-desc {{
  font-size: 11px;
  opacity: 0.95;
}}

.inst-web {{
  font-size: 12px;
  line-height: 1.4;
}}

.txt-ok {{
  color: var(--ok);
  font-size: 12px;
}}
.txt-warn {{
  color: var(--warn);
  font-size: 12px;
}}
.bad-text {{
  color: var(--bad);
}}

/* Tablas de Diagnóstico */
.tabla-contenedor {{
  overflow-x: auto;
  margin: 12px 0 20px;
  border: 1px solid var(--bd);
  border-radius: 8px;
  background: var(--card);
}}
table {{
  border-collapse: collapse;
  width: 100%;
  font-size: 13px;
  background: var(--card);
}}
th, td {{
  border-bottom: 1px solid var(--bd);
  padding: 10px 12px;
  text-align: left;
  vertical-align: top;
}}
th {{
  background: var(--bg);
  color: var(--mut);
  font-weight: 700;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.6px;
  position: sticky;
  top: 0;
  z-index: 2;
}}
tr:hover {{
  background: rgba(0,0,0,0.015);
}}
@media (prefers-color-scheme: dark) {{
  tr:hover {{ background: rgba(255,255,255,0.025); }}
}}

/* Enlaces directos para PDFs no legibles y OCR */
.enlace-busqueda-pdf {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--bad-tx);
  text-decoration: underline;
  font-weight: 600;
}}
.enlace-busqueda-pdf code {{
  background: rgba(0, 0, 0, 0.05);
  padding: 1px 4px;
  border-radius: 4px;
}}
@media (prefers-color-scheme: dark) {{
  .enlace-busqueda-pdf code {{
    background: rgba(255, 255, 255, 0.1);
  }}
}}
.enlace-ocr-pdf {{
  color: var(--bad-tx);
  font-weight: 700;
  text-decoration: underline;
}}
.enlace-ocr-pdf:hover, .enlace-busqueda-pdf:hover {{
  color: var(--bad);
}}

/* Barra de herramientas y selector de vista */
.pasajes-toolbar {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  flex-wrap: wrap;
  margin: 12px 0 16px;
}}
.vista-selector {{
  display: inline-flex;
  background: var(--bg);
  border: 1px solid var(--bd);
  border-radius: 8px;
  padding: 3px;
  gap: 4px;
}}
.btn-vista-pasaje {{
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 6px;
  border: none;
  background: transparent;
  color: var(--mut);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}}
.btn-vista-pasaje:hover {{
  color: var(--tx);
  background: rgba(0, 0, 0, 0.04);
}}
@media (prefers-color-scheme: dark) {{
  .btn-vista-pasaje:hover {{
    background: rgba(255, 255, 255, 0.05);
  }}
}}
.btn-vista-pasaje.activo {{
  background: var(--card);
  color: var(--tx);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
}}

/* Guía de soluciones para citas */
.guia-solucion-citas {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
  margin: 0 0 18px;
}}
.guia-sol-card {{
  padding: 12px 14px;
  background: var(--bg);
  border: 1px solid var(--bd);
  border-radius: 8px;
  border-top-width: 3px;
}}
.guia-sol-card.bad {{ border-top-color: var(--bad); }}
.guia-sol-card.warn {{ border-top-color: var(--warn); }}
.guia-sol-card.ok {{ border-top-color: var(--ok); }}
.guia-sol-tit {{
  font-size: 12px;
  font-weight: 700;
  margin-bottom: 4px;
}}
.guia-sol-card.bad .guia-sol-tit {{ color: var(--bad-tx); }}
.guia-sol-card.warn .guia-sol-tit {{ color: var(--warn-tx); }}
.guia-sol-card.ok .guia-sol-tit {{ color: var(--ok-tx); }}
.guia-sol-txt {{
  font-size: 11.5px;
  color: var(--mut);
  line-height: 1.45;
}}

/* Tarjetas de Coincidencia de Pasajes */
.pasaje-card {{
  background: var(--card);
  border: 1px solid var(--bd);
  border-radius: 10px;
  margin-bottom: 18px;
  overflow: hidden;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
  border-left-width: 4px;
}}
.pasaje-card.bad {{ border-left-color: var(--bad); }}
.pasaje-card.warn {{ border-left-color: var(--warn); }}
.pasaje-card.ok {{ border-left-color: var(--ok); }}

.pasaje-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 10px;
  padding: 10px 16px;
  background: var(--bg);
  border-bottom: 1px solid var(--bd);
}}
.pasaje-meta {{
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}}
.pasaje-fte-meta {{
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--mut);
}}
.pasaje-fuente-nom {{
  color: var(--tx);
  max-width: 340px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.palabras-meta-badge {{
  display: inline-block;
  padding: 2px 7px;
  background: var(--bd);
  color: var(--tx);
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}}

.pasaje-accion {{
  padding: 10px 16px;
  font-size: 12px;
  line-height: 1.5;
  border-bottom: 1px solid var(--bd);
}}
.pasaje-accion.bad {{
  background: var(--bad-bg);
  color: var(--bad-tx);
  border-bottom-color: var(--bad-bd);
}}
.pasaje-accion.warn {{
  background: var(--warn-bg);
  color: var(--warn-tx);
  border-bottom-color: var(--warn-bd);
}}
.pasaje-accion.ok {{
  background: var(--ok-bg);
  color: var(--ok-tx);
  border-bottom-color: var(--ok-bd);
}}
.pasaje-accion-tit {{
  font-weight: 700;
  margin-bottom: 2px;
}}
.pasaje-accion-desc {{
  opacity: 0.95;
}}

.pasaje-grid-comparativa {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  padding: 16px;
}}
@media (max-width: 860px) {{
  .pasaje-grid-comparativa {{
    grid-template-columns: 1fr;
  }}
}}
.pasaje-col {{
  display: flex;
  flex-direction: column;
  min-width: 0;
}}
.col-head {{
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--mut);
  margin-bottom: 8px;
}}
.col-dot {{
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}}
.col-dot.bad {{ background: var(--bad); }}
.col-dot.warn {{ background: var(--warn); }}
.col-dot.ok {{ background: var(--ok); }}
.col-dot.neutral {{ background: #3b82f6; }}

.frag-caja {{
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 12.5px;
  line-height: 1.6;
  background: var(--bad-bg);
  color: var(--bad-tx);
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--bad-bd);
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  flex: 1;
}}
.parr-caja {{
  font-size: 13px;
  line-height: 1.6;
  color: var(--tx);
  background: var(--bg);
  padding: 12px 14px;
  border-radius: 8px;
  border: 1px solid var(--bd);
  overflow-wrap: anywhere;
  word-break: break-word;
  max-height: 280px;
  overflow-y: auto;
  flex: 1;
}}

/* Vista tabla compacta equilibrada */
.tb-det {{
  display: flex;
  flex-direction: column;
  gap: 4px;
}}
.tb-loc {{
  margin: 2px 0;
}}
.tb-fte {{
  font-weight: 600;
  color: var(--tx);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 200px;
}}
.tabla-pasajes {{
  min-width: 900px;
  table-layout: fixed;
  width: 100%;
}}
.tabla-pasajes th:nth-child(1), .tabla-pasajes td:nth-child(1) {{ width: 220px; }}
.tabla-pasajes th:nth-child(2), .tabla-pasajes td:nth-child(2) {{ width: 220px; }}
.tabla-pasajes th:nth-child(3), .tabla-pasajes td:nth-child(3) {{ width: 45%; }}
.tabla-pasajes th:nth-child(4), .tabla-pasajes td:nth-child(4) {{ width: 55%; }}

.palabras-meta {{
  font-size: 11px;
  font-weight: 600;
  color: var(--mut);
  margin-top: 3px;
}}
.ctx-texto {{
  font-size: 12px;
  color: var(--mut);
}}
.ctx-inv {{
  font-family: ui-monospace, Consolas, monospace;
  font-size: 12px;
  background: var(--bg);
  padding: 4px 6px;
  border-radius: 4px;
}}

/* ── Enlaces y Botones ── */
a {{
  color: var(--info);
  text-decoration: none;
}}
a:hover {{
  text-decoration: underline;
}}
.btn-comp {{
  display: inline-block;
  padding: 4px 10px;
  background: var(--info-bg);
  color: var(--info-tx);
  border: 1px solid var(--info-bd);
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  text-decoration: none;
  white-space: nowrap;
}}
.btn-comp:hover {{
  background: var(--info);
  color: #fff;
  text-decoration: none;
}}
.enlace-web {{
  word-break: break-all;
  font-size: 12px;
}}
.detalle-web {{
  font-size: 11.5px;
  color: var(--mut);
}}

.nota {{
  background: var(--info-bg);
  color: var(--info-tx);
  border-left: 4px solid var(--info);
  padding: 10px 16px;
  border-radius: 0 8px 8px 0;
  font-size: 13px;
  margin: 12px 0;
}}
.bad-nota {{
  background: var(--bad-bg);
  color: var(--bad-tx);
  border-left-color: var(--bad);
}}

.caja-vacio {{
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--ok-bg);
  border: 1px solid var(--ok-bd);
  border-radius: 8px;
  padding: 14px 18px;
  margin: 12px 0;
}}
.vacio-svg {{
  color: var(--ok);
  flex-shrink: 0;
}}
.vacio {{
  margin: 0;
  color: var(--ok-tx);
  font-weight: 600;
}}

.subseccion {{
  margin: 20px 0;
}}
.subseccion h4 {{
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 700;
}}
</style>
</head>
<body>

<header>
  <div class="header-titles">
    <h1>Diagnóstico y Revisión de Tesis</h1>
    <div class="sub">Archivo evaluado: <b>{e(d.get("archivo", "Tesis"))}</b> · Fecha de análisis: {e(d.get("fecha", ""))}</div>
  </div>
  <div class="header-actions">
    <a href="../index.html" class="btn-control">← Ir al Centro de Control (Subir archivos / Limpiar)</a>
  </div>
</header>

<main>
  {alerta_html}

  <!-- Guía Unificada del Lenguaje de Colores -->
  <div class="guia-colores">
    <div class="guia-header">Guía del lenguaje de colores (Norma Unificada)</div>
    <div class="guia-items">
      <div class="guia-item">
        <div class="guia-bullet bad"></div>
        <div><b>Rojo (Error / Urgente):</b> Requiere corrección obligatoria. Pasajes copiados sin comillas, citas con etiquetas no registradas, enlaces caídos o letras sustituidas.</div>
      </div>
      <div class="guia-item">
        <div class="guia-bullet warn"></div>
        <div><b>Ámbar (Advertencia):</b> Revisar. Citas escritas a mano (no dinámicas), caracteres invisibles de copiar/pegar, URLs que redirigen o desajustes de numeración.</div>
      </div>
      <div class="guia-item">
        <div class="guia-bullet ok"></div>
        <div><b>Verde (Conforme):</b> Cita en bloque o entrecomillada reglamentaria, fuentes verificadas, enlaces web descargados y similitud segura.</div>
      </div>
      <div class="guia-item">
        <div class="guia-bullet info"></div>
        <div><b>Azul (Informativo):</b> Métricas globales, conteo de palabras, páginas estimadas y enlaces para navegación directa.</div>
      </div>
    </div>
  </div>

  <div class="kpis">{kpis}</div>

  <div class="nota">
    <b>Información clave sobre la similitud:</b> Este kit compara tu tesis exclusivamente contra los documentos almacenados en tu carpeta <code>2-FUENTES</code>. El porcentaje obtenido sirve para identificar exactamente <b>en qué página, título y subtítulo</b> debes aplicar comillas, citas en bloque o paráfrasis antes de la entrega final.
  </div>

  <!-- 1. Pasajes coincidentes -->
  <details open>
    <summary>
      <div class="sum-left">
        <span>1. Párrafos que coinciden con tus fuentes</span>
        <span class="badge {"bad" if sin_comillas else "ok"}">{len(sin_comillas)} sin comillas</span>
      </div>
    </summary>
    <div class="pasajes-toolbar">
      <div class="nota" style="margin: 0; flex: 1;">
        Cada coincidencia indica la <b>página física de Word</b>, <b>título</b> y <b>subtítulo</b> exactos para que la ubiques y corrijas al instante.
      </div>
      <div class="vista-selector">
        <button type="button" class="btn-vista-pasaje activo" onclick="setVistaPasajes('cards')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
          Vista Comparativa
        </button>
        <button type="button" class="btn-vista-pasaje" onclick="setVistaPasajes('tabla')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"></line><line x1="8" y1="12" x2="21" y2="12"></line><line x1="8" y1="18" x2="21" y2="18"></line><line x1="3" y1="6" x2="3.01" y2="6"></line><line x1="3" y1="12" x2="3.01" y2="12"></line><line x1="3" y1="18" x2="3.01" y2="18"></line></svg>
          Vista Tabla
        </button>
      </div>
    </div>

    {guia_solucion}

    <div id="pasajes-cards-container">
      {cards_pasajes}
    </div>
    <div id="pasajes-tabla-container" style="display: none;">
      {s_pasajes}
    </div>
  </details>

  <!-- 2. Similitud por fuente -->
  <details>
    <summary>
      <div class="sum-left">
        <span>2. Similitud desglosada por fuente</span>
        <span class="badge {"warn" if max_sim >= 5 else "ok"}">{len(sim.get("fuentes", []))} fuentes</span>
      </div>
    </summary>
    {s_fuentes}
  </details>

  <!-- 3. Citas y referencias -->
  <details>
    <summary>
      <div class="sum-left">
        <span>3. Citas y referencias bibliográficas de Word</span>
        <span class="badge {"bad" if citas_mal else "ok"}">{citas_mal} problemas</span>
      </div>
    </summary>
    {s_citas}
  </details>

  <!-- 4. Fuentes web -->
  <details>
    <summary>
      <div class="sum-left">
        <span>4. Fuentes web de la bibliografía</span>
        <span class="badge {"warn" if enlaces_mal else "ok"}">{len(enlaces_mal)} con problemas</span>
      </div>
    </summary>
    <p class="nota">
      El sistema descarga automáticamente el contenido de los links y códigos DOI para comparar si incluiste fragmentos de esas páginas sin citar.
    </p>
    {s_web}
  </details>

  <!-- 5. Caracteres invisibles y alfabetos -->
  <details>
    <summary>
      <div class="sum-left">
        <span>5. Caracteres invisibles y letras camufladas</span>
        <span class="badge {"warn" if inv.get("total", 0) else "ok"}">{inv.get("total", 0)} invisibles</span>
      </div>
    </summary>
    {s_inv}
  </details>

  <!-- 6. Tablas y figuras -->
  <details>
    <summary>
      <div class="sum-left">
        <span>6. Numeración de tablas y figuras</span>
        <span class="badge {"warn" if est.get("problemas") else "ok"}">{len(est.get("problemas", []))} problemas</span>
      </div>
    </summary>
    {s_est}
  </details>

  <!-- 7. Historial -->
  <details>
    <summary>
      <div class="sum-left">
        <span>7. Historial de revisiones</span>
        <span class="badge ok">{len(hist)} registradas</span>
      </div>
    </summary>
    <p class="nota">Muestra la evolución de tu tesis a través de las últimas ejecuciones.</p>
    {hist_html}
  </details>

</main>
<script>
function setVistaPasajes(vista) {{
  var cards = document.getElementById('pasajes-cards-container');
  var tabla = document.getElementById('pasajes-tabla-container');
  var btns = document.querySelectorAll('.btn-vista-pasaje');
  if (!cards || !tabla || btns.length < 2) return;
  if (vista === 'tabla') {{
    cards.style.display = 'none';
    tabla.style.display = 'block';
    btns[0].classList.remove('activo');
    btns[1].classList.add('activo');
  }} else {{
    cards.style.display = 'block';
    tabla.style.display = 'none';
    btns[0].classList.add('activo');
    btns[1].classList.remove('activo');
  }}
}}
</script>
</body>
</html>"""

"""Similitud de la tesis con las fuentes propias, usando las funciones de copy-spotter.

Compara la tesis solo contra cada fuente (no las fuentes entre sí), así el tiempo
crece de forma lineal con la cantidad de fuentes. Para cada fragmento que coincide,
indica si en la tesis ya está entre comillas o en cita en bloque (bien) o si quedó
como texto propio (hay que corregir).
"""
import re
import shutil
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

from .docx_utils import parrafos, indice_headings

EXTS = {".pdf", ".docx", ".odt", ".txt"}
ETIQUETA = "__MI_TESIS__"
COMILLAS = re.compile(r"[“\"«]([^”\"»]{15,}?)[”\"»]")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _shingles(palabras, n=4):
    return {" ".join(palabras[i:i + n]) for i in range(max(1, len(palabras) - n + 1))}


def _formatear_bloques(contenedor, prefijo):
    """Convierte texto corrido en párrafos legibles e identifica coincidencias con IDs."""
    if not contenedor:
        return 0
    spans = contenedor.find_all("span")
    nuevo_contenido = []
    m_idx = 0
    for sp in spans:
        is_match = "bold" in (sp.get("style") or "")
        texto = sp.get_text(" ", strip=True)
        if not texto:
            continue
        if is_match:
            m_idx += 1
            sp.attrs = {
                "class": "match",
                "id": f"m-{prefijo}-{m_idx}",
                "data-m": str(m_idx),
                "style": "font-weight:bold",
                "tabindex": "0",
                "title": f"Coincidencia #{m_idx}"
            }
            nuevo_contenido.append(sp)
        else:
            # Dividir textos largos en párrafos de ~50 palabras para que sea legible
            palabras = texto.split()
            tam = 50
            for i in range(0, len(palabras), tam):
                p_tag = contenedor._soup.new_tag("p")
                p_tag["class"] = "doc-p"
                p_tag.string = " ".join(palabras[i:i + tam])
                nuevo_contenido.append(p_tag)
    # Limpiar y reinsertar título y nuevo contenido
    h3 = contenedor.find("h3")
    contenedor.clear()
    if h3:
        contenedor.append(h3)
    for elem in nuevo_contenido:
        contenedor.append(elem)
    return m_idx


def _mejorar_comparacion(html_path, nombre_fuente):
    """Reescribe el HTML de comparación con tipografía legible, navegación interactiva y alto contraste."""
    from html import escape
    raw = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    soup._soup = soup

    # Ajustar títulos
    for h3 in soup.find_all("h3"):
        if "__MI_TESIS__" in h3.text:
            h3.string = "Tu tesis"
        elif nombre_fuente in h3.text:
            h3.string = nombre_fuente

    left = soup.find(id="leftContent")
    right = soup.find(id="rightContent")
    if left:
        left._soup = soup
    if right:
        right._soup = soup

    total_m = _formatear_bloques(left, "L")
    _formatear_bloques(right, "R")

    nuevo_style = '<link rel="stylesheet" href="/css/comparacion.css">\n'

    nuevo_script = f"""<script>
let totalMatches = {total_m};
let curMatch = 1;
let sync = true;
let isScrolling = false;

function jumpTo(idx) {{
  if (totalMatches === 0) return;
  if (idx < 1) idx = totalMatches;
  if (idx > totalMatches) idx = 1;
  curMatch = idx;
  document.getElementById('lblCur').innerText = curMatch + ' / ' + totalMatches;
  document.querySelectorAll('.match').forEach(el => el.classList.remove('active'));

  const mL = document.getElementById('m-L-' + curMatch);
  const mR = document.getElementById('m-R-' + curMatch);
  if (mL) {{
    mL.classList.add('active');
    mL.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
  }}
  if (mR) {{
    mR.classList.add('active');
    mR.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
  }}
}}

function prevMatch() {{ jumpTo(curMatch - 1); }}
function nextMatch() {{ jumpTo(curMatch + 1); }}

document.addEventListener('DOMContentLoaded', () => {{
  const l = document.getElementById('leftContent');
  const r = document.getElementById('rightContent');

  function syncScroll(source, target) {{
    if (!sync || isScrolling) return;
    isScrolling = true;
    const ratio = source.scrollTop / (source.scrollHeight - source.clientHeight);
    target.scrollTop = ratio * (target.scrollHeight - target.clientHeight);
    setTimeout(() => {{ isScrolling = false; }}, 50);
  }}

  if (l && r) {{
    l.addEventListener('scroll', () => syncScroll(l, r));
    r.addEventListener('scroll', () => syncScroll(r, l));
  }}

  document.querySelectorAll('.match').forEach(el => {{
    el.addEventListener('click', (e) => {{
      const mId = parseInt(el.getAttribute('data-m'), 10);
      if (mId) jumpTo(mId);
    }});
  }});

  document.addEventListener('keydown', (e) => {{
    if (e.target.tagName === 'INPUT') return;
    if (e.key === 'j' || e.key === 'ArrowDown') {{ nextMatch(); e.preventDefault(); }}
    if (e.key === 'k' || e.key === 'ArrowUp') {{ prevMatch(); e.preventDefault(); }}
  }});

  if (totalMatches > 0) jumpTo(1);
}});
</script>"""

    nf = escape(nombre_fuente)
    nav_html = f"""<header class="header">
  <div class="header-info">
    <h2>Comparación de texto</h2>
    <div class="sub">Tu tesis vs {nf}</div>
  </div>
  <div class="header-nav">
    <span class="nav-badge"><span id="lblCur">1 / {total_m}</span> coincidencias</span>
    <button type="button" class="btn" onclick="prevMatch()" title="Anterior (k)">↑ Anterior</button>
    <button type="button" class="btn" onclick="nextMatch()" title="Siguiente (j)">↓ Siguiente</button>
    <label class="btn" style="font-weight:normal"><input type="checkbox" checked onchange="sync=this.checked"> Scroll sincro</label>
    <a href="../panel.html" class="btn btn-primary">← Volver al panel</a>
  </div>
</header>"""

    # Reemplazar style y header
    head = soup.find("head") or soup.new_tag("head")
    old_style = soup.find("style")
    if old_style:
        old_style.decompose()

    style_tag = BeautifulSoup(nuevo_style, "html.parser")
    head.append(style_tag)

    body = soup.find("body")
    old_header = body.find("div", class_="header")
    if old_header:
        old_header.decompose()
    old_leyenda = body.find("div", class_="leyenda")
    if old_leyenda:
        old_leyenda.decompose()

    header_tag = BeautifulSoup(nav_html, "html.parser")
    body.insert(0, header_tag)

    script_tag = BeautifulSoup(nuevo_script, "html.parser")
    body.append(script_tag)

    soup.title.string = f"Comparación: Tu tesis vs {nombre_fuente}"
    html_path.write_text(str(soup), encoding="utf-8")


def _ubicar(fragmento, ps_norm):
    """Busca el párrafo que contiene el fragmento y decide si está citado textual."""
    f = _norm(fragmento).split()
    clave = " ".join(f[:8])
    for p, pn, loc in ps_norm:
        if clave and clave in pn:
            if p.sangria_izq >= 600 and len(p.texto.split()) >= 30:
                return "En bloque", p.texto, loc
            citado = " | ".join(_norm(q) for q in COMILLAS.findall(p.texto))
            sh = _shingles(f)
            if citado and sum(1 for s in sh if s in citado) / len(sh) >= 0.6:
                return "Entre comillas", p.texto, loc
            return "Sin comillas", p.texto, loc
    return "No ubicado", "", {"pagina": 0, "titulo": "", "subtitulo": ""}


def _palabras(ruta: Path, file_extension_call, tmp: Path):
    # copy-spotter decide el lector por la extensión en minúscula
    copia = tmp / ("f" + ruta.suffix.lower())
    shutil.copy(ruta, copia)
    try:
        return file_extension_call(str(copia)) or []
    except Exception:
        return []
    finally:
        copia.unlink(missing_ok=True)


def analizar(tesis: Path, carpeta_fuentes: Path, trabajo: Path, bloque=8, minimo_palabras=12, solo_raiz=False):
    from scripts.html_writing import papers_comparison
    from scripts.processing_files import file_extension_call
    from scripts.similarity import difflib_overlap

    if not carpeta_fuentes.is_dir():
        fuentes = []
    elif solo_raiz:
        archivos = list(carpeta_fuentes.glob("*"))
        web_dir = carpeta_fuentes / "web"
        if web_dir.is_dir():
            archivos.extend(web_dir.rglob("*"))
        fuentes = sorted(f for f in archivos if f.is_file() and f.suffix.lower() in EXTS
                         and f.name.upper() != "LEEME.TXT" and not f.name.startswith("~$"))
    else:
        fuentes = sorted(f for f in carpeta_fuentes.rglob("*") if f.is_file() and f.suffix.lower() in EXTS
                         and f.name.upper() != "LEEME.TXT" and not f.name.startswith("~$"))
    if not fuentes:
        return {"fuentes": [], "pasajes": [], "ilegibles": [], "error": "No hay fuentes en el conjunto seleccionado."}

    destino = trabajo / "comparaciones"
    if destino.exists():
        shutil.rmtree(destino)
    destino.mkdir(parents=True)
    tmp = trabajo / "_tmp"
    tmp.mkdir(exist_ok=True)

    t_words = _palabras(tesis, file_extension_call, tmp)
    if not t_words:
        return {"fuentes": [], "pasajes": [], "ilegibles": [], "error": "No se pudo leer el texto de la tesis."}

    ps_all = parrafos(tesis)
    idx_headings = indice_headings(ps_all)
    ps_filtrados = [(p, i) for p, i in zip(ps_all, range(len(ps_all)))
                    if p.texto.strip() and "bibliog" not in (p.estilo or "").lower()]
    ps_norm = [(p, _norm(p.texto), idx_headings[i]) for p, i in ps_filtrados]
    resultados, pasajes, ilegibles, vistos = [], [], [], set()
    total_f = len(fuentes)
    for n, f in enumerate(fuentes):
        nombre = str(f.relative_to(carpeta_fuentes)).replace("\\", "/")
        prog_pct = 55 + int(((n + 1) / total_f) * 38)
        print(f"[PROGRESO: {prog_pct}%] [5/5] Comparando {n + 1}/{total_f}: {nombre[:65]}", flush=True)
        f_words = _palabras(f, file_extension_call, tmp)
        if not f_words:  # PDF escaneado o archivo dañado
            ilegibles.append(nombre)
            continue
        pct = difflib_overlap(t_words, f_words)
        papers_comparison(str(destino), n, t_words, f_words, (ETIQUETA, nombre), bloque)
        resultados.append({"fuente": nombre, "porcentaje": float(pct), "comparacion": f"comparaciones/{n}.html"})
        html = destino / f"{n}.html"
        _mejorar_comparacion(html, nombre)
        lado = BeautifulSoup(html.read_text(encoding="utf-8"), "html.parser").find(id="leftContent")
        if lado is None:
            continue
        for sp in lado.find_all("span"):
            if "bold" not in (sp.get("style") or ""):
                continue
            frag = sp.get_text(" ", strip=True)
            if len(frag.split()) < minimo_palabras or frag in vistos:
                continue
            vistos.add(frag)
            estado, parrafo, loc = _ubicar(frag, ps_norm)
            if estado == "No ubicado":
                continue  # suele ser la lista de Referencias, que se arma sola
            pasajes.append({"fuente": nombre, "palabras": len(frag.split()), "fragmento": frag,
                            "estado": estado, "parrafo": parrafo[:500],
                            "pagina": loc["pagina"], "titulo": loc["titulo"],
                            "subtitulo": loc["subtitulo"]})
    shutil.rmtree(tmp, ignore_errors=True)
    resultados.sort(key=lambda x: -x["porcentaje"])
    orden = {"Sin comillas": 0, "Entre comillas": 1, "En bloque": 2}
    pasajes.sort(key=lambda x: (orden[x["estado"]], -x["palabras"]))
    return {"fuentes": resultados, "pasajes": pasajes, "ilegibles": ilegibles, "error": None}

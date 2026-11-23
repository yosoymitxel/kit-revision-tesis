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


def _mejorar_comparacion(html_path, nombre_fuente):
    """Reescribe el HTML de comparación con mejor estilo, colores unificados y leyenda."""
    texto = html_path.read_text(encoding="utf-8")
    nuevo_style = """<style>
:root{--bg:#f6f7f9;--card:#fff;--tx:#1f2937;--mut:#6b7280;--bd:#e5e7eb;
  --ok:#0f766e;--warn:#b45309;--bad:#b91c1c;--info:#1d4ed8;
  --match:#dc2626;--match-bg:rgba(220,38,38,.08)}
@media (prefers-color-scheme:dark){:root{--bg:#111318;--card:#1b1e25;--tx:#e5e7eb;--mut:#9ca3af;--bd:#2b2f38;
  --match-bg:rgba(220,38,38,.15)}}
*{box-sizing:border-box}
body,html{margin:0;padding:0;font:14px/1.6 system-ui,'Segoe UI',Roboto,sans-serif;background:var(--bg);color:var(--tx)}
.header{padding:16px 24px;border-bottom:1px solid var(--bd);display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;background:var(--card)}
.header h2{margin:0;font-size:18px;font-weight:700}
.header .info{color:var(--mut);font-size:13px;display:block;margin-top:2px}
.header-nav{display:flex;gap:8px}
.leyenda{display:flex;gap:20px;padding:10px 24px;background:var(--card);border-bottom:1px solid var(--bd);font-size:13px;color:var(--mut);flex-wrap:wrap}
.leyenda span{display:flex;align-items:center;gap:6px}
.leyenda .dot{width:12px;height:12px;border-radius:3px;flex-shrink:0}
.leyenda .dot.match{background:var(--match)}
.leyenda .dot.normal{background:var(--mut);opacity:.3}
.container{display:flex;justify-content:space-between;padding:16px 24px;gap:16px}
.content{width:49%;border:1px solid var(--bd);border-radius:10px;padding:18px;overflow:auto;height:84vh;background:var(--card);box-shadow:0 1px 3px rgba(0,0,0,0.03)}
h3{color:var(--tx);border-bottom:2px solid var(--bd);padding-bottom:10px;font-size:15px;margin:0 0 14px}
span{display:inline;line-height:1.75}
span[style*="bold"]{background:var(--match-bg);color:var(--match);border-bottom:2px solid var(--match);border-radius:2px;padding:1px 3px;font-weight:600}
a{color:var(--info);text-decoration:none}
a:hover{text-decoration:underline}
.back{display:inline-block;padding:6px 14px;background:var(--info);color:#fff;border-radius:8px;font-size:13px;text-decoration:none;font-weight:600;transition:opacity .15s}
.back:hover{opacity:.9;text-decoration:none}
.back-alt{background:transparent;color:var(--tx);border:1px solid var(--bd)}
.back-alt:hover{background:var(--bg)}
</style>"""
    texto = re.sub(r"<style>.*?</style>", nuevo_style, texto, count=1, flags=re.DOTALL)
    texto = re.sub(r"<title>[^<]*</title>",
                   "<title>Comparaci\u00f3n: Tu tesis vs " + nombre_fuente + "</title>", texto, count=1)
    texto = texto.replace("__MI_TESIS__", "Tu tesis")
    from html import escape
    nf = escape(nombre_fuente)
    header_html = ('<div class="header">'
                   '<div>'
                   '<h2>Comparaci\u00f3n lado a lado</h2>'
                   '<span class="info">Tu tesis vs ' + nf + '</span>'
                   '</div>'
                   '<div class="header-nav">'
                   '<a href="../panel.html" class="back">\u2190 Volver al panel</a>'
                   '<a href="../../index.html" class="back back-alt">Centro de Control</a>'
                   '</div>'
                   '</div>'
                   '<div class="leyenda">'
                   '<span><span class="dot match"></span> <b>Rojo subrayado</b> = Texto id\u00e9ntico que coincide entre ambos documentos</span>'
                   '<span><span class="dot normal"></span> Texto normal = Redacci\u00f3n sin coincidencia</span>'
                   '</div>')
    texto = texto.replace('<div class="container">', header_html + '\n<div class="container">', 1)
    html_path.write_text(texto, encoding="utf-8")


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


def analizar(tesis: Path, carpeta_fuentes: Path, trabajo: Path, bloque=8, minimo_palabras=12):
    from scripts.html_writing import papers_comparison
    from scripts.processing_files import file_extension_call
    from scripts.similarity import difflib_overlap

    fuentes = sorted(f for f in carpeta_fuentes.rglob("*") if f.is_file() and f.suffix.lower() in EXTS
                     and f.name.upper() != "LEEME.TXT" and not f.name.startswith("~$")) if carpeta_fuentes.is_dir() else []
    if not fuentes:
        return {"fuentes": [], "pasajes": [], "ilegibles": [], "error": "No hay fuentes en 2-FUENTES."}

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
    for n, f in enumerate(fuentes):
        nombre = str(f.relative_to(carpeta_fuentes)).replace("\\", "/")
        print(f"    {n + 1}/{len(fuentes)} {nombre[:70]}")
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

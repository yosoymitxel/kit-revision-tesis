"""Lectura de .docx a bajo nivel (zip + XML), sin modificar nada."""
import re
import zipfile
from pathlib import Path

from lxml import etree

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
B_NS = "http://schemas.openxmlformats.org/officeDocument/2006/bibliography"

# Partes con texto visible del documento
PARTES_TEXTO = re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$")


def partes_texto(z: zipfile.ZipFile):
    return [n for n in z.namelist() if PARTES_TEXTO.match(n)]


def nombre_parte(n: str) -> str:
    base = n.split("/")[-1].removesuffix(".xml")
    if base == "document":
        return "Cuerpo"
    if base.startswith("header"):
        return "Encabezado"
    if base.startswith("footer"):
        return "Pie de página"
    return {"footnotes": "Notas al pie", "endnotes": "Notas finales", "comments": "Comentarios"}.get(base, base)


class Parrafo:
    """Texto visible de un párrafo, separando lo que está dentro de campos de Word."""

    def __init__(self, p, estilo_por_id, pagina=1):
        self.el = p
        self.pagina = pagina     # página física detectada en el documento
        self.texto = ""          # todo el texto visible, incluido el resultado de los campos
        self.texto_fuera_campos = ""  # texto escrito a mano (sin resultados de campos)
        self.campos = []         # instrucciones de campo (CITATION, BIBLIOGRAPHY, ...)
        ppr = p.find(W + "pPr")
        sid = None
        self.sangria_izq = 0
        if ppr is not None:
            ps = ppr.find(W + "pStyle")
            if ps is not None:
                sid = ps.get(W + "val")
            ind = ppr.find(W + "ind")
            if ind is not None:
                try:
                    self.sangria_izq = int(ind.get(W + "left") or ind.get(W + "start") or 0)
                except ValueError:
                    pass
        self.estilo = estilo_por_id.get(sid, sid or "Normal")
        profundidad = 0
        instr = ""
        for el in p.iter():
            if el.tag == W + "fldChar":
                tipo = el.get(W + "fldCharType")
                if tipo == "begin":
                    profundidad += 1
                    instr = ""
                elif tipo == "separate" and instr.strip():
                    self.campos.append(instr.strip())
                    instr = ""
                elif tipo == "end":
                    profundidad = max(0, profundidad - 1)
            elif el.tag == W + "instrText":
                instr += el.text or ""
            elif el.tag == W + "fldSimple":
                self.campos.append((el.get(W + "instr") or "").strip())
            elif el.tag == W + "t":
                t = el.text or ""
                self.texto += t
                dentro = profundidad > 0 or any(a.tag in (W + "fldSimple", W + "sdtContent") for a in el.iterancestors())
                if not dentro:
                    self.texto_fuera_campos += t
            elif el.tag in (W + "br", W + "cr"):
                self.texto += " "
                self.texto_fuera_campos += " "
            elif el.tag == W + "tab":
                self.texto += "\t"
                self.texto_fuera_campos += "\t"


def estilos(z):
    out = {}
    if "word/styles.xml" in z.namelist():
        for s in etree.fromstring(z.read("word/styles.xml")).iter(W + "style"):
            n = s.find(W + "name")
            out[s.get(W + "styleId")] = n.get(W + "val") if n is not None else s.get(W + "styleId")
    return out


def parrafos(ruta: Path, parte="word/document.xml"):
    with zipfile.ZipFile(ruta) as z:
        est = estilos(z)
        raiz = etree.fromstring(z.read(parte))
    out = []
    pag = 1
    for p in raiz.iter(W + "p"):
        p_obj = Parrafo(p, est, pagina=pag)
        quiebres = len(p.findall(".//" + W + "lastRenderedPageBreak")) + len(
            [b for b in p.findall(".//" + W + "br") if b.get(W + "type") == "page"]
        )
        pag += quiebres
        out.append(p_obj)
    return out


def _es_heading(estilo: str) -> bool:
    """Determina si un estilo de Word es un título (Heading 1, Heading 2, etc.)."""
    if not estilo:
        return False
    e = estilo.lower().replace(" ", "")
    return (e.startswith("heading") or e.startswith("título") or e.startswith("titulo")
            or e.startswith("ttulo"))


def _nivel_heading(estilo: str, texto: str = "") -> int:
    """Devuelve el nivel del heading (1-9) o 99 si no es heading."""
    if _es_heading(estilo):
        import re
        m = re.search(r"\d+", estilo)
        return int(m.group()) if m else 1
    # Detección por texto en mayúsculas de capítulos y secciones mayores
    t = texto.strip()
    if t and len(t) < 120 and (t.startswith("CAPÍTULO") or t.startswith("CAPITULO")):
        return 1
    return 99


def indice_headings(ps):
    """Construye un índice de headings activos y páginas para cada párrafo.

    Devuelve una lista paralela a ps donde cada elemento es un dict
    con las claves:
      - pagina: número de página en Word
      - titulo: capítulo o título principal (Heading 1)
      - subtitulo: sección o subsección (Heading 2, 3...)
      - seccion_corta: texto resumido de localización
    """
    headings = {}  # nivel -> texto
    hay_paginas_reales = any(getattr(p, "pagina", 1) > 1 for p in ps)
    paginas_estimadas = 0
    resultado = []
    for p in ps:
        if hay_paginas_reales:
            pag_num = getattr(p, "pagina", 1)
        else:
            if p.texto.strip():
                paginas_estimadas += len(p.texto.split()) / 350.0
            pag_num = max(1, int(paginas_estimadas) + 1)

        nivel = _nivel_heading(p.estilo, p.texto)
        txt_limpio = p.texto.strip()
        # Ignorar entradas del índice general de Word (TOC)
        est = (p.estilo or "").lower()
        es_toc = "toc" in est or "table of" in est or "tabla de" in est

        if nivel < 99 and txt_limpio and not es_toc and len(txt_limpio) > 2:
            # Limpiar headings de niveles iguales o inferiores
            for k in list(headings):
                if k >= nivel:
                    del headings[k]
            headings[nivel] = txt_limpio

        niveles = sorted(headings)
        titulo = headings.get(niveles[0], "") if niveles else ""
        subtitulos = [headings[k] for k in niveles[1:] if headings[k] != titulo]
        subtitulo = " › ".join(subtitulos) if subtitulos else ""

        corta_partes = [f"Pág. {pag_num}"]
        if titulo:
            corta_partes.append(titulo[:50])
        if subtitulo:
            corta_partes.append(subtitulos[-1][:40])

        resultado.append({
            "pagina": pag_num,
            "titulo": titulo[:140],
            "subtitulo": subtitulo[:160],
            "seccion_corta": " · ".join(corta_partes),
        })
    return resultado


def fuentes_bibliograficas(ruta: Path):
    """Devuelve (encontrado, {tag: titulo}) del almacén de fuentes de Word (customXml)."""
    with zipfile.ZipFile(ruta) as z:
        for n in z.namelist():
            if n.startswith("customXml/item") and n.endswith(".xml") and "Props" not in n:
                data = z.read(n)
                if b"Sources" in data and B_NS.encode() in data:
                    raiz = etree.fromstring(data)
                    out = {}
                    for s in raiz.iter("{%s}Source" % B_NS):
                        tag = s.findtext("{%s}Tag" % B_NS)
                        tit = s.findtext("{%s}Title" % B_NS) or ""
                        if tag:
                            out[tag] = tit
                    return True, out
    return False, {}

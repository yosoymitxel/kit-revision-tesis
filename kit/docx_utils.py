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

    def __init__(self, p, estilo_por_id):
        self.el = p
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
    return [Parrafo(p, est) for p in raiz.iter(W + "p")]


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

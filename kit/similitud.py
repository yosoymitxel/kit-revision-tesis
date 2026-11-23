"""Similitud de la tesis con las fuentes propias, usando copy-spotter.

Para cada fragmento que coincide, indica si en la tesis ya está entre comillas
o en cita en bloque (bien) o si quedó como texto propio (hay que corregir).
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

from bs4 import BeautifulSoup

from .docx_utils import parrafos

EXTS = {".pdf", ".docx", ".odt", ".txt"}
ETIQUETA = "__MI_TESIS__"
COMILLAS = re.compile(r"[“\"«]([^”\"»]{15,}?)[”\"»]")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _ubicar(fragmento, ps_norm):
    """Busca el párrafo que contiene el fragmento y decide si está citado textual."""
    f = _norm(fragmento)
    clave = " ".join(f.split()[:8])
    for p, pn in ps_norm:
        if clave and clave in pn:
            if p.sangria_izq >= 600 and len(p.texto.split()) >= 30:
                return "En bloque", p.texto
            for q in COMILLAS.findall(p.texto):
                if clave in _norm(q):
                    return "Entre comillas", p.texto
            return "Sin comillas", p.texto
    return "No ubicado", ""


def analizar(tesis: Path, carpeta_fuentes: Path, trabajo: Path, bloque=8, minimo_palabras=12):
    fuentes = [f for f in carpeta_fuentes.iterdir() if f.is_file() and f.suffix.lower() in EXTS] if carpeta_fuentes.is_dir() else []
    if not fuentes:
        return {"fuentes": [], "pasajes": [], "error": "No hay fuentes en 2-FUENTES."}
    cs = shutil.which("copy-spotter") or str(Path(sys.executable).with_name("copy-spotter"))
    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada"
        entrada.mkdir()
        shutil.copy(tesis, entrada / (ETIQUETA + tesis.suffix.lower()))
        for f in fuentes:
            shutil.copy(f, entrada / f.name)
        # copy-spotter ignora -o y escribe en ../results respecto de la carpeta actual
        cwd = trabajo / "_tmp"
        cwd.mkdir(parents=True, exist_ok=True)
        r = subprocess.run([cs, str(entrada), "-s", str(bloque)], capture_output=True, text=True, cwd=cwd,
                           encoding="utf-8", errors="replace")
        shutil.rmtree(cwd, ignore_errors=True)
    m = re.search(r"Results saved at:\s*(.+?_results\.html)", r.stdout + r.stderr)
    if r.returncode != 0 or not m:
        return {"fuentes": [], "pasajes": [], "error": "copy-spotter falló: " + (r.stderr or r.stdout)[-800:]}
    informe = Path(m.group(1).strip())
    carpeta_html = informe.parent

    filas = BeautifulSoup(informe.read_text(encoding="utf-8"), "html.parser").find_all("tr")
    encabezado = [c.get_text(strip=True) for c in filas[0].find_all(["td", "th"])]
    resultados = []
    for fila in filas[1:]:
        celdas = fila.find_all(["td", "th"])
        if not celdas or celdas[0].get_text(strip=True) != ETIQUETA:
            continue
        for nombre, celda in zip(encabezado[1:], celdas[1:]):
            a = celda.find("a")
            if nombre != ETIQUETA and a:
                resultados.append({"fuente": nombre, "porcentaje": float(celda.get_text(strip=True)),
                                   "comparacion": Path(a["href"].replace("file:///", "").replace("file://", "")).name})
    resultados.sort(key=lambda x: -x["porcentaje"])

    ps_norm = [(p, _norm(p.texto)) for p in parrafos(tesis)
               if p.texto.strip() and "bibliog" not in (p.estilo or "").lower()]
    pasajes, vistos = [], set()
    for res in resultados:
        html = carpeta_html / res["comparacion"]
        if not html.exists():
            continue
        s = BeautifulSoup(html.read_text(encoding="utf-8"), "html.parser")
        h = [x.get_text(strip=True) for x in s.find_all("h3")]
        lado = s.find(id="leftContent") if h and h[0] == ETIQUETA else s.find(id="rightContent")
        if lado is None:
            continue
        for sp in lado.find_all("span"):
            if "bold" not in (sp.get("style") or ""):
                continue
            frag = sp.get_text(" ", strip=True)
            if len(frag.split()) < minimo_palabras or frag in vistos:
                continue
            vistos.add(frag)
            estado, parrafo = _ubicar(frag, ps_norm)
            if estado == "No ubicado":
                continue  # suele ser la lista de Referencias, que se arma sola
            pasajes.append({"fuente": res["fuente"], "palabras": len(frag.split()), "fragmento": frag,
                            "estado": estado, "parrafo": parrafo[:500]})
    orden = {"Sin comillas": 0, "No ubicado": 1, "Entre comillas": 2, "En bloque": 3}
    pasajes.sort(key=lambda x: (orden[x["estado"]], -x["palabras"]))
    # copiar las comparaciones lado a lado a resultados
    destino = trabajo / "comparaciones"
    if destino.exists():
        shutil.rmtree(destino)
    shutil.copytree(carpeta_html, destino)
    shutil.rmtree(carpeta_html.parent, ignore_errors=True)
    for res in resultados:
        res["comparacion"] = "comparaciones/" + res["comparacion"]
    return {"fuentes": resultados, "pasajes": pasajes, "error": None}

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

from .docx_utils import parrafos

EXTS = {".pdf", ".docx", ".odt", ".txt"}
ETIQUETA = "__MI_TESIS__"
COMILLAS = re.compile(r"[“\"«]([^”\"»]{15,}?)[”\"»]")


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _shingles(palabras, n=4):
    return {" ".join(palabras[i:i + n]) for i in range(max(1, len(palabras) - n + 1))}


def _ubicar(fragmento, ps_norm):
    """Busca el párrafo que contiene el fragmento y decide si está citado textual."""
    f = _norm(fragmento).split()
    clave = " ".join(f[:8])
    for p, pn in ps_norm:
        if clave and clave in pn:
            if p.sangria_izq >= 600 and len(p.texto.split()) >= 30:
                return "En bloque", p.texto
            citado = " | ".join(_norm(q) for q in COMILLAS.findall(p.texto))
            sh = _shingles(f)
            if citado and sum(1 for s in sh if s in citado) / len(sh) >= 0.6:
                return "Entre comillas", p.texto
            return "Sin comillas", p.texto
    return "No ubicado", ""


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

    ps_norm = [(p, _norm(p.texto)) for p in parrafos(tesis)
               if p.texto.strip() and "bibliog" not in (p.estilo or "").lower()]
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
            estado, parrafo = _ubicar(frag, ps_norm)
            if estado == "No ubicado":
                continue  # suele ser la lista de Referencias, que se arma sola
            pasajes.append({"fuente": nombre, "palabras": len(frag.split()), "fragmento": frag,
                            "estado": estado, "parrafo": parrafo[:500]})
    shutil.rmtree(tmp, ignore_errors=True)
    resultados.sort(key=lambda x: -x["porcentaje"])
    orden = {"Sin comillas": 0, "Entre comillas": 1, "En bloque": 2}
    pasajes.sort(key=lambda x: (orden[x["estado"]], -x["palabras"]))
    return {"fuentes": resultados, "pasajes": pasajes, "ilegibles": ilegibles, "error": None}

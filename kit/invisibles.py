"""Caracteres invisibles y letras de otros alfabetos camufladas en el texto.

Detecta y, si se pide, limpia SOLO el texto visible (<w:t>) de cuerpo, encabezados,
pies, notas y comentarios. No toca customXml (fuentes de la bibliografía), campos,
estilos ni metadatos, así que las citas de Word siguen funcionando.

Estos caracteres suelen llegar al copiar y pegar desde PDF, páginas web o chats.
Borrarlos no cambia lo que dice el texto ni oculta cómo fue escrito.
"""
import re
import shutil
import zipfile
from pathlib import Path

from .docx_utils import W, nombre_parte, partes_texto
from lxml import etree

INVISIBLES = {
    "​": "Espacio de ancho cero (U+200B)",
    "‌": "No unión de ancho cero (U+200C)",
    "‍": "Unión de ancho cero (U+200D)",
    "⁠": "Unión de palabra (U+2060)",
    "﻿": "Marca de orden de bytes (U+FEFF)",
    "­": "Guion suave (U+00AD)",
    "‎": "Marca izquierda a derecha (U+200E)",
    "‏": "Marca derecha a izquierda (U+200F)",
    "‪": "Incrustación de dirección (U+202A)",
    "‫": "Incrustación de dirección (U+202B)",
    "‬": "Fin de incrustación (U+202C)",
    "‭": "Anulación de dirección (U+202D)",
    "‮": "Anulación de dirección (U+202E)",
    "⁡": "Aplicación de función invisible (U+2061)",
    "⁢": "Multiplicación invisible (U+2062)",
    "⁣": "Separador invisible (U+2063)",
    "⁤": "Suma invisible (U+2064)",
    "᠎": "Separador de vocal mongol (U+180E)",
}
PATRON = re.compile("[" + "".join(INVISIBLES) + "]")

# Letras cirílicas o griegas que se ven iguales a las latinas
HOMOGLIFOS = set("аеорсухіјѕԁԛԝАВЕКМНОРСТХІЈЅοαΑΒΕΗΙΚΜΝΟΡΤΥΧ")
PALABRA = re.compile(r"\w+", re.UNICODE)


def _contexto(t, i, ancho=40):
    a = max(0, i - ancho)
    frag = t[a:i + ancho]
    return PATRON.sub("⟦·⟧", frag).replace("\n", " ")


def analizar(ruta: Path):
    hallazgos = []   # (parte, tipo, contexto)
    conteo = {}
    sustituidos = []
    with zipfile.ZipFile(ruta) as z:
        for parte in partes_texto(z):
            raiz = etree.fromstring(z.read(parte))
            for p in raiz.iter(W + "p"):
                t = "".join(x.text or "" for x in p.iter(W + "t"))
                for m in PATRON.finditer(t):
                    c = m.group()
                    conteo[c] = conteo.get(c, 0) + 1
                    if len(hallazgos) < 300:
                        hallazgos.append((nombre_parte(parte), INVISIBLES[c], _contexto(t, m.start())))
                for w in PALABRA.finditer(t):
                    pal = w.group()
                    if any(ch in HOMOGLIFOS for ch in pal) and any("a" <= ch.lower() <= "z" for ch in pal):
                        sustituidos.append((nombre_parte(parte), pal, t[max(0, w.start() - 40):w.end() + 40]))
    return {
        "total": sum(conteo.values()),
        "por_tipo": {INVISIBLES[k]: v for k, v in sorted(conteo.items(), key=lambda kv: -kv[1])},
        "ejemplos": hallazgos,
        "sustituidos": sustituidos[:200],
    }


_WT = re.compile(r"(<w:t(?:\s[^>]*)?>)([^<]*)(</w:t>)")
_ENT = re.compile(r"&#(x[0-9a-fA-F]+|\d+);")


def _es_invisible(ent: str) -> bool:
    try:
        cp = int(ent[1:], 16) if ent[0] in "xX" else int(ent)
    except ValueError:
        return False
    return chr(cp) in INVISIBLES


def limpiar(origen: Path, destino: Path):
    """Copia el .docx a destino quitando invisibles del texto visible. Devuelve cuántos quitó."""
    quitados = 0

    def sub_ent(m):
        nonlocal quitados
        if _es_invisible(m.group(1)):
            quitados += 1
            return ""
        return m.group(0)

    def sub_t(m):
        nonlocal quitados
        cuerpo = _ENT.sub(sub_ent, m.group(2))
        nuevo, n = PATRON.subn("", cuerpo)
        quitados += n
        return m.group(1) + nuevo + m.group(3)

    tmp = destino.with_suffix(".tmp")
    with zipfile.ZipFile(origen) as zin, zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as zout:
        objetivos = set(partes_texto(zin))
        for info in zin.infolist():
            data = zin.read(info.filename)
            if info.filename in objetivos:
                xml = data.decode("utf-8")
                nuevo = _WT.sub(sub_t, xml)
                if nuevo != xml:
                    etree.fromstring(nuevo.encode("utf-8"))  # validar antes de escribir
                    data = nuevo.encode("utf-8")
            zout.writestr(info, data)
    shutil.move(tmp, destino)
    return quitados

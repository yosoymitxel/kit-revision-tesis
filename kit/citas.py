"""Citas de Word (campos CITATION) contra el almacén de fuentes de la bibliografía."""
import re
from collections import Counter

from .docx_utils import fuentes_bibliograficas, parrafos, indice_headings

CITA_TEXTO = re.compile(r"\([A-ZÁÉÍÓÚÑ][^()]{1,90}?,\s*(?:19|20)\d\d[a-z]?(?:,\s*[^()]{1,25})?\)|\([A-ZÁÉÍÓÚÑ][^()]{1,60}?,\s*s\.\s*f\.\)")


def analizar(ruta):
    ps = parrafos(ruta)
    idx = indice_headings(ps)
    tags = Counter()
    hay_bibliografia = False
    texto_plano = []
    for i, p in enumerate(ps):
        for c in p.campos:
            m = re.match(r"CITATION\s+(\S+)", c)
            if m:
                tags[m.group(1)] += 1
                # citas múltiples: \m Tag2
                for extra in re.findall(r"\\m\s+(\S+)", c):
                    tags[extra] += 1
            if c.upper().startswith("BIBLIOGRAPHY"):
                hay_bibliografia = True
        for m in CITA_TEXTO.finditer(p.texto_fuera_campos):
            loc = idx[i]
            texto_plano.append({
                "cita": m.group(),
                "contexto": p.texto_fuera_campos[max(0, m.start() - 60):m.end() + 20],
                "pagina": loc["pagina"],
                "titulo": loc["titulo"],
                "subtitulo": loc["subtitulo"],
            })
    hay_almacen, fuentes = fuentes_bibliograficas(ruta)
    citadas = set(tags)
    return {
        "campos_cita": sum(tags.values()),
        "fuentes_citadas": len(citadas),
        "fuentes_registradas": len(fuentes),
        "hay_almacen": hay_almacen,
        "hay_bibliografia": hay_bibliografia,
        "sin_fuente": sorted(citadas - set(fuentes)),
        "sin_citar": sorted((t, fuentes[t]) for t in set(fuentes) - citadas),
        "texto_plano": texto_plano,
    }

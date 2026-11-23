"""Conteo de palabras y numeración de tablas y figuras."""
import re

from .docx_utils import parrafos

ROTULO = re.compile(r"^\s*(Tabla|Figura)\s+(\d+)(?!\d)")
MENCION = re.compile(r"\b(Tabla|Figura)\s+(\d+)(?!\d)")


def analizar(ruta):
    ps = parrafos(ruta)
    palabras = 0
    rotulos = {"Tabla": [], "Figura": []}
    menciones = {"Tabla": set(), "Figura": set()}
    for p in ps:
        est = (p.estilo or "").lower()
        es_indice = est.startswith(("toc", "table of figures", "tabla de ilustraciones")) or "índice" in est
        if not es_indice:
            palabras += len(p.texto.split())
        m = ROTULO.match(p.texto)
        if m and ("caption" in est or "epígrafe" in est or "descripción" in est):
            rotulos[m.group(1)].append(int(m.group(2)))
        elif not es_indice:
            for t, n in MENCION.findall(p.texto):
                menciones[t].add(int(n))
    problemas = []
    for tipo, nums in rotulos.items():
        if not nums:
            continue
        dup = sorted({n for n in nums if nums.count(n) > 1})
        if dup:
            problemas.append(f"{tipo}: número repetido {', '.join(map(str, dup))}")
        faltan = sorted(set(range(1, max(nums) + 1)) - set(nums))
        if faltan:
            problemas.append(f"{tipo}: falta el número {', '.join(map(str, faltan))}")
        desorden = [b for a, b in zip(nums, nums[1:]) if b < a]
        if desorden:
            problemas.append(f"{tipo}: numeración fuera de orden cerca de {desorden[0]}")
        fantasmas = sorted(menciones[tipo] - set(nums))
        if fantasmas:
            problemas.append(f"{tipo}: se menciona en el texto pero no existe: {', '.join(map(str, fantasmas))}")
    return {
        "palabras": palabras,
        "tablas": len(rotulos["Tabla"]),
        "figuras": len(rotulos["Figura"]),
        "problemas": problemas,
    }

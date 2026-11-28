"""Conteo de palabras, exposición antiplagio (citas vs no citas) y numeración de tablas y figuras."""
import re

from .docx_utils import parrafos

ROTULO = re.compile(r"^\s*(Tabla|Figura)\s+(\d+)(?!\d)")
MENCION = re.compile(r"\b(Tabla|Figura)\s+(\d+)(?!\d)")
COMILLAS_CITA = re.compile(r'[“"«]([^”"»]{15,}?)[”"»]')
CITA_PLANA = re.compile(
    r"\([A-ZÁÉÍÓÚÑ][^()]{1,90}?,\s*(?:19|20)\d\d[a-z]?(?:,\s*[^()]{1,25})?\)"
    r"|\([A-ZÁÉÍÓÚÑ][^()]{1,60}?,\s*s\.\s*f\.\)"
)


def _calcular_exposicion(ps) -> dict:
    """Calcula el porcentaje de texto expuesto a antiplagio (no citas) vs texto en citas."""
    palabras_cuerpo = 0
    palabras_bibliografia = 0
    palabras_citas = 0
    palabras_parafrasis_citada = 0
    palabras_redaccion_propia = 0

    for p in ps:
        est = (p.estilo or "").lower()
        es_indice = est.startswith(("toc", "table of figures", "tabla de ilustraciones")) or "índice" in est
        if es_indice:
            continue
        w = len(p.texto.split())
        if not w:
            continue
        if "bibliog" in est:
            palabras_bibliografia += w
            continue

        palabras_cuerpo += w
        es_bloque = p.sangria_izq >= 600 and w >= 30
        if es_bloque:
            palabras_citas += w
            continue

        citas_q = min(sum(len(m.group(1).split()) for m in COMILLAS_CITA.finditer(p.texto)), w)
        palabras_citas += citas_q
        resto = w - citas_q
        tiene_cita = any(c.startswith("CITATION") for c in p.campos) or bool(CITA_PLANA.search(p.texto_fuera_campos))
        if tiene_cita:
            palabras_parafrasis_citada += resto
        else:
            palabras_redaccion_propia += resto

    palabras_no_citas = palabras_cuerpo - palabras_citas
    if palabras_cuerpo > 0:
        pct_citas = round(palabras_citas / palabras_cuerpo * 100, 2)
        pct_no_citas = round(100.0 - pct_citas, 2)
        pct_parafrasis = round(palabras_parafrasis_citada / palabras_cuerpo * 100, 2)
        pct_redaccion = round(max(0.0, pct_no_citas - pct_parafrasis), 2)
    else:
        pct_citas = pct_no_citas = pct_parafrasis = pct_redaccion = 0.0

    return {
        "palabras_cuerpo": palabras_cuerpo,
        "palabras_bibliografia": palabras_bibliografia,
        "palabras_citas": palabras_citas,
        "palabras_no_citas": palabras_no_citas,
        "palabras_parafrasis_citada": palabras_parafrasis_citada,
        "palabras_redaccion_propia": palabras_redaccion_propia,
        "pct_citas": pct_citas,
        "pct_no_citas": pct_no_citas,
        "pct_parafrasis_citada": pct_parafrasis,
        "pct_redaccion_propia": pct_redaccion,
    }


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
        "exposicion": _calcular_exposicion(ps),
    }

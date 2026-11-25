"""Punto de entrada: revisa la tesis de 1-MI-TESIS contra 2-FUENTES y escribe el panel en 3-RESULTADOS."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import citas, estructura, invisibles, panel, similitud, web

RAIZ = Path(__file__).resolve().parent.parent
TESIS, FUENTES, RESULTADOS = RAIZ / "1-MI-TESIS", RAIZ / "2-FUENTES", RAIZ / "3-RESULTADOS"


def obtener_slug(tesis_path: Path) -> str:
    """Devuelve el identificador de carpeta exclusivo para la tesis."""
    try:
        rel = tesis_path.relative_to(TESIS)
        if len(rel.parts) > 1:
            return rel.parts[0]
    except Exception:
        pass
    return tesis_path.stem


def carpeta_resultados(tesis_path: Path) -> Path:
    """Retorna la carpeta de resultados exclusiva para la tesis."""
    slug = obtener_slug(tesis_path)
    d = RESULTADOS / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def carpeta_fuentes(tesis_path: Path, seleccion: str = None):
    """Retorna (ruta_fuentes, solo_raiz, etiqueta) según la selección o carpeta propia de la tesis."""
    if seleccion == "__todas__":
        return FUENTES, False, "Todas (2-FUENTES)"
    if seleccion == "__raiz__":
        return FUENTES, True, "General (raíz de 2-FUENTES)"
    if seleccion:
        cand = FUENTES / seleccion
        if cand.is_dir():
            return cand, False, seleccion
    slug = obtener_slug(tesis_path)
    fuente_propia = FUENTES / slug
    if fuente_propia.is_dir() and any(fuente_propia.iterdir()):
        return fuente_propia, False, slug
    return FUENTES, False, "Todas (2-FUENTES)"


def buscar_tesis(nombre=None):
    if nombre:
        for p in TESIS.rglob("*.docx"):
            if p.name.startswith("~$"):
                continue
            rel = p.relative_to(TESIS)
            rel_str = str(rel).replace("\\", "/")
            slug = rel.parts[0] if len(rel.parts) > 1 else p.stem
            if nombre in (p.name, p.stem, rel_str, slug):
                return p
    docs = sorted((p for p in TESIS.rglob("*.docx") if not p.name.startswith("~$")), key=lambda p: p.stat().st_mtime, reverse=True)
    return docs[0] if docs else None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    ap = argparse.ArgumentParser(description="Revisión de tesis antes de entregar")
    ap.add_argument("--tesis", type=str, default=None, help="nombre o ruta del .docx en 1-MI-TESIS")
    ap.add_argument("--fuentes", type=str, default=None, help="carpeta de fuentes en 2-FUENTES (__todas__, __raiz__, o subcarpeta)")
    ap.add_argument("--bloque", type=int, default=8, help="palabras seguidas mínimas para contar coincidencia")
    ap.add_argument("--sin-similitud", action="store_true", help="saltar la comparación con fuentes")
    ap.add_argument("--sin-web", action="store_true", help="no descargar las fuentes web de la bibliografía")
    ap.add_argument("--actualizar-web", action="store_true", help="volver a descargar las fuentes web ya guardadas")
    args = ap.parse_args()

    tesis = buscar_tesis(args.tesis)
    if not tesis:
        print("No hay ningún .docx en la carpeta 1-MI-TESIS. Copiá ahí tu tesis y volvé a ejecutar.", flush=True)
        return 1

    res_dir = carpeta_resultados(tesis)
    fuentes_dir, solo_raiz, fuentes_label = carpeta_fuentes(tesis, args.fuentes)
    slug = obtener_slug(tesis)

    print(f"Revisando: {tesis.name} (Carpeta: {slug})", flush=True)
    print(f"Fuentes: {fuentes_label} -> {fuentes_dir.relative_to(RAIZ)}", flush=True)
    print(f"Resultados: {res_dir.relative_to(RAIZ)}", flush=True)

    print("[PROGRESO: 10%] [1/5] Analizando citas y referencias...", flush=True)
    c = citas.analizar(tesis)
    print(f"  · Citas procesadas: {c.get('campos_cita', 0)} dinámicas, {len(c.get('texto_plano', []))} a mano", flush=True)

    print("[PROGRESO: 25%] [2/5] Analizando estructura, tablas y figuras...", flush=True)
    s = estructura.analizar(tesis)
    n_tablas = s.get('tablas', 0) if isinstance(s.get('tablas', 0), int) else len(s.get('tablas', []))
    n_figuras = s.get('figuras', 0) if isinstance(s.get('figuras', 0), int) else len(s.get('figuras', []))
    print(f"  · Palabras: {s.get('palabras', 0):,} · Tablas/Figuras: {n_tablas}/{n_figuras}", flush=True)

    print("[PROGRESO: 40%] [3/5] Analizando caracteres invisibles...", flush=True)
    i = invisibles.analizar(tesis)
    print(f"  · Invisibles encontrados: {i.get('total', 0)}", flush=True)

    w = []
    if not args.sin_web:
        print("[PROGRESO: 50%] [4/5] Verificando fuentes web de la bibliografía...", flush=True)
        w = web.descargar(tesis, fuentes_dir / "web", actualizar=args.actualizar_web)
    else:
        print("[PROGRESO: 50%] [4/5] Fuentes web omitidas.", flush=True)

    if args.sin_similitud:
        print("[PROGRESO: 90%] [5/5] Comparación con fuentes omitida.", flush=True)
        sim = {"fuentes": [], "pasajes": [], "error": "Comparación con fuentes omitida."}
    else:
        print("[PROGRESO: 55%] [5/5] Comparando similitud con fuentes...", flush=True)
        sim = similitud.analizar(tesis, fuentes_dir, res_dir, bloque=args.bloque, solo_raiz=solo_raiz)

    print("[PROGRESO: 95%] Guardando panel de resultados e historial...", flush=True)

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    hist_path = res_dir / "historial.json"
    try:
        historial = json.loads(hist_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        historial = []
    historial.append({
        "fecha": fecha, "archivo": tesis.name, "fuentes": fuentes_label,
        "max_sim": sim["fuentes"][0]["porcentaje"] if sim["fuentes"] else 0,
        "sin_comillas": sum(1 for p in sim["pasajes"] if p["estado"] == "Sin comillas"),
        "citas_mal": len(c["sin_fuente"]) + len(c["sin_citar"]) + (0 if c["hay_almacen"] else 1),
        "invisibles": i["total"],
        "enlaces_mal": sum(1 for x in w if x["estado"] != "OK"),
    })
    hist_path.write_text(json.dumps(historial, ensure_ascii=False, indent=1), encoding="utf-8")

    datos = {"archivo": tesis.name, "carpeta_tesis": slug, "fuentes_usadas": fuentes_label,
             "fecha": fecha, "citas": c, "estructura": s, "invisibles": i,
             "similitud": sim, "web": w, "historial": historial}
    (res_dir / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (res_dir / "panel.html").write_text(panel.generar(datos), encoding="utf-8")

    # Guardar también en raíz de RESULTADOS como referencia al último análisis realizado
    (RESULTADOS / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (RESULTADOS / "panel.html").write_text(panel.generar(datos), encoding="utf-8")

    print(f"\nListo. Panel de esta tesis: {res_dir / 'panel.html'}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

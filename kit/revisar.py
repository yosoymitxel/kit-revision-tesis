"""Punto de entrada: revisa la tesis de 1-MI-TESIS contra 2-FUENTES y escribe el panel en 3-RESULTADOS."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import citas, estructura, invisibles, panel, similitud, web

RAIZ = Path(__file__).resolve().parent.parent
TESIS, FUENTES, RESULTADOS = RAIZ / "1-MI-TESIS", RAIZ / "2-FUENTES", RAIZ / "3-RESULTADOS"


def buscar_tesis():
    docs = sorted((p for p in TESIS.glob("*.docx") if not p.name.startswith("~$")), key=lambda p: p.stat().st_mtime, reverse=True)
    return docs[0] if docs else None


def main():
    ap = argparse.ArgumentParser(description="Revisión de tesis antes de entregar")
    ap.add_argument("--bloque", type=int, default=8, help="palabras seguidas mínimas para contar coincidencia")
    ap.add_argument("--sin-similitud", action="store_true", help="saltar la comparación con fuentes")
    ap.add_argument("--sin-web", action="store_true", help="no descargar las fuentes web de la bibliografía")
    ap.add_argument("--actualizar-web", action="store_true", help="volver a descargar las fuentes web ya guardadas")
    args = ap.parse_args()

    tesis = buscar_tesis()
    if not tesis:
        print("No hay ningún .docx en la carpeta 1-MI-TESIS. Copiá ahí tu tesis y volvé a ejecutar.")
        return 1
    RESULTADOS.mkdir(exist_ok=True)
    print(f"Revisando: {tesis.name}")

    print("  · citas y referencias")
    c = citas.analizar(tesis)
    print("  · tablas, figuras y palabras")
    s = estructura.analizar(tesis)
    print("  · caracteres invisibles")
    i = invisibles.analizar(tesis)
    w = []
    if not args.sin_web:
        print("  · fuentes web de la bibliografía")
        w = web.descargar(tesis, FUENTES / "web", actualizar=args.actualizar_web)
    if args.sin_similitud:
        sim = {"fuentes": [], "pasajes": [], "error": "Comparación con fuentes omitida."}
    else:
        print("  · similitud con tus fuentes (puede tardar un par de minutos)")
        sim = similitud.analizar(tesis, FUENTES, RESULTADOS, bloque=args.bloque)

    fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
    hist_path = RESULTADOS / "historial.json"
    try:
        historial = json.loads(hist_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        historial = []
    historial.append({
        "fecha": fecha, "archivo": tesis.name,
        "max_sim": sim["fuentes"][0]["porcentaje"] if sim["fuentes"] else 0,
        "sin_comillas": sum(1 for p in sim["pasajes"] if p["estado"] == "Sin comillas"),
        "citas_mal": len(c["sin_fuente"]) + len(c["sin_citar"]) + (0 if c["hay_almacen"] else 1),
        "invisibles": i["total"],
        "enlaces_mal": sum(1 for x in w if x["estado"] != "OK"),
    })
    hist_path.write_text(json.dumps(historial, ensure_ascii=False, indent=1), encoding="utf-8")

    datos = {"archivo": tesis.name, "fecha": fecha, "citas": c, "estructura": s, "invisibles": i,
             "similitud": sim, "web": w, "historial": historial}
    (RESULTADOS / "datos.json").write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (RESULTADOS / "panel.html").write_text(panel.generar(datos), encoding="utf-8")
    print(f"\nListo. Panel: {RESULTADOS / 'panel.html'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

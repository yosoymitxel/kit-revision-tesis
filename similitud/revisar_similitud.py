#!/usr/bin/env python3
"""Compara tu tesis contra tus propias fuentes y muestra qué fragmentos coinciden.

Uso:
    python revisar_similitud.py MI_TESIS.docx CARPETA_DE_FUENTES [--bloque 8]

- MI_TESIS: .docx, .pdf, .odt o .txt
- CARPETA_DE_FUENTES: los PDF/DOCX/TXT que citaste (artículos, leyes, tesis anteriores...)
- --bloque: mínimo de palabras seguidas iguales para contar como coincidencia.
  Con 2 (lo que trae copy-spotter) marca casi todo; 8 es un punto de partida razonable.

El objetivo es encontrar los párrafos que quedaron copiados sin comillas o sin cita
para corregirlos: citar textual (entre comillas, con autor, año y página) o
reescribir de verdad con su cita. No sirve para "engañar" al detector.
"""
import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import webbrowser
from pathlib import Path

from bs4 import BeautifulSoup

EXTS = {".pdf", ".docx", ".odt", ".txt"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tesis", type=Path)
    ap.add_argument("fuentes", type=Path)
    ap.add_argument("--bloque", type=int, default=8, help="palabras seguidas mínimas (por defecto 8)")
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el informe en el navegador")
    args = ap.parse_args()

    if not args.tesis.is_file() or args.tesis.suffix.lower() not in EXTS:
        print(f"No encuentro la tesis o su formato no es {sorted(EXTS)}: {args.tesis}")
        return 1
    fuentes = [p for p in args.fuentes.iterdir() if p.is_file() and p.suffix.lower() in EXTS] if args.fuentes.is_dir() else []
    if not fuentes:
        print(f"La carpeta de fuentes no tiene archivos {sorted(EXTS)}: {args.fuentes}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        entrada = Path(tmp) / "entrada"
        entrada.mkdir()
        nombre_tesis = "__MI_TESIS__" + args.tesis.suffix.lower()
        shutil.copy(args.tesis, entrada / nombre_tesis)
        for f in fuentes:
            shutil.copy(f, entrada / f.name)

        print(f"Comparando la tesis contra {len(fuentes)} fuentes (bloque = {args.bloque} palabras)...")
        # copy-spotter ignora -o y guarda en ../results respecto de la carpeta actual,
        # así que se lo corre desde una subcarpeta de "resultados-similitud".
        base = Path.cwd() / "resultados-similitud"
        trabajo = base / "_tmp"
        trabajo.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["copy-spotter", str(entrada), "-s", str(args.bloque)],
                           capture_output=True, text=True, cwd=trabajo)
        shutil.rmtree(trabajo, ignore_errors=True)
        salida = r.stdout + r.stderr
        m = re.search(r"Results saved at:\s*(\S+_results\.html)", salida)
        if r.returncode != 0 or not m:
            print("copy-spotter falló:\n" + salida)
            return 1
        informe = Path(m.group(1))

    filas = BeautifulSoup(informe.read_text(encoding="utf-8"), "html.parser").find_all("tr")
    encabezado = [c.get_text(strip=True) for c in filas[0].find_all(["td", "th"])]
    resultados = []
    for fila in filas[1:]:
        celdas = fila.find_all(["td", "th"])
        if not celdas or celdas[0].get_text(strip=True) != "__MI_TESIS__":
            continue
        for nombre, celda in zip(encabezado[1:], celdas[1:]):
            enlace = celda.find("a")
            if nombre == "__MI_TESIS__" or not enlace:
                continue
            pct = float(celda.get_text(strip=True))
            resultados.append((pct, nombre, enlace["href"]))

    resultados.sort(reverse=True)
    print("\nSimilitud de tu tesis con cada fuente (mayor primero):\n")
    for pct, nombre, href in resultados:
        alerta = "  <-- revisar" if pct >= 5 else ""
        print(f"  {pct:6.2f} %  {nombre}{alerta}")
    print("\nEn cada comparación lado a lado, las frases en verde son las que coinciden.")
    print("Si una coincidencia ya está entre comillas y con su cita APA, está bien.")
    print(f"\nInforme completo: {informe}")
    if not args.no_abrir:
        webbrowser.open(informe.as_uri())
    return 0


if __name__ == "__main__":
    sys.exit(main())

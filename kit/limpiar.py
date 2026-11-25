"""Crea en 3-RESULTADOS una copia de la tesis sin caracteres invisibles. El original no se toca."""
import argparse
import sys

from . import citas, invisibles
from .revisar import RESULTADOS, buscar_tesis, carpeta_resultados


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    ap = argparse.ArgumentParser(description="Limpieza de caracteres invisibles en la tesis")
    ap.add_argument("--tesis", type=str, default=None, help="nombre del archivo .docx específico en 1-MI-TESIS")
    args = ap.parse_args()

    tesis = buscar_tesis(args.tesis)
    if not tesis:
        print("No hay ningún .docx en 1-MI-TESIS.", flush=True)
        return 1
    res_dir = carpeta_resultados(tesis)
    destino = res_dir / f"{tesis.stem} (sin invisibles).docx"
    print(f"[PROGRESO: 20%] Analizando documento: {tesis.name}...", flush=True)
    antes = citas.analizar(tesis)
    print(f"[PROGRESO: 50%] Eliminando caracteres invisibles...", flush=True)
    n = invisibles.limpiar(tesis, destino)
    print(f"[PROGRESO: 80%] Verificando integridad de citas y referencias...", flush=True)
    despues = citas.analizar(destino)
    if (antes["campos_cita"], antes["fuentes_registradas"]) != (despues["campos_cita"], despues["fuentes_registradas"]):
        destino.unlink()
        print("Se canceló: la copia limpia no conservaba las citas. Tu archivo original está intacto.", flush=True)
        return 1

    # Copiar también en la raíz de resultados como respaldo de conveniencia
    import shutil
    try:
        shutil.copy2(destino, RESULTADOS / destino.name)
    except Exception:
        pass
    print(f"[PROGRESO: 100%] Quitados {n} caracteres invisibles. Citas conservadas: {despues['campos_cita']}.", flush=True)
    print(f"Copia limpia creada exitosamente: {destino.name}", flush=True)
    print("Abrila en Word, revisá que se vea bien y recién ahí reemplazá tu archivo.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Crea en 3-RESULTADOS una copia de la tesis sin caracteres invisibles. El original no se toca."""
import sys

from . import citas, invisibles
from .revisar import RESULTADOS, buscar_tesis


def main():
    tesis = buscar_tesis()
    if not tesis:
        print("No hay ningún .docx en 1-MI-TESIS.")
        return 1
    RESULTADOS.mkdir(exist_ok=True)
    destino = RESULTADOS / f"{tesis.stem} (sin invisibles).docx"
    antes = citas.analizar(tesis)
    n = invisibles.limpiar(tesis, destino)
    despues = citas.analizar(destino)
    if (antes["campos_cita"], antes["fuentes_registradas"]) != (despues["campos_cita"], despues["fuentes_registradas"]):
        destino.unlink()
        print("Se canceló: la copia limpia no conservaba las citas. Tu archivo original está intacto.")
        return 1
    print(f"Quitados {n} caracteres invisibles. Citas conservadas: {despues['campos_cita']}.")
    print(f"Copia limpia: {destino}")
    print("Abrila en Word, revisá que se vea bien y recién ahí reemplazá tu archivo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

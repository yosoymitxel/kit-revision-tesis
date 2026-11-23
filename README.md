# Kit de revisión de tesis

Revisá tu tesis **antes** de entregarla: qué párrafos quedaron copiados sin comillas, qué citas no tienen referencia, si hay caracteres raros de copiar y pegar y si la numeración de tablas y figuras está bien. Todo corre en tu computadora: tu tesis no se sube a ningún lado.

## Uso (Windows)

1. Instalá [Python 3.10 o superior](https://www.python.org/downloads/) marcando **Add Python to PATH** (una sola vez).
2. Descargá el kit (**Code → Download ZIP**) y descomprimilo.
3. Copiá tu tesis `.docx` en **`1-MI-TESIS`**.
4. Copiá en **`2-FUENTES`** los PDF/DOCX/TXT que citaste (artículos, leyes, normas, tesis anteriores).
5. Doble clic en **`REVISAR.bat`**. La primera vez tarda unos minutos porque instala lo necesario.
6. Se abre **`3-RESULTADOS/panel.html`** con el panel.

En Linux o macOS: `./revisar.sh` (y `./revisar.sh limpiar`).

## Qué muestra el panel

| Indicador | Qué significa | Qué hacer |
| --- | --- | --- |
| Similitud máxima | Coincidencia con la fuente más parecida de `2-FUENTES` | Mirar la comparación lado a lado |
| Párrafos copiados sin comillas | Texto igual a una fuente pero sin comillas ni cita en bloque | Citar textual (comillas + autor, año, página o artículo) o reescribir manteniendo la cita |
| Problemas de citas | Citas de Word sin fuente registrada, fuentes nunca citadas o almacén de fuentes dañado | Corregir desde **Referencias → Administrar fuentes** |
| Citas escritas a mano | `(Autor, 2020)` escrito como texto, no como cita de Word | Reemplazar por **Insertar cita** |
| Caracteres invisibles | Espacios de ancho cero y similares que llegan al copiar y pegar | `LIMPIAR-INVISIBLES.bat` |
| Letras de otro alfabeto | Letras cirílicas o griegas que se ven iguales a las latinas | Reescribir la palabra a mano |
| Tablas y figuras | Números repetidos, saltos o menciones a tablas que no existen | Actualizar campos (Ctrl+A, F9) y revisar |
| Historial | Cómo cambió cada indicador entre revisiones | — |

> El porcentaje del panel **no** es el que va a dar Plagiarism Checker X: solo compara contra tus fuentes. Sirve para saber dónde corregir.

## Limpiar caracteres invisibles sin romper las citas

`LIMPIAR-INVISIBLES.bat` crea `3-RESULTADOS/<tesis> (sin invisibles).docx`:

- Quita solo caracteres invisibles del texto visible (cuerpo, encabezados, pies, notas, comentarios).
- **No toca** el almacén de fuentes de Word (`customXml`), campos, estilos ni imágenes.
- Compara las citas antes y después; si cambia algo, cancela y no deja archivo.
- Tu archivo original nunca se modifica.

Herramientas de "limpieza de marcas de agua" que borran `customXml` dejan las citas APA en error, porque ahí Word guarda la bibliografía. Por eso el kit no las usa.

Quitar invisibles corrige basura de copiar y pegar; **no** cambia cómo fue escrito el texto. Los detectores de IA analizan la redacción, no esos caracteres.

## Herramientas que usa o recomienda

Ver [`docs/integraciones.md`](docs/integraciones.md): copy-spotter, Plagx Draft Preflight (Word) y Plagx Cite + Preflight MCP (Claude).

## Más

- [`docs/checklist-antes-de-entregar.md`](docs/checklist-antes-de-entregar.md)
- [`docs/citas-y-bibliografia.md`](docs/citas-y-bibliografia.md)
- [`docs/uso-de-ia.md`](docs/uso-de-ia.md)

## Créditos

[copy-spotter](https://github.com/Wazzabeee/copy-spotter) (Clément Delteil) · [Plagx](https://github.com/plagiarismcheckerx) (Plagiarism Checker X, MIT).

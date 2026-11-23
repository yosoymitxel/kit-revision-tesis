# Kit de revisión de tesis antes de entregar

Herramientas gratuitas para dejar la tesis prolija **antes** de que la pase la universidad por Plagiarism Checker X y antes de la defensa.

La idea es simple: encontrar a tiempo lo que quedó mal citado y corregirlo. Ninguna de estas herramientas "baja el porcentaje" a la fuerza: lo que baja el porcentaje de forma legítima es citar bien (comillas + autor, año y página) o redactar con tus palabras y citar igual.

| Qué revisa | Herramienta | Dónde |
| --- | --- | --- |
| Frases copiadas de tus fuentes sin comillas o sin cita | `copy-spotter` + script de este repo | [`similitud/`](similitud/) |
| Citas sin entrada en Referencias y referencias que nunca citaste | Plagx Draft Preflight (complemento de Word) | [`docs/citas-y-bibliografia.md`](docs/citas-y-bibliografia.md) |
| Bibliografía APA 7, DOI, referencias duplicadas | Plagx Cite + Preflight MCP (para Claude) | [`docs/citas-y-bibliografia.md`](docs/citas-y-bibliografia.md) |
| Formato APA y detalles que marcan los tribunales | Checklist | [`docs/checklist-antes-de-entregar.md`](docs/checklist-antes-de-entregar.md) |

## 1. Similitud con tus fuentes (lo más parecido al detector)

Plagiarism Checker X compara tu texto con internet y con su base. Acá no tenemos esa base, pero sí tenemos algo útil: **tus propias fuentes**. Si las juntás en una carpeta, el script te muestra qué párrafos de tu tesis coinciden con cuál fuente y te abre una comparación lado a lado.

### Instalación (una sola vez)

1. Instalá [Python 3.10 o superior](https://www.python.org/downloads/) (en Windows, marcá *Add Python to PATH*).
2. Descargá este repo (botón verde **Code → Download ZIP**) y descomprimilo.
3. Abrí una terminal en la carpeta `similitud` y corré:

```bash
pip install -r requirements.txt
```

### Uso

1. Creá una carpeta, por ejemplo `fuentes`, y poné adentro los PDF, DOCX o TXT que citaste (artículos, leyes, tesis anteriores, apuntes de cátedra).
2. Corré:

```bash
python revisar_similitud.py "C:\ruta\a\MiTesis.docx" "C:\ruta\a\fuentes"
```

3. Se imprime el porcentaje de coincidencia con cada fuente y se abre el informe en el navegador. Cada celda lleva a la comparación lado a lado; lo que coincide aparece en verde.

Opcional: `--bloque 12` para marcar solo coincidencias largas (12 palabras seguidas o más); `--bloque 5` para ser más estricto. Por defecto usa 8.

### Qué hacer con cada coincidencia

- **Está entre comillas y con su cita APA:** está bien, dejala.
- **Es una definición o un artículo de ley que necesitás tal cual:** ponela entre comillas, con autor, año y página (o artículo). Si pasa de 40 palabras, va como cita en bloque.
- **Es una idea que tomaste pero copiaste la redacción:** reescribila con tus palabras y mantené la cita.
- **No sabés de dónde salió:** buscá la fuente original y citala. Si no la encontrás, sacala.

### Límites

- Solo compara contra las fuentes que vos pongas en la carpeta; no busca en internet.
- Las tablas y figuras pegadas como imagen no se revisan.
- El porcentaje no es el mismo que va a dar Plagiarism Checker X: usalo para encontrar *dónde* corregir, no como predicción del número final.

## 2. Citas y bibliografía

Ver [`docs/citas-y-bibliografia.md`](docs/citas-y-bibliografia.md).

## 3. Checklist final

Ver [`docs/checklist-antes-de-entregar.md`](docs/checklist-antes-de-entregar.md).

## Créditos

- [copy-spotter](https://github.com/Wazzabeee/copy-spotter) — Clément Delteil (Wazzabeee).
- [Plagx Draft Preflight](https://github.com/plagiarismcheckerx/plagx-preflight-word) y [Plagx Cite + Preflight MCP](https://github.com/plagiarismcheckerx/plagx-mcp) — Plagiarism Checker X (MIT).

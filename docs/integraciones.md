# Integraciones

| Herramienta | Para qué | Cómo se integra |
| --- | --- | --- |
| [copy-spotter](https://github.com/Wazzabeee/copy-spotter) | Similitud entre la tesis y tus fuentes, con comparación lado a lado | Se instala sola con `REVISAR.bat` |
| [Noplag Engine](https://github.com/NoplagLabs/noplag-engine) | Comparación local del DOCX contra el corpus indexado | Acción opcional desde el panel; Docker Compose, PostgreSQL y API FastAPI en localhost:8010 |
| [Brave Search API](https://brave.com/search/api/) | Descubre páginas públicas que contienen frases extraídas de la tesis | API key opcional en `.env`; no recibe el DOCX completo |
| [SearXNG](https://github.com/searxng/searxng) | Metabuscador local que agrega motores de búsqueda web | Docker Compose; API JSON local en localhost:8888 |
| [Playwright](https://playwright.dev/python/) | Leer fuentes web armadas con JavaScript | Se usa solo si la descarga simple no trae texto; instala Chromium la primera vez |
| [Plagx Draft Preflight](https://github.com/plagiarismcheckerx/plagx-preflight-word) | Citas sin referencia y referencias sin citar, dentro de Word | Complemento de Word: Inicio → Complementos → "Plagx Draft Preflight" |
| [Plagx Cite + Preflight MCP](https://github.com/plagiarismcheckerx/plagx-mcp) | Bibliografía APA 7, DOI, duplicados, revisión de borradores desde Claude | `claude mcp add plagx -- npx -y plagx-mcp` (requiere Node.js 18+) |

## Herramientas que el kit no usa

| Herramienta | Motivo |
| --- | --- |
| Limpiadores de "marcas de agua" que borran `customXml` (p. ej. watermarks-remover) | Eliminan el almacén de fuentes de Word y rompen todas las citas APA |
| "Humanizadores" y evasores de similitud | Están hechos para engañar al detector; si el tribunal lo descubre, es fraude académico |


## Noplag Engine

Noplag es complementario a copy-spotter. Mantiene su propio reporte y base de datos; no sustituye, borra ni recalcula las comparaciones existentes. Indexa PDF, DOCX y TXT del conjunto activo, páginas web de las referencias y páginas externas descubiertas con Brave Search y SearXNG. Los archivos ODT siguen disponibles para el análisis habitual, pero Noplag no los ingiere.

La búsqueda distribuye frases distintivas a lo largo de la tesis, consulta ambos proveedores, deduplica URLs y descarga páginas públicas accesibles. HTML, TXT, PDF con capa de texto y DOCX se convierten a texto y se guardan bajo el resultado de cada tesis. La extracción está limitada a 5 MiB por respuesta, 35 páginas por defecto y tres URLs por dominio. Los destinos privados y locales se rechazan.

Brave necesita una clave API; SearXNG se autohospeda en Docker y usa los motores habilitados en su configuración. El DOCX completo no se envía a los buscadores: reciben fragmentos breves como consultas. El reporte distingue proveedores, URLs descubiertas, páginas descargadas y fallos de extracción.

La búsqueda depende de los índices y motores disponibles. No garantiza cobertura de toda Internet ni detecta automáticamente paráfrasis semánticas. Noplag conserva su API sin autenticación en `127.0.0.1:8010`; SearXNG también se publica únicamente en `127.0.0.1:8888`.

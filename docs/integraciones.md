# Integraciones

| Herramienta | Para qué | Cómo se integra |
| --- | --- | --- |
| [copy-spotter](https://github.com/Wazzabeee/copy-spotter) | Similitud entre la tesis y tus fuentes, con comparación lado a lado | Se instala sola con `REVISAR.bat` |
| [Noplag Engine](https://github.com/NoplagLabs/noplag-engine) | Segundo motor independiente para detectar coincidencias textuales y cercanas contra un corpus indexado | Acción opcional desde el panel; Docker Compose local, PostgreSQL y API FastAPI en localhost:8010 |
| [Playwright](https://playwright.dev/python/) | Leer fuentes web armadas con JavaScript | Se usa solo si la descarga simple no trae texto; instala Chromium la primera vez |
| [Plagx Draft Preflight](https://github.com/plagiarismcheckerx/plagx-preflight-word) | Citas sin referencia y referencias sin citar, dentro de Word | Complemento de Word: Inicio → Complementos → "Plagx Draft Preflight" |
| [Plagx Cite + Preflight MCP](https://github.com/plagiarismcheckerx/plagx-mcp) | Bibliografía APA 7, DOI, duplicados, revisión de borradores desde Claude | `claude mcp add plagx -- npx -y plagx-mcp` (requiere Node.js 18+) |

## Herramientas que el kit no usa

| Herramienta | Motivo |
| --- | --- |
| Limpiadores de "marcas de agua" que borran `customXml` (p. ej. watermarks-remover) | Eliminan el almacén de fuentes de Word y rompen todas las citas APA |
| "Humanizadores" y evasores de similitud | Están hechos para engañar al detector; si el tribunal lo descubre, es fraude académico |


## Noplag Engine

Noplag es complementario a copy-spotter. Mantiene su propio reporte y base de datos; no sustituye, borra ni recalcula las comparaciones existentes. Indexa PDF, DOCX y TXT del conjunto activo, además de páginas web descargadas desde las referencias del DOCX. Los archivos ODT siguen disponibles para el análisis original del kit, pero Noplag no los ingiere. El proyecto open source no consulta toda la web, no detecta paráfrasis semánticas y su API no tiene autenticación: por eso el Compose del kit publica el servicio únicamente en 127.0.0.1:8010.

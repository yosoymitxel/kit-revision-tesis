# Integraciones

| Herramienta | Para qué | Cómo se integra |
| --- | --- | --- |
| [copy-spotter](https://github.com/Wazzabeee/copy-spotter) | Similitud entre la tesis y tus fuentes, con comparación lado a lado | Se instala sola con `REVISAR.bat` |
| [Noplag Engine](https://github.com/NoplagLabs/noplag-engine) | Comparación local del DOCX contra el corpus indexado | Acción opcional desde el panel; Docker Compose, PostgreSQL y API FastAPI en localhost:8010 |
| [LA Referencia](https://www.lareferencia.info/) | Catálogo regional de tesis y publicaciones en acceso abierto | Consulta del buscador VuFind; no requiere API key |
| [Crossref](https://www.crossref.org/) + [Habanero](https://pypi.org/project/habanero/) | Recupera metadatos, DOI y abstracts de publicaciones | API REST pública, sin API key; `CROSSREF_MAILTO` opcional |
| [OpenAIRE Graph](https://graph.openaire.eu/) | Amplía el descubrimiento académico internacional | Graph API v4 pública, sin API key |
| [OAI-PMH](https://www.openarchives.org/pmh/) + [Sickle](https://pypi.org/project/sickle/) | Cosecha metadatos de repositorios universitarios | Endpoints públicos definidos en `ACADEMIC_OAI_ENDPOINTS` |
| [Sentence Transformers](https://www.sbert.net/) | Compara semánticamente fragmentos en español y otros idiomas | Modelo local opcional; requiere `requirements-semantic.txt` y descarga inicial |
| [Brave Search API](https://brave.com/search/api/) | Descubre páginas web generales | API key opcional; desactivada cuando no se configura |
| [SearXNG](https://github.com/searxng/searxng) | Metabuscador de Internet como respaldo | Docker Compose; API JSON local en localhost:8888 |
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


## Descubrimiento académico y similitud semántica

La búsqueda académica sin claves consulta el buscador de LA Referencia, Crossref y OpenAIRE Graph. LA Referencia agrega registros de repositorios regionales; la descarga de texto completo depende de los enlaces que publiquen los repositorios. Crossref y OpenAIRE aportan registros bibliográficos y, cuando están disponibles, abstracts o enlaces de acceso abierto. Un abstract se guarda y etiqueta como resumen, nunca como artículo completo.

Sickle se utiliza únicamente cuando se configuran endpoints OAI-PMH públicos en `ACADEMIC_OAI_ENDPOINTS`. OAI-PMH es un protocolo de cosecha de metadatos, no un buscador de texto completo: cada repositorio debe publicar su endpoint y habilitar el formato `oai_dc`. La cosecha está limitada por endpoint y se prioriza localmente con los términos de la tesis.

El análisis semántico es una segunda pasada local sobre las fuentes que se hayan podido extraer. La dependencia está separada en `requirements-semantic.txt` por el tamaño de PyTorch y del modelo. El modelo `paraphrase-multilingual-MiniLM-L12-v2` sirve para recuperar fragmentos semánticamente próximos; sus puntajes no son porcentajes de plagio ni evidencia concluyente. Sin fuentes completas en el corpus no puede detectar una paráfrasis de una página que nunca se descubrió o descargó.

Sin claves: LA Referencia, Crossref, OpenAIRE, Sickle/OAI-PMH y Sentence Transformers no requieren API keys. `CROSSREF_MAILTO` es un contacto opcional para el uso responsable de la API. No se requiere Brave; SearXNG queda como respaldo de búsqueda general.

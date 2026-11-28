# Kit de revisión de tesis

Revisa tu documento de tesis antes de entregarlo a la universidad o pasarlo por herramientas de control antiplagio. Detecta párrafos idénticos sin comillas, citas manuales sin vincular, referencias huérfanas, caracteres invisibles de copiar y pegar y problemas de numeración en tablas y figuras.

El análisis de documentos se ejecuta localmente. La verificación de referencias web realiza solicitudes a las URL bibliográficas. La comparación adicional con Noplag también se ejecuta en contenedores locales y no envía tu tesis a un servicio externo.

## Inicio rápido

Tienes dos formas de usar el kit: mediante la interfaz visual en el navegador o directamente con los archivos por lotes (.bat / .sh).

### Opción 1: Panel interactivo (Recomendado)

1. En Windows, haz doble clic en `INICIAR-INTERFAZ.bat` (o ejecuta `./iniciar_interfaz.sh` en Linux y macOS).
2. Se abrirá automáticamente la interfaz web en tu navegador (`http://127.0.0.1:8000/`).
3. Arrastra tu tesis (`.docx`) a la caja de carga.
4. Arrastra tus archivos fuente (PDF, DOCX o TXT) a la sección de fuentes.
5. Haz clic en **Revisar tesis**. El sistema ejecutará el análisis y mostrará el progreso en la consola integrada.
6. Al finalizar, pulsa en **Abrir panel de resultados** para explorar el diagnóstico.

### Opción 2: Carpetas y scripts por lotes

1. Copia tu archivo `.docx` en la carpeta `1-MI-TESIS`.
2. Copia tus fuentes bibliográficas en `2-FUENTES`. Si tu bibliografía de Word incluye enlaces o códigos DOI, el kit intentará descargarlos automáticamente en `2-FUENTES/web`.
3. Haz doble clic en `REVISAR.bat` (o `./revisar.sh` en Linux y macOS).
4. Al terminar el análisis, abre el archivo `3-RESULTADOS/panel.html` en cualquier navegador.

### Opciones de ejecución desde la terminal

Puedes agregar parámetros al comando de revisión:

- `--sin-web`: Omite la descarga de páginas web referenciadas en Word para acelerar el análisis.
- `--actualizar-web`: Fuerza la descarga nuevamente de las páginas web almacenadas en caché.
- `--bloque 12`: Reporta únicamente coincidencias que contengan 12 o más palabras consecutivas (el valor por defecto es 8).

## Paso adicional: comparación ampliada con Noplag Engine

La interfaz incluye una acción independiente para comparar el DOCX completo con un segundo motor de similitud. No reemplaza Copy-spotter ni modifica sus resultados.

- Reutiliza el conjunto seleccionado de `2-FUENTES` y descarga las URL/DOI de la bibliografía antes de indexarlo.
- Indexa PDF, DOCX y TXT en un corpus PostgreSQL persistente. Los archivos idénticos no se vuelven a indexar; los documentos administrados por el kit que ya no pertenecen al conjunto activo se retiran del corpus de esta integración.
- Envía el archivo DOCX directamente a la API local, con idioma español, y consulta el progreso hasta completar el análisis.
- Guarda un reporte independiente en `3-RESULTADOS/<tesis>/noplag.html` y sus datos en `noplag.json`.
- Requiere Docker con Compose. La primera ejecución construye el motor; el servicio queda limitado a localhost en el puerto 8010 y conserva el corpus en un volumen Docker.
- Esta versión de Noplag busca únicamente en el corpus indexado. No realiza una búsqueda global en Internet ni detecta paráfrasis semánticas.

## Diagnóstico del panel de resultados

El panel (`3-RESULTADOS/panel.html`) clasifica cada hallazgo mediante un sistema de cuatro colores:

- **Rojo (Corrección obligatoria):** Párrafos copiados sin comillas, citas con etiquetas no registradas en Word, enlaces caídos y letras de otros alfabetos camufladas.
- **Ámbar (Revisión recomendada):** Citas escritas a mano (texto plano), caracteres invisibles de copiar y pegar y numeraciones discontinuas.
- **Verde (Conforme):** Citas textuales o en bloque reglamentarias y fuentes comprobadas.
- **Azul (Informativo):** Conteo de palabras, métricas generales y enlaces de navegación directa.

| Sección | Qué analiza | Acción recomendada |
| --- | --- | --- |
| Párrafos coincidentes | Texto idéntico a tus fuentes sin formato de cita | Si tiene 40 palabras o más, aplicar formato de bloque (sangría de 1.27 cm, sin comillas e indicando autor, año y página). Si es menor, entrecomillar o parafrasear |
| Similitud por fuente | Porcentaje de coincidencia desglosado por cada archivo de `2-FUENTES` | Abrir la comparativa visual lado a lado para evaluar el contexto de cada coincidencia |
| Citas y referencias | Citas en el texto cuya fuente no existe en Word, o fuentes cargadas que nunca se citan | Registrar las fuentes faltantes desde Referencias > Administrar fuentes, o eliminar las no utilizadas |
| Citas escritas a mano | Textos como `(Gómez, 2024)` tipeados manualmente entre paréntesis | Reemplazarlos por campos oficiales de Word mediante Referencias > Insertar cita |
| Fuentes web | Enlaces de la bibliografía caídos, con redirección o con bloqueo | Actualizar el enlace, buscar la versión archivada en Wayback Machine o guardar la página como PDF en `2-FUENTES/web` |
| Caracteres invisibles | Espacios de ancho cero, guiones suaves y marcas de formato pegadas desde la web | Ejecutar `LIMPIAR-INVISIBLES.bat` para removerlos sin alterar citas ni estilos |
| Letras de otro alfabeto | Caracteres cirílicos o griegos idénticos visualmente a letras latinas | Reescribir la palabra con el teclado en español para evitar penalizaciones en comités evaluadores |
| Tablas y figuras | Saltos en la numeración correlativa o menciones a elementos inexistentes | Corregir la numeración correlativa en los epígrafes de Word |
| Historial | Evolución de las métricas entre diferentes ejecuciones | Evaluar la reducción progresiva de coincidencias y errores |

> El porcentaje de similitud calculado corresponde únicamente a la comparación contra los documentos que colocaste en `2-FUENTES`. No es un índice global de internet, sino una guía exacta para saber en qué página física y bajo qué título debes corregir tu texto.

## Limpieza segura de caracteres invisibles

Copiar fragmentos desde navegadores, chats o visores PDF suele introducir caracteres no imprimibles (espacios de ancho cero, saltos de línea ocultos). Los sistemas universitarios detectan estos caracteres como intentos de alteración.

El script `LIMPIAR-INVISIBLES.bat` genera una versión saneada en `3-RESULTADOS/<tesis> (sin invisibles).docx`:

- Limpia únicamente el texto visible (cuerpo, tablas, encabezados, notas al pie y comentarios).
- Preserva intactos los campos automáticos, estilos tipográficos, imágenes y el almacén `customXml/item.xml` donde Word guarda la bibliografía APA.
- Valida que la cantidad y estructura de citas sea idéntica antes y después del proceso. Si detecta alguna alteración, cancela la operación automáticamente.
- El archivo original de tu tesis nunca se sobreescribe ni se modifica.

## Fuentes en formato PDF escaneado

Si una fuente en `2-FUENTES` es una imagen o un documento escaneado sin capa de texto seleccionable, el analizador no podrá leer su contenido. El panel alertará de esta condición y ofrecerá dos acciones inmediatas:

1. Un enlace directo para buscar el documento por su nombre exacto en Google y obtener una copia digital original.
2. Un enlace a herramientas de reconocimiento óptico de caracteres (OCR) como iLovePDF para generar la versión con texto seleccionable antes de volver a ejecutar la revisión.

## Requisitos del sistema

- Windows 10/11, Linux o macOS.
- Python 3.10 o versión superior (en Windows, asegúrate de activar la casilla "Add Python to PATH" durante la instalación).
- Microsoft Word (para la edición y aplicación de citas en formato docx).

## Documentación complementaria

- [`docs/checklist-antes-de-entregar.md`](docs/checklist-antes-de-entregar.md): Verificación final antes de enviar el documento a evaluación.
- [`docs/citas-y-bibliografia.md`](docs/citas-y-bibliografia.md): Guía de buenas prácticas y formato APA en Word.
- [`docs/uso-de-ia.md`](docs/uso-de-ia.md): Pautas sobre detección y redacción académica asistida.
- [`docs/integraciones.md`](docs/integraciones.md): Detalles técnicos sobre los módulos de análisis.

# Citas y bibliografía

Dos herramientas gratuitas de Plagiarism Checker X (licencia MIT). **Ninguna detecta plagio**: revisan que cada cita tenga su referencia y viceversa, y ayudan a armar la bibliografía en APA 7.

## Plagx Draft Preflight (complemento de Word)

Repo: <https://github.com/plagiarismcheckerx/plagx-preflight-word>

### Instalar

En Word: **Inicio → Complementos**, buscá **Plagx Draft Preflight** e instalalo. Funciona en Word para Windows, Mac, web y iPad.

### Antes de usarlo

- El título **Referencias** tiene que tener estilo **Título 1** (o cualquier Título 1–6).
- Cada referencia en su propio párrafo.

### Usar

1. **Inicio → Check draft**.
2. Elegí **Whole document**, estilo **APA** y **Check draft**.
3. Hacé clic en cada aviso para ir al lugar del documento.

### Qué mirar

- **Citas sin entrada en la lista de referencias**: falta agregar la fuente a Referencias o el autor/año está mal escrito.
- **Referencias que nunca se citan**: o la citás en el texto o la sacás. APA no admite referencias "de relleno".
- Comillas o paréntesis sin cerrar y espacios dobles.

La parte de gramática está pensada para inglés; en una tesis en español conviene ignorar esos avisos.

Privacidad: el texto se revisa dentro de Word y no se envía a ningún servidor.

## Plagx Cite + Preflight MCP (para Claude u otros asistentes)

Repo: <https://github.com/plagiarismcheckerx/plagx-mcp> · Requiere [Node.js](https://nodejs.org/) 18+.

### Instalar

- **Claude Desktop**: descargá `plagx-mcp.mcpb` de la [última versión](https://github.com/plagiarismcheckerx/plagx-mcp/releases/latest) y abrilo, o agregá a `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "plagx": { "command": "npx", "args": ["-y", "plagx-mcp"] }
  }
}
```

- **Claude Code**: `claude mcp add plagx -- npx -y plagx-mcp`

### Qué le podés pedir

- "Revisá este capítulo: ¿hay citas sin referencia o referencias sin citar? APA."
- "Convertí estos DOI en referencias APA 7."
- "¿Hay referencias duplicadas en esta lista?"
- "Dame la cita narrativa de este libro, página 42."

Corre en tu computadora; solo las consultas de DOI salen a internet (Crossref).

## Ojo con Word

Si usás el administrador de fuentes de Word (**Referencias → Insertar cita**), las citas son campos automáticos. Ambas herramientas leen el texto visible, así que las detectan igual. Lo que no hacen es arreglar los campos: si una cita aparece mal, corregila desde la fuente en Word, no escribiendo encima.

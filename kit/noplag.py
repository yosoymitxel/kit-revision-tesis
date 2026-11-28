"""Integración opcional con Noplag Engine para una segunda pasada de similitud.

No reemplaza copy-spotter. Indexa el conjunto de fuentes activo y envía
directamente el DOCX a la API local de Noplag; los reportes se guardan aparte.
"""
import argparse
import hashlib
import html
import json
import mimetypes
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from . import web
from .revisar import buscar_tesis, carpeta_fuentes, obtener_slug

RAIZ = Path(__file__).resolve().parent.parent
FUENTES_DIR = RAIZ / "2-FUENTES"
RESULTADOS_DIR = RAIZ / "3-RESULTADOS"
COMPOSE_FILE = RAIZ / "compose.noplag.yml"
API_BASE = os.environ.get("NOPLAG_API_URL", "http://127.0.0.1:8010").rstrip("/")
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_CORPUS_TEXT_BYTES = 400 * 1024
SUPPORTED = {".pdf", ".docx", ".txt"}


class NoplagError(RuntimeError):
    """Error esperado de configuración, comunicación o procesamiento."""


def _api(method, path, *, timeout=60, **kwargs):
    try:
        response = requests.request(method, API_BASE + path, timeout=timeout, **kwargs)
    except requests.RequestException as exc:
        raise NoplagError(f"No se pudo conectar con Noplag ({API_BASE}): {exc}") from exc

    if not response.ok:
        try:
            payload = response.json()
            detail = payload.get("detail") or payload.get("message") or payload
        except ValueError:
            detail = response.text[:500]
        raise NoplagError(f"Noplag respondió HTTP {response.status_code}: {detail}")

    if response.status_code == 204 or not response.content:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise NoplagError("Noplag devolvió una respuesta que no es JSON.") from exc


def _health():
    try:
        response = requests.get(API_BASE + "/health", timeout=3)
        return response.ok
    except requests.RequestException:
        return False


def _iniciar_motor():
    if _health():
        print(f"Motor Noplag disponible en {API_BASE}.", flush=True)
        return

    if not COMPOSE_FILE.exists():
        raise NoplagError("No se encuentra compose.noplag.yml en la raíz del kit.")

    print("[PROGRESO: 5%] Iniciando Noplag Engine con Docker Compose...", flush=True)
    command = ["docker", "compose", "-f", str(COMPOSE_FILE), "up", "-d"]
    try:
        process = subprocess.Popen(
            command,
            cwd=str(RAIZ),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise NoplagError("No se encontró Docker. Instala Docker Engine/Desktop con el complemento Docker Compose.") from exc

    for line in iter(process.stdout.readline, ""):
        print("  " + line.rstrip(), flush=True)
    process.stdout.close()
    code = process.wait()
    if code != 0:
        raise NoplagError(
            "Docker Compose no pudo iniciar Noplag. Revisa que Docker esté ejecutándose "
            "y que el puerto 8010 esté libre. Si lo cambias en compose.noplag.yml, "
            "define también NOPLAG_API_URL con el mismo puerto."
        )

    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        if _health():
            print("[PROGRESO: 12%] Noplag está listo.", flush=True)
            return
        time.sleep(2)
    raise NoplagError("Noplag no respondió en 6 minutos. Revisa: docker compose -f compose.noplag.yml logs engine")


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _fmt_mb(size_bytes: int) -> str:
    return f"{size_bytes / (1024 * 1024):.2f} MiB"


def _reducir_docx(src: Path, dst: Path) -> bool:
    """Crea una copia temporal del DOCX sin archivos multimedia ni incrustados."""
    try:
        with zipfile.ZipFile(src, "r") as zin, zipfile.ZipFile(
            dst, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6
        ) as zout:
            for item in zin.infolist():
                if item.filename.startswith(("word/media/", "word/embeddings/")):
                    continue
                zout.writestr(item, zin.read(item.filename))
        return dst.exists() and dst.stat().st_size <= MAX_FILE_BYTES
    except (OSError, zipfile.BadZipFile):
        return False


def _extraer_txt_docx(src: Path, dst: Path) -> bool:
    """Extrae texto plano de word/document.xml como último recurso para DOCX > 10 MiB."""
    try:
        with zipfile.ZipFile(src, "r") as zin:
            if "word/document.xml" not in zin.namelist():
                return False
            root = ET.fromstring(zin.read("word/document.xml"))
        ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
        lines = []
        for para in root.iter(f"{ns}p"):
            text = "".join(node.text or "" for node in para.iter(f"{ns}t"))
            if text.strip():
                lines.append(text)
        content = "\n".join(lines).strip()
        if not content:
            return False
        dst.write_text(content, encoding="utf-8")
        return dst.stat().st_size <= MAX_FILE_BYTES
    except (OSError, zipfile.BadZipFile, ET.ParseError):
        return False


def _extraer_txt_pdf(src: Path, dst: Path) -> tuple[bool, str | None]:
    """Extrae la capa de texto de un PDF > 10 MiB usando pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text

        text = (extract_text(str(src)) or "").strip()
    except Exception as exc:
        return False, f"no se pudo extraer texto del PDF ({exc})"

    if not text:
        return False, "PDF escaneado sin capa de texto extraíble"

    dst.write_text(text, encoding="utf-8")
    if dst.stat().st_size > MAX_FILE_BYTES:
        return False, f"incluso solo el texto supera 10 MiB ({_fmt_mb(dst.stat().st_size)})"
    return True, None


def _dividir_txt(path: Path, tmp_dir: Path, safe_stem: str, max_bytes: int = MAX_CORPUS_TEXT_BYTES) -> list[Path]:
    """Divide un archivo de texto extenso en partes <= max_bytes para evitar bloqueos en Noplag."""
    if path.stat().st_size <= max_bytes:
        return [path]
    text = path.read_text(encoding="utf-8", errors="replace")
    parts: list[Path] = []
    chunk: list[str] = []
    chunk_bytes = 0
    for line in text.splitlines(keepends=True):
        line_bytes = len(line.encode("utf-8"))
        if chunk and chunk_bytes + line_bytes > max_bytes:
            part_path = tmp_dir / f"{safe_stem}_p{len(parts) + 1}.txt"
            part_path.write_text("".join(chunk), encoding="utf-8")
            parts.append(part_path)
            chunk = []
            chunk_bytes = 0
        if line_bytes > max_bytes:
            encoded = line.encode("utf-8")
            for start in range(0, len(encoded), max_bytes):
                part_path = tmp_dir / f"{safe_stem}_p{len(parts) + 1}.txt"
                part_path.write_bytes(encoded[start : start + max_bytes])
                parts.append(part_path)
        else:
            chunk.append(line)
            chunk_bytes += line_bytes
    if chunk:
        part_path = tmp_dir / f"{safe_stem}_p{len(parts) + 1}.txt"
        part_path.write_text("".join(chunk), encoding="utf-8")
        parts.append(part_path)
    return parts


def _preparar_archivo_noplag(path: Path, tmp_dir: Path, etiqueta: str) -> tuple[Path, str, str | None]:
    """Reduce temporalmente archivos > 10 MiB para Noplag sin tocar el original."""
    orig_size = path.stat().st_size
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if orig_size <= MAX_FILE_BYTES:
        return path, mime, None

    ext = path.suffix.lower()
    safe_stem = f"{abs(hash(etiqueta))}_{path.stem[:40]}"

    if ext == ".docx":
        dst_docx = tmp_dir / f"{safe_stem}.docx"
        if _reducir_docx(path, dst_docx):
            print(
                f"  Optimizado para Noplag (sin imágenes): {etiqueta} "
                f"({_fmt_mb(orig_size)} -> {_fmt_mb(dst_docx.stat().st_size)})",
                flush=True,
            )
            return dst_docx, "application/vnd.openxmlformats-officedocument.wordprocessingml.document", None

        dst_txt = tmp_dir / f"{safe_stem}.txt"
        if _extraer_txt_docx(path, dst_txt):
            print(
                f"  Optimizado a texto plano para Noplag: {etiqueta} "
                f"({_fmt_mb(orig_size)} -> {_fmt_mb(dst_txt.stat().st_size)})",
                flush=True,
            )
            return dst_txt, "text/plain", None

        return (
            path,
            mime,
            f"supera 10 MiB ({_fmt_mb(orig_size)}) incluso tras quitar imágenes y extraer texto. "
            "Opciones: divide el documento en partes/capítulos o quita anexos pesados.",
        )

    if ext == ".pdf":
        dst_txt = tmp_dir / f"{safe_stem}.txt"
        ok, motivo = _extraer_txt_pdf(path, dst_txt)
        if ok:
            print(
                f"  Optimizado a texto plano para Noplag: {etiqueta} "
                f"({_fmt_mb(orig_size)} -> {_fmt_mb(dst_txt.stat().st_size)})",
                flush=True,
            )
            return dst_txt, "text/plain", None

        return (
            path,
            mime,
            f"supera 10 MiB ({_fmt_mb(orig_size)}) y no pudo reducirse ({motivo}). "
            "Opciones: comprime el PDF (p. ej. Ghostscript/iLovePDF), aplica OCR si es escaneado o divídelo en partes.",
        )

    return (
        path,
        mime,
        f"supera 10 MiB ({_fmt_mb(orig_size)}). Opción: divide el archivo de texto en partes menores a 10 MiB.",
    )


def _collect_sources(folder: Path, solo_raiz: bool):
    if solo_raiz:
        candidates = [p for p in folder.glob("*") if p.is_file()]
        web_folder = folder / "web"
        if web_folder.is_dir():
            candidates.extend(p for p in web_folder.rglob("*") if p.is_file())
    else:
        candidates = [p for p in folder.rglob("*") if p.is_file()]

    candidates = [
        p for p in candidates
        if p.suffix.lower() in SUPPORTED | {".odt"}
        and not p.name.startswith("~$")
        and p.name.upper() != "LEEME.TXT"
    ]
    supported = sorted((p for p in candidates if p.suffix.lower() in SUPPORTED), key=lambda p: str(p).lower())
    unsupported = [p for p in candidates if p.suffix.lower() == ".odt"]
    return supported, unsupported


def _list_corpus():
    documents = []
    offset = 0
    while True:
        page = _api("GET", f"/v1/corpus/documents?limit=100&offset={offset}")
        batch = page.get("documents", [])
        documents.extend(batch)
        offset += len(batch)
        if not batch or offset >= int(page.get("total", 0)):
            break
    return documents


def _save_manifest(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def _corpus_metadata(document_id: str, timeout: int = 120):
    # The detail endpoint also returns extracted_text. Use the paginated list
    # endpoint so polling does not download the full source body repeatedly.
    offset = 0
    while True:
        page = _api("GET", f"/v1/corpus/documents?limit=100&offset={offset}", timeout=timeout)
        batch = page.get("documents", [])
        for item in batch:
            if str(item.get("id")) == str(document_id):
                return item
        offset += len(batch)
        if not batch or offset >= int(page.get("total", 0)):
            return None


def _wait_document(document_id: str, timeout=900):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            metadata = _corpus_metadata(document_id, timeout=180)
        except NoplagError as exc:
            if "timed out" in str(exc).lower() and time.monotonic() < deadline:
                time.sleep(3)
                continue
            raise
        if metadata is None:
            raise NoplagError(f"Noplag no encuentra la fuente recién cargada ({document_id}).")
        state = metadata.get("fingerprint_status")
        if state == "fingerprinted":
            return True
        if state == "failed":
            return False
        time.sleep(2.5)
    raise NoplagError(f"Se agotó el tiempo de indexación de una fuente ({document_id}).")


def _index_sources(folder: Path, solo_raiz: bool, label: str):
    sources, unsupported = _collect_sources(folder, solo_raiz)
    if unsupported:
        print(f"  Aviso: {len(unsupported)} archivo(s) ODT se omiten en Noplag; siguen disponibles en el análisis habitual.", flush=True)
    if not sources:
        raise NoplagError(
            "No hay fuentes PDF, DOCX o TXT compatibles en el conjunto seleccionado. "
            "Agrega fuentes en 2-FUENTES y vuelve a ejecutar."
        )

    manifest_path = RESULTADOS_DIR / ".noplag-corpus.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        manifest = {"documents": {}}

    old_records = manifest.get("documents", {})
    with tempfile.TemporaryDirectory(prefix="noplag_corpus_") as tmp_name:
        tmp_dir = Path(tmp_name)
        current = []
        omitidos_peso = []
        for path in sources:
            relative = str(path.relative_to(folder)).replace("\\", "/")
            upload_path, mime, err = _preparar_archivo_noplag(path, tmp_dir, relative)
            if err:
                print(f"  ERROR/OMITIDO (>10 MiB): {relative} — {err}", flush=True)
                omitidos_peso.append(f"{relative}: {err}")
                continue
            if mime == "text/plain" and upload_path.stat().st_size > MAX_CORPUS_TEXT_BYTES:
                safe_stem = f"{abs(hash(relative))}_{path.stem[:32]}"
                parts = _dividir_txt(upload_path, tmp_dir, safe_stem)
                print(
                    f"  Dividido para indexación ágil en Noplag: {relative} ({len(parts)} partes)",
                    flush=True,
                )
                for idx_part, part_path in enumerate(parts, 1):
                    part_rel = f"{relative} [parte {idx_part}/{len(parts)}]"
                    current.append({
                        "path": part_path,
                        "upload_name": f"{relative}.part{idx_part}.txt",
                        "mime": mime,
                        "relative": part_rel,
                        "sha256": _hash(part_path),
                    })
                continue
            upload_name = relative if upload_path == path else f"{relative}{upload_path.suffix}"
            current.append({
                "path": upload_path,
                "upload_name": upload_name,
                "mime": mime,
                "relative": relative,
                "sha256": _hash(upload_path),
            })

        if not current and omitidos_peso:
            raise NoplagError(
                "Ninguna fuente pudo prepararse bajo el límite de 10 MiB de Noplag:\n- "
                + "\n- ".join(omitidos_peso)
            )

        current_hashes = {item["sha256"] for item in current}

        # Remove only files previously managed by this integration that no longer
        # belong to the currently selected set. Manually uploaded corpus items stay.
        stale_ids = {
            str(item.get("id"))
            for item in old_records.values()
            if item.get("id") and item.get("sha256") not in current_hashes
        }
        for document_id in sorted(stale_ids):
            try:
                _api("DELETE", f"/v1/corpus/documents/{document_id}")
                print(f"  Fuente retirada del índice: {document_id}", flush=True)
            except NoplagError as exc:
                print(f"  Aviso al retirar fuente antigua: {exc}", flush=True)

        remote = _list_corpus()
        by_hash = {item.get("sha256"): item for item in remote if item.get("sha256")}
        next_manifest = {"scope": label, "documents": {}}
        total = len(current)
        ready_count = 0
        for index, item in enumerate(current, 1):
            digest = item["sha256"]
            relative = item["relative"]
            metadata = by_hash.get(digest)

            if metadata is None:
                upload_path = item["path"]
                print(f"  [{index}/{total}] Indexando: {relative}", flush=True)
                try:
                    with upload_path.open("rb") as stream:
                        metadata = _api(
                            "POST",
                            "/v1/corpus/documents",
                            timeout=180,
                            files={"file": (item["upload_name"], stream, item["mime"])},
                        )
                    by_hash[digest] = metadata
                except NoplagError as exc:
                    msg = str(exc)
                    if "HTTP 422" in msg or "no extractable text" in msg.lower():
                        print(
                            f"    Aviso: {relative} no tiene texto extraíble (PDF escaneado o corrupto); "
                            "se omite en Noplag. Opción: aplicar OCR al PDF.",
                            flush=True,
                        )
                    else:
                        print(f"    Aviso: Noplag no pudo indexar {relative} ({msg}); se omite.", flush=True)
                    continue
            else:
                print(f"  [{index}/{total}] Ya indexada: {relative}", flush=True)

            document_id = str(metadata["id"])
            state = metadata.get("fingerprint_status", "pending")
            if state == "pending":
                print(f"    Esperando indexación de {relative}...", flush=True)
                ready = _wait_document(document_id)
            else:
                ready = state == "fingerprinted"

            next_manifest["documents"][relative] = {"sha256": digest, "id": document_id}
            _save_manifest(manifest_path, next_manifest)

            if ready:
                ready_count += 1
            else:
                print(f"    Aviso: Noplag no pudo indexar {relative}; se conserva en el kit.", flush=True)

        if omitidos_peso:
            print(
                f"  Aviso: {len(omitidos_peso)} fuente(s) superaron 10 MiB tras intentar optimizarlas y fueron omitidas en Noplag.",
                flush=True,
            )

        if ready_count == 0:
            raise NoplagError("Ninguna fuente del conjunto pudo indexarse correctamente en Noplag.")

    _save_manifest(manifest_path, next_manifest)
    print(f"[PROGRESO: 48%] Fuentes listas para comparar: {ready_count}/{len(next_manifest['documents'])}.", flush=True)
    return ready_count


def _render_html(data: dict) -> str:
    esc = html.escape
    pct = float(data.get("similarity_pct") or 0)
    coverage = data.get("coverage", "unknown")
    coverage_label = "Cobertura parcial" if coverage == "partial" else "Cobertura completa"
    warning = (
        "<div class='warning'>El motor alcanzó su límite de tiempo. Se muestran las coincidencias encontradas, pero el análisis no cubrió todos los fragmentos.</div>"
        if coverage == "partial" else ""
    )

    blocks = []
    for source in data.get("sources", []):
        passages = []
        for passage in source.get("passages", []):
            query = esc(passage.get("query_excerpt") or "Fragmento no disponible")
            original = esc(passage.get("source_excerpt") or "Fragmento de fuente no disponible")
            start = passage.get("query_start", 0)
            end = passage.get("query_end", 0)
            passages.append(
                "<div class='passage'>"
                f"<div class='meta'>Tesis · caracteres {start}–{end}</div>"
                f"<blockquote>{query}</blockquote>"
                "<div class='meta'>Fuente</div>"
                f"<blockquote>{original}</blockquote>"
                "</div>"
            )
        source_name = esc(source.get("filename") or "Fuente sin nombre")
        source_url = source.get("source_url")
        source_link = (
            f"<a href='{esc(source_url)}' target='_blank' rel='noopener'>Abrir fuente</a>"
            if source_url and str(source_url).startswith(("https://", "http://")) else ""
        )
        blocks.append(
            "<section class='source'>"
            "<div class='source-head'>"
            f"<h2>{source_name}</h2>"
            f"<strong>{float(source.get('similarity_pct') or 0):.2f}%</strong>"
            "</div>"
            f"<div class='meta'>{int(source.get('matched_chars') or 0):,} caracteres coincidentes · {len(passages)} fragmentos · {source_link}</div>"
            + ("".join(passages) if passages else "<p>La fuente se recuperó, pero no hay fragmentos detallados en el reporte.</p>")
            + "</section>"
        )

    if not blocks:
        blocks.append("<p>No se encontraron coincidencias en las fuentes indexadas.</p>")

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparación adicional · Noplag</title>
<style>
:root{{color-scheme:light;--ink:#20242b;--muted:#667085;--line:#e4e7ec;--surface:#fff;--warning:#9a6700}}
*{{box-sizing:border-box}}body{{margin:0;background:#f6f7f9;color:var(--ink);font:15px/1.55 system-ui,sans-serif}}
main{{max-width:1000px;margin:0 auto;padding:32px 20px}}header,.source{{background:var(--surface);border:1px solid var(--line);border-radius:12px;padding:20px;margin-bottom:16px}}
h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:16px;margin:0}}.muted,.meta{{color:var(--muted);font-size:12px}}
.stats{{display:flex;gap:22px;flex-wrap:wrap;margin-top:18px}}.stat b{{display:block;font-size:23px}}
.source-head{{display:flex;justify-content:space-between;gap:12px;align-items:center}}.source-head strong{{white-space:nowrap}}
.passage{{border-top:1px solid var(--line);margin-top:16px;padding-top:12px}}
blockquote{{margin:6px 0 12px;padding:10px 12px;background:#f8fafc;border-left:3px solid #98a2b3;border-radius:4px;white-space:pre-wrap;overflow-wrap:anywhere}}
.warning{{padding:12px;background:#fff4d6;border:1px solid #f3d58a;border-radius:8px;margin-top:14px;color:var(--warning)}}
a{{color:#175cd3}}.back{{display:inline-block;margin-top:12px}}
</style>
</head>
<body><main>
<header>
<h1>Comparación adicional · Noplag Engine</h1>
<div class="muted">{esc(data.get("tesis") or "")} · {esc(data.get("fecha") or "")} · Idioma: español</div>
<div class="stats">
<div class="stat"><b>{pct:.2f}%</b><span class="muted">Similitud global</span></div>
<div class="stat"><b>{int(data.get("word_count") or 0):,}</b><span class="muted">Palabras revisadas</span></div>
<div class="stat"><b>{int(data.get("total_matched_chars") or 0):,}</b><span class="muted">Caracteres coincidentes</span></div>
<div class="stat"><b>{len(data.get("sources", []))}</b><span class="muted">Fuentes coincidentes</span></div>
<div class="stat"><b>{esc(coverage_label)}</b><span class="muted">Estado de cobertura</span></div>
</div>
{warning}
<a class="back" href="../panel.html">Volver al panel del kit</a>
</header>
{"".join(blocks)}
</main></body></html>"""


def _run_check(tesis: Path, res_dir: Path, fuentes_label: str, total_fuentes: int):
    with tempfile.TemporaryDirectory(prefix="noplag_tesis_") as tmp_name:
        tmp_dir = Path(tmp_name)
        upload_path, mime, err = _preparar_archivo_noplag(tesis, tmp_dir, tesis.name)
        if err:
            raise NoplagError(
                f"La tesis {err} La revisión habitual del kit no tiene este límite de 10 MiB."
            )

        upload_name = tesis.name if upload_path == tesis else f"{tesis.stem}{upload_path.suffix}"
        print("[PROGRESO: 55%] Enviando la tesis optimizada a Noplag (español)...", flush=True)
        try:
            with upload_path.open("rb") as stream:
                created = _api(
                    "POST",
                    "/v1/checks/upload",
                    timeout=180,
                    data={"language": "es"},
                    files={"file": (upload_name, stream, mime)},
                )
        except NoplagError as exc:
            if "422" not in str(exc) and "corrupt" not in str(exc).lower():
                raise
            # The stripped DOCX has broken internal refs; extract plain text instead.
            print(
                "  El DOCX optimizado fue rechazado; reenviando como texto plano...",
                flush=True,
            )
            safe_stem = f"{abs(hash(tesis.name))}_{tesis.stem[:40]}"
            txt_path = tmp_dir / f"{safe_stem}_check.txt"
            if not _extraer_txt_docx(tesis, txt_path):
                raise NoplagError(
                    "No se pudo extraer texto de la tesis para Noplag. "
                    "La revisión habitual del kit no tiene este límite."
                ) from exc
            upload_name = f"{tesis.stem}.txt"
            with txt_path.open("rb") as stream:
                created = _api(
                    "POST",
                    "/v1/checks/upload",
                    timeout=180,
                    data={"language": "es"},
                    files={"file": (upload_name, stream, "text/plain")},
                )

    check_id = created.get("check_id")
    if not check_id:
        raise NoplagError("Noplag no devolvió el identificador de revisión.")

    print(f"  Revisión creada: {check_id}", flush=True)
    stage_progress = {
        "pending": 58,
        "chunking": 62,
        "fingerprinting": 68,
        "retrieving": 76,
        "aligning": 88,
        "assembling": 96,
    }
    deadline = time.monotonic() + 7200
    last_stage = None
    while time.monotonic() < deadline:
        try:
            status = _api("GET", f"/v1/checks/{check_id}", timeout=180)
        except NoplagError as exc:
            if "timed out" in str(exc).lower() and time.monotonic() < deadline:
                time.sleep(3)
                continue
            raise
        state = status.get("status")
        stage = status.get("stage") or state
        if stage != last_stage:
            print(f"[PROGRESO: {stage_progress.get(stage, 70)}%] Noplag: {stage}.", flush=True)
            last_stage = stage
        if state == "complete":
            break
        if state == "failed":
            raise NoplagError(status.get("error_message") or "Noplag no pudo completar la comparación.")
        time.sleep(2)
    else:
        raise NoplagError("La comparación superó el límite de espera de dos horas. El motor puede seguir procesándola.")

    report = _api("GET", f"/v1/checks/{check_id}/report", timeout=180)
    query_text = report.get("query_text") or ""
    sources = []
    for source in report.get("sources", []):
        passages = []
        for passage in source.get("passages", []):
            start = int(passage.get("query_start") or 0)
            end = int(passage.get("query_end") or start)
            passages.append({
                "query_start": start,
                "query_end": end,
                "query_excerpt": query_text[start:end][:1200] if query_text else "",
                "source_excerpt": passage.get("overlap_text_preview") or "",
            })
        sources.append({
            "filename": source.get("source_filename") or "Fuente sin nombre",
            "source_url": source.get("source_url"),
            "similarity_pct": float(source.get("similarity_pct") or 0),
            "matched_chars": int(source.get("matched_chars") or 0),
            "passages": passages,
        })

    result = {
        "engine": "Noplag Engine",
        "check_id": str(check_id),
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tesis": tesis.name,
        "tesis_sha256": _hash(tesis),
        "fuentes_usadas": fuentes_label,
        "fuentes_indexadas": total_fuentes,
        "language": "es",
        "word_count": int(report.get("word_count") or 0),
        "similarity_pct": float(report.get("overall_similarity_pct") or 0),
        "total_matched_chars": int(report.get("total_matched_chars") or 0),
        "coverage": report.get("coverage") or "unknown",
        "coverage_reason": report.get("coverage_reason"),
        "checked_chunks": int(report.get("checked_chunks") or 0),
        "total_chunks": int(report.get("total_chunks") or 0),
        "sources": sources,
    }

    res_dir.mkdir(parents=True, exist_ok=True)
    json_path = res_dir / "noplag.json"
    html_path = res_dir / "noplag.html"
    temporary = json_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(json_path)
    html_path.write_text(_render_html(result), encoding="utf-8")
    summary = {
        "fecha": result["fecha"],
        "similarity_pct": result["similarity_pct"],
        "sources_count": len(result["sources"]),
        "passages_count": sum(len(source.get("passages", [])) for source in result["sources"]),
        "word_count": result["word_count"],
        "coverage": result["coverage"],
        "fuentes_usadas": result["fuentes_usadas"],
    }
    summary_path = res_dir / "noplag-resumen.json"
    summary_tmp = summary_path.with_suffix(".json.tmp")
    summary_tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_tmp.replace(summary_path)
    print("[PROGRESO: 98%] Reporte Noplag guardado sin modificar los resultados anteriores.", flush=True)
    print(f"  Reporte: {html_path.relative_to(RAIZ)}", flush=True)
    return result


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

    parser = argparse.ArgumentParser(description="Comparación adicional de tesis con Noplag Engine")
    parser.add_argument("--tesis", type=str, default=None)
    parser.add_argument("--fuentes", type=str, default=None)
    args = parser.parse_args()

    tesis = buscar_tesis(args.tesis)
    if not tesis:
        print("No se encontró un DOCX en 1-MI-TESIS.", flush=True)
        return 1

    folder, solo_raiz, label = carpeta_fuentes(tesis, args.fuentes)
    slug = obtener_slug(tesis)
    result_dir = RESULTADOS_DIR / slug

    try:
        _iniciar_motor()
        print("[PROGRESO: 18%] Descargando o reutilizando fuentes web de la bibliografía...", flush=True)
        try:
            web_results = web.descargar(tesis, folder / "web", actualizar=False)
            ok_web = sum(1 for item in web_results if item.get("estado") == "OK")
            print(f"  Fuentes web verificadas: {ok_web}/{len(web_results)}.", flush=True)
        except Exception as exc:
            print(f"  Aviso: no se pudieron actualizar las fuentes web: {exc}", flush=True)

        print("[PROGRESO: 28%] Preparando corpus de fuentes...", flush=True)
        total = _index_sources(folder, solo_raiz, label)
        result = _run_check(tesis, result_dir, label, total)
        print(
            f"[PROGRESO: 100%] Comparación adicional completada: "
            f"{result['similarity_pct']:.2f}% · {len(result['sources'])} fuentes coincidentes.",
            flush=True,
        )
        return 0
    except NoplagError as exc:
        print(f"ERROR NOPLAG: {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())

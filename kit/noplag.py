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
import re
import secrets
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from . import busqueda_web, web
from .revisar import buscar_tesis, carpeta_fuentes, obtener_slug

RAIZ = Path(__file__).resolve().parent.parent
FUENTES_DIR = RAIZ / "2-FUENTES"
RESULTADOS_DIR = RAIZ / "3-RESULTADOS"
COMPOSE_FILE = RAIZ / "compose.noplag.yml"
ENV_FILE = RAIZ / ".env"
SEARXNG_ENV_FILE = RAIZ / ".env.searxng"
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


def _asegurar_env_local():
    """Crea .env una sola vez y carga variables sin imprimir secretos."""
    template = RAIZ / ".env.example"
    if ENV_FILE.exists():
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    elif template.exists():
        lines = template.read_text(encoding="utf-8").splitlines()
    else:
        lines = []

    values = {}
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    secret = values.get("SEARXNG_SECRET", "")
    if not secret or secret == "GENERATED_ON_FIRST_RUN":
        secret = os.getenv("SEARXNG_SECRET") or secrets.token_hex(32)

    def set_value(key, value):
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=")
        for index, line in enumerate(lines):
            if pattern.match(line):
                lines[index] = f"{key}={value}"
                return
        lines.append(f"{key}={value}")

    set_value("SEARXNG_SECRET", secret)
    defaults = {
        "BRAVE_SEARCH_API_KEY": "",
        "SEARXNG_URL": "http://127.0.0.1:8888",
        "SEARXNG_ENABLED": "true",
        "WEB_SEARCH_MAX_QUERIES": "120",
        "WEB_SEARCH_MAX_RESULTS": "160",
        "WEB_SEARCH_MAX_DOWNLOADS": "50",
        "WEB_SEARCH_MAX_PER_DOMAIN": "3",
        "SEARXNG_LANGUAGE": "all",
    }
    # Migra los valores por defecto antiguos; conserva otros valores personalizados.
    if values.get("WEB_SEARCH_MAX_QUERIES") == "20":
        set_value("WEB_SEARCH_MAX_QUERIES", "120")
    if values.get("WEB_SEARCH_MAX_RESULTS") == "80":
        set_value("WEB_SEARCH_MAX_RESULTS", "160")
    if values.get("WEB_SEARCH_MAX_DOWNLOADS") == "35":
        set_value("WEB_SEARCH_MAX_DOWNLOADS", "50")
    if values.get("SEARXNG_LANGUAGE") == "es":
        set_value("SEARXNG_LANGUAGE", "all")
    for key, value in defaults.items():
        if key not in values:
            set_value(key, value)
    ENV_FILE.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    SEARXNG_ENV_FILE.write_text(f"SEARXNG_SECRET={secret}\n", encoding="utf-8")
    try:
        if os.name != "nt":
            ENV_FILE.chmod(0o600)
            SEARXNG_ENV_FILE.chmod(0o600)
    except OSError:
        pass
    for line in lines:
        if line.strip() and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _health_url(url: str) -> bool:
    try:
        return requests.get(url, timeout=3).ok
    except requests.RequestException:
        return False


def _iniciar_motor():
    _asegurar_env_local()
    if not COMPOSE_FILE.exists():
        raise NoplagError("No se encuentra compose.noplag.yml en la raíz del kit.")
    # Compose siempre se ejecuta: Noplag puede estar activo y SearXNG apagado.
    print("[PROGRESO: 5%] Iniciando Noplag y SearXNG con Docker Compose...", flush=True)
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
        raise NoplagError("No se encontró Docker. Instala Docker Engine/Desktop con Docker Compose.") from exc
    for line in iter(process.stdout.readline, ""):
        print("  " + line.rstrip(), flush=True)
    process.stdout.close()
    if process.wait() != 0:
        raise NoplagError("Docker Compose no pudo iniciar los servicios. Revisa Docker y los puertos 8010/8888.")
    restart = subprocess.run(
        ["docker", "compose", "-f", str(COMPOSE_FILE), "restart", "searxng"],
        cwd=str(RAIZ),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if restart.returncode != 0:
        print("  Aviso: no se pudo reiniciar SearXNG para recargar settings.yml.", flush=True)

    deadline = time.monotonic() + 360
    while time.monotonic() < deadline:
        if _health_url(API_BASE + "/health"):
            print("[PROGRESO: 12%] Noplag está listo.", flush=True)
            break
        time.sleep(2)
    else:
        raise NoplagError("Noplag no respondió en 6 minutos. Revisa: docker compose -f compose.noplag.yml logs engine")

    searx_url = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888").rstrip("/")
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if _health_url(searx_url + "/"):
            print(f"[PROGRESO: 15%] SearXNG está listo en {searx_url}.", flush=True)
            return
        time.sleep(2)
    print("  Aviso: SearXNG no respondió; se intentará continuar con Brave Search si está configurado.", flush=True)


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


def _index_sources(
    folder: Path,
    solo_raiz: bool,
    label: str,
    extra_folders: list[Path] | None = None,
):
    sources, unsupported = _collect_sources(folder, solo_raiz)
    source_entries = [
        (path, str(path.relative_to(folder)).replace("\\", "/"))
        for path in sources
    ]
    for extra_folder in extra_folders or []:
        if not extra_folder.is_dir():
            continue
        external, _ = _collect_sources(extra_folder, False)
        source_entries.extend((path, f"Internet/{path.name}") for path in external)
    if unsupported:
        print(f"  Aviso: {len(unsupported)} archivo(s) ODT se omiten en Noplag; siguen disponibles en el análisis habitual.", flush=True)
    if not source_entries:
        raise NoplagError(
            "No hay fuentes PDF, DOCX o TXT compatibles. Agrega fuentes en 2-FUENTES "
            "o configura Brave Search/SearXNG para descubrir páginas externas."
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
        for path, relative in source_entries:
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
                        "upload_name": f"{path.name}.part{idx_part}.txt" if relative.startswith("Internet/") else f"{relative}.part{idx_part}.txt",
                        "mime": mime,
                        "relative": part_rel,
                        "sha256": _hash(part_path),
                    })
                continue
            upload_name = (path.name if relative.startswith("Internet/") else relative) if upload_path == path else f"{relative}{upload_path.suffix}"
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
                        razon = "PDF escaneado sin texto extraíble. Opción: aplicar OCR al PDF."
                        print(
                            f"    Aviso: {relative} no tiene texto extraíble (PDF escaneado o corrupto); "
                            "se omite en Noplag. Opción: aplicar OCR al PDF.",
                            flush=True,
                        )
                    else:
                        razon = msg
                        print(f"    Aviso: Noplag no pudo indexar {relative} ({msg}); se omite.", flush=True)
                    omitidos_peso.append(f"{relative}: {razon}")
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
    return ready_count, omitidos_peso


def _render_html(data: dict) -> str:
    esc = html.escape
    pct = float(data.get("similarity_pct") or 0)
    coverage = data.get("coverage", "unknown")
    coverage_label = {"partial": "Cobertura parcial", "complete": "Cobertura completa"}.get(coverage, "Cobertura no informada")
    sources = sorted(
        data.get("sources", []),
        key=lambda item: float(item.get("similarity_pct") or 0),
        reverse=True,
    )
    matched_total = sum(max(0, int(source.get("matched_chars") or 0)) for source in sources)
    weight_total = matched_total or sum(max(0.0, float(source.get("similarity_pct") or 0)) for source in sources)
    chart_colors = ["var(--accent)", "var(--ink)", "var(--chart-3)", "var(--chart-4)"]

    source_nav = []
    source_cards = []
    donut_segments = []
    donut_legend = []
    circumference = 2 * 3.141592653589793 * 43
    offset = 0.0

    for idx, source in enumerate(sources):
        name = esc(source.get("filename") or "Fuente sin nombre")
        similarity = float(source.get("similarity_pct") or 0)
        matched = max(0, int(source.get("matched_chars") or 0))
        passages = source.get("passages", [])
        source_url = source.get("source_url")
        source_link = (
            f'<a class="text-link" href="{esc(source_url)}" target="_blank" rel="noopener noreferrer">Abrir fuente original</a>'
            if source_url and str(source_url).startswith(("https://", "http://")) else ""
        )
        provider = esc(source.get("search_provider") or "")
        weight = matched if matched_total else similarity
        share = (weight / weight_total * 100) if weight_total else 0
        color = chart_colors[idx % len(chart_colors)]

        if weight_total and weight > 0:
            segment_length = circumference * weight / weight_total
            gap = min(2.4, segment_length * 0.08)
            dash = max(0.0, segment_length - gap)
            donut_segments.append(
                f'<a class="donut-segment" href="#source-{idx}" aria-label="{name}: {share:.1f}% de participación">'
                f'<circle cx="60" cy="60" r="43" fill="none" stroke="{color}" stroke-width="18" '
                f'stroke-dasharray="{dash:.2f} {circumference:.2f}" stroke-dashoffset="{-offset:.2f}" '
                f'transform="rotate(-90 60 60)"><title>{name}: {share:.1f}% de participación · {similarity:.2f}% similitud</title></circle></a>'
            )
            offset += segment_length

        source_nav.append(f'<a href="#source-{idx}"><span>{idx + 1:02d}</span>{name}</a>')
        donut_legend.append(
            f'<a class="legend-row" href="#source-{idx}">'
            f'<span class="legend-dot" style="--dot:{color}"></span>'
            f'<span class="legend-name">{name}</span>'
            f'<strong>{share:.1f}%</strong></a>'
        )

        passages_html = []
        for passage_idx, passage in enumerate(passages, 1):
            query = esc(passage.get("query_excerpt") or "Fragmento no disponible")
            original = esc(passage.get("source_excerpt") or "Fragmento de fuente no disponible")
            start = int(passage.get("query_start") or 0)
            end = int(passage.get("query_end") or start)
            passages_html.append(
                f'<article class="passage">'
                f'<div class="passage-kicker">Coincidencia {passage_idx} · caracteres {start:,}–{end:,}</div>'
                f'<div class="passage-grid">'
                f'<div><h4>Texto de la tesis</h4><blockquote>{query}</blockquote></div>'
                f'<div><h4>Texto de la fuente</h4><blockquote>{original}</blockquote></div>'
                f'</div></article>'
            )
        if not passages_html:
            passages_html.append('<p class="empty-state">La fuente fue recuperada, pero no hay fragmentos detallados en el reporte.</p>')

        source_cards.append(
            f'<section class="source-card" id="source-{idx}">'
            f'<div class="source-heading"><div><p class="eyebrow">Fuente {idx + 1:02d}</p><h3>{name}</h3></div>'
            f'<div class="source-score"><strong>{similarity:.2f}%</strong><span>similitud</span></div></div>'
            f'<div class="source-meta"><span>{matched:,} caracteres coincidentes</span><span>{len(passages)} fragmentos</span>'
            + (f'<span>{provider}</span>' if provider else "")
            + source_link + '</div>'
            + "".join(passages_html)
            + '</section>'
        )

    if not source_cards:
        source_cards.append('<div class="empty-state">No se encontraron coincidencias en las fuentes indexadas.</div>')

    donut_html = (
        '<div class="donut-layout"><svg class="donut-chart" viewBox="0 0 120 120" role="img" aria-label="Distribución interactiva de coincidencias por fuente">'
        + "".join(donut_segments)
        + '<circle cx="60" cy="60" r="29" fill="var(--surface)"/>'
        + f'<text x="60" y="57" class="donut-total" text-anchor="middle">{len(sources)}</text>'
        + '<text x="60" y="70" class="donut-caption" text-anchor="middle">fuentes</text>'
        + '</svg><div class="donut-legend">' + "".join(donut_legend) + '</div></div>'
        + ('<p class="chart-note">Los segmentos representan la participación de cada fuente en los caracteres coincidentes.</p>' if matched_total else '<p class="chart-note">No hay recuento de caracteres por fuente; se usa la similitud individual como proporción relativa.</p>')
    ) if sources else '<p class="empty-state">No hay fuentes coincidentes para distribuir.</p>'

    warning = ""
    if coverage == "partial":
        warning += (
            '<div class="notice notice-warning"><strong>Cobertura parcial.</strong> El motor no alcanzó a revisar todos los fragmentos. '
            'Las coincidencias encontradas son útiles, pero el resultado no representa una cobertura completa del documento.</div>'
        )
    omitidos = data.get("omitidos") or []
    if omitidos:
        items = "".join(f"<li>{esc(item)}</li>" for item in omitidos)
        warning += (
            f'<details class="notice notice-warning"><summary>{len(omitidos)} fuente(s) omitida(s)</summary>'
            '<p>Estas fuentes no pudieron procesarse para Noplag. Siguen disponibles en la revisión habitual del kit.</p>'
            f'<ul>{items}</ul></details>'
        )

    busqueda = data.get("busqueda_externa") or {}
    busqueda_html = ""
    if busqueda:
        providers = busqueda.get("proveedores") or {}
        provider_rows = ""
        for name, info in providers.items():
            details = (
                f'{int(info.get("consultas_ok") or 0)} consultas válidas · '
                f'{int(info.get("resultados") or 0)} resultados · '
                f'{int(info.get("consultas_fallback") or 0)} ampliadas'
            )
            diagnostics = (info.get("errores") or []) + (info.get("motores_sin_respuesta") or [])
            diagnostic_text = " | ".join(map(str, diagnostics[:3]))
            if diagnostic_text:
                details += " · " + diagnostic_text
            provider_rows += (
                f'<li><div><span>{esc(name)}</span><small>{esc(details)}</small></div>'
                f'<strong>{esc(info.get("estado", "sin estado"))}</strong></li>'
            )
        links = []
        for page in busqueda.get("paginas", [])[:50]:
            url = page.get("url") or ""
            if str(url).startswith(("https://", "http://")):
                links.append(
                    f'<li><a class="text-link" href="{esc(url)}" target="_blank" rel="noopener noreferrer">'
                    f'{esc(page.get("title") or url)}</a><span>{esc(", ".join(page.get("providers") or [page.get("provider", "Internet")]))}</span></li>'
                )
        busqueda_html = (
            '<section class="report-section" id="web-search"><div class="section-heading"><div><p class="eyebrow">Descubrimiento</p>'
            '<h2>Búsqueda externa en Internet</h2></div></div>'
            f'<div class="search-metrics"><div><strong>{int(busqueda.get("consultas_generadas") or 0)}</strong><span>consultas</span></div>'
            f'<div><strong>{int(busqueda.get("resultados_descubiertos") or 0)}</strong><span>URLs descubiertas</span></div>'
            f'<div><strong>{int(busqueda.get("paginas_descargadas") or 0)}</strong><span>páginas incorporadas</span></div></div>'
            + (f'<ul class="provider-list">{provider_rows}</ul>' if provider_rows else "")
            + ('<ul class="web-pages">' + "".join(links) + '</ul>' if links else '<p class="empty-state">No se descargaron páginas externas.</p>')
            + (f'<p class="chart-note">{esc(busqueda.get("limitacion") or "")}</p>' if busqueda.get("limitacion") else "")
            + '</section>'
        )

    thesis = esc(data.get("tesis") or "Documento")
    fecha = esc(data.get("fecha") or "")
    coverage_class = "partial" if coverage == "partial" else "complete"
    source_nav_html = "".join(source_nav[:12])
    web_nav_html = '<a href="#web-search"><span>03</span> Búsqueda externa</a>' if busqueda_html else ""
    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light dark">
<title>Comparación Noplag · {thesis}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600;700&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--ground:#f6f7f8;--surface:#fff;--raised:#f0f2f4;--line:#e2e5e8;--ink:#191c20;--muted:#606a75;--faint:#77818c;--accent:#1d5fbf;--accent-soft:#edf3fb;--chart-3:#7e8791;--chart-4:#c1c7ce;--warning:#8a5a00;--warning-bg:#fff7e6;--warning-line:#ead29b;--sidebar:236px;--radius:8px;--font:"Geist",Inter,system-ui,sans-serif;--mono:"Geist Mono",ui-monospace,monospace}}
:root[data-theme="dark"]{{--ground:#101318;--surface:#191e25;--raised:#222933;--line:#303945;--ink:#eef1f4;--muted:#aab3bd;--faint:#8d98a4;--accent:#79a9ec;--accent-soft:#1b2a40;--chart-3:#8793a1;--chart-4:#53606e;--warning:#edc36d;--warning-bg:#342b19;--warning-line:#68552e}}
@media(prefers-color-scheme:dark){{:root:not([data-theme="light"]){{--ground:#101318;--surface:#191e25;--raised:#222933;--line:#303945;--ink:#eef1f4;--muted:#aab3bd;--faint:#8d98a4;--accent:#79a9ec;--accent-soft:#1b2a40;--chart-3:#8793a1;--chart-4:#53606e;--warning:#edc36d;--warning-bg:#342b19;--warning-line:#68552e}}}}
*,*::before,*::after{{box-sizing:border-box}}
html{{scroll-behavior:smooth;scroll-padding-top:24px}}
body{{margin:0;background:var(--ground);color:var(--ink);font:14px/1.58 var(--font);-webkit-font-smoothing:antialiased}}
a{{color:inherit;text-decoration:none}}button{{font:inherit;color:inherit}}
.layout{{min-height:100vh;display:grid;grid-template-columns:var(--sidebar) minmax(0,1fr)}}
.sidebar{{position:sticky;top:0;height:100vh;overflow:auto;padding:22px 14px;background:var(--surface);border-right:1px solid var(--line);display:flex;flex-direction:column;gap:20px}}
.brand{{padding:4px 9px 18px;border-bottom:1px solid var(--line)}}
.brand strong{{display:block;font-size:14px;font-weight:650;letter-spacing:-.02em}}
.brand span{{display:block;margin-top:4px;color:var(--muted);font-size:12px;overflow-wrap:anywhere}}
.nav-label,.eyebrow{{font-size:10px;font-weight:650;letter-spacing:.09em;text-transform:uppercase;color:var(--faint)}}
.nav{{display:grid;gap:4px}}
.nav a{{display:flex;align-items:center;gap:9px;padding:9px 10px;border-radius:5px;color:var(--muted);font-size:13px;min-height:38px}}
.nav a:hover,.nav a:focus-visible{{background:var(--raised);color:var(--ink);outline:2px solid transparent}}
.nav a span{{font:11px var(--mono);color:var(--faint)}}
.sidebar-foot{{margin-top:auto;color:var(--faint);font-size:11px;line-height:1.5}}
.main{{width:100%;max-width:1280px;padding:34px clamp(18px,3.2vw,48px) 72px;margin:0 auto;min-width:0}}
.topbar{{display:flex;align-items:center;justify-content:space-between;gap:14px;margin-bottom:30px}}
.topbar h1{{font-size:clamp(22px,2.2vw,30px);line-height:1.18;letter-spacing:-.035em;font-weight:600;margin:0}}
.subtitle{{margin-top:7px;color:var(--muted);font-size:13px;overflow-wrap:anywhere}}
.actions{{display:flex;gap:8px;flex-shrink:0}}
.button{{border:1px solid var(--line);background:var(--surface);padding:8px 12px;border-radius:5px;min-height:36px;font-size:12px;cursor:pointer}}
.button:hover{{border-color:var(--accent);color:var(--accent)}}
.kpis{{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border:1px solid var(--line);background:var(--surface);border-radius:var(--radius);margin-bottom:28px}}
.kpi{{padding:18px 20px;min-width:0}}
.kpi+.kpi{{border-left:1px solid var(--line)}}
.kpi strong{{display:block;font:500 clamp(22px,2.4vw,30px)/1.1 var(--mono);letter-spacing:-.05em}}
.kpi span{{display:block;margin-top:7px;font-size:11px;color:var(--muted);line-height:1.4}}
.kpi.primary strong{{color:var(--accent)}}
.notice{{padding:12px 15px;border:1px solid var(--warning-line);background:var(--warning-bg);color:var(--warning);border-radius:6px;margin:0 0 18px;font-size:13px}}
.notice p{{margin:7px 0}}.notice ul{{margin:8px 0 0;padding-left:18px}}
.report-section{{margin-top:36px;scroll-margin-top:22px}}
.section-heading{{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:14px}}
.section-heading h2{{font-size:18px;font-weight:600;letter-spacing:-.02em;margin:3px 0 0}}
.section-heading p{{margin:0}}
.overview-grid{{display:grid;grid-template-columns:minmax(280px,.85fr) minmax(0,1.15fr);gap:14px}}
.panel,.source-card{{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:20px;min-width:0}}
.panel h3{{font-size:14px;font-weight:600;margin:0 0 15px}}
.donut-layout{{display:grid;grid-template-columns:136px minmax(0,1fr);align-items:center;gap:15px}}
.donut-chart{{display:block;width:100%;max-width:136px;height:auto;overflow:visible}}
.donut-segment{{cursor:pointer;outline:none}}
.donut-segment circle{{transition:stroke-width .16s ease,opacity .16s ease}}
.donut-segment:hover circle,.donut-segment:focus-visible circle{{stroke-width:22;opacity:.85}}
.donut-total{{font:600 17px var(--mono);fill:var(--ink)}}
.donut-caption{{font:10px var(--font);fill:var(--muted)}}
.donut-legend{{display:grid;gap:7px;min-width:0}}
.legend-row{{display:grid;grid-template-columns:9px minmax(0,1fr) auto;gap:8px;align-items:center;font-size:12px;min-width:0}}
.legend-row:hover .legend-name{{color:var(--accent);text-decoration:underline}}
.legend-dot{{width:8px;height:8px;border-radius:2px;background:var(--dot)}}
.legend-name{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted)}}
.legend-row strong{{font:11px var(--mono);font-weight:500}}
.chart-note{{margin:13px 0 0;color:var(--faint);font-size:11px;line-height:1.5}}
.source-list{{display:grid;gap:8px}}
.source-row{{display:grid;grid-template-columns:minmax(0,1fr) 64px;gap:8px 14px;align-items:center;padding:10px 0;border-bottom:1px solid var(--line)}}
.source-row:last-child{{border:0}}
.source-row a{{font-size:12px;overflow-wrap:anywhere}}
.source-row strong{{font:12px var(--mono);text-align:right}}
.source-track{{grid-column:1/-1;height:4px;background:var(--raised);border-radius:3px;overflow:hidden}}
.source-track span{{display:block;height:100%;background:var(--accent);border-radius:3px}}
.source-card{{margin-top:14px;scroll-margin-top:18px}}
.source-heading{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px}}
.source-heading h3{{font-size:15px;line-height:1.35;font-weight:600;overflow-wrap:anywhere;margin:4px 0 0}}
.source-score{{text-align:right;flex:none}}
.source-score strong{{display:block;font:500 23px/1 var(--mono);letter-spacing:-.04em}}
.source-score span{{display:block;margin-top:5px;color:var(--muted);font-size:10px}}
.source-meta{{display:flex;flex-wrap:wrap;gap:7px 16px;margin:12px 0 15px;color:var(--muted);font-size:11px}}
.text-link{{color:var(--accent);text-decoration:underline;text-underline-offset:2px}}
.passage{{border-top:1px solid var(--line);padding-top:14px;margin-top:14px}}
.passage-kicker{{color:var(--faint);font:10px var(--mono);margin-bottom:9px}}
.passage-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
.passage h4{{font-size:11px;font-weight:600;color:var(--muted);margin:0 0 6px}}
blockquote{{margin:0;padding:12px 14px;border-left:2px solid var(--accent);background:var(--raised);border-radius:0 5px 5px 0;white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px;line-height:1.65}}
.empty-state{{padding:14px;background:var(--raised);border-radius:5px;color:var(--muted);font-size:13px}}
.search-metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:14px 0}}
.search-metrics div{{padding:13px;background:var(--raised);border-radius:5px}}
.search-metrics strong{{display:block;font:500 20px var(--mono)}}
.search-metrics span{{display:block;margin-top:3px;color:var(--muted);font-size:11px}}
.provider-list,.web-pages{{list-style:none;padding:0;margin:12px 0;display:grid;gap:7px}}
.provider-list li,.web-pages li{{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-bottom:1px solid var(--line);font-size:12px}}
.provider-list strong,.web-pages span{{font-size:11px;color:var(--muted)}}.provider-list small{{display:block;margin-top:3px;color:var(--muted);font-size:10px;line-height:1.5;overflow-wrap:anywhere}}
.mobile-menu{{display:none}}
:focus-visible{{outline:2px solid var(--accent);outline-offset:3px}}
@media(max-width:1000px){{.layout{{grid-template-columns:196px minmax(0,1fr)}}.main{{padding-inline:22px}}.kpis{{grid-template-columns:repeat(2,minmax(0,1fr))}}.kpi:nth-child(3){{border-left:0;border-top:1px solid var(--line)}}.kpi:nth-child(4){{border-top:1px solid var(--line)}}}}
@media(max-width:760px){{.layout{{display:block}}.sidebar{{position:static;height:auto;padding:12px 16px;border-right:0;border-bottom:1px solid var(--line);gap:10px}}.brand{{padding:0 0 9px}}.nav{{display:flex;overflow-x:auto;padding-bottom:3px;gap:5px}}.nav a{{white-space:nowrap;flex:none;min-height:40px}}.sidebar-foot{{display:none}}.main{{padding:22px 16px 48px}}.topbar{{align-items:flex-start;flex-direction:column;margin-bottom:20px}}.actions{{width:100%}}.actions .button{{flex:1}}.overview-grid{{grid-template-columns:1fr}}.donut-layout{{grid-template-columns:120px minmax(0,1fr)}}.passage-grid{{grid-template-columns:1fr}}}}
@media(max-width:480px){{.kpi{{padding:14px}}.kpi strong{{font-size:22px}}.panel,.source-card{{padding:15px}}.donut-layout{{grid-template-columns:100px minmax(0,1fr);gap:10px}}.donut-chart{{max-width:100px}}.legend-row{{font-size:11px}}.source-heading h3{{font-size:14px}}.source-score strong{{font-size:19px}}.search-metrics{{gap:6px}}.search-metrics div{{padding:10px}}.search-metrics strong{{font-size:17px}}.source-row{{grid-template-columns:minmax(0,1fr) 54px}}}}
@media(prefers-reduced-motion:reduce){{*,*::before,*::after{{scroll-behavior:auto!important;transition:none!important}}}}
@media print{{.sidebar,.actions{{display:none!important}}.layout{{display:block}}.main{{max-width:none;padding:0}}.panel,.source-card{{break-inside:avoid}}}}
</style>
</head>
<body>
<div class="layout">
<aside class="sidebar" id="report-nav">
  <div class="brand"><strong>Kit Revisión · Noplag</strong><span>{thesis}</span></div>
  <p class="nav-label">Informe</p>
  <nav class="nav" aria-label="Secciones del informe">
    <a href="#overview"><span>01</span> Resumen</a>
    <a href="#sources"><span>02</span> Fuentes</a>
    {source_nav_html}
    {web_nav_html}
  </nav>
  <div class="sidebar-foot">Comparación complementaria.<br>Los resultados habituales del kit no se modifican.</div>
</aside>
<main class="main">
  <header class="topbar">
    <div><h1>Comparación adicional · Noplag Engine</h1><p class="subtitle">{thesis} · {fecha} · Idioma: español</p></div>
    <div class="actions"><button class="button" type="button" onclick="window.print()">Imprimir / PDF</button><button class="button" type="button" id="theme-toggle" aria-label="Cambiar tema">Cambiar tema</button><a class="button" href="../panel.html">Volver al diagnóstico</a></div>
  </header>
  {warning}
  <section class="kpis" id="overview" aria-label="Indicadores del análisis">
    <div class="kpi primary"><strong>{pct:.2f}%</strong><span>Similitud global</span></div>
    <div class="kpi"><strong>{int(data.get("word_count") or 0):,}</strong><span>Palabras revisadas</span></div>
    <div class="kpi"><strong>{int(data.get("total_matched_chars") or 0):,}</strong><span>Caracteres coincidentes</span></div>
    <div class="kpi"><strong>{len(sources)}</strong><span>Fuentes coincidentes · {esc(coverage_label)}</span></div>
  </section>
  <section class="report-section" id="sources">
    <div class="section-heading"><div><p class="eyebrow">Coincidencias</p><h2>Distribución por fuente</h2></div></div>
    <div class="overview-grid">
      <div class="panel"><h3>Participación de cada fuente</h3>{donut_html}</div>
      <div class="panel"><h3>Fuentes con mayor similitud</h3><div class="source-list">
        {"".join(f'<div class="source-row"><a href="#source-{idx}">{esc(source.get("filename") or "Fuente sin nombre")}</a><strong>{float(source.get("similarity_pct") or 0):.2f}%</strong><div class="source-track"><span style="width:{min(100,max(0,float(source.get("similarity_pct") or 0))):.2f}%"></span></div></div>' for idx, source in enumerate(sources[:8]))}
      </div></div>
    </div>
    {"".join(source_cards)}
  </section>
  {busqueda_html}
</main>
</div>
<script>
(function(){{
  var root=document.documentElement;
  var saved=null;
  try{{saved=localStorage.getItem("noplag-theme")}}catch(e){{}}
  if(saved==="light"||saved==="dark")root.setAttribute("data-theme",saved);
  else root.setAttribute("data-theme",window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light");
  var button=document.getElementById("theme-toggle");
  if(button)button.addEventListener("click",function(){{
    var current=root.getAttribute("data-theme");
    var next=current==="dark"?"light":"dark";
    root.setAttribute("data-theme",next);
    try{{localStorage.setItem("noplag-theme",next)}}catch(e){{}}
  }});
}})();
</script>
</body>
</html>"""


def _run_check(tesis: Path, res_dir: Path, fuentes_label: str, total_fuentes: int, busqueda_externa: dict | None = None, indice_externo: Path | None = None):
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

    external_by_name = {}
    if indice_externo and indice_externo.exists():
        try:
            records = json.loads(indice_externo.read_text(encoding="utf-8"))
            external_by_name = {Path(item.get("filename", "")).name: item for item in records}
        except (OSError, ValueError, TypeError):
            external_by_name = {}
    for source in sources:
        source_name = Path(source.get("filename") or "").name
        base_name = re.sub(r"\.part\d+\.txt$", ".txt", source_name, flags=re.IGNORECASE)
        metadata = external_by_name.get(source_name) or external_by_name.get(base_name)
        if metadata:
            source["source_url"] = source.get("source_url") or metadata.get("url")
            source["source_title"] = metadata.get("title")
            source["search_provider"] = ", ".join(metadata.get("providers") or [metadata.get("provider", "Internet")])

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
        "busqueda_externa": busqueda_externa or {},
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

    parser = argparse.ArgumentParser(description="Comparación adicional con Noplag Engine y búsqueda externa")
    parser.add_argument("--tesis", type=str, default=None)
    parser.add_argument("--fuentes", type=str, default=None)
    parser.add_argument("--sin-busqueda-externa", action="store_true", help="No consultar Brave Search ni SearXNG")
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

        extra_folders = []
        search_report = {
            "estado": "omitida",
            "consultas_generadas": 0,
            "paginas_descargadas": 0,
            "proveedores": {},
            "paginas": [],
        }
        external_index = None
        if not args.sin_busqueda_externa:
            print("[PROGRESO: 20%] Buscando frases de la tesis en Brave Search y SearXNG...", flush=True)
            try:
                external_folder, search_report, external_index = busqueda_web.descubrir_fuentes(tesis, result_dir)
                if search_report.get("fuentes_indexables"):
                    extra_folders.append(external_folder)
            except Exception as exc:
                search_report = {
                    "estado": "error",
                    "consultas_generadas": 0,
                    "paginas_descargadas": 0,
                    "proveedores": {},
                    "paginas": [],
                    "errores": [str(exc)[:300]],
                    "limitacion": "La búsqueda externa falló; se continúa con el corpus local.",
                }
                print(f"  Aviso: falló la búsqueda externa: {exc}", flush=True)
        else:
            print("  Búsqueda externa omitida por parámetro.", flush=True)

        print("[PROGRESO: 35%] Preparando corpus local y páginas descubiertas en Internet...", flush=True)
        total, omitidos = _index_sources(folder, solo_raiz, label, extra_folders=extra_folders)
        result = _run_check(
            tesis,
            result_dir,
            f"{label} + Internet" if extra_folders else label,
            total,
            busqueda_externa=search_report,
            indice_externo=external_index,
        )
        result["omitidos"] = omitidos
        # Re-save with omitidos included
        json_path = result_dir / "noplag.json"
        temporary = json_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(json_path)
        html_path = result_dir / "noplag.html"
        html_path.write_text(_render_html(result), encoding="utf-8")
        summary = {
            "fecha": result["fecha"],
            "similarity_pct": result["similarity_pct"],
            "sources_count": len(result["sources"]),
            "passages_count": sum(len(source.get("passages", [])) for source in result["sources"]),
            "word_count": result["word_count"],
            "coverage": result["coverage"],
            "fuentes_usadas": result["fuentes_usadas"],
            "omitidos": omitidos,
            "busqueda_externa": search_report,
        }
        summary_path = result_dir / "noplag-resumen.json"
        summary_tmp = summary_path.with_suffix(".json.tmp")
        summary_tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        summary_tmp.replace(summary_path)
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

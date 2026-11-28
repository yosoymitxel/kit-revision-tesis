"""Comparación semántica local y opcional de la tesis contra el corpus disponible.

Los puntajes son similitud de embeddings, no porcentajes legales de plagio.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from . import busqueda_web

SUPPORTED = {".pdf", ".docx", ".txt"}


def _env_int(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def extraer_texto(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return "\n\n".join(busqueda_web.extraer_parrafos_docx(path))
    if suffix == ".pdf":
        try:
            from pdfminer.high_level import extract_text
            return extract_text(str(path)) or ""
        except Exception:
            return ""
    if suffix == ".txt":
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
    return ""


def segmentar(text: str, words_per_chunk: int = 90, overlap: int = 40) -> list[str]:
    words = re.findall(r"\S+", re.sub(r"\s+", " ", text).strip())
    if len(words) < 35:
        return []
    step = max(1, words_per_chunk - overlap)
    chunks = []
    for start in range(0, len(words), step):
        chunk = " ".join(words[start:start + words_per_chunk]).strip()
        if len(chunk.split()) >= 35:
            chunks.append(chunk)
    return chunks


def _sample_evenly(items: list[str], limit: int) -> list[str]:
    if len(items) <= limit:
        return items
    if limit <= 1:
        return items[:1]
    indexes = sorted({round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)})
    return [items[index] for index in indexes]


def analizar(tesis: Path, sources: list[Path], index_path: Path | None = None) -> dict:
    enabled = os.getenv("SEMANTIC_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    model_name = os.getenv(
        "SEMANTIC_MODEL", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    ).strip()
    try:
        threshold = float(os.getenv("SEMANTIC_THRESHOLD", "0.78"))
    except (TypeError, ValueError):
        threshold = 0.78
    threshold = max(0.50, min(0.99, threshold))
    result = {
        "estado": "omitido" if not enabled else "pendiente", "modelo": model_name,
        "umbral": threshold, "fragmentos_tesis": 0, "fuentes_analizadas": 0,
        "coincidencias": [],
        "limitacion": (
            "La similitud semántica compara únicamente con las fuentes cargadas o recuperadas en este análisis. "
            "El puntaje es una señal para revisión humana, no una medida de plagio ni una prueba de copia."
        ),
    }
    if not enabled:
        return result

    thesis_text = "\n\n".join(busqueda_web.extraer_parrafos_docx(tesis))
    thesis_chunks = _sample_evenly(
        segmentar(thesis_text), _env_int("SEMANTIC_MAX_THESIS_CHUNKS", 800, 50, 2000)
    )
    if not thesis_chunks:
        result.update({"estado": "sin_texto", "errores": ["No se pudo extraer texto suficiente de la tesis."]})
        return result

    index = {}
    if index_path and index_path.exists():
        try:
            index = {
                Path(row.get("filename", "")).name: row
                for row in json.loads(index_path.read_text(encoding="utf-8"))
            }
        except (OSError, ValueError, TypeError):
            index = {}

    per_source_limit = _env_int("SEMANTIC_MAX_CHUNKS_PER_SOURCE", 80, 10, 300)
    total_limit = _env_int("SEMANTIC_MAX_TOTAL_SOURCE_CHUNKS", 2000, 100, 10000)
    source_rows, total_chunks = [], 0
    for path in sources:
        if path.suffix.lower() not in SUPPORTED or not path.is_file():
            continue
        chunks = _sample_evenly(segmentar(extraer_texto(path)), per_source_limit)
        if not chunks:
            continue
        remaining = total_limit - total_chunks
        if remaining <= 0:
            break
        metadata = index.get(path.name, {})
        for chunk in chunks[:remaining]:
            source_rows.append({
                "path": path, "name": path.name, "url": metadata.get("url"),
                "title": metadata.get("title") or path.name, "text": chunk,
            })
        total_chunks += min(len(chunks), remaining)

    result.update({
        "fragmentos_tesis": len(thesis_chunks),
        "fuentes_analizadas": len({row["name"] for row in source_rows}),
        "fragmentos_fuentes": total_chunks,
    })
    if not source_rows:
        result["estado"] = "sin_fuentes"
        return result

    try:
        import numpy as np
        from sentence_transformers import SentenceTransformer
    except ImportError:
        result.update({
            "estado": "dependencia_no_instalada",
            "errores": [
                "El análisis semántico es opcional. Instálalo con: python -m pip install -r requirements-semantic.txt"
            ],
        })
        return result

    try:
        device = os.getenv("SEMANTIC_DEVICE", "cpu").strip() or "cpu"
        model = SentenceTransformer(model_name, device=device)
        thesis_embeddings = model.encode(
            thesis_chunks, normalize_embeddings=True, batch_size=32,
            show_progress_bar=False, convert_to_numpy=True,
        )
        source_embeddings = model.encode(
            [row["text"] for row in source_rows], normalize_embeddings=True,
            batch_size=32, show_progress_bar=False, convert_to_numpy=True,
        )
        similarities = np.matmul(thesis_embeddings, source_embeddings.T)
        best_by_pair = {}
        for thesis_index, scores in enumerate(similarities):
            order = np.argsort(scores)[::-1][:10]
            for source_index in order:
                score = float(scores[source_index])
                if score < threshold:
                    break
                row = source_rows[int(source_index)]
                key = (row["name"], thesis_index)
                candidate = {
                    "source_name": row["title"], "source_file": row["name"],
                    "source_url": row["url"], "similarity": round(score, 4),
                    "tesis_excerpt": thesis_chunks[thesis_index][:1200],
                    "source_excerpt": row["text"][:1200], "thesis_chunk": thesis_index,
                }
                if key not in best_by_pair or score > best_by_pair[key]["similarity"]:
                    best_by_pair[key] = candidate
        matches = sorted(best_by_pair.values(), key=lambda row: row["similarity"], reverse=True)
        per_file, selected = {}, []
        for match in matches:
            if per_file.get(match["source_file"], 0) >= 5:
                continue
            per_file[match["source_file"]] = per_file.get(match["source_file"], 0) + 1
            selected.append(match)
            if len(selected) >= 60:
                break
        result.update({
            "estado": "activo", "coincidencias": selected,
            "coincidencias_totales": len(matches), "dispositivo": device,
        })
    except Exception as exc:
        result.update({"estado": "error", "errores": [f"{type(exc).__name__}: {str(exc)[:260]}"]})
    return result

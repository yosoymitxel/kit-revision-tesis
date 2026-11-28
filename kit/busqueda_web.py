"""Busca fragmentos del DOCX en Brave Search y SearXNG y prepara páginas para Noplag."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import os
import re
import socket
import unicodedata
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urldefrag, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"
USER_AGENT = "KitRevisionTesis/1.0 (+https://github.com/yosoymitxel/kit-revision-tesis)"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MAX_DOWNLOAD = 5 * 1024 * 1024
MAX_TEXT = 500_000
MIN_TEXT = 450
TIMEOUT = (7, 18)
STOPWORDS_ES = frozenset("""
a al algo algunas algunos ante antes como con contra cual cuales cuando de del desde donde durante e el ella ellas ellos en entre era erais eran eras es esa esas ese eso esos esta estaba estaban estado estas este esto estos fue fueron ha había habían han hasta hay la las le les lo los más me mi mis mucho muy nada ni no nos o os otra otras otro otros para pero poca pocas poco pocos por porque que quien quienes se sea según ser si sin sobre son su sus también te tiene tienen todo todos tu tus un una uno unos unas y ya
""".split())


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def extraer_parrafos_docx(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return []
    result = []
    for paragraph in root.iter(f"{W_NS}p"):
        value = "".join(node.text or "" for node in paragraph.iter(f"{W_NS}t"))
        value = re.sub(r"\s+", " ", value).strip()
        if value:
            result.append(value)
    return result


def _tokens(text: str) -> list[str]:
    return re.findall(r"[^\W_]{3,}", text.casefold(), flags=re.UNICODE)


def generar_consultas(parrafos: list[str], max_queries: int | None = None) -> list[dict]:
    """Selecciona frases repartidas por el documento y prepara una consulta menos restrictiva."""
    eligible = []
    frequency: dict[str, int] = {}
    for index, paragraph in enumerate(parrafos):
        text = re.sub(r"\s+", " ", paragraph).strip()
        words = _tokens(text)
        if not 12 <= len(words) <= 180 or len(text) < 75:
            continue
        if re.search(
            r"\b(referencias bibliográficas|bibliografía|agradecimientos|índice general|"
            r"hoja de aprobación|dedicatoria)\b",
            text,
            flags=re.IGNORECASE,
        ):
            continue
        eligible.append((index, text))
        for word in set(words):
            frequency[word] = frequency.get(word, 0) + 1

    if not eligible:
        return []

    total = len(eligible)
    total_words = sum(len(_tokens(text)) for _, text in eligible)
    candidates = []
    for index, text in eligible:
        words = re.findall(r"\S+", text)
        size = min(14, max(10, len(words)))
        phrase_best, score_best = "", -1.0
        for start in range(max(1, len(words) - size + 1)):
            phrase = " ".join(words[start:start + size]).strip(" ,;:")
            phrase = phrase.replace('"', "").replace("“", "").replace("”", "")
            tokens = _tokens(phrase)
            if len(tokens) < 9 or not 65 <= len(phrase) <= 240:
                continue
            rarity = sum(
                math.log((total + 1) / (frequency.get(token, 1) + 0.5))
                for token in set(tokens)
            )
            score = rarity * len(set(tokens)) / max(1, len(tokens))
            if score > score_best:
                phrase_best, score_best = phrase, score
        if phrase_best:
            tokens = list(dict.fromkeys(_tokens(phrase_best)))
            useful = [token for token in tokens if token not in STOPWORDS_ES]
            ranked = sorted(
                useful,
                key=lambda token: (frequency.get(token, 0), -len(token)),
            )
            selected = set(ranked[:7])
            fallback_query = " ".join(token for token in tokens if token in selected)
            if len(_tokens(fallback_query)) < 4:
                fallback_query = " ".join(tokens[:7])
            candidates.append({
                "paragraph_index": index,
                "phrase": phrase_best,
                "query": '"' + phrase_best + '"',
                "fallback_query": fallback_query,
                "score": round(score_best, 4),
            })

    if not candidates:
        return []

    # Una búsqueda cada ~450 palabras; 120 es el límite por defecto, no un número fijo.
    if max_queries is None:
        configured_limit = _int_env("WEB_SEARCH_MAX_QUERIES", 120, 1, 160)
        recommended = max(20, math.ceil(total_words / 450))
        limit = min(configured_limit, recommended)
    else:
        limit = max_queries
    limit = max(1, min(160, limit))

    first = candidates[0]["paragraph_index"]
    span = max(1, candidates[-1]["paragraph_index"] - first + 1)
    chosen, used = [], set()
    for bucket in range(limit):
        low = first + int(bucket * span / limit)
        high = first + int((bucket + 1) * span / limit)
        group = [
            item for item in candidates
            if low <= item["paragraph_index"] < max(high, low + 1)
            and item["phrase"].casefold() not in used
        ]
        if group:
            item = max(group, key=lambda row: row["score"])
            chosen.append(item)
            used.add(item["phrase"].casefold())
    if len(chosen) < limit:
        rest = sorted(
            (item for item in candidates if item["phrase"].casefold() not in used),
            key=lambda row: row["score"],
            reverse=True,
        )
        chosen.extend(rest[:limit - len(chosen)])
    return chosen[:limit]


def _canonical_url(url: str) -> str:
    url, _ = urldefrag(url)
    parts = urlsplit(url)
    query = [
        (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_")
        and key.lower() not in {"gclid", "fbclid", "mc_cid", "mc_eid"}
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", urlencode(query, doseq=True), ""))


def _normalizar_resultado(item: dict, provider: str, phrase: str) -> dict | None:
    url = item.get("url")
    if not isinstance(url, str) or not url.strip().startswith(("http://", "https://")):
        return None
    return {
        "url": _canonical_url(url.strip()),
        "title": str(item.get("title") or "").strip()[:400],
        "snippet": str(item.get("description") or item.get("content") or "").strip()[:1200],
        "provider": provider,
        "query": phrase,
    }


def _buscar_brave(query: str, key: str) -> list[dict]:
    params = {
        "q": query,
        "search_lang": os.getenv("BRAVE_SEARCH_LANG", "es"),
        "count": 10,
        "safesearch": "moderate",
        "text_decorations": "false",
    }
    country = os.getenv("BRAVE_SEARCH_COUNTRY", "").strip()
    if country:
        params["country"] = country
    response = requests.get(
        BRAVE_ENDPOINT,
        params=params,
        headers={"Accept": "application/json", "X-Subscription-Token": key, "User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"Brave Search HTTP {response.status_code}: {response.text[:160]}")
    return response.json().get("web", {}).get("results", []) or []


def _buscar_searxng(query: str, base: str) -> tuple[list[dict], list[str]]:
    response = requests.get(
        base.rstrip("/") + "/search",
        params={
            "q": query,
            "format": "json",
            "language": os.getenv("SEARXNG_LANGUAGE", "all").strip() or "all",
            "safesearch": 0,
        },
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(
            f"SearXNG HTTP {response.status_code}: {response.text[:220] or 'respuesta vacía'}"
        )
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("SearXNG devolvió una respuesta JSON inesperada.")
    warnings = []
    for engine in payload.get("unresponsive_engines") or []:
        if isinstance(engine, (list, tuple)):
            warnings.append(": ".join(str(part) for part in engine))
        else:
            warnings.append(str(engine))
    return payload.get("results", []) or [], warnings


def _consultar(name: str, queries: list[dict], key: str = "", base: str = ""):
    stats = {
        "estado": "activo",
        "consultas_ok": 0,
        "consultas_fallback": 0,
        "consultas_sin_resultados": 0,
        "resultados": 0,
        "motores_sin_respuesta": [],
        "errores": [],
    }
    if not queries:
        stats["estado"] = "sin_consultas"
        return [], stats

    def run(item):
        if name == "Brave Search":
            rows = _buscar_brave(item["query"], key)
            warnings = []
        else:
            rows, warnings = _buscar_searxng(item["query"], base)
        fallback_used = False
        if not rows and item.get("fallback_query"):
            fallback_used = True
            if name == "Brave Search":
                rows = _buscar_brave(item["fallback_query"], key)
            else:
                rows, fallback_warnings = _buscar_searxng(item["fallback_query"], base)
                warnings.extend(fallback_warnings)
        return rows, fallback_used, warnings

    results = []
    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as pool:
        futures = {pool.submit(run, item): item for item in queries}
        for future in as_completed(futures):
            item = futures[future]
            try:
                rows, fallback_used, warnings = future.result()
                stats["consultas_ok"] += 1
                if fallback_used:
                    stats["consultas_fallback"] += 1
                if not rows:
                    stats["consultas_sin_resultados"] += 1
                for warning in warnings:
                    if warning and warning not in stats["motores_sin_respuesta"]:
                        stats["motores_sin_respuesta"].append(warning[:180])
                for row in rows:
                    normalized = _normalizar_resultado(row, name, item["phrase"])
                    if normalized:
                        results.append(normalized)
            except Exception as exc:
                if len(stats["errores"]) < 10:
                    stats["errores"].append(str(exc)[:240])

    stats["resultados"] = len(results)
    stats["motores_sin_respuesta"] = stats["motores_sin_respuesta"][:30]
    if stats["consultas_ok"] == 0:
        stats["estado"] = "error"
    elif not results and (stats["errores"] or stats["motores_sin_respuesta"]):
        stats["estado"] = "error"
    elif not results:
        stats["estado"] = "sin_resultados"
    elif stats["errores"] or stats["motores_sin_respuesta"]:
        stats["estado"] = "parcial"
    return results, stats


def url_publica_segura(url: str) -> bool:
    """Evita descargar destinos locales/privados o esquemas no HTTP."""
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"} or not parts.hostname:
            return False
        if parts.username or parts.password or parts.port not in (None, 80, 443):
            return False
        host = parts.hostname.rstrip(".").lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            return False
        try:
            return ipaddress.ip_address(host).is_global
        except ValueError:
            addresses = socket.getaddrinfo(host, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
            return bool(addresses) and all(ipaddress.ip_address(row[4][0]).is_global for row in addresses)
    except (ValueError, OSError):
        return False


def _extraer_html(raw: bytes) -> tuple[str, str]:
    soup = BeautifulSoup(raw, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    for node in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "svg", "iframe", "aside", "button"]):
        node.decompose()
    main = soup.find("main") or soup.find("article")
    node = main if main and len(main.get_text(" ", strip=True)) >= MIN_TEXT else soup
    text = node.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", text)[:MAX_TEXT].strip(), title[:300]


def _extraer_docx(raw: bytes) -> str:
    try:
        with zipfile.ZipFile(BytesIO(raw)) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError):
        return ""
    return "\n".join(
        "".join(node.text or "" for node in para.iter(f"{W_NS}t")).strip()
        for para in root.iter(f"{W_NS}p")
    )[:MAX_TEXT]


def _extraer_pdf(raw: bytes) -> str:
    try:
        from pdfminer.high_level import extract_text
        return (extract_text(BytesIO(raw)) or "")[:MAX_TEXT]
    except Exception:
        return ""


def _descargar(result: dict) -> dict:
    original, current = result["url"], result["url"]
    raw, content_type, encoding = b"", "", "utf-8"
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/pdf,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document;q=0.9,*/*;q=0.2"}
    for _ in range(6):
        if not url_publica_segura(current):
            return {"ok": False, "url": original, "reason": "URL privada, local o no permitida"}
        try:
            with requests.get(current, headers=headers, timeout=TIMEOUT, stream=True, allow_redirects=False) as response:
                if response.is_redirect or response.is_permanent_redirect:
                    location = response.headers.get("Location")
                    if not location:
                        return {"ok": False, "url": original, "reason": "redirección sin destino"}
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    return {"ok": False, "url": original, "reason": f"HTTP {response.status_code}"}
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                encoding = response.encoding or "utf-8"
                length = response.headers.get("Content-Length")
                if length and int(length) > MAX_DOWNLOAD:
                    return {"ok": False, "url": original, "reason": "supera 5 MiB"}
                parts, total = [], 0
                for chunk in response.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > MAX_DOWNLOAD:
                        return {"ok": False, "url": original, "reason": "supera 5 MiB"}
                    parts.append(chunk)
                raw = b"".join(parts)
            break
        except (requests.RequestException, ValueError) as exc:
            return {"ok": False, "url": original, "reason": str(exc)[:180]}
    else:
        return {"ok": False, "url": original, "reason": "demasiadas redirecciones"}

    title = result.get("title") or ""
    if raw.startswith(b"%PDF-") or "pdf" in content_type:
        text = _extraer_pdf(raw)
    elif "wordprocessingml" in content_type or raw.startswith(b"PK\x03\x04"):
        text = _extraer_docx(raw)
    elif "html" in content_type or b"<html" in raw[:1000].lower() or b"<!doctype html" in raw[:1000].lower():
        text, detected_title = _extraer_html(raw)
        title = title or detected_title
    elif content_type.startswith("text/"):
        text = raw.decode(encoding, errors="replace")
    else:
        return {"ok": False, "url": original, "reason": f"tipo no compatible: {content_type or 'desconocido'}"}
    text = re.sub(r"\n{3,}", "\n\n", (text or "")).strip()
    if len(text) < MIN_TEXT:
        return {"ok": False, "url": original, "reason": "contenido extraíble insuficiente"}
    return {
        "ok": True,
        "url": _canonical_url(current),
        "title": title[:300] or (urlsplit(current).hostname or "Fuente web"),
        "text": text[:MAX_TEXT],
    }


def descubrir_fuentes(tesis: Path, resultado_dir: Path) -> tuple[Path, dict, Path]:
    output = resultado_dir / "busqueda-web"
    sources_dir = output / "fuentes"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for old in sources_dir.glob("*.txt"):
        old.unlink(missing_ok=True)

    queries = generar_consultas(extraer_parrafos_docx(tesis))
    key = os.getenv("BRAVE_SEARCH_API_KEY", "").strip()
    searx_url = os.getenv("SEARXNG_URL", "http://127.0.0.1:8888").strip()
    searx_enabled = os.getenv("SEARXNG_ENABLED", "true").lower() not in {"0", "false", "no"}
    providers, found = {}, []
    print(f"  Fragmentos de búsqueda generados: {len(queries)}.", flush=True)
    if key:
        rows, providers["brave"] = _consultar("Brave Search", queries, key=key)
        found.extend(rows)
    else:
        providers["brave"] = {"estado": "no_configurado", "consultas_ok": 0, "resultados": 0, "errores": ["Falta BRAVE_SEARCH_API_KEY en .env."]}
    if searx_enabled and searx_url:
        rows, providers["searxng"] = _consultar("SearXNG", queries, base=searx_url)
        found.extend(rows)
    else:
        providers["searxng"] = {"estado": "deshabilitado", "consultas_ok": 0, "resultados": 0, "errores": []}

    unique = {}
    for item in found:
        url = item["url"].casefold().rstrip("/")
        if url not in unique:
            unique[url] = item
        else:
            prev = unique[url]
            prev["providers"] = sorted(set(prev.get("providers", [prev["provider"]]) + [item["provider"]]))
    max_downloads = _int_env("WEB_SEARCH_MAX_DOWNLOADS", 35, 1, 100)
    max_results = _int_env("WEB_SEARCH_MAX_RESULTS", 160, 1, 200)
    domain_limit = _int_env("WEB_SEARCH_MAX_PER_DOMAIN", 3, 1, 10)
    selected, domains = [], {}
    for item in unique.values():
        domain = (urlsplit(item["url"]).hostname or "").lower()
        if domains.get(domain, 0) >= domain_limit:
            continue
        selected.append(item)
        domains[domain] = domains.get(domain, 0) + 1
        if len(selected) >= min(max_downloads, max_results):
            break

    pages, failed = [], []
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(selected)))) as pool:
        futures = {pool.submit(_descargar, item): item for item in selected}
        for future in as_completed(futures):
            item = futures[future]
            try:
                page = future.result()
            except Exception as exc:
                page = {"ok": False, "url": item["url"], "reason": str(exc)[:180]}
            if not page.get("ok"):
                if len(failed) < 50:
                    failed.append({"url": item["url"], "reason": page.get("reason", "error")})
                continue
            digest = hashlib.sha256(page["url"].encode("utf-8")).hexdigest()[:12]
            slug = unicodedata.normalize("NFKD", page["title"]).encode("ascii", "ignore").decode("ascii")
            slug = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_")[:55] or "fuente"
            filename = f"web_{digest}_{slug}.txt"
            providers_found = item.get("providers", [item["provider"]])
            content = f"TÍTULO: {page['title']}\nURL: {page['url']}\nPROVEEDORES: {', '.join(providers_found)}\n\n{page['text']}"
            (sources_dir / filename).write_text(content, encoding="utf-8")
            pages.append({
                "filename": filename, "url": page["url"], "title": page["title"],
                "provider": item["provider"], "providers": providers_found,
                "query": item.get("query", ""), "characters": len(page["text"]),
            })

    pages.sort(key=lambda row: row["url"])
    index_path = output / "indice-fuentes.json"
    index_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    configured_states = [
        info.get("estado")
        for info in providers.values()
        if info.get("estado") not in {"no_configurado", "deshabilitado", "sin_consultas"}
    ]
    if pages:
        state = "completa" if configured_states and all(item == "activo" for item in configured_states) else "parcial"
    elif unique:
        state = "sin_paginas_utilizables"
    elif any(item == "error" for item in configured_states):
        state = "error"
    else:
        state = "sin_resultados"
    report = {
        "estado": state,
        "fecha": datetime.now().astimezone().isoformat(timespec="seconds"),
        "consultas_generadas": len(queries),
        "consultas_ampliadas": sum(int(info.get("consultas_fallback") or 0) for info in providers.values()),
        "consultas_sin_resultados": sum(int(info.get("consultas_sin_resultados") or 0) for info in providers.values()),
        "palabras_elegibles": sum(len(_tokens(paragraph)) for paragraph in extraer_parrafos_docx(tesis)),
        "resultados_descubiertos": len(unique),
        "paginas_seleccionadas": len(selected),
        "paginas_descargadas": len(pages),
        "paginas_omitidas": len(failed),
        "fuentes_indexables": len(pages),
        "proveedores": providers,
        "paginas": pages,
        "errores_descarga": failed,
        "limitacion": "La cobertura depende de los índices de Brave y los motores habilitados en SearXNG; no representa toda Internet ni detecta por sí sola paráfrasis semánticas.",
    }
    (output / "reporte-busqueda.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Búsqueda externa: {len(queries)} consultas · {len(unique)} URLs · {len(pages)} páginas extraídas.", flush=True)
    for name, info in providers.items():
        print(
            f"    {name}: {info['estado']} · {info['consultas_ok']}/{len(queries)} consultas · "
            f"{info['resultados']} resultados · {info.get('consultas_fallback', 0)} ampliadas.",
            flush=True,
        )
        for error in info.get("errores", [])[:3]:
            print(f"      Error: {error}", flush=True)
        for engine in info.get("motores_sin_respuesta", [])[:5]:
            print(f"      Motor sin respuesta: {engine}", flush=True)
    if failed:
        print(f"  Páginas no procesables: {len(failed)}.", flush=True)
    return sources_dir, report, index_path

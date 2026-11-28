"""Descubrimiento académico sin API keys: LA Referencia, Crossref, OpenAIRE y OAI-PMH."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from . import busqueda_web

USER_AGENT = "KitRevisionTesis/1.0 (+https://github.com/yosoymitxel/kit-revision-tesis)"
LA_REFERENCIA_URL = "https://buscador.lareferencia.info/vufind/Search/Results"
OPENAIRE_URL = "https://api.openaire.eu/graph/v4/research-products"
TIMEOUT = (8, 25)


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def _split_endpoints(value: str | None = None) -> list[str]:
    raw = os.getenv("ACADEMIC_OAI_ENDPOINTS", "") if value is None else value
    return list(dict.fromkeys(item.strip().rstrip("/") for item in raw.split(";") if item.strip()))


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(filter(None, (_clean(item) for item in value)))
    if isinstance(value, dict):
        for key in ("value", "content", "text", "name", "label"):
            if value.get(key):
                return _clean(value[key])
        return " ".join(filter(None, (_clean(item) for item in value.values())))
    text = BeautifulSoup(str(value), "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _nested_urls(value) -> list[str]:
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_lower = str(key).lower()
            if isinstance(child, str) and child.startswith(("https://", "http://")):
                if any(token in key_lower for token in ("url", "uri", "webresource", "landing", "fulltext")):
                    found.append(child.strip())
            else:
                found.extend(_nested_urls(child))
    elif isinstance(value, list):
        for child in value:
            found.extend(_nested_urls(child))
    return list(dict.fromkeys(found))


def _nested_doi(value) -> str:
    if isinstance(value, dict):
        for key, child in value.items():
            if "doi" in str(key).lower() and isinstance(child, str) and child.strip():
                return child.strip()
            candidate = _nested_doi(child)
            if candidate:
                return candidate
    elif isinstance(value, list):
        for child in value:
            candidate = _nested_doi(child)
            if candidate:
                return candidate
    elif isinstance(value, str) and value.lower().startswith("10."):
        return value.strip()
    return ""


def _normalize_record(*, provider: str, title: str, url: str = "", abstract: str = "",
                      doi: str = "", fulltext_url: str = "", language: str = "") -> dict | None:
    title = _clean(title)[:500]
    abstract = _clean(abstract)[:20000]
    if not title and not abstract:
        return None
    if not url and doi:
        url = f"https://doi.org/{doi.removeprefix('https://doi.org/').removeprefix('http://doi.org/')}"
    if not url and fulltext_url:
        url = fulltext_url
    if not url or not url.startswith(("https://", "http://")):
        return None
    return {
        "provider": provider, "title": title or "Publicación académica", "url": url,
        "fulltext_url": fulltext_url if fulltext_url.startswith(("https://", "http://")) else "",
        "abstract": abstract, "doi": doi, "language": language,
    }


def parsear_resultados_lareferencia(document: str, base_url: str = "https://buscador.lareferencia.info") -> list[dict]:
    """Extrae registros del HTML de VuFind; tolera variaciones menores de plantilla."""
    soup = BeautifulSoup(document, "html.parser")
    records, seen, anchors = [], set(), []
    for container in soup.select("div.result, li.result, .result-listing, .record"):
        anchor = container.select_one("a.title, h2 a, h3 a, .title a, a[href*='/Record/']")
        if anchor:
            anchors.append((container, anchor))
    if not anchors:
        for anchor in soup.select("a[href*='/Record/']"):
            anchors.append((anchor.find_parent(["div", "li", "article"]) or anchor.parent, anchor))
    for container, anchor in anchors:
        href = anchor.get("href", "").strip()
        url = urljoin(base_url, href)
        if not href or url in seen or not url.startswith(("https://", "http://")):
            continue
        seen.add(url)
        title = _clean(anchor.get_text(" ", strip=True) or anchor.get("title"))
        if not title:
            continue
        summary = ""
        for selector in (".summary", ".description", ".resultItemLine2", ".snippet", "p"):
            node = container.select_one(selector) if container else None
            if node:
                summary = _clean(node.get_text(" ", strip=True))
                if summary:
                    break
        fulltext = ""
        if container:
            for link in container.select("a[href]"):
                candidate = urljoin(base_url, link.get("href", ""))
                label = f"{link.get_text(' ', strip=True)} {link.get('href', '')}".lower()
                if candidate.lower().split("?", 1)[0].endswith(".pdf") or any(
                    token in label for token in ("pdf", "texto completo", "full text", "bitstream", "download")
                ):
                    fulltext = candidate
                    break
        record = _normalize_record(
            provider="LA Referencia", title=title, url=url,
            abstract=summary, fulltext_url=fulltext,
        )
        if record:
            records.append(record)
    return records


def _buscar_lareferencia(query: str, limit: int) -> list[dict]:
    response = requests.get(
        LA_REFERENCIA_URL,
        params={"lookfor": query, "type": "AllFields", "limit": limit},
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"LA Referencia HTTP {response.status_code}")
    content = response.text
    if "anubis" in content[:12000].lower() or "access denied" in content[:12000].lower():
        raise RuntimeError("LA Referencia bloqueó la consulta automatizada (protección anti-bots)")
    return parsear_resultados_lareferencia(content, response.url)


def _buscar_crossref(query: str, limit: int) -> list[dict]:
    try:
        from habanero import Crossref
    except ImportError as exc:
        raise RuntimeError("Falta Habanero; ejecuta pip install -r requirements.txt") from exc
    mailto = os.getenv("CROSSREF_MAILTO", "").strip() or None
    client = Crossref(mailto=mailto, timeout=TIMEOUT[1])
    response = client.works(
        query=query, limit=limit,
        select=["DOI", "title", "URL", "abstract", "published", "language", "link", "type"],
    )
    items = (response or {}).get("message", {}).get("items", []) or []
    results = []
    for item in items:
        doi = str(item.get("DOI") or "").strip()
        links = item.get("link") or []
        pdf = next((
            link.get("URL", "") for link in links if isinstance(link, dict)
            and ("pdf" in str(link.get("content-type", "")).lower()
                 or str(link.get("intended-application", "")).lower() == "text-mining")
        ), "")
        record = _normalize_record(
            provider="Crossref", title=item.get("title"),
            url=item.get("URL") or (f"https://doi.org/{doi}" if doi else ""),
            abstract=item.get("abstract", ""), doi=doi, fulltext_url=pdf,
            language=item.get("language", ""),
        )
        if record:
            results.append(record)
    return results


def _buscar_openaire(query: str, limit: int) -> list[dict]:
    response = requests.get(
        OPENAIRE_URL,
        params={
            "search": query, "page": 1, "page_size": limit,
            "select": "id,mainTitle,description,publicationDate,instances,pids",
        },
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        timeout=TIMEOUT,
    )
    if not response.ok:
        raise RuntimeError(f"OpenAIRE Graph HTTP {response.status_code}: {response.text[:160]}")
    payload = response.json()
    results = []
    for item in payload.get("results", []) or []:
        urls = _nested_urls(item.get("instances") or [])
        fulltext = next((url for url in urls if ".pdf" in url.lower() or "bitstream" in url.lower()), "")
        page_url = next((url for url in urls if url != fulltext), "")
        doi = _nested_doi(item.get("pids") or item)
        record = _normalize_record(
            provider="OpenAIRE", title=item.get("mainTitle"),
            url=page_url or fulltext or (f"https://doi.org/{doi}" if doi else ""),
            abstract=item.get("description", ""), doi=doi, fulltext_url=fulltext,
        )
        if record:
            results.append(record)
    return results


def cosechar_oai_pmh(endpoints: list[str], max_records: int, queries: list[str]) -> tuple[list[dict], dict]:
    stats = {
        "estado": "sin_configurar" if not endpoints else "activo",
        "consultas_enviadas": 0, "consultas_ok": 0, "consultas_con_fallos": 0,
        "consultas_fallback": 0, "resultados": 0, "errores": [],
        "motores_sin_respuesta": [], "registros_cosechados": 0,
    }
    if not endpoints:
        stats["errores"].append(
            "Configura endpoints OAI-PMH públicos en ACADEMIC_OAI_ENDPOINTS (separados por punto y coma)."
        )
        return [], stats
    try:
        from sickle import Sickle
    except ImportError:
        stats["estado"] = "error"
        stats["consultas_con_fallos"] = 1
        stats["errores"].append("Falta Sickle; ejecuta pip install -r requirements.txt.")
        return [], stats

    terms = set()
    for query in queries:
        terms.update(re.findall(r"[^\W_]{4,}", query.casefold(), flags=re.UNICODE))
    records, failures = [], 0
    for endpoint in endpoints:
        stats["consultas_enviadas"] += 1
        try:
            client = Sickle(endpoint, timeout=TIMEOUT[1])
            iterator = client.ListRecords(metadataPrefix="oai_dc")
            harvested, ranked = 0, []
            for record in iterator:
                harvested += 1
                metadata = getattr(record, "metadata", {}) or {}
                title = _clean(metadata.get("title"))
                description = _clean(metadata.get("description"))
                identifiers = metadata.get("identifier") or []
                relations = metadata.get("relation") or []
                links = [value for value in [*identifiers, *relations]
                         if isinstance(value, str) and value.startswith(("https://", "http://"))]
                fulltext = next((url for url in links if ".pdf" in url.lower() or any(
                    marker in url.lower() for marker in ("bitstream", "download", "fulltext")
                )), "")
                page_url = next((url for url in links if url != fulltext), "")
                blob = f"{title} {description}".casefold()
                score = sum(1 for term in terms if term in blob)
                if score and (page_url or fulltext) and (len(description) >= 120 or fulltext):
                    item = _normalize_record(
                        provider="OAI-PMH", title=title, url=page_url or fulltext,
                        abstract=description, fulltext_url=fulltext,
                    )
                    if item:
                        ranked.append((score, item))
                if harvested >= max_records:
                    break
            stats["registros_cosechados"] += harvested
            ranked.sort(key=lambda row: row[0], reverse=True)
            records.extend(item for _, item in ranked[:_int_env("ACADEMIC_MAX_RESULTS_PER_QUERY", 5, 1, 20)])
            stats["consultas_ok"] += 1
        except Exception as exc:
            failures += 1
            stats["consultas_con_fallos"] += 1
            if len(stats["errores"]) < 10:
                stats["errores"].append(f"{endpoint}: {str(exc)[:200]}")
    stats["resultados"] = len(records)
    if stats["consultas_ok"] == 0:
        stats["estado"] = "error"
    elif failures:
        stats["estado"] = "parcial"
    elif not records:
        stats["estado"] = "sin_resultados"
    return records, stats


def _buscar_proveedor(name: str, queries: list[str], limit: int) -> tuple[list[dict], dict]:
    stats = {
        "estado": "activo", "consultas_enviadas": 0, "consultas_ok": 0,
        "consultas_con_fallos": 0, "consultas_fallback": 0,
        "consultas_sin_resultados": 0, "resultados": 0, "errores": [],
        "motores_sin_respuesta": [],
    }
    results = []
    for query in queries:
        stats["consultas_enviadas"] += 1
        try:
            if name == "LA Referencia":
                rows = _buscar_lareferencia(query, limit)
            elif name == "Crossref":
                rows = _buscar_crossref(query, limit)
            else:
                rows = _buscar_openaire(query, limit)
            stats["consultas_ok"] += 1
            if not rows:
                stats["consultas_sin_resultados"] += 1
            results.extend(rows)
        except Exception as exc:
            stats["consultas_con_fallos"] += 1
            if len(stats["errores"]) < 10:
                stats["errores"].append(str(exc)[:240])
        time.sleep(0.15)
    stats["resultados"] = len(results)
    if not stats["consultas_ok"]:
        stats["estado"] = "error"
    elif not results and stats["consultas_con_fallos"]:
        stats["estado"] = "error"
    elif not results:
        stats["estado"] = "sin_resultados"
    elif stats["consultas_con_fallos"]:
        stats["estado"] = "parcial"
    return results, stats


def _slug(title: str) -> str:
    value = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_")[:55] or "documento"


def descubrir_fuentes(tesis: Path, resultado_dir: Path) -> tuple[Path, dict, Path]:
    output = resultado_dir / "fuentes-academicas"
    sources_dir = output / "fuentes"
    sources_dir.mkdir(parents=True, exist_ok=True)
    for old in sources_dir.glob("academic_*.txt"):
        old.unlink(missing_ok=True)

    enabled = os.getenv("ACADEMIC_ENABLED", "true").strip().lower() not in {"0", "false", "no"}
    max_queries = _int_env("ACADEMIC_MAX_QUERIES", 8, 1, 20)
    per_query = _int_env("ACADEMIC_MAX_RESULTS_PER_QUERY", 5, 1, 20)
    max_downloads = _int_env("ACADEMIC_MAX_DOWNLOADS", 35, 1, 80)
    endpoints = _split_endpoints()
    query_rows = busqueda_web.generar_consultas(
        busqueda_web.extraer_parrafos_docx(tesis), max_queries=max_queries
    )
    queries = list(dict.fromkeys(
        (item.get("fallback_query") or item.get("phrase", "")).strip()
        for item in query_rows if (item.get("fallback_query") or item.get("phrase", "")).strip()
    ))

    providers, records = {}, []
    names = ("LA Referencia", "Crossref", "OpenAIRE", "OAI-PMH")
    if not enabled:
        for name in names:
            providers[name] = {"estado": "deshabilitado", "consultas_enviadas": 0,
                               "consultas_ok": 0, "consultas_con_fallos": 0,
                               "consultas_fallback": 0, "resultados": 0, "errores": []}
    elif queries:
        for name in names[:3]:
            rows, stats = _buscar_proveedor(name, queries, per_query)
            providers[name] = stats
            records.extend(rows)
        rows, providers["OAI-PMH"] = cosechar_oai_pmh(
            endpoints, _int_env("ACADEMIC_OAI_MAX_RECORDS", 250, 20, 2000), queries
        )
        records.extend(rows)
    else:
        for name in names:
            providers[name] = {"estado": "sin_consultas", "consultas_enviadas": 0,
                               "consultas_ok": 0, "consultas_con_fallos": 0,
                               "consultas_fallback": 0, "resultados": 0, "errores": []}

    unique = {}
    for item in records:
        key = (item.get("doi") or item.get("url") or "").casefold().rstrip("/")
        if not key:
            continue
        if key not in unique:
            item["providers"] = [item["provider"]]
            unique[key] = item
        else:
            current = unique[key]
            current["providers"] = sorted(set(current.get("providers", []) + [item["provider"]]))
            if not current.get("fulltext_url") and item.get("fulltext_url"):
                current["fulltext_url"] = item["fulltext_url"]
            if len(item.get("abstract", "")) > len(current.get("abstract", "")):
                current["abstract"] = item["abstract"]

    selected = list(unique.values())[:max_downloads]
    pages, failures = [], []
    for item in selected:
        text, full_text = "", False
        download_url = item.get("fulltext_url", "")
        if download_url:
            downloaded = busqueda_web._descargar({
                "url": download_url, "title": item.get("title", ""), "provider": item["provider"],
            })
            if downloaded.get("ok"):
                text, full_text = downloaded["text"], True
            else:
                failures.append({"url": download_url, "reason": downloaded.get("reason", "no descargable")})
        if not text and len(item.get("abstract", "")) >= 180:
            text = item["abstract"]
        if not text:
            continue

        url = item.get("url") or download_url
        digest = hashlib.sha256((item.get("doi") or url).encode("utf-8")).hexdigest()[:12]
        filename = f"academic_{digest}_{_slug(item.get('title', 'documento'))}.txt"
        provider_names = item.get("providers") or [item["provider"]]
        content_type = "texto_completo" if full_text else "resumen_bibliografico"
        header = (
            f"TÍTULO: {item.get('title', '')}\nURL: {url}\nDOI: {item.get('doi', '')}\n"
            f"PROVEEDORES: {', '.join(provider_names)}\nTIPO DE CONTENIDO: {content_type}\n\n"
        )
        (sources_dir / filename).write_text(header + text[:500000], encoding="utf-8")
        pages.append({
            "filename": filename, "url": url, "title": item.get("title") or "Publicación académica",
            "provider": item["provider"], "providers": provider_names, "characters": len(text),
            "full_text": full_text, "content_type": content_type, "doi": item.get("doi", ""),
        })

    for name, stats in providers.items():
        stats["resultados_unicos"] = sum(1 for item in unique.values() if name in item.get("providers", []))
    index_path = output / "indice-fuentes.json"
    index_path.write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding="utf-8")
    active = [info for info in providers.values()
              if info.get("estado") not in {"deshabilitado", "sin_configurar", "sin_consultas"}]
    report = {
        "estado": "completa" if pages and active and all(x.get("estado") == "activo" for x in active)
                  else "parcial" if pages else "error" if active and all(x.get("estado") == "error" for x in active)
                  else "sin_resultados",
        "consultas_generadas": len(queries), "resultados_descubiertos": len(unique),
        "paginas_descargadas": len(pages),
        "textos_completos": sum(1 for page in pages if page["full_text"]),
        "resumenes_indexados": sum(1 for page in pages if not page["full_text"]),
        "fuentes_indexables": len(pages), "proveedores": providers, "paginas": pages,
        "errores_descarga": failures[:50],
        "limitacion": (
            "LA Referencia, Crossref y OpenAIRE descubren registros académicos; OAI-PMH cosecha los repositorios "
            "configurados. Solo se compara texto completo cuando existe un archivo accesible; los abstracts se "
            "etiquetan como resúmenes. Las fuentes académicas no cubren toda Internet."
        ),
    }
    (output / "reporte-busqueda.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"  Fuentes académicas: {len(queries)} consultas · {len(unique)} registros · {len(pages)} textos "
        f"({report['textos_completos']} completos, {report['resumenes_indexados']} resúmenes).",
        flush=True,
    )
    for name, info in providers.items():
        print(f"    {name}: {info.get('estado')} · {info.get('consultas_enviadas', 0)} consultas · "
              f"{info.get('resultados', 0)} resultados.", flush=True)
        for error in info.get("errores", [])[:2]:
            print(f"      Aviso: {error}", flush=True)
    return sources_dir, report, index_path

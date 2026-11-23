"""Fuentes web: lee las URL y DOI de la bibliografía de Word, verifica cada enlace
y descarga su texto a 2-FUENTES/web/ para incluirlo en la comparación.

Primero intenta una descarga simple. Si la página no trae texto (sitios armados con
JavaScript), usa Playwright con Chromium, que se instala solo la primera vez.
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from lxml import etree

from .docx_utils import B_NS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36 kit-revision-tesis")
MIN_TEXTO = 400  # caracteres; por debajo se intenta con Playwright


def fuentes_con_url(ruta_docx):
    import zipfile
    out = []
    with zipfile.ZipFile(ruta_docx) as z:
        for n in z.namelist():
            if not (n.startswith("customXml/item") and n.endswith(".xml")) or "Props" in n:
                continue
            data = z.read(n)
            if B_NS.encode() not in data:
                continue
            for s in etree.fromstring(data).iter("{%s}Source" % B_NS):
                g = lambda k: (s.findtext("{%s}%s" % (B_NS, k)) or "").strip()
                url = g("URL")
                doi = g("DOI")
                if not url and doi:
                    url = "https://doi.org/" + re.sub(r"^(https?://(dx\.)?doi\.org/)", "", doi)
                if url:
                    out.append({"tag": g("Tag"), "titulo": g("Title"), "url": url})
    return out


def _slug(texto, n=50):
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Za-z0-9]+", "_", t).strip("_")[:n] or "fuente"


def _texto_html(html):
    s = BeautifulSoup(html, "html.parser")
    for t in s(["script", "style", "noscript", "nav", "header", "footer", "form", "svg"]):
        t.decompose()
    return re.sub(r"\n{3,}", "\n\n", s.get_text("\n", strip=True))


def _playwright_texto(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright no instalado"
    for intento in range(2):
        try:
            with sync_playwright() as p:
                nav = p.chromium.launch()
                pag = nav.new_page(user_agent=UA)
                pag.goto(url, wait_until="networkidle", timeout=45000)
                html = pag.content()
                final = pag.url
                nav.close()
            return (_texto_html(html), final), None
        except Exception as e:  # primera vez: falta el navegador
            if intento == 0 and "Executable doesn't exist" in str(e):
                print("    instalando Chromium para Playwright (solo la primera vez)...")
                subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
                continue
            return None, str(e).splitlines()[0][:160]
    return None, "no se pudo abrir"


def _mismo_destino(a, b):
    ua, ub = urlparse(a), urlparse(b)
    return ua.netloc.lower().removeprefix("www.") == ub.netloc.lower().removeprefix("www.") and \
        ua.path.rstrip("/") == ub.path.rstrip("/")


def descargar(ruta_docx, carpeta: Path, actualizar=False):
    carpeta.mkdir(parents=True, exist_ok=True)
    indice_path = carpeta / "_indice.json"
    try:
        indice = json.loads(indice_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        indice = {}
    resultados = []
    sesion = requests.Session()
    sesion.headers.update({"User-Agent": UA, "Accept-Language": "es,en;q=0.8"})
    for f in fuentes_con_url(ruta_docx):
        url = f["url"]
        previo = indice.get(url)
        if previo and not actualizar and (carpeta / previo.get("archivo", "")).exists():
            resultados.append(previo)
            continue
        print(f"    {url[:90]}")
        r = {"tag": f["tag"], "titulo": f["titulo"], "url": url, "final": url, "estado": "", "archivo": "", "metodo": ""}
        base = f"{f['tag'] or 'web'}_{_slug(f['titulo'] or urlparse(url).netloc, 40)}"
        try:
            resp = sesion.get(url, timeout=30, allow_redirects=True)
            r["final"] = resp.url
            codigo = resp.status_code
            tipo = resp.headers.get("Content-Type", "").lower()
        except requests.RequestException as e:
            codigo, tipo, resp = None, "", None
            r["estado"] = "Caído"
            r["detalle"] = type(e).__name__
        if resp is not None:
            if codigo >= 400 and codigo not in (403, 429):
                r["estado"] = "Caído"
                r["detalle"] = f"HTTP {codigo}"
            elif "pdf" in tipo or resp.content[:5] == b"%PDF-":
                (carpeta / (base + ".pdf")).write_bytes(resp.content)
                r.update(archivo=base + ".pdf", metodo="descarga", estado="OK")
            else:
                texto = _texto_html(resp.text) if codigo < 400 else ""
                metodo = "descarga"
                if len(texto) < MIN_TEXTO:
                    res, err = _playwright_texto(url)
                    if res:
                        texto, r["final"] = res
                        metodo = "Playwright"
                    elif codigo in (403, 429):
                        r["estado"], r["detalle"] = "Bloqueado", f"HTTP {codigo}; {err}"
                if len(texto) >= MIN_TEXTO:
                    (carpeta / (base + ".txt")).write_text(f"{f['titulo']}\n{url}\n\n{texto}", encoding="utf-8")
                    r.update(archivo=base + ".txt", metodo=metodo, estado="OK")
                elif not r["estado"]:
                    r["estado"], r["detalle"] = "Sin texto", "la página no tiene texto legible"
        if r["estado"] == "OK" and "doi.org" not in url and not _mismo_destino(url, r["final"]):
            r["estado"] = "Redirige"
            r["detalle"] = r["final"]
        indice[url] = r
        resultados.append(r)
    indice_path.write_text(json.dumps(indice, ensure_ascii=False, indent=1), encoding="utf-8")
    return resultados

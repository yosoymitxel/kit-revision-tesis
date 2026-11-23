"""Servidor web local para el Centro de Control de Revisión de Tesis.

Permite:
1. Subir la tesis a 1-MI-TESIS.
2. Subir y gestionar archivos en 2-FUENTES.
3. Ejecutar 'revisar' o 'limpiar' con salida de consola en vivo.
4. Abrir y explorar los resultados (panel.html, comparaciones).
"""
import cgi
import http.server
import json
import os
import re
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TESIS_DIR = RAIZ / "1-MI-TESIS"
FUENTES_DIR = RAIZ / "2-FUENTES"
RESULTADOS_DIR = RAIZ / "3-RESULTADOS"

# Estado global de ejecución de procesos
PROCESO_ACTUAL = None
LOGS_EJECUCION = []
EJECUTANDO = False
ACCION_ACTUAL = ""
CODIGO_SALIDA = None
LOCK = threading.Lock()


def _formatear_tamano(n_bytes):
    if n_bytes < 1024:
        return f"{n_bytes} B"
    elif n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 * 1024):.1f} MB"


def obtener_estado():
    """Retorna un resumen estructurado del estado de las carpetas y resultados."""
    with LOCK:
        ejec = EJECUTANDO
        accion = ACCION_ACTUAL
        salida_code = CODIGO_SALIDA

    # 1. Tesis
    tesis_file = None
    if TESIS_DIR.exists():
        docs = sorted([p for p in TESIS_DIR.glob("*.docx") if not p.name.startswith("~$")],
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if docs:
            t = docs[0]
            st = t.stat()
            tesis_file = {
                "nombre": t.name,
                "tamano": _formatear_tamano(st.st_size),
                "bytes": st.st_size,
                "modificado": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
            }

    # 2. Fuentes
    fuentes_lista = []
    exts_validas = {".pdf", ".docx", ".odt", ".txt"}
    if FUENTES_DIR.exists():
        for f in sorted(FUENTES_DIR.rglob("*")):
            if f.is_file() and f.suffix.lower() in exts_validas and not f.name.startswith("~$") and f.name.upper() != "LEEME.TXT":
                rel = str(f.relative_to(FUENTES_DIR)).replace("\\", "/")
                fuentes_lista.append({
                    "nombre": rel,
                    "tamano": _formatear_tamano(f.stat().st_size),
                    "tipo": f.suffix.lower().replace(".", "").upper(),
                    "es_web": rel.startswith("web/")
                })

    # 3. Resultados
    panel_path = RESULTADOS_DIR / "panel.html"
    datos_path = RESULTADOS_DIR / "datos.json"
    resultados_info = {"existe": panel_path.exists()}
    if panel_path.exists():
        st = panel_path.stat()
        resultados_info["fecha"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
        if datos_path.exists():
            try:
                dt = json.loads(datos_path.read_text(encoding="utf-8"))
                resultados_info["archivo"] = dt.get("archivo", "")
                sim = dt.get("similitud", {})
                cit = dt.get("citas", {})
                inv = dt.get("invisibles", {})
                est = dt.get("estructura", {})
                w = dt.get("web", [])
                max_s = sim["fuentes"][0]["porcentaje"] if sim.get("fuentes") else 0
                sin_c = len([p for p in sim.get("pasajes", []) if p.get("estado") == "Sin comillas"])
                c_mal = len(cit.get("sin_fuente", [])) + len(cit.get("sin_citar", []))
                resultados_info["resumen"] = {
                    "max_sim": round(max_s, 1),
                    "sin_comillas": sin_c,
                    "citas_mal": c_mal,
                    "invisibles": inv.get("total", 0),
                    "palabras": est.get("palabras", 0),
                    "enlaces_mal": len([x for x in w if x.get("estado") != "OK"])
                }
            except Exception:
                pass

    # 4. Copia limpia de invisibles
    copia_limpia = None
    if RESULTADOS_DIR.exists():
        limpias = sorted(RESULTADOS_DIR.glob("*sin invisibles*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if limpias:
            copia_limpia = {
                "nombre": limpias[0].name,
                "tamano": _formatear_tamano(limpias[0].stat().st_size)
            }

    return {
        "tesis": tesis_file,
        "fuentes": fuentes_lista,
        "total_fuentes": len(fuentes_lista),
        "resultados": resultados_info,
        "limpieza": copia_limpia,
        "ejecutando": ejec,
        "accion_actual": accion,
        "codigo_salida": salida_code
    }


def ejecutar_herramienta(comando, accion_nombre):
    """Ejecuta un comando en un hilo separado capturando salida en vivo."""
    global PROCESO_ACTUAL, LOGS_EJECUCION, EJECUTANDO, ACCION_ACTUAL, CODIGO_SALIDA

    with LOCK:
        if EJECUTANDO:
            return False
        EJECUTANDO = True
        ACCION_ACTUAL = accion_nombre
        LOGS_EJECUCION = []
        CODIGO_SALIDA = None

    def _tarea():
        global EJECUTANDO, CODIGO_SALIDA, PROCESO_ACTUAL
        try:
            cmd = [sys.executable, "-m"] + comando
            proc = subprocess.Popen(
                cmd,
                cwd=str(RAIZ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1
            )
            PROCESO_ACTUAL = proc

            for linea in iter(proc.stdout.readline, ''):
                if linea:
                    with LOCK:
                        LOGS_EJECUCION.append(linea.rstrip("\r\n"))

            proc.stdout.close()
            code = proc.wait()
            with LOCK:
                CODIGO_SALIDA = code
        except Exception as ex:
            with LOCK:
                LOGS_EJECUCION.append(f"Error al ejecutar: {ex}")
                CODIGO_SALIDA = 1
        finally:
            with LOCK:
                EJECUTANDO = False
                PROCESO_ACTUAL = None

    t = threading.Thread(target=_tarea, daemon=True)
    t.start()
    return True


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(RAIZ), **kwargs)

    def log_message(self, format, *args):
        # Desactivar logs ruidosos en la terminal estándar
        pass

    def do_GET(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path

        if path in ("", "/", "/index.html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            idx = RAIZ / "index.html"
            self.wfile.write(idx.read_bytes())
            return

        if path == "/api/estado":
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(obtener_estado(), ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/logs":
            with LOCK:
                data = {
                    "ejecutando": EJECUTANDO,
                    "accion": ACCION_ACTUAL,
                    "codigo_salida": CODIGO_SALIDA,
                    "logs": LOGS_EJECUCION[-800:]  # Últimas 800 líneas
                }
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode("utf-8"))
            return

        if path == "/api/abrir-archivo":
            qs = urllib.parse.parse_qs(url_parsed.query)
            rel = qs.get("ruta", [""])[0]
            target = (RAIZ / rel).resolve()
            if target.exists() and str(target).startswith(str(RAIZ)):
                try:
                    if os.name == "nt":
                        os.startfile(target)
                    elif sys.platform == "darwin":
                        subprocess.run(["open", str(target)], check=False)
                    else:
                        subprocess.run(["xdg-open", str(target)], check=False)
                except Exception:
                    pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        super().do_GET()

    def do_POST(self):
        url_parsed = urllib.parse.urlparse(self.path)
        path = url_parsed.path

        if path == "/api/ejecutar":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
            except Exception:
                datos = {}

            accion = datos.get("accion", "revisar")
            if accion == "revisar":
                ok = ejecutar_herramienta(["kit.revisar"], "Revisión completa de tesis")
            elif accion == "revisar_rapido":
                ok = ejecutar_herramienta(["kit.revisar", "--sin-similitud", "--sin-web"], "Revisión rápida (sin similitud)")
            elif accion == "limpiar":
                ok = ejecutar_herramienta(["kit.limpiar"], "Limpieza de caracteres invisibles")
            else:
                ok = False

            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "accion": accion}).encode("utf-8"))
            return

        if path == "/api/detener":
            global PROCESO_ACTUAL
            with LOCK:
                if PROCESO_ACTUAL:
                    try:
                        PROCESO_ACTUAL.terminate()
                    except Exception:
                        pass
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
            return

        if path == "/api/eliminar-fuente":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
                nom = datos.get("nombre", "")
                target = (FUENTES_DIR / nom).resolve()
                if target.exists() and str(target).startswith(str(FUENTES_DIR)):
                    target.unlink()
                    resp = {"ok": True, "mensaje": "Archivo eliminado"}
                else:
                    resp = {"ok": False, "error": "Archivo no encontrado"}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path in ("/api/subir-tesis", "/api/subir-fuentes"):
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"):
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "Se requiere multipart/form-data"}')
                return

            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)

            # Extraer boundary
            m_bound = re.search(r'boundary=([^;]+)', content_type)
            if not m_bound:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"ok": false, "error": "Boundary no encontrado"}')
                return

            boundary = m_bound.group(1).strip().strip('"').encode("ascii")
            partes = body.split(b"--" + boundary)

            archivos_guardados = []
            es_tesis = (path == "/api/subir-tesis")
            destino_dir = TESIS_DIR if es_tesis else FUENTES_DIR
            destino_dir.mkdir(parents=True, exist_ok=True)

            for part in partes:
                if not part or part in (b"--\r\n", b"--", b"\r\n"):
                    continue
                    if b"\r\n\r\n" in part:
                        head, contenido = part.split(b"\r\n\r\n", 1)
                        if contenido.endswith(b"\r\n"):
                            contenido = contenido[:-2]
                        head_str = head.decode("utf-8", errors="ignore")
                    m_fn = re.search(r'filename="([^"]+)"', head_str)
                    if m_fn:
                        filename = Path(m_fn.group(1)).name
                        if not filename:
                            continue

                        # Validaciones de extensión
                        ext = Path(filename).suffix.lower()
                        if es_tesis and ext != ".docx":
                            continue
                        if not es_tesis and ext not in (".pdf", ".docx", ".odt", ".txt"):
                            continue

                        # Si es tesis, podemos archivar la tesis anterior
                        out_path = destino_dir / filename
                        out_path.write_bytes(contenido)
                        archivos_guardados.append(filename)

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({
                "ok": True,
                "archivos": archivos_guardados,
                "total": len(archivos_guardados)
            }).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()


def iniciar_servidor(puerto_inicial=8000, abrir_navegador=True):
    socketserver.TCPServer.allow_reuse_address = True
    for puerto in range(puerto_inicial, puerto_inicial + 20):
        try:
            servidor = socketserver.ThreadingTCPServer(("127.0.0.1", puerto), Handler)
            url = f"http://127.0.0.1:{puerto}/"
            print("=" * 65)
            print(f" Centro de Control - Revisión de Tesis")
            print(f" Servidor iniciado en: {url}")
            print("=" * 65)
            print(" Presiona Ctrl+C en esta ventana para detener el servidor.\n")
            if abrir_navegador:
                threading.Timer(0.8, lambda: webbrowser.open(url)).start()
            servidor.serve_forever()
            break
        except OSError as e:
            if "Address already in use" in str(e) or e.errno == 10048 or "10048" in str(e):
                continue
            raise


if __name__ == "__main__":
    puerto = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        puerto = int(sys.argv[1])
    iniciar_servidor(puerto)

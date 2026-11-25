"""Servidor web local para el Centro de Control de Revisión de Tesis.

Permite:
1. Subir la tesis a 1-MI-TESIS.
2. Subir y gestionar archivos en 2-FUENTES.
3. Ejecutar 'revisar' o 'limpiar' con salida de consola en vivo.
4. Abrir y explorar los resultados (panel.html, comparaciones).
"""
import http.server
import json
import os
import re
import shutil
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
PROGRESO_ACTUAL = 0
PASO_ACTUAL = ""
TESIS_SELECCIONADA = None
FUENTE_SELECCIONADA = "__todas__"
LOCK = threading.Lock()


def _limpiar_nombre_carpeta(nombre: str) -> str:
    """Normaliza el nombre de subcarpeta evitando traversal o caracteres inválidos."""
    limpio = re.sub(r'[<>:"/\\|?*]+', "_", (nombre or "").strip()).strip(". ")
    return limpio


def _formatear_tamano(n_bytes):
    if n_bytes < 1024:
        return f"{n_bytes} B"
    elif n_bytes < 1024 * 1024:
        return f"{n_bytes / 1024:.1f} KB"
    return f"{n_bytes / (1024 * 1024):.1f} MB"


def obtener_estado():
    """Retorna un resumen estructurado del estado de las carpetas y resultados."""
    global TESIS_SELECCIONADA, FUENTE_SELECCIONADA
    with LOCK:
        ejec = EJECUTANDO
        accion = ACCION_ACTUAL
        salida_code = CODIGO_SALIDA
        prog = PROGRESO_ACTUAL
        paso = PASO_ACTUAL

    # 1. Tesis (agrupadas por carpeta de tesis, admitiendo varias versiones .docx por tesis)
    tesis_lista = []
    carpetas_tesis = []
    tesis_activa = None
    if TESIS_DIR.exists():
        carpetas_tesis = sorted(
            d.name for d in TESIS_DIR.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
        docs = sorted([p for p in TESIS_DIR.rglob("*.docx") if not p.name.startswith("~$")],
                      key=lambda p: p.stat().st_mtime, reverse=True)
        for p in docs:
            st = p.stat()
            rel = p.relative_to(TESIS_DIR)
            rel_str = str(rel).replace("\\", "/")
            carpeta = rel.parts[0] if len(rel.parts) > 1 else ""
            slug = carpeta if carpeta else p.stem

            t_res_dir = RESULTADOS_DIR / slug
            tiene_res = (t_res_dir / "panel.html").exists()
            panel_url = f"3-RESULTADOS/{slug}/panel.html" if tiene_res else None

            tesis_lista.append({
                "nombre": p.name,
                "ruta_relativa": rel_str,
                "carpeta": carpeta,
                "slug": slug,
                "tamano": _formatear_tamano(st.st_size),
                "bytes": st.st_size,
                "modificado": time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime)),
                "activa": False,
                "tiene_resultados": tiene_res,
                "panel_url": panel_url
            })

        if tesis_lista:
            sel = None
            if TESIS_SELECCIONADA:
                sel = next((t for t in tesis_lista if t["ruta_relativa"] == TESIS_SELECCIONADA or t["nombre"] == TESIS_SELECCIONADA or t["slug"] == TESIS_SELECCIONADA), None)
            if not sel:
                sel = tesis_lista[0]
            TESIS_SELECCIONADA = sel["ruta_relativa"]
            sel["activa"] = True
            tesis_activa = sel

    # 2. Fuentes y conjuntos intercambiables en 2-FUENTES
    fuentes_todas = []
    fuentes_carpetas = []
    exts_validas = {".pdf", ".docx", ".odt", ".txt"}
    if FUENTES_DIR.exists():
        subcarpetas = sorted(
            d for d in FUENTES_DIR.iterdir()
            if d.is_dir() and d.name != "web" and not d.name.startswith(".")
        )
        for f in sorted(FUENTES_DIR.rglob("*")):
            if f.is_file() and f.suffix.lower() in exts_validas and not f.name.startswith("~$") and f.name.upper() != "LEEME.TXT":
                rel = str(f.relative_to(FUENTES_DIR)).replace("\\", "/")
                parts = f.relative_to(FUENTES_DIR).parts
                carpeta_f = parts[0] if (len(parts) > 1 and parts[0] != "web") else "__raiz__"
                fuentes_todas.append({
                    "nombre": rel,
                    "carpeta": carpeta_f,
                    "tamano": _formatear_tamano(f.stat().st_size),
                    "tipo": f.suffix.lower().replace(".", "").upper(),
                    "es_web": "web/" in rel
                })

        total_raiz = sum(1 for x in fuentes_todas if x["carpeta"] == "__raiz__")
        fuentes_carpetas.append({
            "id": "__todas__",
            "nombre": "Todas las fuentes (2-FUENTES completo)",
            "total": len(fuentes_todas)
        })
        if subcarpetas and total_raiz > 0:
            fuentes_carpetas.append({
                "id": "__raiz__",
                "nombre": "General (raíz de 2-FUENTES)",
                "total": total_raiz
            })
        for d in subcarpetas:
            cnt = sum(1 for x in fuentes_todas if x["carpeta"] == d.name)
            fuentes_carpetas.append({
                "id": d.name,
                "nombre": d.name,
                "total": cnt
            })

        ids_validos = {c["id"] for c in fuentes_carpetas}
        if FUENTE_SELECCIONADA not in ids_validos:
            FUENTE_SELECCIONADA = "__todas__"

    if FUENTE_SELECCIONADA == "__todas__":
        fuentes_lista = fuentes_todas
    else:
        fuentes_lista = [x for x in fuentes_todas if x["carpeta"] == FUENTE_SELECCIONADA]

    # 3. Resultados vinculados a la tesis activa
    panel_path = None
    datos_path = None
    panel_url = None
    if tesis_activa:
        slug = tesis_activa["slug"]
        t_res_dir = RESULTADOS_DIR / slug
        if (t_res_dir / "panel.html").exists():
            panel_path = t_res_dir / "panel.html"
            datos_path = t_res_dir / "datos.json"
            panel_url = f"3-RESULTADOS/{slug}/panel.html"

    # Fallback a raíz solo si el archivo evaluado coincide con la tesis activa
    if not panel_path and tesis_activa and (RESULTADOS_DIR / "panel.html").exists() and (RESULTADOS_DIR / "datos.json").exists():
        try:
            dt_root = json.loads((RESULTADOS_DIR / "datos.json").read_text(encoding="utf-8"))
            if dt_root.get("archivo") == tesis_activa["nombre"] or dt_root.get("carpeta_tesis") == tesis_activa["slug"]:
                panel_path = RESULTADOS_DIR / "panel.html"
                datos_path = RESULTADOS_DIR / "datos.json"
                panel_url = "3-RESULTADOS/panel.html"
        except Exception:
            pass

    resultados_info = {"existe": bool(panel_path and panel_path.exists()), "panel_url": panel_url or "3-RESULTADOS/panel.html"}
    if panel_path and panel_path.exists():
        st = panel_path.stat()
        resultados_info["fecha"] = time.strftime("%Y-%m-%d %H:%M", time.localtime(st.st_mtime))
        if datos_path and datos_path.exists():
            try:
                dt = json.loads(datos_path.read_text(encoding="utf-8"))
                resultados_info["archivo"] = dt.get("archivo", "")
                resultados_info["fuentes_usadas"] = dt.get("fuentes_usadas", "")
                sim = dt.get("similitud", {})
                cit = dt.get("citas", {})
                inv = dt.get("invisibles", {})
                est = dt.get("estructura", {})
                w = dt.get("web", [])
                max_s = sim["fuentes"][0]["porcentaje"] if sim.get("fuentes") else 0
                sin_c = len([p for p in sim.get("pasajes", []) if p.get("estado") == "Sin comillas"])
                c_din = cit.get("campos_cita", 0)
                c_mano = len(cit.get("texto_plano", []))
                c_mal = len(cit.get("sin_fuente", [])) + len(cit.get("sin_citar", []))
                resultados_info["resumen"] = {
                    "max_sim": round(max_s, 1),
                    "sin_comillas": sin_c,
                    "citas_totales": c_din + c_mano,
                    "citas_din": c_din,
                    "citas_mano": c_mano,
                    "citas_mal": c_mal,
                    "invisibles": inv.get("total", 0),
                    "palabras": est.get("palabras", 0),
                    "enlaces_mal": len([x for x in w if x.get("estado") != "OK"])
                }
            except Exception:
                pass

    # 4. Copia limpia de invisibles de la tesis activa
    copia_limpia = None
    if tesis_activa:
        slug = tesis_activa["slug"]
        t_res_dir = RESULTADOS_DIR / slug
        limpias = []
        if t_res_dir.exists():
            limpias = sorted(t_res_dir.glob("*sin invisibles*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not limpias and RESULTADOS_DIR.exists():
            stem_limpio = tesis_activa["nombre"].replace(".docx", "")
            limpias = sorted(RESULTADOS_DIR.glob(f"*{stem_limpio}*sin invisibles*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if limpias:
            rel_limpia = str(limpias[0].relative_to(RESULTADOS_DIR)).replace("\\", "/")
            copia_limpia = {
                "nombre": limpias[0].name,
                "tamano": _formatear_tamano(limpias[0].stat().st_size),
                "url": f"3-RESULTADOS/{rel_limpia}"
            }

    return {
        "tesis": tesis_activa,
        "tesis_lista": tesis_lista,
        "carpetas_tesis": carpetas_tesis,
        "total_tesis": len(tesis_lista),
        "fuentes": fuentes_lista,
        "fuentes_carpetas": fuentes_carpetas,
        "fuente_seleccionada": FUENTE_SELECCIONADA,
        "total_fuentes": len(fuentes_lista),
        "total_fuentes_global": len(fuentes_todas),
        "resultados": resultados_info,
        "limpieza": copia_limpia,
        "ejecutando": ejec,
        "accion_actual": accion,
        "codigo_salida": salida_code,
        "progreso": prog,
        "paso": paso
    }


def ejecutar_herramienta(comando, accion_nombre):
    """Ejecuta un comando en un hilo separado capturando salida en vivo y progreso."""
    global PROCESO_ACTUAL, LOGS_EJECUCION, EJECUTANDO, ACCION_ACTUAL, CODIGO_SALIDA, PROGRESO_ACTUAL, PASO_ACTUAL

    with LOCK:
        if EJECUTANDO:
            return False
        EJECUTANDO = True
        ACCION_ACTUAL = accion_nombre
        LOGS_EJECUCION = []
        CODIGO_SALIDA = None
        PROGRESO_ACTUAL = 5
        PASO_ACTUAL = "Iniciando proceso..."

    def _tarea():
        global EJECUTANDO, CODIGO_SALIDA, PROCESO_ACTUAL, PROGRESO_ACTUAL, PASO_ACTUAL
        try:
            env = os.environ.copy()
            env["PYTHONUNBUFFERED"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"
            cmd = [sys.executable, "-u", "-m"] + comando
            proc = subprocess.Popen(
                cmd,
                cwd=str(RAIZ),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=env
            )
            PROCESO_ACTUAL = proc

            for linea in iter(proc.stdout.readline, ''):
                if linea:
                    texto = linea.rstrip("\r\n")
                    with LOCK:
                        LOGS_EJECUCION.append(texto)
                        # Detectar patrón de progreso: [PROGRESO: 45%] [4/5] Descripción
                        m_prog = re.search(r'\[PROGRESO:\s*(\d+)%\]\s*(.*)', texto)
                        if m_prog:
                            try:
                                PROGRESO_ACTUAL = int(m_prog.group(1))
                                if m_prog.group(2):
                                    PASO_ACTUAL = m_prog.group(2).strip()
                            except ValueError:
                                pass

            proc.stdout.close()
            code = proc.wait()
            with LOCK:
                CODIGO_SALIDA = code
                if code == 0:
                    PROGRESO_ACTUAL = 100
                    PASO_ACTUAL = "Completado con éxito"
        except Exception as ex:
            with LOCK:
                LOGS_EJECUCION.append(f"Error al ejecutar: {ex}")
                CODIGO_SALIDA = 1
                PASO_ACTUAL = f"Error: {ex}"
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
                    "progreso": PROGRESO_ACTUAL,
                    "paso": PASO_ACTUAL,
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
        global TESIS_SELECCIONADA, FUENTE_SELECCIONADA
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
            tesis_solicitada = datos.get("tesis") or TESIS_SELECCIONADA
            fuente_solicitada = datos.get("fuentes") or FUENTE_SELECCIONADA
            extra_tesis = ["--tesis", tesis_solicitada] if tesis_solicitada else []
            extra_fuentes = ["--fuentes", fuente_solicitada] if fuente_solicitada else []

            if accion == "revisar":
                ok = ejecutar_herramienta(["kit.revisar"] + extra_tesis + extra_fuentes, "Revisión completa de tesis")
            elif accion == "revisar_rapido":
                ok = ejecutar_herramienta(["kit.revisar", "--sin-similitud", "--sin-web"] + extra_tesis + extra_fuentes, "Revisión rápida (sin similitud)")
            elif accion == "limpiar":
                ok = ejecutar_herramienta(["kit.limpiar"] + extra_tesis, "Limpieza de caracteres invisibles")
            else:
                ok = False

            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": ok, "accion": accion, "tesis": tesis_solicitada, "fuentes": fuente_solicitada}).encode("utf-8"))
            return

        if path == "/api/seleccionar-fuente":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
                f_id = datos.get("fuentes", "__todas__")
                if f_id in ("__todas__", "__raiz__") or (FUENTES_DIR / f_id).is_dir():
                    FUENTE_SELECCIONADA = f_id
                    resp = {"ok": True, "fuente_seleccionada": f_id}
                else:
                    resp = {"ok": False, "error": "Carpeta de fuentes no encontrada"}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path in ("/api/crear-carpeta-tesis", "/api/crear-carpeta-fuentes"):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
                nombre = _limpiar_nombre_carpeta(datos.get("nombre", ""))
                es_tesis_dir = (path == "/api/crear-carpeta-tesis")
                base = TESIS_DIR if es_tesis_dir else FUENTES_DIR
                if not nombre or (not es_tesis_dir and nombre.lower() == "web"):
                    resp = {"ok": False, "error": "Nombre de carpeta inválido"}
                else:
                    (base / nombre).mkdir(parents=True, exist_ok=True)
                    if not es_tesis_dir:
                        FUENTE_SELECCIONADA = nombre
                    resp = {"ok": True, "nombre": nombre}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/seleccionar-tesis":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
                nom = datos.get("nombre", "")
                target = (TESIS_DIR / nom).resolve()
                if not target.exists():
                    for p in TESIS_DIR.rglob("*.docx"):
                        if not p.name.startswith("~$") and (p.name == nom or p.stem == nom or str(p.relative_to(TESIS_DIR)).replace("\\", "/") == nom):
                            target = p.resolve()
                            nom = str(p.relative_to(TESIS_DIR)).replace("\\", "/")
                            break
                if target.exists() and str(target).startswith(str(TESIS_DIR.resolve())):
                    TESIS_SELECCIONADA = nom
                    resp = {"ok": True, "activa": nom}
                else:
                    resp = {"ok": False, "error": "Archivo no encontrado"}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/eliminar-tesis":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="ignore")
            try:
                datos = json.loads(body)
                nom = datos.get("nombre", "")
                target = (TESIS_DIR / nom).resolve()
                if not target.exists():
                    for p in TESIS_DIR.rglob("*.docx"):
                        if not p.name.startswith("~$") and (p.name == nom or p.stem == nom or str(p.relative_to(TESIS_DIR)).replace("\\", "/") == nom):
                            target = p.resolve()
                            nom = str(p.relative_to(TESIS_DIR)).replace("\\", "/")
                            break
                if target.exists() and str(target).startswith(str(TESIS_DIR.resolve())):
                    parent = target.parent
                    target.unlink()
                    if parent != TESIS_DIR and parent.exists() and not any(parent.iterdir()):
                        shutil.rmtree(parent, ignore_errors=True)
                    if TESIS_SELECCIONADA in (nom, target.name):
                        TESIS_SELECCIONADA = None
                    resp = {"ok": True, "mensaje": "Tesis eliminada"}
                else:
                    resp = {"ok": False, "error": "Archivo no encontrado"}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/vaciar-tesis":
            try:
                borrados = 0
                if TESIS_DIR.exists():
                    for item in list(TESIS_DIR.iterdir()):
                        if item.name.upper() == "LEEME.TXT":
                            continue
                        if item.is_file():
                            item.unlink(missing_ok=True)
                            borrados += 1
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                            borrados += 1
                TESIS_SELECCIONADA = None
                resp = {"ok": True, "borrados": borrados}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/organizar-carpetas":
            try:
                movidos = 0
                if TESIS_DIR.exists():
                    for f in list(TESIS_DIR.glob("*.docx")):
                        if f.name.startswith("~$"):
                            continue
                        folder = TESIS_DIR / f.stem
                        folder.mkdir(parents=True, exist_ok=True)
                        dest = folder / f.name
                        if not dest.exists():
                            shutil.move(str(f), str(dest))
                            movidos += 1
                resp = {"ok": True, "movidos": movidos}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
            return

        if path == "/api/vaciar-fuentes":
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="ignore") if length else ""
                try:
                    datos = json.loads(body) if body else {}
                except Exception:
                    datos = {}
                carpeta = datos.get("carpeta") or FUENTE_SELECCIONADA

                borrados = 0
                if carpeta and carpeta not in ("__todas__", "__raiz__"):
                    target_dir = (FUENTES_DIR / carpeta).resolve()
                    if target_dir.is_dir() and str(target_dir).startswith(str(FUENTES_DIR.resolve())):
                        for item in list(target_dir.iterdir()):
                            if item.is_file():
                                item.unlink(missing_ok=True)
                                borrados += 1
                            elif item.is_dir():
                                shutil.rmtree(item, ignore_errors=True)
                                borrados += 1
                elif carpeta == "__raiz__" and FUENTES_DIR.exists():
                    for item in list(FUENTES_DIR.iterdir()):
                        if item.name.upper() == "LEEME.TXT":
                            continue
                        if item.is_file():
                            item.unlink(missing_ok=True)
                            borrados += 1
                        elif item.is_dir() and item.name == "web":
                            shutil.rmtree(item, ignore_errors=True)
                            borrados += 1
                elif FUENTES_DIR.exists():
                    for item in list(FUENTES_DIR.iterdir()):
                        if item.name.upper() == "LEEME.TXT":
                            continue
                        if item.is_file():
                            item.unlink(missing_ok=True)
                            borrados += 1
                        elif item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                            borrados += 1
                resp = {"ok": True, "borrados": borrados}
            except Exception as e:
                resp = {"ok": False, "error": str(e)}

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode("utf-8"))
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
            qs = urllib.parse.parse_qs(url_parsed.query)
            carpeta_req = _limpiar_nombre_carpeta(qs.get("carpeta", [""])[0])
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

                        # Si es tesis, guardarla en la carpeta elegida o su propia carpeta de tesis
                        if es_tesis:
                            nombre_sub = carpeta_req or Path(filename).stem
                            sub_carpeta = destino_dir / nombre_sub
                            sub_carpeta.mkdir(parents=True, exist_ok=True)
                            out_path = sub_carpeta / filename
                            out_path.write_bytes(contenido)
                            rel_str = str(out_path.relative_to(destino_dir)).replace("\\", "/")
                            TESIS_SELECCIONADA = rel_str
                            archivos_guardados.append(rel_str)
                        else:
                            if carpeta_req and carpeta_req not in ("__todas__", "__raiz__"):
                                sub_f = destino_dir / carpeta_req
                                sub_f.mkdir(parents=True, exist_ok=True)
                                out_path = sub_f / filename
                            else:
                                out_path = destino_dir / filename
                            out_path.write_bytes(contenido)
                            archivos_guardados.append(str(out_path.relative_to(destino_dir)).replace("\\", "/"))

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

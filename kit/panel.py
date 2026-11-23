"""Panel HTML autocontenido con los resultados."""
from html import escape as e


def _estado(ok, warn=False):
    return "ok" if ok else ("warn" if warn else "bad")


def _kpi(titulo, valor, estado, detalle=""):
    return (f'<div class="kpi {estado}"><div class="kv">{e(str(valor))}</div>'
            f'<div class="kt">{e(titulo)}</div><div class="kd">{e(detalle)}</div></div>')


def _tabla(cabeceras, filas, vacio="Nada para mostrar."):
    if not filas:
        return f'<p class="vacio">{e(vacio)}</p>'
    th = "".join(f"<th>{e(c)}</th>" for c in cabeceras)
    trs = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in f) + "</tr>" for f in filas)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def generar(d):
    sim, cit, inv, est = d["similitud"], d["citas"], d["invisibles"], d["estructura"]
    sin_comillas = [p for p in sim["pasajes"] if p["estado"] == "Sin comillas"]
    max_sim = sim["fuentes"][0]["porcentaje"] if sim["fuentes"] else 0
    citas_mal = len(cit["sin_fuente"]) + len(cit["sin_citar"]) + (0 if cit["hay_almacen"] else 1)

    kpis = "".join([
        _kpi("Palabras", f'{est["palabras"]:,}'.replace(",", "."), "neutral", f'{est["tablas"]} tablas · {est["figuras"]} figuras'),
        _kpi("Similitud máxima", f"{max_sim:.1f} %", _estado(max_sim < 5, max_sim < 15),
             sim["fuentes"][0]["fuente"] if sim["fuentes"] else "sin fuentes"),
        _kpi("Párrafos copiados sin comillas", len(sin_comillas), _estado(not sin_comillas),
             f'de {len(sim["pasajes"])} coincidencias largas'),
        _kpi("Problemas de citas", citas_mal, _estado(citas_mal == 0),
             f'{cit["campos_cita"]} citas · {cit["fuentes_registradas"]} fuentes'),
        _kpi("Citas escritas a mano", len(cit["texto_plano"]), _estado(not cit["texto_plano"], True), "no enlazadas a Referencias"),
        _kpi("Caracteres invisibles", inv["total"], _estado(inv["total"] == 0, True), "de copiar y pegar"),
        _kpi("Letras de otro alfabeto", len(inv["sustituidos"]), _estado(not inv["sustituidos"]), "cirílico o griego camuflado"),
        _kpi("Tablas y figuras", len(est["problemas"]), _estado(not est["problemas"], True), "problemas de numeración"),
    ])

    alertas = []
    if not cit["hay_almacen"]:
        alertas.append("El documento no tiene el almacén de fuentes de Word (customXml). Las citas van a mostrar "
                       "error. ¿Lo pasaste por alguna herramienta de limpieza? Volvé a una copia anterior.")
    if not cit["hay_bibliografia"]:
        alertas.append("No se encontró la lista de Referencias automática (campo BIBLIOGRAPHY).")
    if sim.get("error"):
        alertas.append(sim["error"])
    if sim.get("ilegibles"):
        alertas.append("No se pudo leer texto de: " + ", ".join(sim["ilegibles"])
                       + ". Suelen ser PDF escaneados; pasalos por OCR o conseguí la versión digital.")
    alerta_html = "".join(f'<div class="alerta">⚠ {e(a)}</div>' for a in alertas)

    hist = d.get("historial", [])
    hist_html = _tabla(["Fecha", "Archivo", "Similitud máx.", "Sin comillas", "Problemas de citas", "Invisibles"],
                       [[e(h["fecha"]), e(h["archivo"]), f'{h["max_sim"]:.1f} %', h["sin_comillas"], h["citas_mal"], h["invisibles"]]
                        for h in reversed(hist[-10:])])

    s_fuentes = _tabla(["Fuente", "Similitud", "Comparación"],
                       [[e(f["fuente"]), f'{f["porcentaje"]:.2f} %', f'<a href="{e(f["comparacion"])}" target="_blank">ver lado a lado</a>']
                        for f in sim["fuentes"]], "Poné tus fuentes (PDF, DOCX, TXT) en la carpeta 2-FUENTES.")
    s_pasajes = _tabla(["Estado", "Fuente", "Palabras", "Fragmento que coincide", "Párrafo de tu tesis"],
                       [[f'<span class="tag {"bad" if p["estado"]=="Sin comillas" else "warn" if p["estado"]=="No ubicado" else "ok"}">{e(p["estado"])}</span>',
                         e(p["fuente"]), p["palabras"], e(p["fragmento"]), e(p["parrafo"])] for p in sim["pasajes"]],
                       "No hay coincidencias largas con tus fuentes.")
    s_citas = (_tabla(["Etiqueta citada sin fuente registrada"], [[e(t)] for t in cit["sin_fuente"]], "Todas las citas tienen su fuente.")
               + _tabla(["Fuente registrada que nunca se cita", "Título"], [[e(t), e(ti)] for t, ti in cit["sin_citar"]],
                        "Todas las fuentes registradas se citan.")
               + _tabla(["Cita escrita a mano", "Contexto"], [[e(c), e(x)] for c, x in cit["texto_plano"]],
                        "No hay citas escritas a mano."))
    s_inv = (_tabla(["Tipo", "Cantidad"], [[e(k), v] for k, v in inv["por_tipo"].items()], "No hay caracteres invisibles.")
             + _tabla(["Dónde", "Tipo", "Contexto (⟦·⟧ = invisible)"], [[e(a), e(b), e(c)] for a, b, c in inv["ejemplos"][:60]], "")
             + _tabla(["Dónde", "Palabra", "Contexto"], [[e(a), e(b), e(c)] for a, b, c in inv["sustituidos"][:60]],
                      "No hay letras de otros alfabetos camufladas."))
    s_est = _tabla(["Problema"], [[e(p)] for p in est["problemas"]], "Numeración de tablas y figuras correcta.")

    return f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Revisión de tesis</title>
<style>
:root{{--bg:#f6f7f9;--card:#fff;--tx:#1f2937;--mut:#6b7280;--ok:#0f766e;--warn:#b45309;--bad:#b91c1c;--bd:#e5e7eb}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111318;--card:#1b1e25;--tx:#e5e7eb;--mut:#9ca3af;--bd:#2b2f38}}}}
*{{box-sizing:border-box}}body{{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--tx)}}
header{{padding:24px 32px 8px}}h1{{margin:0;font-size:22px}}.sub{{color:var(--mut)}}
main{{padding:8px 32px 48px;max-width:1300px}}
.kpis{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px;margin:16px 0}}
.kpi{{background:var(--card);border:1px solid var(--bd);border-left:5px solid var(--mut);border-radius:10px;padding:14px}}
.kpi.ok{{border-left-color:var(--ok)}}.kpi.warn{{border-left-color:var(--warn)}}.kpi.bad{{border-left-color:var(--bad)}}
.kv{{font-size:28px;font-weight:700}}.kt{{font-weight:600}}.kd{{color:var(--mut);font-size:13px}}
.alerta{{background:#fef2f2;color:#7f1d1d;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;margin:8px 0}}
details{{background:var(--card);border:1px solid var(--bd);border-radius:10px;margin:12px 0;padding:6px 16px}}
summary{{cursor:pointer;font-weight:600;padding:8px 0}}
table{{border-collapse:collapse;width:100%;margin:8px 0 16px;font-size:14px}}
th,td{{border-bottom:1px solid var(--bd);padding:6px 8px;text-align:left;vertical-align:top}}th{{color:var(--mut);font-weight:600}}
.tag{{padding:2px 8px;border-radius:99px;font-size:12px;font-weight:600;white-space:nowrap;color:#fff}}
.tag.ok{{background:var(--ok)}}.tag.warn{{background:var(--warn)}}.tag.bad{{background:var(--bad)}}
.vacio{{color:var(--mut)}}a{{color:inherit}}
.nota{{color:var(--mut);font-size:13px}}
</style></head><body>
<header><h1>Revisión de tesis</h1><div class="sub">{e(d["archivo"])} · {e(d["fecha"])}</div></header>
<main>
{alerta_html}
<div class="kpis">{kpis}</div>
<p class="nota">El porcentaje acá no es el que dará Plagiarism Checker X: solo compara con tus fuentes de 2-FUENTES. Sirve para saber <b>dónde</b> corregir.</p>
<details open><summary>Párrafos que coinciden con tus fuentes</summary>
<p class="nota">“Sin comillas”: poné el texto entre comillas con su cita (autor, año y página o artículo) o reescribilo con tus palabras manteniendo la cita.</p>{s_pasajes}</details>
<details><summary>Similitud por fuente</summary>{s_fuentes}</details>
<details><summary>Citas y referencias</summary>{s_citas}</details>
<details><summary>Caracteres invisibles y letras camufladas</summary>
<p class="nota">Llegan al copiar y pegar desde PDF, web o chats. Las letras de otro alfabeto dentro de palabras en español son un truco conocido contra los detectores y los tribunales las consideran fraude: corregilas. Para quitar los invisibles sin romper citas usá <b>LIMPIAR-INVISIBLES</b>.</p>{s_inv}</details>
<details><summary>Numeración de tablas y figuras</summary>{s_est}</details>
<details><summary>Historial de revisiones</summary>{hist_html}</details>
</main></body></html>"""

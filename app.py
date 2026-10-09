"""
app.py - Espacio de trabajo de prospección (Streamlit Cloud + Supabase).
"""
import csv
import datetime
import html
import io
import os
import re
import time
from urllib.parse import quote
 
import requests
import streamlit as st
from openai import OpenAI
 
CAMPOS = [
    "place_id", "nombre", "categoria", "direccion", "telefono", "rating", "num_resenas",
    "web", "maps", "mensaje", "link_whatsapp", "estado", "fecha_contacto",
]
# Columnas que se mandan a Google Sheets (place_id debe ir primero: es la llave).
COLUMNAS_HOJA = ["place_id", "nombre", "telefono", "categoria", "rating",
                 "num_resenas", "estado", "fecha_contacto", "maps", "mensaje"]
ESTADOS = ["nuevo", "contactado", "respondio", "cliente", "descartado"]
ETIQUETA = {"nuevo": "Nuevo", "contactado": "Contactado", "respondio": "Respondió",
            "cliente": "Cliente", "descartado": "Descartado"}
COLOR = {"nuevo": "#1D4E89", "contactado": "#A86A00", "respondio": "#1F7A5A",
         "cliente": "#14532D", "descartado": "#8A94A0"}
API = "https://api.apify.com/v2"
ACTOR = "compass~crawler-google-places"
MENSAJE_SEGUIMIENTO = (
    "Hola, buen día. Solo paso a preguntar si pudo ver mi mensaje sobre el menú "
    "digital. Con gusto les preparo un ejemplo con sus platillos, sin compromiso."
)
 
st.set_page_config(page_title="Prospección de restaurantes", layout="wide",
                   initial_sidebar_state="collapsed")
 
ESTILO = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&display=swap');
:root {
  --bg:#EEF0F3; --surface:#FFFFFF; --ink:#17202B; --muted:#5E6A78; --line:#D8DDE3;
  --accent:#1D4E89; --accent-soft:#E6EDF6;
}
.stApp, [data-testid="stAppViewContainer"] { background:var(--bg); color:var(--ink);
  font-family:'IBM Plex Sans', system-ui, -apple-system, 'Segoe UI', sans-serif; }
input, textarea, button { font-family:inherit !important; }
footer, [data-testid="stDecoration"] { display:none !important; }
.block-container { padding-top:4.5rem; padding-bottom:3rem; max-width:1280px; }
[data-testid="stSidebar"] { background:#E3E7EC; border-right:1px solid var(--line); }
 
/* Encabezado y embudo */
.topbar { display:flex; align-items:baseline; justify-content:space-between;
  border-bottom:1px solid var(--line); padding-bottom:.6rem; margin-bottom:.9rem; }
.topbar .title { font-size:1.3rem; font-weight:600; letter-spacing:-.01em; }
.topbar .sub { font-size:.85rem; color:var(--muted); }
.pipe .bar { display:flex; height:6px; border-radius:3px; overflow:hidden; background:var(--line); }
.pipe .bar span { display:block; height:100%; }
.pipe .legend { display:flex; flex-wrap:wrap; gap:.4rem 1.5rem; margin-top:.6rem;
  font-size:.85rem; color:var(--muted); }
.pipe .legend b { color:var(--ink); font-weight:600; margin-left:.35rem;
  font-variant-numeric:tabular-nums; }
.pipe .legend i { display:inline-block; width:8px; height:8px; border-radius:2px; margin-right:.4rem; }
 
/* Pestañas */
[data-testid="stTabs"] { margin-top:.6rem; }
[data-testid="stTabs"] button[role="tab"] { font-weight:500; font-size:.95rem; }
 
/* Paneles */
[data-testid="stVerticalBlockBorderWrapper"] { background:var(--surface);
  border-color:var(--line) !important; border-radius:8px; }
.panel-title { font-size:.95rem; font-weight:600; margin-bottom:.2rem; }
.panel-help { font-size:.82rem; color:var(--muted); margin-bottom:.6rem; }
 
/* Controles */
.stButton button, .stDownloadButton button, [data-testid^="stBaseLinkButton"] {
  border-radius:4px; font-weight:500; }
[data-testid="stWidgetLabel"] p { font-size:.85rem; color:var(--muted); font-weight:500; }
 
/* Lista de prospectos */
.st-key-lista [data-testid="stVerticalBlock"] { gap:0; }
[class*="st-key-sel_"] button { justify-content:flex-start !important; text-align:left;
  border:none !important; background:transparent !important; color:var(--ink) !important;
  padding:.55rem .75rem .1rem !important; min-height:0 !important; border-radius:0 !important;
  font-weight:500; box-shadow:none !important; }
[class*="st-key-sel_"] button p { text-align:left; }
[class*="st-key-sel_"] button:hover { background:#F1F4F8 !important; }
[class*="st-key-sel_"] button[kind="primary"],
[class*="st-key-sel_"] [data-testid="stBaseButton-primary"] {
  background:var(--accent-soft) !important; box-shadow:inset 3px 0 0 var(--accent) !important; }
.row-meta { display:flex; justify-content:space-between; font-size:.78rem; color:var(--muted);
  padding:.05rem .75rem .6rem; border-bottom:1px solid var(--line);
  font-variant-numeric:tabular-nums; }
.row-meta span::before { content:""; display:inline-block; width:7px; height:7px;
  border-radius:2px; margin-right:.4rem; background:var(--c); }
 
/* Detalle */
.det-head { display:flex; align-items:center; justify-content:space-between; gap:1rem; }
.det-head .name { font-size:1.25rem; font-weight:600; letter-spacing:-.01em; }
.badge { display:inline-block; font-size:.8rem; font-weight:500; padding:.12rem .55rem;
  border:1px solid var(--c); color:var(--c); border-radius:4px; white-space:nowrap; }
.facts { display:grid; grid-template-columns:7rem 1fr; gap:.4rem 1rem; margin:.8rem 0 1rem;
  font-size:.9rem; }
.facts dt { color:var(--muted); }
.facts dd { margin:0; word-break:break-word; }
.facts a { color:var(--accent); }
.quote { border-left:3px solid var(--line); padding:.2rem .8rem; color:var(--muted);
  font-size:.9rem; white-space:pre-wrap; margin:.2rem 0 .9rem; }
.lbl { font-size:.8rem; color:var(--muted); font-weight:500; }
.empty { color:var(--muted); font-size:.9rem; padding:1.2rem .2rem; }
</style>
"""
st.markdown(ESTILO, unsafe_allow_html=True)
 
 
def secreto(nombre, defecto=""):
    try:
        return str(st.secrets[nombre])
    except Exception:  # noqa: BLE001
        return os.getenv(nombre, defecto)
 
 
def esc(texto):
    return html.escape(str(texto or ""))
 
 
# ---------------------------------------------------------------- login
def pedir_login():
    clave = secreto("APP_PASSWORD")
    if not clave:
        return  # sin contraseña configurada (uso local)
    if st.session_state.get("autorizado"):
        return
    izq, centro, _ = st.columns([1, 1, 1])
    with centro:
        st.markdown('<div class="topbar"><div class="title">Acceso</div></div>',
                    unsafe_allow_html=True)
        intento = st.text_input("Contraseña", type="password")
        if intento and intento == clave:
            st.session_state["autorizado"] = True
            st.rerun()
        elif intento:
            st.error("Contraseña incorrecta.")
    st.stop()
 
 
pedir_login()
 
 
# ---------------------------------------------------------------- utilidades
def col(fila, *nombres):
    for n in nombres:
        v = fila.get(n)
        if v not in (None, ""):
            return str(v).strip()
    return ""
 
 
def a_entero(valor):
    try:
        return int(float(valor))
    except (TypeError, ValueError):
        return 0
 
 
def esta_cerrado(fila):
    return any(col(fila, c).lower() in ("true", "1", "yes")
               for c in ("permanentlyClosed", "temporarilyClosed"))
 
 
def link_whatsapp(telefono, mensaje):
    digitos = re.sub(r"\D", "", telefono or "")
    if len(digitos) == 10:
        digitos = "52" + digitos
    return f"https://wa.me/{digitos}?text={quote(mensaje)}" if digitos else ""
 
 
# ---------------------------------------------------------------- Supabase
def _sb():
    url = secreto("SUPABASE_URL").rstrip("/") + "/rest/v1/prospectos"
    key = secreto("SUPABASE_KEY")
    headers = {"apikey": key, "Authorization": f"Bearer {key}",
               "Content-Type": "application/json"}
    return url, headers
 
 
def cargar():
    url, headers = _sb()
    r = requests.get(url, headers=headers, params={"select": "*", "limit": 10000}, timeout=60)
    r.raise_for_status()
    return {fila["place_id"]: fila for fila in r.json()}
 
 
def guardar_nuevos(filas_nuevas):
    """Inserta o actualiza varias filas a la vez."""
    if not filas_nuevas:
        return
    url, headers = _sb()
    headers = {**headers, "Prefer": "resolution=merge-duplicates"}
    cuerpo = [{c: str(f.get(c, "")) for c in CAMPOS} for f in filas_nuevas]
    r = requests.post(url, headers=headers, params={"on_conflict": "place_id"},
                      json=cuerpo, timeout=60)
    r.raise_for_status()
 
 
def actualizar(place_id, **cambios):
    if "mensaje" in cambios:
        filas_db = cargar()
        tel = filas_db.get(place_id, {}).get("telefono", "")
        cambios["link_whatsapp"] = link_whatsapp(tel, cambios["mensaje"])
    url, headers = _sb()
    r = requests.patch(url, headers=headers, params={"place_id": f"eq.{place_id}"},
                       json=cambios, timeout=60)
    r.raise_for_status()
 
 
def aplicar(place_id, **cambios):
    """Guarda cambios, refresca el selector de estado y recarga la página."""
    actualizar(place_id, **cambios)
    st.session_state.pop(f"est_{place_id}", None)
    st.rerun()
 
 
def al_cambiar_estado(place_id):
    actualizar(place_id, estado=st.session_state[f"est_{place_id}"])
 
 
# ------------------------------------------------------- Apify y OpenAI
def correr_apify(token, terminos, ubicacion, max_lugares, tope, log):
    headers = {"Authorization": f"Bearer {token}"}
    entrada = {
        "searchStringsArray": terminos,
        "locationQuery": ubicacion,
        "maxCrawledPlacesPerSearch": max_lugares,
        "language": "es",
        "skipClosedPlaces": True,
    }
    r = requests.post(f"{API}/acts/{ACTOR}/runs", headers=headers,
                      params={"maxTotalChargeUsd": tope}, json=entrada, timeout=60)
    r.raise_for_status()
    run_id = r.json()["data"]["id"]
    log("Búsqueda iniciada en Apify. Esperando resultados...")
 
    limite = time.time() + 15 * 60
    while True:
        time.sleep(5)
        s = requests.get(f"{API}/actor-runs/{run_id}", headers=headers, timeout=60)
        s.raise_for_status()
        data = s.json()["data"]
        estado = data["status"]
        if estado in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
            break
        if time.time() > limite:
            log("Se acabó el tiempo de espera; reviso lo que haya.")
            break
    if estado != "SUCCEEDED":
        log(f"La corrida terminó con estado {estado}. Descargo lo que haya.")
 
    items = requests.get(f"{API}/datasets/{data['defaultDatasetId']}/items", headers=headers,
                         params={"format": "json", "clean": "true"}, timeout=120)
    items.raise_for_status()
    return items.json()
 
 
def redactar(cliente, modelo, tu_nombre, nombre, categoria, rating, resenas, indicaciones=""):
    sistema = (
        "Eres un vendedor local de Saltillo, México, que escribe mensajes de WhatsApp "
        "cortos y naturales a dueños de restaurantes. Ofreces: (1) un menú digital "
        "que el cliente ve en su celular y (2) una tarjeta NFC que lleva directo a las "
        "reseñas de Google Maps. Reglas: máximo 60 palabras; tono amable y normal, "
        "como persona real (nada de frases de vendedor ni exageraciones); máximo 1 emoji; "
        "NO inventes datos del restaurante ni menciones platillos; NO digas que ya tienes "
        "las tarjetas en mano; NO critiques su número de reseñas; ofrece preparar un "
        "ejemplo de menú digital sin compromiso; termina con una pregunta corta; "
        f"firma con el nombre {tu_nombre or '[tu nombre]'}."
    )
    if indicaciones.strip():
        sistema += (
            "\n\nIndicaciones extra del vendedor sobre el enfoque o el tono del mensaje "
            "(síguelas, pero sin romper las reglas anteriores): " + indicaciones.strip()
        )
    usuario = (f'Restaurante: "{nombre}". Tipo de negocio: {categoria or "restaurante"}. '
               f"Calificación en Google: {rating}. Reseñas: {resenas}.")
    resp = cliente.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()
 
 
def redactar_seguimiento(cliente, modelo, tu_nombre, nombre, categoria, mensaje_anterior,
                         dias, indicaciones=""):
    sistema = (
        "Eres un vendedor local de Saltillo, México, que da seguimiento por WhatsApp a un "
        "dueño de restaurante que no ha respondido. Ofreces un menú digital y una tarjeta NFC "
        "a reseñas de Google Maps. Reglas: máximo 40 palabras; tono amable, natural y sin "
        "presionar (nada de frases de vendedor ni urgencia falsa); máximo 1 emoji; NO repitas "
        "el mensaje anterior ni lo copies; NO inventes datos ni menciones platillos; "
        "recuerda brevemente que ofreces preparar un ejemplo de menú sin compromiso; "
        "termina con una pregunta corta; "
        f"firma con el nombre {tu_nombre or '[tu nombre]'}."
    )
    if indicaciones.strip():
        sistema += "\n\nIndicaciones extra del vendedor (síguelas sin romper las reglas): " + indicaciones.strip()
    usuario = (f'Restaurante: "{nombre}". Tipo de negocio: {categoria or "restaurante"}. '
               f"Hace {dias} días le escribí este mensaje y no ha respondido:\n\n{mensaje_anterior}")
    resp = cliente.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()
 
 
# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.markdown('<div class="panel-title">Configuración</div>', unsafe_allow_html=True)
    apify_token = st.text_input("Token de Apify", value=secreto("APIFY_TOKEN"), type="password")
    openai_key = st.text_input("Clave de OpenAI", value=secreto("OPENAI_API_KEY"), type="password")
    tu_nombre = st.text_input("Tu nombre (firma del mensaje)", value=secreto("TU_NOMBRE"))
    modelo = st.text_input("Modelo de OpenAI", value=secreto("OPENAI_MODEL", "gpt-4o-mini"))
    dias_seg = st.number_input("Días antes del seguimiento", min_value=1, max_value=14, value=2)
 
# ---------------------------------------------------------------- datos de la sesión
try:
    filas = cargar()
except Exception as e:  # noqa: BLE001
    st.error(f"No se pudo leer la base de datos. Revisa SUPABASE_URL y SUPABASE_KEY. Detalle: {e}")
    st.stop()
 
hoy = datetime.date.today()
conteo = {e: sum(1 for f in filas.values() if f.get("estado") == e) for e in ESTADOS}
pendientes = []
for pid, f in filas.items():
    if f.get("estado") != "contactado":
        continue
    try:
        fecha = datetime.date.fromisoformat(f.get("fecha_contacto", ""))
    except ValueError:
        continue
    if (hoy - fecha).days >= dias_seg:
        pendientes.append((pid, f, (hoy - fecha).days))
 
# ---------------------------------------------------------------- encabezado
total = sum(conteo.values())
segmentos = "".join(
    f'<span style="width:{conteo[e] / total * 100:.2f}%;background:{COLOR[e]}"></span>'
    for e in ESTADOS if conteo[e]) if total else ""
leyenda = "".join(
    f'<span><i style="background:{COLOR[e]}"></i>{ETIQUETA[e]}<b>{conteo[e]}</b></span>'
    for e in ESTADOS)
st.markdown(
    '<div class="topbar"><div class="title">Prospección de restaurantes</div>'
    f'<div class="sub">{total} prospectos en total</div></div>'
    f'<div class="pipe"><div class="bar">{segmentos}</div><div class="legend">{leyenda}</div></div>',
    unsafe_allow_html=True)
 
tab1, tab2, tab3 = st.tabs(["Buscar", f"Prospectos ({total})", f"Seguimientos ({len(pendientes)})"])
 
# ---------------------------------------------------------------- pestaña 1
with tab1:
    izq, der = st.columns([3, 2], gap="large")
    with izq:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Qué buscar</div>'
                        '<div class="panel-help">Cambia la zona o el término en cada búsqueda para no '
                        'pagar por lugares repetidos.</div>', unsafe_allow_html=True)
            terminos_txt = st.text_input("Términos (separa con comas)", "restaurantes")
            ubicacion = st.text_input("Ciudad o zona", "Saltillo, Coahuila, Mexico")
            a, b = st.columns(2)
            max_lugares = a.slider("Lugares por búsqueda", 5, 50, 20)
            max_resenas = b.number_input("Máximo de reseñas", 0, 1000, 60)
    with der:
        with st.container(border=True):
            st.markdown('<div class="panel-title">Mensajes y gasto</div>'
                        '<div class="panel-help">Apify cobra cada lugar que trae, aunque ya lo tengas.</div>',
                        unsafe_allow_html=True)
            max_nuevos = st.slider("Mensajes a redactar", 1, 30, 5)
            tope = st.number_input("Tope de gasto en Apify (USD)", min_value=0.1, max_value=5.0,
                                   value=1.0, step=0.1)
            indicaciones = st.text_area(
                "Cómo quieres el mensaje (opcional)",
                placeholder="Ej: más corto y casual, empieza preguntando si hablo con el dueño.",
                height=90)
 
    if st.button("Buscar y redactar mensajes", type="primary"):
        if not (apify_token and openai_key):
            st.error("Faltan el token de Apify o la clave de OpenAI. Agrégalos en Configuración.")
        else:
            terminos = [t.strip() for t in terminos_txt.split(",") if t.strip()]
            try:
                with st.status("Trabajando...", expanded=True) as estado_ui:
                    resultados = correr_apify(apify_token, terminos, ubicacion,
                                              max_lugares, tope, st.write)
                    st.write(f"Lugares recibidos: {len(resultados)}")
                    existentes = cargar()
                    candidatos = []
                    for fila in resultados:
                        nombre = col(fila, "title", "name")
                        telefono = col(fila, "phoneUnformatted", "phone")
                        pid = col(fila, "placeId", "place_id", "cid", "url") or nombre
                        resenas = a_entero(col(fila, "reviewsCount", "reviews"))
                        if (not nombre or not telefono or esta_cerrado(fila)
                                or pid in existentes or resenas > max_resenas):
                            continue
                        candidatos.append((pid, nombre, telefono, fila))
                    candidatos.sort(key=lambda c: a_entero(col(c[3], "reviewsCount", "reviews")))
                    st.write(f"Prospectos nuevos con teléfono y hasta {max_resenas} reseñas: {len(candidatos)}")
 
                    cliente = OpenAI(api_key=openai_key)
                    nuevas = []
                    for pid, nombre, telefono, fila in candidatos[:max_nuevos]:
                        categoria = col(fila, "categoryName", "category")
                        rating = col(fila, "totalScore", "rating") or "N/D"
                        resenas = a_entero(col(fila, "reviewsCount", "reviews"))
                        mensaje = redactar(cliente, modelo, tu_nombre, nombre, categoria,
                                           rating, resenas, indicaciones)
                        nuevas.append({
                            "place_id": pid, "nombre": nombre, "categoria": categoria,
                            "direccion": col(fila, "address", "street"), "telefono": telefono,
                            "rating": rating, "num_resenas": resenas,
                            "web": col(fila, "website"), "maps": col(fila, "url"),
                            "mensaje": mensaje, "link_whatsapp": link_whatsapp(telefono, mensaje),
                            "estado": "nuevo", "fecha_contacto": "",
                        })
                        st.write(f"Mensaje listo: {nombre}")
                    guardar_nuevos(nuevas)
                    estado_ui.update(label="Listo", state="complete")
                st.success(f"Se agregaron {len(nuevas)} prospectos. Revísalos en la pestaña Prospectos.")
            except Exception as e:  # noqa: BLE001
                st.error(f"La búsqueda se detuvo: {e}")
 
# ---------------------------------------------------------------- pestaña 2
with tab2:
    if not filas:
        st.markdown('<div class="empty">Aún no hay prospectos. Ve a la pestaña Buscar para traer '
                    'los primeros.</div>', unsafe_allow_html=True)
    else:
        t1, t2, t3 = st.columns([3, 2, 1])
        filtro = t1.multiselect("Estado", ESTADOS, default=["nuevo"], format_func=ETIQUETA.get,
                                label_visibility="collapsed", placeholder="Filtrar por estado")
        texto = t2.text_input("Buscar", placeholder="Buscar por nombre",
                              label_visibility="collapsed")
        with t3.popover("Exportar", use_container_width=True):
            buffer = io.StringIO()
            w = csv.DictWriter(buffer, fieldnames=CAMPOS, extrasaction="ignore")
            w.writeheader()
            w.writerows(filas.values())
            st.download_button("Descargar CSV", buffer.getvalue().encode("utf-8-sig"),
                               file_name="prospectos.csv", mime="text/csv",
                               use_container_width=True)
            if st.button("Enviar a Google Sheets", use_container_width=True):
                if not secreto("SHEETS_URL"):
                    st.error("Falta SHEETS_URL en los Secrets.")
                else:
                    try:
                        datos = [COLUMNAS_HOJA] + [[str(f.get(c, "")) for c in COLUMNAS_HOJA]
                                                   for f in filas.values()]
                        r = requests.post(secreto("SHEETS_URL"),
                                          json={"token": secreto("SHEETS_TOKEN"), "filas": datos},
                                          timeout=60)
                        if r.text.strip() == "ok":
                            st.success("Hoja actualizada.")
                        else:
                            st.error(f"Respuesta inesperada: {r.text[:200]}")
                    except Exception as e:  # noqa: BLE001
                        st.error(f"No se pudo enviar: {e}")
 
        visibles = [(pid, f) for pid, f in filas.items()
                    if f.get("estado") in filtro and texto.lower() in f.get("nombre", "").lower()]
        visibles.sort(key=lambda x: a_entero(x[1].get("num_resenas")))
        ids = [pid for pid, _ in visibles]
        if st.session_state.get("sel_pid") not in ids:
            st.session_state["sel_pid"] = ids[0] if ids else None
        sel = st.session_state["sel_pid"]
 
        lista, detalle = st.columns([2, 3], gap="medium")
 
        with lista:
            st.caption(f"{len(visibles)} de {total} prospectos, de menos a más reseñas")
            with st.container(height=620, border=True, key="lista"):
                if not visibles:
                    st.markdown('<div class="empty">Ningún prospecto coincide con el filtro.</div>',
                                unsafe_allow_html=True)
                for i, (pid, f) in enumerate(visibles):
                    if st.button(f["nombre"], key=f"sel_{i}", use_container_width=True,
                                 type="primary" if pid == sel else "secondary"):
                        st.session_state["sel_pid"] = pid
                        st.rerun()
                    est = f.get("estado", "nuevo")
                    st.markdown(
                        f'<div class="row-meta"><span style="--c:{COLOR.get(est, "#8A94A0")}">'
                        f'{ETIQUETA.get(est, esc(est))}</span>'
                        f'<span style="--c:transparent;margin:0">{esc(f.get("num_resenas"))} reseñas</span></div>',
                        unsafe_allow_html=True)
 
        with detalle:
            f = filas.get(sel) if sel else None
            with st.container(border=True):
                if not f:
                    st.markdown('<div class="empty">Elige un prospecto de la lista para ver su '
                                'mensaje.</div>', unsafe_allow_html=True)
                else:
                    est = f.get("estado", "nuevo")
                    maps = f.get("maps", "")
                    enlace_maps = (f'<a href="{esc(maps)}" target="_blank" rel="noopener">'
                                   'Abrir en Google Maps</a>') if maps.startswith("http") else "No disponible"
                    contacto = (f'<dt>Contactado</dt><dd>{esc(f.get("fecha_contacto"))}</dd>'
                                if f.get("fecha_contacto") else "")
                    st.markdown(
                        f'<div class="det-head"><div class="name">{esc(f.get("nombre"))}</div>'
                        f'<span class="badge" style="--c:{COLOR.get(est, "#8A94A0")}">'
                        f'{ETIQUETA.get(est, esc(est))}</span></div>'
                        '<dl class="facts">'
                        f'<dt>Categoría</dt><dd>{esc(f.get("categoria")) or "Sin dato"}</dd>'
                        f'<dt>Dirección</dt><dd>{esc(f.get("direccion")) or "Sin dato"}</dd>'
                        f'<dt>Teléfono</dt><dd>{esc(f.get("telefono"))}</dd>'
                        f'<dt>Calificación</dt><dd>{esc(f.get("rating"))} con {esc(f.get("num_resenas"))} reseñas</dd>'
                        f'<dt>Ubicación</dt><dd>{enlace_maps}</dd>'
                        f'{contacto}</dl>',
                        unsafe_allow_html=True)
 
                    msg = st.text_area("Mensaje", value=f.get("mensaje", ""),
                                       key=f"msg_{sel}", height=170)
                    b1, b2, b3, b4 = st.columns([1.3, 1.4, 1, 1])
                    b1.link_button("Abrir WhatsApp", link_whatsapp(f.get("telefono"), msg),
                                   type="primary", use_container_width=True)
                    if b2.button("Marcar como enviado", key=f"env_{sel}", use_container_width=True):
                        aplicar(sel, mensaje=msg, estado="contactado",
                                fecha_contacto=hoy.isoformat())
                    if b3.button("Regenerar", key=f"reg_{sel}", use_container_width=True):
                        if not openai_key:
                            st.error("Falta la clave de OpenAI en Configuración.")
                        else:
                            try:
                                nuevo = redactar(OpenAI(api_key=openai_key), modelo, tu_nombre,
                                                 f["nombre"], f["categoria"], f["rating"],
                                                 f["num_resenas"],
                                                 st.session_state.get("indicaciones_regen", ""))
                                actualizar(sel, mensaje=nuevo)
                                st.session_state.pop(f"msg_{sel}", None)
                                ok = True
                            except Exception as e:  # noqa: BLE001
                                ok = False
                                st.error(f"No se pudo regenerar: {e}")
                            if ok:
                                st.rerun()
                    if b4.button("Descartar", key=f"desc_{sel}", use_container_width=True):
                        aplicar(sel, estado="descartado")
 
                    c1, c2 = st.columns([1, 2])
                    c1.selectbox("Estado", ESTADOS, index=ESTADOS.index(est) if est in ESTADOS else 0,
                                 key=f"est_{sel}", format_func=ETIQUETA.get,
                                 on_change=al_cambiar_estado, args=(sel,))
                    c2.text_input("Indicación para regenerar (opcional)", key="indicaciones_regen",
                                  placeholder="Ej: más corto, tono más formal")
 
# ---------------------------------------------------------------- pestaña 3
with tab3:
    if not pendientes:
        st.markdown(f'<div class="empty">No hay seguimientos pendientes. Aparecen aquí cuando pasan '
                    f'{dias_seg} días desde el primer contacto.</div>', unsafe_allow_html=True)
    else:
        st.text_input("Indicación para los seguimientos con IA (opcional)", key="indicaciones_seg",
                      placeholder="Ej: más corto, pregunta si prefiere que le llame")
    for pid, f, dias in pendientes:
        with st.container(border=True):
            st.markdown(
                f'<div class="det-head"><div class="name">{esc(f.get("nombre"))}</div>'
                f'<span class="badge" style="--c:{COLOR["contactado"]}">Contactado hace {dias} días</span></div>'
                f'<div class="lbl" style="margin-top:.8rem">Mensaje enviado</div>'
                f'<div class="quote">{esc(f.get("mensaje"))}</div>',
                unsafe_allow_html=True)
            msg = st.text_area("Mensaje de seguimiento",
                               value=st.session_state.get(f"seg_ia_{pid}", MENSAJE_SEGUIMIENTO),
                               key=f"seg_{pid}", height=100)
            b1, b2, b3, b4, b5 = st.columns(5)
            b1.link_button("Abrir WhatsApp", link_whatsapp(f.get("telefono"), msg),
                           type="primary", use_container_width=True)
            if b2.button("Redactar con IA", key=f"ia_{pid}", use_container_width=True):
                if not openai_key:
                    st.error("Falta la clave de OpenAI en Configuración.")
                else:
                    try:
                        st.session_state[f"seg_ia_{pid}"] = redactar_seguimiento(
                            OpenAI(api_key=openai_key), modelo, tu_nombre, f["nombre"],
                            f["categoria"], f["mensaje"], dias,
                            st.session_state.get("indicaciones_seg", ""))
                        st.session_state.pop(f"seg_{pid}", None)
                        generado = True
                    except Exception as e:  # noqa: BLE001
                        generado = False
                        st.error(f"No se pudo generar: {e}")
                    if generado:
                        st.rerun()
            if b3.button("Ya di seguimiento", key=f"sdone_{pid}", use_container_width=True):
                aplicar(pid, fecha_contacto=hoy.isoformat())
            if b4.button("Respondió", key=f"resp_{pid}", use_container_width=True):
                aplicar(pid, estado="respondio")
            if b5.button("Descartar", key=f"sdesc_{pid}", use_container_width=True):
                aplicar(pid, estado="descartado")
 

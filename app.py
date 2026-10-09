"""
app.py - Prospección de restaurantes (versión nube: Streamlit Cloud + Supabase).
"""
import datetime
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
ESTADOS = ["nuevo", "contactado", "respondio", "cliente", "descartado"]
API = "https://api.apify.com/v2"
ACTOR = "compass~crawler-google-places"
MENSAJE_SEGUIMIENTO = (
    "Hola, buen día. Solo paso a preguntar si pudo ver mi mensaje sobre el menú "
    "digital. Con gusto les preparo un ejemplo con sus platillos, sin compromiso."
)

st.set_page_config(page_title="Prospección de restaurantes", page_icon="🍽️", layout="wide")


def secreto(nombre, defecto=""):
    try:
        return str(st.secrets[nombre])
    except Exception:  # noqa: BLE001
        return os.getenv(nombre, defecto)


# ---------------------------------------------------------------- login
def pedir_login():
    clave = secreto("APP_PASSWORD")
    if not clave:
        return  # sin contraseña configurada (uso local)
    if st.session_state.get("autorizado"):
        return
    st.title("🔒 Acceso")
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
        filas = cargar()
        tel = filas.get(place_id, {}).get("telefono", "")
        cambios["link_whatsapp"] = link_whatsapp(tel, cambios["mensaje"])
    url, headers = _sb()
    r = requests.patch(url, headers=headers, params={"place_id": f"eq.{place_id}"},
                       json=cambios, timeout=60)
    r.raise_for_status()


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


def redactar(cliente, modelo, tu_nombre, nombre, categoria, rating, resenas):
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
    usuario = (f'Restaurante: "{nombre}". Tipo de negocio: {categoria or "restaurante"}. '
               f"Calificación en Google: {rating}. Reseñas: {resenas}.")
    resp = cliente.chat.completions.create(
        model=modelo,
        messages=[{"role": "system", "content": sistema}, {"role": "user", "content": usuario}],
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()


# ---------------------------------------------------------------- barra lateral
with st.sidebar:
    st.header("Configuración")
    apify_token = st.text_input("Token de Apify", value=secreto("APIFY_TOKEN"), type="password")
    openai_key = st.text_input("Clave de OpenAI", value=secreto("OPENAI_API_KEY"), type="password")
    tu_nombre = st.text_input("Tu nombre (firma del mensaje)", value=secreto("TU_NOMBRE"))
    modelo = st.text_input("Modelo de OpenAI", value=secreto("OPENAI_MODEL", "gpt-4o-mini"))
    dias_seg = st.number_input("Días antes del seguimiento", min_value=1, max_value=14, value=2)

st.title("🍽️ Prospección de restaurantes")
tab1, tab2, tab3 = st.tabs(["1. Buscar prospectos", "2. Prospectos", "3. Seguimientos"])

# ---------------------------------------------------------------- pestaña 1
with tab1:
    st.write("Busca restaurantes nuevos y deja los mensajes listos para enviar.")
    c1, c2 = st.columns(2)
    terminos_txt = c1.text_input("Qué buscar (separa con comas)", "restaurantes")
    ubicacion = c2.text_input("Ciudad o zona", "Saltillo, Coahuila, Mexico")
    c3, c4, c5, c6 = st.columns(4)
    max_lugares = c3.slider("Lugares por búsqueda", 5, 50, 20)
    max_nuevos = c4.slider("Mensajes a redactar", 1, 30, 5)
    max_resenas = c5.number_input("Máx. reseñas", 0, 1000, 60)
    tope = c6.number_input("Tope de gasto Apify (USD)", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    st.caption("Apify cobra cada lugar que trae, aunque ya lo tengas. Para no repetir, "
               "cambia la zona o el término cada vez (ej. 'Colonia República, Saltillo', "
               "'taquerías', 'cafeterías').")

    if st.button("Buscar y redactar mensajes", type="primary"):
        if not (apify_token and openai_key):
            st.error("Faltan el token de Apify o la clave de OpenAI (barra lateral).")
        else:
            terminos = [t.strip() for t in terminos_txt.split(",") if t.strip()]
            try:
                with st.status("Trabajando...", expanded=True) as estado_ui:
                    resultados = correr_apify(apify_token, terminos, ubicacion,
                                              max_lugares, tope, st.write)
                    st.write(f"Lugares recibidos: {len(resultados)}")
                    filas = cargar()
                    candidatos = []
                    for fila in resultados:
                        nombre = col(fila, "title", "name")
                        telefono = col(fila, "phoneUnformatted", "phone")
                        pid = col(fila, "placeId", "place_id", "cid", "url") or nombre
                        resenas = a_entero(col(fila, "reviewsCount", "reviews"))
                        if (not nombre or not telefono or esta_cerrado(fila)
                                or pid in filas or resenas > max_resenas):
                            continue
                        candidatos.append((pid, nombre, telefono, fila))
                    candidatos.sort(key=lambda c: a_entero(col(c[3], "reviewsCount", "reviews")))
                    st.write(f"Prospectos nuevos con teléfono y ≤ {max_resenas} reseñas: {len(candidatos)}")

                    cliente = OpenAI(api_key=openai_key)
                    nuevas = []
                    for pid, nombre, telefono, fila in candidatos[:max_nuevos]:
                        categoria = col(fila, "categoryName", "category")
                        rating = col(fila, "totalScore", "rating") or "N/D"
                        resenas = a_entero(col(fila, "reviewsCount", "reviews"))
                        mensaje = redactar(cliente, modelo, tu_nombre, nombre, categoria, rating, resenas)
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
                st.success(f"Se agregaron {len(nuevas)} prospectos. Ve a la pestaña 'Prospectos'.")
            except Exception as e:  # noqa: BLE001
                st.error(f"Algo falló: {e}")

# ---------------------------------------------------------------- pestaña 2
with tab2:
    filas = cargar()
    if not filas:
        st.info("Todavía no hay prospectos. Ve a la pestaña 'Buscar prospectos'.")
    else:
        conteo = {e: sum(1 for f in filas.values() if f["estado"] == e) for e in ESTADOS}
        for c, e in zip(st.columns(len(ESTADOS)), ESTADOS):
            c.metric(e.capitalize(), conteo[e])

                if st.button("Enviar a Google Sheets"):
            datos = [CAMPOS] + [[str(f.get(c, "")) for c in CAMPOS] for f in filas.values()]
            r = requests.post(secreto("SHEETS_URL"),
                              json={"token": secreto("SHEETS_TOKEN"), "filas": datos}, timeout=60)
            if r.text.strip() == "ok":
                st.success("Hoja actualizada.")
            else:
                st.error(f"Respuesta: {r.text[:200]}")

        filtro = st.multiselect("Mostrar", ESTADOS, default=["nuevo"])
        for pid, f in filas.items():
            if f["estado"] not in filtro:
                continue
            titulo = f"{f['nombre']}  ·  ⭐ {f['rating']} ({f['num_resenas']} reseñas)  ·  {f['estado']}"
            with st.expander(titulo):
                st.caption(f"{f['categoria']} · {f['direccion']} · Tel: {f['telefono']}")
                if f["maps"]:
                    st.markdown(f"[Ver en Google Maps]({f['maps']})")
                msg = st.text_area("Mensaje (puedes editarlo)", value=f["mensaje"],
                                   key=f"msg_{pid}", height=140)
                b1, b2, b3, _ = st.columns([1, 1, 1, 3])
                b1.link_button("Abrir WhatsApp", link_whatsapp(f["telefono"], msg))
                if b2.button("Ya lo envié", key=f"env_{pid}"):
                    actualizar(pid, mensaje=msg, estado="contactado",
                               fecha_contacto=datetime.date.today().isoformat())
                    st.rerun()
                if b3.button("Descartar", key=f"desc_{pid}"):
                    actualizar(pid, estado="descartado")
                    st.rerun()

# ---------------------------------------------------------------- pestaña 3
with tab3:
    filas = cargar()
    hoy = datetime.date.today()
    pendientes = []
    for pid, f in filas.items():
        if f["estado"] != "contactado":
            continue
        try:
            fecha = datetime.date.fromisoformat(f["fecha_contacto"])
        except ValueError:
            continue
        if (hoy - fecha).days >= dias_seg:
            pendientes.append((pid, f, (hoy - fecha).days))

    if not pendientes:
        st.info("No tienes seguimientos pendientes por hoy.")
    for pid, f, dias in pendientes:
        with st.expander(f"{f['nombre']}  ·  contactado hace {dias} días", expanded=True):
            msg = st.text_area("Mensaje de seguimiento", value=MENSAJE_SEGUIMIENTO,
                               key=f"seg_{pid}", height=100)
            b1, b2, b3, b4, _ = st.columns([1, 1, 1, 1, 2])
            b1.link_button("Abrir WhatsApp", link_whatsapp(f["telefono"], msg))
            if b2.button("Ya di seguimiento", key=f"sdone_{pid}"):
                actualizar(pid, fecha_contacto=hoy.isoformat())
                st.rerun()
            if b3.button("Respondió", key=f"resp_{pid}"):
                actualizar(pid, estado="respondio")
                st.rerun()
            if b4.button("Descartar", key=f"sdesc_{pid}"):
                actualizar(pid, estado="descartado")
                st.rerun()

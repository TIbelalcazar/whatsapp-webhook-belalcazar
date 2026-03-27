import os
from datetime import datetime
from urllib.parse import quote

import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "belalcazarbot")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")

AZURE_CLIENT_ID = os.getenv("AZURE_CLIENT_ID", "")
AZURE_TENANT_ID = os.getenv("AZURE_TENANT_ID", "")
AZURE_CLIENT_SECRET = os.getenv("AZURE_CLIENT_SECRET", "")

SHAREPOINT_HOSTNAME = os.getenv("SHAREPOINT_HOSTNAME", "")
SHAREPOINT_SITE_PATH = os.getenv("SHAREPOINT_SITE_PATH", "")
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH", "")
EXCEL_TABLE_NAME = os.getenv("EXCEL_TABLE_NAME", "tblPedidos")

pedidos_en_curso = {}
clientes_en_datos = {}


def send_whatsapp_text(to_number, message_text):
    if not WHATSAPP_TOKEN or not PHONE_NUMBER_ID:
        print("Faltan WHATSAPP_TOKEN o PHONE_NUMBER_ID")
        return

    url = f"https://graph.facebook.com/v22.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text},
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    print("Respuesta envío WhatsApp:", response.status_code, response.text)


def get_graph_token():
    if not AZURE_CLIENT_ID or not AZURE_TENANT_ID or not AZURE_CLIENT_SECRET:
        raise Exception("Faltan variables de Azure/Graph")

    token_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token"
    data = {
        "client_id": AZURE_CLIENT_ID,
        "client_secret": AZURE_CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }

    response = requests.post(token_url, data=data, timeout=30)
    response.raise_for_status()
    return response.json()["access_token"]


def get_site_id(graph_token):
    url = f"https://graph.microsoft.com/v1.0/sites/{SHAREPOINT_HOSTNAME}:/{SHAREPOINT_SITE_PATH}"
    headers = {"Authorization": f"Bearer {graph_token}"}

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def get_drive_item_id(graph_token, site_id):
    encoded_path = quote(EXCEL_FILE_PATH, safe="/")
    url = f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/root:/{encoded_path}"
    headers = {"Authorization": f"Bearer {graph_token}"}

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()["id"]


def construir_detalle_categoria(categorias_dict):
    bloques = []
    for categoria, items in categorias_dict.items():
        if items:
            bloques.append(f"{categoria}: " + " | ".join(items))
    return " || ".join(bloques)


def construir_pedido_plano(categorias_dict):
    todos = []
    for items in categorias_dict.values():
        todos.extend(items)
    return " | ".join(todos)


def guardar_pedido_en_excel(whatsapp_cliente, nombre, direccion, contacto, categorias_dict):
    graph_token = get_graph_token()
    site_id = get_site_id(graph_token)
    item_id = get_drive_item_id(graph_token, site_id)

    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    categorias_usadas = " | ".join([cat for cat, items in categorias_dict.items() if items])
    detalle_categoria = construir_detalle_categoria(categorias_dict)
    pedido_texto = construir_pedido_plano(categorias_dict)

    url = (
        f"https://graph.microsoft.com/v1.0/sites/{site_id}/drive/items/"
        f"{item_id}/workbook/tables/{EXCEL_TABLE_NAME}/rows/add"
    )
    headers = {
        "Authorization": f"Bearer {graph_token}",
        "Content-Type": "application/json",
    }

    payload = {
        "values": [[
            fecha_hora,
            "'" + whatsapp_cliente,
            nombre,
            direccion,
            "'" + contacto,
            categorias_usadas,
            detalle_categoria,
            pedido_texto,
            "Pendiente",
        ]]
    }

    response = requests.post(url, headers=headers, json=payload, timeout=60)
    print("Respuesta Excel Graph:", response.status_code, response.text)
    response.raise_for_status()


@app.route("/", methods=["GET"])
def home():
    return "Webhook Belalcázar activo", 200


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Token inválido", 403

    if request.method == "POST":
        data = request.get_json(silent=True)
        print("Webhook recibido:", data)

        try:
            entry = data.get("entry", [])
            for entry_item in entry:
                changes = entry_item.get("changes", [])
                for change in changes:
                    value = change.get("value", {})
                    messages = value.get("messages", [])

                    for message in messages:
                        from_number = message.get("from", "")
                        message_type = message.get("type", "")

                        if message_type != "text":
                            continue

                        original_text = message.get("text", {}).get("body", "").strip()
                        user_text = original_text.lower()

                        print("Número:", from_number)
                        print("Texto recibido:", user_text)

                        # Inicio
                        if user_text in ["hola", "buenas", "buenos dias", "buen día", "quiero pedir"]:
                            pedidos_en_curso[from_number] = {
                                "Carnes": [],
                                "Frutas y Verduras": [],
                                "Abarrotes y Granos": [],
                            }
                            clientes_en_datos[from_number] = {
                                "estado": "esperando_categoria"
                            }

                            send_whatsapp_text(
                                from_number,
                                "Hola, bienvenido(a) a Supermercados Belalcázar 👋\n\n"
                                "Somos Supermercados Belalcázar y estamos tomando pedidos a domicilio para nuestra tienda de Ciudad Guabinas."
                            )

                            send_whatsapp_text(
                                from_number,
                                "Iniciemos con tu pedido 🛒\n\n"
                                "¿Qué deseas pedir?\n\n"
                                "1️⃣ Carnes\n"
                                "2️⃣ Frutas y Verduras\n"
                                "3️⃣ Abarrotes y Granos\n"
                                "4️⃣ Terminar pedido"
                            )
                            continue

                        # Si escribe directo sin saludo
                        if from_number not in clientes_en_datos:
                            pedidos_en_curso[from_number] = {
                                "Carnes": [],
                                "Frutas y Verduras": [],
                                "Abarrotes y Granos": [],
                            }
                            clientes_en_datos[from_number] = {
                                "estado": "esperando_categoria"
                            }

                            send_whatsapp_text(
                                from_number,
                                "Hola, bienvenido(a) a Supermercados Belalcázar 👋\n\n"
                                "Iniciemos con tu pedido 🛒\n\n"
                                "¿Qué deseas pedir?\n\n"
                                "1️⃣ Carnes\n"
                                "2️⃣ Frutas y Verduras\n"
                                "3️⃣ Abarrotes y Granos\n"
                                "4️⃣ Terminar pedido"
                            )
                            continue

                        estado_actual = clientes_en_datos[from_number].get("estado")

                        # Elegir categoría o terminar pedido
                        if estado_actual == "esperando_categoria":
                            categoria = None

                            if user_text in ["1", "carnes", "carne"]:
                                categoria = "Carnes"
                            elif user_text in ["2", "frutas y verduras", "frutas", "verduras"]:
                                categoria = "Frutas y Verduras"
                            elif user_text in ["3", "abarrotes y granos", "abarrotes", "granos"]:
                                categoria = "Abarrotes y Granos"
                            elif user_text in ["4", "terminar pedido", "terminar"]:
                                categorias_dict = pedidos_en_curso.get(from_number, {})
                                hay_productos = any(categorias_dict.get(cat) for cat in categorias_dict)

                                if not hay_productos:
                                    send_whatsapp_text(
                                        from_number,
                                        "Aún no vemos productos en tu pedido 🛒\n\n"
                                        "Por favor elige una categoría:\n\n"
                                        "1️⃣ Carnes\n"
                                        "2️⃣ Frutas y Verduras\n"
                                        "3️⃣ Abarrotes y Granos"
                                    )
                                    continue

                                clientes_en_datos[from_number]["estado"] = "esperando_nombre"

                                categorias_usadas = " | ".join(
                                    [cat for cat, items in categorias_dict.items() if items]
                                )
                                detalle_categoria = construir_detalle_categoria(categorias_dict)

                                send_whatsapp_text(
                                    from_number,
                                    "Gracias, ya recibimos tu pedido 🛒\n\n"
                                    f"Categorías: {categorias_usadas}\n\n"
                                    f"Detalle de tu pedido:\n{detalle_categoria}\n\n"
                                    "Ahora por favor indícanos el nombre de la persona que recibirá el pedido."
                                )
                                continue

                            if not categoria:
                                send_whatsapp_text(
                                    from_number,
                                    "Por favor elige una opción válida:\n\n"
                                    "1️⃣ Carnes\n"
                                    "2️⃣ Frutas y Verduras\n"
                                    "3️⃣ Abarrotes y Granos\n"
                                    "4️⃣ Terminar pedido"
                                )
                                continue

                            clientes_en_datos[from_number]["estado"] = "tomando_pedido_categoria"
                            clientes_en_datos[from_number]["categoria_actual"] = categoria

                            send_whatsapp_text(
                                from_number,
                                f"Perfecto 👍\n\n"
                                f"Estás en la categoría: {categoria}\n\n"
                                "Ahora escríbenos los productos de esta categoría.\n"
                                "Cuando termines esta categoría, escribe: FIN"
                            )
                            continue

                        # Tomando pedido de una categoría
                        if estado_actual == "tomando_pedido_categoria":
                            if user_text in ["fin", "fin de categoria", "fin categoría", "terminé", "termine", "listo"]:
                                clientes_en_datos[from_number]["estado"] = "esperando_categoria"
                                clientes_en_datos[from_number]["categoria_actual"] = ""

                                send_whatsapp_text(
                                    from_number,
                                    "Muy bien ✅\n\n"
                                    "¿Deseas agregar productos de otra categoría?\n\n"
                                    "1️⃣ Carnes\n"
                                    "2️⃣ Frutas y Verduras\n"
                                    "3️⃣ Abarrotes y Granos\n"
                                    "4️⃣ Terminar pedido"
                                )
                                continue

                            categoria_actual = clientes_en_datos[from_number].get("categoria_actual", "")
                            if categoria_actual:
                                pedidos_en_curso[from_number][categoria_actual].append(original_text)

                            send_whatsapp_text(
                                from_number,
                                "Anotado 🛒\n\n"
                                "Puedes seguir escribiendo productos de esta categoría.\n"
                                "Cuando termines esta categoría, escribe: FIN"
                            )
                            continue

                        # Nombre
                        if estado_actual == "esperando_nombre":
                            clientes_en_datos[from_number]["nombre"] = original_text
                            clientes_en_datos[from_number]["estado"] = "esperando_direccion"

                            send_whatsapp_text(
                                from_number,
                                "Gracias 😊\n\n"
                                "Ahora por favor indícanos la dirección de entrega."
                            )
                            continue

                        # Dirección
                        if estado_actual == "esperando_direccion":
                            clientes_en_datos[from_number]["direccion"] = original_text
                            clientes_en_datos[from_number]["estado"] = "esperando_contacto"

                            send_whatsapp_text(
                                from_number,
                                "Perfecto 👍\n\n"
                                "Ahora por favor compártenos el número de contacto para el domicilio."
                            )
                            continue

                        # Contacto y guardado en Excel
                        if estado_actual == "esperando_contacto":
                            clientes_en_datos[from_number]["contacto"] = original_text

                            categorias_dict = pedidos_en_curso.get(from_number, {})
                            nombre = clientes_en_datos[from_number].get("nombre", "")
                            direccion = clientes_en_datos[from_number].get("direccion", "")
                            contacto = clientes_en_datos[from_number].get("contacto", "")

                            categorias_usadas = " | ".join(
                                [cat for cat, items in categorias_dict.items() if items]
                            )
                            detalle_categoria = construir_detalle_categoria(categorias_dict)

                            print("PEDIDO COMPLETO")
                            print("Cliente WhatsApp:", from_number)
                            print("Nombre:", nombre)
                            print("Dirección:", direccion)
                            print("Contacto:", contacto)
                            print("Categorías:", categorias_usadas)
                            print("Detalle por categoría:", detalle_categoria)

                            try:
                                guardar_pedido_en_excel(
                                    whatsapp_cliente=from_number,
                                    nombre=nombre,
                                    direccion=direccion,
                                    contacto=contacto,
                                    categorias_dict=categorias_dict,
                                )

                                send_whatsapp_text(
                                    from_number,
                                    "Gracias, ya tenemos todos los datos de tu pedido ✅\n\n"
                                    f"Nombre: {nombre}\n"
                                    f"Dirección: {direccion}\n"
                                    f"Contacto: {contacto}\n"
                                    f"Categorías: {categorias_usadas}\n\n"
                                    f"Detalle del pedido:\n{detalle_categoria}\n\n"
                                    "Tu pedido fue registrado correctamente y en un momento un asesor de Supermercados Belalcázar revisará tu solicitud."
                                )
                            except Exception as e:
                                print("Error guardando en Excel:", str(e))
                                send_whatsapp_text(
                                    from_number,
                                    "Ya tenemos todos los datos de tu pedido ✅\n\n"
                                    "Sin embargo, tuvimos un problema registrándolo internamente en este momento.\n"
                                    "Un asesor de Supermercados Belalcázar revisará tu solicitud manualmente."
                                )

                            pedidos_en_curso.pop(from_number, None)
                            clientes_en_datos.pop(from_number, None)
                            continue

        except Exception as e:
            print("Error procesando webhook:", str(e))

        return "EVENT_RECEIVED", 200

    return "Método no permitido", 405

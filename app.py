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

# Memoria temporal del piloto
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


def guardar_pedido_en_excel(whatsapp_cliente, nombre, direccion, contacto, pedido_lista):
    graph_token = get_graph_token()
    site_id = get_site_id(graph_token)
    item_id = get_drive_item_id(graph_token, site_id)

    pedido_texto = " | ".join(pedido_lista)
    fecha_hora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
            whatsapp_cliente,
            nombre,
            direccion,
            contacto,
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
                            pedidos_en_curso[from_number] = []
                            clientes_en_datos[from_number] = {"estado": "tomando_pedido"}

                            reply = (
                                "Hola, bienvenido(a) a Supermercados Belalcázar 👋\n\n"
                                "Somos Supermercados Belalcázar y estamos tomando pedidos a domicilio para nuestra tienda de Ciudad Guabinas.\n\n"
                                "Por favor escríbenos tu pedido con la mayor claridad posible, indicando:\n"
                                "- cantidad\n"
                                "- unidad de medida\n"
                                "- producto\n"
                                "- y marca, si tienes alguna preferencia\n\n"
                                "Ejemplos:\n"
                                "- 1 kilo de arroz Diana\n"
                                "- 1 litro de leche Alpina\n"
                                "- 500 gramos de azúcar\n"
                                "- 2 unidades de atún Van Camps\n\n"
                                "Puedes enviarnos tu pedido en varios mensajes.\n"
                                "Cuando termines, escribe: FIN"
                            )
                            send_whatsapp_text(from_number, reply)
                            continue

                        # Si escribe directo sin saludo
                        if from_number not in pedidos_en_curso:
                            pedidos_en_curso[from_number] = [original_text]
                            clientes_en_datos[from_number] = {"estado": "tomando_pedido"}

                            reply = (
                                "Hola, bienvenido(a) a Supermercados Belalcázar 👋\n\n"
                                "Ya empezamos a tomar tu pedido 🛒\n\n"
                                "Por favor sigue escribiéndolo con claridad, indicando:\n"
                                "- cantidad\n"
                                "- unidad de medida\n"
                                "- producto\n"
                                "- y marca, si tienes alguna preferencia\n\n"
                                "Cuando termines, escribe: FIN"
                            )
                            send_whatsapp_text(from_number, reply)
                            continue

                        # FIN del pedido
                        if user_text in ["fin", "fin de pedido", "eso es todo", "listo", "terminé", "termine"]:
                            pedido_cliente = pedidos_en_curso.get(from_number, [])

                            if not pedido_cliente:
                                reply = (
                                    "Aún no vemos productos en tu pedido 🛒\n\n"
                                    "Por favor escríbenos los productos y cuando termines escribe: FIN"
                                )
                                send_whatsapp_text(from_number, reply)
                                continue

                            resumen = "\n".join([f"- {item}" for item in pedido_cliente])

                            clientes_en_datos[from_number] = {
                                "estado": "esperando_nombre",
                                "pedido": pedido_cliente,
                            }

                            reply = (
                                "Gracias, ya recibimos tu pedido 🛒\n\n"
                                f"Resumen de tu pedido:\n{resumen}\n\n"
                                "Ahora por favor indícanos el nombre de la persona que recibirá el pedido."
                            )
                            send_whatsapp_text(from_number, reply)
                            continue

                        # Nombre
                        if from_number in clientes_en_datos and clientes_en_datos[from_number].get("estado") == "esperando_nombre":
                            clientes_en_datos[from_number]["nombre"] = original_text
                            clientes_en_datos[from_number]["estado"] = "esperando_direccion"

                            reply = "Gracias 😊\n\nAhora por favor indícanos la dirección de entrega."
                            send_whatsapp_text(from_number, reply)
                            continue

                        # Dirección
                        if from_number in clientes_en_datos and clientes_en_datos[from_number].get("estado") == "esperando_direccion":
                            clientes_en_datos[from_number]["direccion"] = original_text
                            clientes_en_datos[from_number]["estado"] = "esperando_contacto"

                            reply = "Perfecto 👍\n\nAhora por favor compártenos el número de contacto para el domicilio."
                            send_whatsapp_text(from_number, reply)
                            continue

                        # Contacto y guardado en Excel
                        if from_number in clientes_en_datos and clientes_en_datos[from_number].get("estado") == "esperando_contacto":
                            clientes_en_datos[from_number]["contacto"] = original_text

                            pedido_cliente = clientes_en_datos[from_number].get("pedido", [])
                            nombre = clientes_en_datos[from_number].get("nombre", "")
                            direccion = clientes_en_datos[from_number].get("direccion", "")
                            contacto = clientes_en_datos[from_number].get("contacto", "")
                            resumen = "\n".join([f"- {item}" for item in pedido_cliente])

                            print("PEDIDO COMPLETO")
                            print("Cliente WhatsApp:", from_number)
                            print("Nombre:", nombre)
                            print("Dirección:", direccion)
                            print("Contacto:", contacto)
                            print("Resumen pedido:", resumen)

                            try:
                                guardar_pedido_en_excel(
                                    whatsapp_cliente=from_number,
                                    nombre=nombre,
                                    direccion=direccion,
                                    contacto=contacto,
                                    pedido_lista=pedido_cliente,
                                )

                                reply = (
                                    "Gracias, ya tenemos todos los datos de tu pedido ✅\n\n"
                                    f"Nombre: {nombre}\n"
                                    f"Dirección: {direccion}\n"
                                    f"Contacto: {contacto}\n\n"
                                    f"Pedido:\n{resumen}\n\n"
                                    "Tu pedido fue registrado correctamente y en un momento un asesor de Supermercados Belalcázar revisará tu solicitud."
                                )
                            except Exception as e:
                                print("Error guardando en Excel:", str(e))
                                reply = (
                                    "Ya tenemos todos los datos de tu pedido ✅\n\n"
                                    "Sin embargo, tuvimos un problema registrándolo internamente en este momento.\n"
                                    "Un asesor de Supermercados Belalcázar revisará tu solicitud manualmente."
                                )

                            send_whatsapp_text(from_number, reply)

                            pedidos_en_curso.pop(from_number, None)
                            clientes_en_datos.pop(from_number, None)
                            continue

                        # Agregar línea al pedido
                        pedidos_en_curso[from_number].append(original_text)
                        reply = (
                            "Anotado 🛒\n\n"
                            "Puedes seguir escribiendo tu pedido.\n"
                            "Cuando termines, escribe: FIN"
                        )
                        send_whatsapp_text(from_number, reply)

        except Exception as e:
            print("Error procesando webhook:", str(e))

        return "EVENT_RECEIVED", 200

    return "Método no permitido", 405

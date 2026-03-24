import os
import requests
from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "belalcazarbot")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
PHONE_NUMBER_ID = os.getenv("PHONE_NUMBER_ID", "")


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
        "text": {
            "body": message_text
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    print("Respuesta envío WhatsApp:", response.status_code, response.text)


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

                        if message_type == "text":
                            user_text = message.get("text", {}).get("body", "").strip().lower()
                            print("Número:", from_number)
                            print("Texto recibido:", user_text)

                            if user_text in ["hola", "buenas", "buenos dias", "buen día", "quiero pedir"]:
                                reply = (
                                    "Hola, bienvenido(a) a Supermercados Belalcázar.\n\n"
                                    "Estamos tomando pedidos a domicilio para nuestra tienda de Ciudad Guabinas.\n\n"
                                    "1️⃣ Hacer pedido\n"
                                    "2️⃣ Hablar con asesor"
                                )
                                send_whatsapp_text(from_number, reply)

        except Exception as e:
            print("Error procesando webhook:", str(e))

        return "EVENT_RECEIVED", 200

    return "Método no permitido", 405

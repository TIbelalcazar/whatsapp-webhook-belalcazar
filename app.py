from flask import Flask, request

app = Flask(__name__)

VERIFY_TOKEN = "belalcazarbot"

@app.route("/", methods=["GET"])
def home():
    return "Webhook Belalcázar activo"

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
        return "EVENT_RECEIVED", 200

    return "Método no permitido", 405

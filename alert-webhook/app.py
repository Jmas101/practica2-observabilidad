
import json
import logging
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

app = Flask(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s"
)


@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/alerts")
def recibir_alertas():
    datos = request.get_json(silent=True)

    if not isinstance(datos, dict):
        return jsonify({"error": "JSON invalido"}), 400

    alertas = datos.get("alerts", [])

    for alerta in alertas:
        registro = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "service": "alert-webhook",
            "msg": "alert_received",
            "alert": alerta.get("labels", {}).get("alertname"),
            "severity": alerta.get("labels", {}).get("severity"),
            "status": alerta.get("status"),
            "summary": alerta.get("annotations", {}).get("summary")
        }

        app.logger.info(json.dumps(registro))

    return jsonify({
        "status": "received",
        "count": len(alertas)
    }), 200


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5001"))
    )

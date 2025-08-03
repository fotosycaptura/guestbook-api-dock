from flask import Flask, request, jsonify
from flask_cors import CORS
import csv
import os
from datetime import datetime
import html
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
logging.basicConfig(filename='/app/datos/api.log', level=logging.INFO)

def prevenir_csv_injection(texto):
    if isinstance(texto, str) and texto.startswith(('=', '+', '-', '@')):
        return "'" + texto
    return texto

def obtener_ip_real(req):
    """
    Devuelve la IP real del cliente, incluso si hay proxy inverso como Nginx.
    """
    forwarded_for = req.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        # Puede venir como 'IP1, IP2, ...'
        return forwarded_for.split(",")[0].strip()
    return req.remote_addr

app = Flask(__name__)
CORS(app, origins=["https://fotosycaptura.cl"])  # o "*" para todos
limiter = Limiter(get_remote_address, app=app, default_limits=["5 per minute"])
CSV_PATH = "/app/datos/visitas.csv"

# Asegurarse de que el archivo existe
if not os.path.exists(CSV_PATH):
    with open(CSV_PATH, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['fecha', 'hora', 'nombre', 'mensaje', 'ip', 'estado'])

@app.route('/ping/', methods=['GET'])
def ping():
    return jsonify({
        'ok': True,
        'message': 'Libro de visitas activo'
        }), 200

@app.route("/api/firmar", methods=["POST"])
def firmar_libro():
    data = request.get_json()
    # Verificar origen seguro (solo desde mi sitio)
    origen = request.headers.get('Origin', '')
    if not origen.startswith('https://fotosycaptura.cl'):
        return jsonify({
            'status': 'error',
            'message': 'Origen no autorizado.'
            }), 403
    nombre = html.escape(prevenir_csv_injection(data.get("nombre", "").strip()))
    mensaje = html.escape(prevenir_csv_injection(data.get("mensaje", "").strip()))
    #ip = request.remote_addr
    ip = obtener_ip_real(request)
    estado = '0'

    if not nombre or not mensaje:
        return jsonify({"status": "error", "message": "Nombre y mensaje son requeridos"}), 400

    ahora = datetime.now()
    fecha_str = ahora.strftime("%Y-%m-%d %H:%M:%S")
    hora_clave = ahora.strftime("%Y-%m-%d %H")  # para antispam por IP/hora

    # Verificar si ya existe un mensaje de esta IP en esta hora
    with open(CSV_PATH, mode='r', encoding='utf-8') as f:            
        reader = csv.DictReader(f)
        for row in reader:
            if row['ip'] == ip and row['hora'].startswith(hora_clave):
                return jsonify({
                    "status": "error",
                    "message": "Ya enviaste un mensaje desde esta IP en esta hora."
                }), 429

    # Guardar el mensaje
    with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow([fecha_str, hora_clave, nombre, mensaje, ip, estado])
        
    # luego dentro de firmar_libro
    logging.info(f"{fecha_str} | {ip} | {nombre[:20]} firmó el libro")

    return jsonify({
        "status": "success",
        "message": "Gracias por firmar el libro de visitas. Tu mensaje será revisado y publicado más tarde."
    }), 200

if __name__ == "__main__":
    app.run(debug=False)

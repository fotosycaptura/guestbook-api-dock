from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import csv
import os
from datetime import datetime
import html
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
import geoip2.database
from PIL import Image, ImageDraw, ImageFont
import io

logging.basicConfig(filename='/app/datos/api.log', level=logging.INFO)

# Función de prevención de CSV Injection
def prevenir_csv_injection(texto):
    if isinstance(texto, str) and texto.startswith(('=', '+', '-', '@')):
        return "'" + texto
    return texto

# Función para obtener la IP real del cliente
def obtener_ip_real(req):
    forwarded_for = req.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return req.remote_addr

# Inicialización de Flask y CORS
app = Flask(__name__)
CORS(app, origins=["https://fotosycaptura.cl"])  # o "*" para todos
limiter = Limiter(get_remote_address, app=app, default_limits=["5 per minute"])

# Ruta de CSV para visitas
CSV_PATH = "/app/datos/visitas.csv"

# Inicialización de GeoIP2
geoip_reader = geoip2.database.Reader('/app/datos/GeoLite2-City.mmdb')

# Asegurarse de que el archivo CSV exista
if not os.path.exists(CSV_PATH):
    with open(CSV_PATH, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['fecha', 'hora', 'nombre', 'mensaje', 'ip', 'estado'])

# Ruta de prueba para verificar si la API está activa
@app.route('/ping/', methods=['GET'])
def ping():
    return jsonify({
        'ok': True,
        'message': 'Libro de visitas activo'
    }), 200

# Ruta para firmar el libro de visitas
@app.route("/api/firmar", methods=["POST"])
def firmar_libro():
    data = request.get_json()
    origen = request.headers.get('Origin', '')
    if not origen.startswith('https://fotosycaptura.cl'):
        return jsonify({
            'status': 'error',
            'message': 'Origen no autorizado.'
        }), 403

    nombre = html.escape(prevenir_csv_injection(data.get("nombre", "").strip()))
    mensaje = html.escape(prevenir_csv_injection(data.get("mensaje", "").strip()))
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

    # Guardar el mensaje en el CSV
    with open(CSV_PATH, mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow([fecha_str, hora_clave, nombre, mensaje, ip, estado])
    
    logging.info(f"{fecha_str} | {ip} | {nombre[:20]} firmó el libro")

    return jsonify({
        "status": "success",
        "message": "Gracias por firmar el libro de visitas. Tu mensaje será revisado y publicado más tarde."
    }), 200

# Ruta para obtener estadísticas y la imagen del contador de visitas
@app.route('/api/contador', methods=['GET'])
def contador_visitas():
    # Contar el número de visitas
    visitas_count = 0
    with open(CSV_PATH, mode='r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        visitas_count = sum(1 for row in reader)  # Cuenta el número de filas

    # Obtener estadísticas de GeoIP (ubicación de la IP)
    try:
        response = geoip_reader.city(obtener_ip_real(request))
        ciudad = response.city.name or "Desconocida"
        pais = response.country.name or "Desconocido"
    except geoip2.errors.AddressNotFoundError:
        ciudad = pais = "Desconocido"

    # Crear una imagen del contador de visitas
    img = Image.new('RGB', (80, 30), color = (73, 109, 137))
    d = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    d.text((10,10), f"{visitas_count}", font=font, fill=(255,255,0))

    # Guardar la imagen en memoria y devolverla
    img_io = io.BytesIO()
    img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

if __name__ == "__main__":
    app.run(debug=False)

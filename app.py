from flask import Flask, request, jsonify, send_file, make_response
from flask_cors import CORS
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import csv
import os
import io
from datetime import datetime
import html
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging
logging.basicConfig(filename='/app/datos/api.log', level=logging.INFO)

# Ruta del archivo donde se almacenan las visitas y las IPs relacionadas al contador
VISITAS_FILE = "/app/datos/contador.txt"
REFERER_LOG_FILE = "/app/datos/referer.log"
CSV_PATH = "/app/datos/visitas.csv"

#----------------------------------------------------------------------------------
# Métodos de la api relacionadas al libro de visitas
#----------------------------------------------------------------------------------
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

#----------------------------------------------------------------------------------
# Métodos de la api relacionadas al contador
#----------------------------------------------------------------------------------

# Función para obtener el número de visitas
def get_visitas():
    if os.path.exists(VISITAS_FILE):
        with open(VISITAS_FILE, 'r') as file:
            return int(file.read())
    else:
        return 0

# Función para actualizar el contador de visitas
def incrementar_visitas():
    visitas = get_visitas() + 1
    with open(VISITAS_FILE, 'w') as file:
        file.write(str(visitas))
    return visitas

# Función para registrar la URL de referencia (Referer)
def registrar_referer(ip_visitante, referer, user_agent):
    with open(REFERER_LOG_FILE, 'a') as referer_file:
        referer_file.write(f"{datetime.now()} - {ip_visitante} - {referer} - {user_agent}\n")

# Función para generar la imagen con el número de visitas
def generar_imagen(visitas):
    """
    Genera la imagen PNG del contador al estilo 'contador CGI' con un tile por dígito.
    """
    numero = str(visitas)
    img = _render_counter_image(numero, spacing=4).convert("RGB")
    img_byte_array = io.BytesIO()
    img.save(img_byte_array, format='PNG', optimize=True)
    img_byte_array.seek(0)
    return img_byte_array

def _load_font(size=44):
    """
    Carga la fuente para el contador de visitas
    """
    try:
        return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()

def _make_digit_tile(ch, w=46, h=46):
    """Renderiza un dígito (0-9) con estilo 'contador CGI' verde."""
    bg1 = (140, 255, 140)   # verde claro
    bg2 = (50, 190, 50)     # verde medio
    tri = (20, 150, 20)     # triángulo oscuro
    border = (0, 120, 0)    # borde

    # Degradado vertical
    im = Image.new("RGB", (w, h), bg1)
    draw = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        r = int(bg1[0]*(1-t) + bg2[0]*t)
        g = int(bg1[1]*(1-t) + bg2[1]*t)
        b = int(bg1[2]*(1-t) + bg2[2]*t)
        draw.line([(0, y), (w, y)], fill=(r, g, b))

    # Triángulo “doblez” en esquina sup. derecha
    draw.polygon([(w, 0), (w, int(h*0.5)), (int(w*0.5), 0)], fill=tri)

    # Borde sutil
    draw.rectangle([0, 0, w-1, h-1], outline=border)

    # Texto con sombra
    font = _load_font(size=44)
    txt = str(ch)
    tw, th = draw.textbbox((0, 0), txt, font=font)[2:]
    x = (w - tw) // 2
    y = (h - th) // 2 + 2

    # Sombra suave
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.text((x+1, y+1), txt, font=font, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(1.2))
    im = Image.alpha_composite(im.convert("RGBA"), shadow)

    # Texto principal
    draw = ImageDraw.Draw(im)
    draw.text((x, y-1), txt, font=font, fill=(15, 60, 15))
    return im.convert("RGBA")

def _render_counter_image(number_str, spacing=4):
    tiles = [_make_digit_tile(ch) for ch in number_str]
    w = sum(t.size[0] for t in tiles) + spacing * (len(tiles) - 1)
    h = max(t.size[1] for t in tiles) if tiles else 64
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    x = 0
    for i, t in enumerate(tiles):
        out.alpha_composite(t, (x, 0))
        x += t.size[0] + (spacing if i < len(tiles)-1 else 0)
    return out

app = Flask(__name__)
CORS(app, origins=["https://fotosycaptura.cl"])  # o "*" para todos
limiter = Limiter(get_remote_address, app=app, default_limits=["5 per minute"])

# Asegurarse de que el archivo existe
if not os.path.exists(CSV_PATH):
    with open(CSV_PATH, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['fecha', 'hora', 'nombre', 'mensaje', 'ip', 'estado'])

# Endpoint para verificar estado de la api
@app.route('/ping/', methods=['GET'])
def ping():
    return jsonify({
        'ok': True,
        'message': 'Libro de visitas activo'
        }), 200

# Endpoint para firmar el libro de visitas
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

    ip = obtener_ip_real(request)
    # El estado sirve para setear el mensaje del visitante como no publicado o no autorizado
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

# Endpoint para generar la imagen del contador de visitas
# Rate limit más alto para permitir cargas de páginas concurridas
@limiter.limit("120 per minute")
@app.route('/contador.png')
def contador():
    # Incrementar visitas
    visitas = incrementar_visitas()

    # IP real (considera X-Forwarded-For)
    ip_visitante = obtener_ip_real(request)

    # Referer (página de origen)
    referer = request.headers.get('Referer', 'Desconocido')
    user_agent = request.headers.get('User-Agent', 'Desconocido')
    registrar_referer(ip_visitante, referer, user_agent)

    # Imagen del contador
    img_data = generar_imagen(visitas)

    # Respuesta sin caché
    resp = make_response(send_file(img_data, mimetype='image/png'))
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

if __name__ == "__main__":
    app.run(debug=False)

# 📖 Guestbook-api-dock

En los comienzos de la Internet, muchas páginas incluían un "Libro de Visitas" donde los visitantes dejaban un saludo, una opinión o simplemente su nombre y ciudad. Este proyecto recupera esa tradición, pero con herramientas modernas: una API en Python (Flask), contenida en Docker, y diseñada para integrarse con sitios web estáticos.

En términos simples, esto es un libro de visitas clásico bien al estilo retro. 

Funciona sin base de datos, guardando las firmas en un archivo `.csv`, lo que lo hace ideal para servidores personales pequeños, usando por ejemplo una Raspberry. 

Este proyecto, incluye ciertas medidas de seguridad (un hechizo simple pero inquebrantable XD) para prevenir spam y permitir una revisión antes de publicar, aunque lo de la publicación, te lo dejaré de tarea. Yo ya lo resolví usando Python...

---

## 🚀 Características

- API construida con **Flask** y **Docker** 🐳
- Guarda comentarios en un archivo `.csv`
- Protección antispam por IP y hora
- Validación del `Origin` para evitar abusos externos
- Endpoint `/ping` para monitoreo o prueba de disponibilidad
- Código ligero, sin base de datos, ideal para Raspberry Pi y entornos de bajos recursos

---

## 📁 Estructura del proyecto

```bash
📦 guestbook-api-dock
├── app.py # Código principal de la API
├── Dockerfile # Imagen base para la app
├── docker-compose.yml # El archivo docker
├── requirements.txt # Dependencias de Python
└── datos/
    └── visitas.csv # Archivo con los mensajes recibidos
```
---

## 🧱 Requisitos

- Docker + Docker Compose
- Puerto expuesto (por ejemplo 8000)
- Un servidor web externo (como GitHub Pages o Nginx) que envíe las firmas vía fetch/post

---

## 🔧 Instalación y ejecución

Clona este repositorio

```bash
git clone https://github.com/fotosycaptura/guestbook-api-dock.git
cd guestbook-api-dock
```

## Crear carpeta para los datos

```bash
mkdir -p datos
```

## Construir e iniciar el contenedor

```bash
docker-compose up -d --build
```

## 📬 Endpoints disponibles

`POST /api/firmar`

Envía una firma al libro de visitas. Se espera un JSON con los campos:

```json
{
  "nombre": "Jhon",
  "mensaje": "¡Tu sitio es genial!"
}
```
🔒 Requiere que el header Origin comience con https://fotosycaptura.cl

`GET /ping/`

Devuelve el estado de la API.

```json
{
  "ok": true,
  "message": "Libro de visitas activo"
}
```

## 🛡️ Seguridad implementada

- Validación de origen (Origin) para evitar abusos desde otras webs.
- Verificación de IP real incluso tras proxy inverso (X-Forwarded-For).
- Rate limit con flask-limiter: 5 solicitudes por minuto por IP.
- Prevención de inyecciones en CSV (ej. =1+1, @cmd) para evitar peligros al abrirlo en Excel.
- Codificación de entrada con html.escape().

## 📝 Publicación de mensajes

Los mensajes son guardados en el archivo `datos/visitas.csv` con estado 0 (pendiente).
Pueden luego ser leídos por un script externo en Python, moderados y convertidos en .md para usarlos en un sitio Web, o con Pelican.

## 📷 Ejemplo de integración en HTML

```html
<form id="libroForm">
  <input type="text" name="nombre" placeholder="Tu nombre" required>
  <textarea name="mensaje" placeholder="Tu mensaje..." required></textarea>
  <button type="submit">Firmar</button>
</form>

<script>
  document.getElementById("libroForm").addEventListener("submit", async function(e) {
    e.preventDefault();
    const datos = {
      nombre: this.nombre.value,
      mensaje: this.mensaje.value
    };

    const res = await fetch("https://api.sitioweb.com/firmar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(datos)
    });

    const resultado = await res.json();
    alert(resultado.message);
  });
</script>
```
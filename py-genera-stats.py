from pathlib import Path
import pandas as pd, json, pytz
from datetime import datetime
import re
from urllib.parse import urlparse
import geoip2.database
"""
 Este script está encargado de generar un archivo json que para las estadísticas que serán leídas por el sitio web.
 El primer paso consiste en leer los logs.
 Luego traduce y parsea para convertirlo en datos últiles para procesar vía pandas.
 Se obtienen referencias de ubicación mediante ip y geoip2 para los países visitantes.
 Finalmente, guarda los datos en json y se deja listo para que lo lea la página web desde la api.
 Quizás, haya que modificar las rutas para que estén en un solo lugar para facilidad de mantenimiento.
"""

# Ruta general
RUTA_GENERAL = "./datos/"

# Ruta a tu archivo real de logs:
LOG_PATH = Path(RUTA_GENERAL + "referer.log")  # <-- CAMBIA ESTA RUTA

# Ruta a la base local GeoLite2
GEOIP_DB = "./datos/GeoLite2-Country.mmdb"  # Cambia por tu ubicación

# === REGEX/UTILIDADES ===
_SPLIT_RE = re.compile(r"\s-\s")  # separa por " - "
BROWSER_TOKEN_RE = re.compile(
    r"(Firefox/\S+|Chrome/\S+|CriOS/\S+|Edg/\S+|Edge/\S+|OPR/\S+|Opera/\S+|Safari/\S+)",
    re.IGNORECASE,
)

def parse_line(line: str):
    """
    Espera líneas con 4 partes separadas por ' - ':
    1) timestamp, 2) ip, 3) url, 4) user-agent
    """
    line = line.strip()
    if not line:
        return None

    parts = _SPLIT_RE.split(line, maxsplit=3)
    if len(parts) != 4:
        # Línea inesperada: puedes loguearla o descartarla
        return None

    ts_str, ip, url, ua = parts

    # Fecha/hora
    try:
        ts = pd.to_datetime(ts_str)
    except Exception:
        ts = pd.NaT

    # URL
    try:
        p = urlparse(url)
        domain = p.netloc
        path = p.path or "/"
        query = p.query or ""
    except Exception:
        domain, path, query = None, None, None

    # SO (lo que esté entre el primer paréntesis del UA)
    os_info = None
    if "(" in ua and ")" in ua:
        try:
            os_info = ua.split("(", 1)[1].split(")", 1)[0].strip()
        except Exception:
            os_info = None

    # Navegador (primer token conocido)
    browser = None
    m = BROWSER_TOKEN_RE.search(ua)
    if m:
        browser = m.group(1)

    # Heurística simple de bot
    is_bot = bool(re.search(r"\b(bot|spider|crawler|Bytespider)\b", ua, re.IGNORECASE))

    return {
        "ts": ts,
        "ip": ip,
        "url": url,
        "domain": domain,
        "path": path,
        "query": query,
        "user_agent": ua,
        "os_info": os_info,
        "browser": browser,
        "is_bot": is_bot,
    }

def parse_log_file(path: Path) -> pd.DataFrame:
    rows = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            row = parse_line(line)
            if row:
                rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty and "ts" in df.columns:
        df["date"] = df["ts"].dt.date
        df["hour"] = df["ts"].dt.hour
        df["minute"] = df["ts"].dt.minute
    return df

# === EJECUCIÓN ===
df = parse_log_file(LOG_PATH)

# === Lecutra para detectar países ===

reader = geoip2.database.Reader(GEOIP_DB)

def get_country(ip):
    try:
        response = reader.country(ip)
        return response.country.name or "Desconocido"
    except geoip2.errors.AddressNotFoundError:
        return "No encontrado"
    except:
        return "Error"

# Añadimos columna 'country' al DataFrame
df["country"] = df["ip"].apply(get_country)

# Guardamos de nuevo el CSV enriquecido
OUT_CSV = LOG_PATH.with_suffix(".geo_parsed.csv")
df.to_csv(OUT_CSV, index=False, encoding="utf-8")

# === Entradas / Salidas ===
INPUT_CSV  = Path(RUTA_GENERAL + "referer.geo_parsed.csv")
# Coloca el JSON dentro de "content/data" para que Pelican lo copie tal cual al sitio:
OUTPUT_JSON = Path(RUTA_GENERAL + "stat/site_stats.json")
OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

# === Carga de datos ===
df = pd.read_csv(INPUT_CSV, parse_dates=["ts"], keep_default_na=False)

# Columnas derivadas mínimas
if "date" not in df.columns:
    df["date"] = df["ts"].dt.date

def top_counts(series, top_n=15):
    # Devuelve (labels, counts) para Plotly
    vc = series.value_counts().head(top_n)
    return list(vc.index.astype(str)), list(map(int, vc.values))

# País o IP
if "country" in df.columns and df["country"].notna().any():
    paises, pais_counts = top_counts(df["country"])
else:
    paises, pais_counts = top_counts(df["ip"])

# Páginas (path si existe; si no, url completa)
rutas, ruta_counts = top_counts(df["path"] if "path" in df.columns else df["url"])

# Serie diaria
serie_diaria = (
    df.groupby("date").size().reset_index(name="visitas").sort_values("date")
)
fechas = serie_diaria["date"].astype(str).tolist()
visitas_por_dia = serie_diaria["visitas"].astype(int).tolist()

# Bots vs humanos
bots_vs = df["is_bot"].value_counts().to_dict() if "is_bot" in df.columns else {}
bots    = int(bots_vs.get(True, 0))
humanos = int(bots_vs.get(False, 0))

# Navegadores / SO
browsers, browser_counts = top_counts(df["browser"])  if "browser" in df.columns  else ([], [])
os_labels, os_counts     = top_counts(df["os_info"])  if "os_info" in df.columns  else ([], [])

# Marca de tiempo CL
ahora_cl = datetime.now(pytz.timezone("America/Santiago")).strftime("%Y-%m-%d %H:%M:%S %Z")

# === Estructura JSON (lista para Plotly) ===
data = {
    "generated_at": ahora_cl,           # para cache-busting y trazabilidad
    "top_n": 15,
    "country": {"labels": paises, "counts": pais_counts},
    "path":    {"labels": rutas,  "counts": ruta_counts},
    "daily":   {"dates": fechas,  "visits": visitas_por_dia},
    "bots_vs_humans": {
        "labels": ["Humanos", "Bots"],
        "values": [humanos, bots]
    },
    "browsers": {"labels": browsers, "counts": browser_counts},
    "os":       {"labels": os_labels, "counts": os_counts}
}

# === Escritura ===
with OUTPUT_JSON.open("w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"OK → JSON escrito en: {OUTPUT_JSON}")

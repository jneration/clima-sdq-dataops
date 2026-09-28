"""Configuración central del pipeline de clima de Santo Domingo."""
from pathlib import Path

# --- Rutas ---
RAIZ = Path(__file__).resolve().parent.parent
DIR_RAW = RAIZ / "datos" / "raw"
DIR_LOGS = RAIZ / "logs"

# --- Fuente de datos (Open-Meteo, CC BY 4.0) ---
LATITUD = 18.4861
LONGITUD = -69.9312
ZONA_HORARIA = "America/Santo_Domingo"
VARIABLES = "temperature_2m,relative_humidity_2m,precipitation"
URL_HISTORICO = "https://archive-api.open-meteo.com/v1/archive"
URL_PRONOSTICO = "https://api.open-meteo.com/v1/forecast"
MESES_HISTORICO = 12
RETRASO_ARCHIVO_DIAS = 6     # el servicio de archivo publica con unos días de retraso
DIAS_SOLAPE_INCREMENTAL = 7  # debe ser mayor que RETRASO_ARCHIVO_DIAS para no dejar huecos

# --- SQL Server (autenticación de Windows, driver ODBC 18) ---
SERVIDOR = r"localhost\SQLEXPRESS"
BASE_DATOS = "ClimaSDQ"
CADENA_CONEXION = (
    "DRIVER={ODBC Driver 18 for SQL Server};"
    f"SERVER={SERVIDOR};DATABASE={BASE_DATOS};"
    "Trusted_Connection=yes;TrustServerCertificate=yes;"
)

# --- Reglas de calidad de datos ---
TEMP_MIN_C, TEMP_MAX_C = 10.0, 45.0
HUMEDAD_MIN, HUMEDAD_MAX = 0.0, 100.0
FRESCURA_MAX_HORAS = 72      # alerta si la última lectura es más vieja que esto
UMBRAL_CALOR_EXTREMO_C = 32.0
LECTURAS_POR_DIA = 24

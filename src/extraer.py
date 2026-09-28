"""Extracción de datos climáticos horarios desde la API de Open-Meteo."""
import json
import logging
import time
from datetime import date, datetime, timedelta

import pandas as pd
import requests

import config

log = logging.getLogger(__name__)


def _pedir(url: str, params: dict, intentos: int = 3, espera_s: int = 5) -> dict:
    """GET con reintentos. Lanza RuntimeError si la API no responde."""
    ultimo_error = None
    for n in range(1, intentos + 1):
        try:
            r = requests.get(url, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            ultimo_error = e
            log.warning("Intento %d/%d falló: %s", n, intentos, e)
            if n < intentos:
                time.sleep(espera_s * n)
    raise RuntimeError(f"La API no respondió tras {intentos} intentos: {ultimo_error}")


def _guardar_json(datos: dict, etiqueta: str) -> None:
    config.DIR_RAW.mkdir(parents=True, exist_ok=True)
    ruta = config.DIR_RAW / f"{etiqueta}_{datetime.now():%Y%m%d_%H%M%S}.json"
    ruta.write_text(json.dumps(datos), encoding="utf-8")
    log.info("JSON crudo guardado en %s", ruta)


def _a_dataframe(datos: dict) -> pd.DataFrame:
    h = datos["hourly"]
    return pd.DataFrame({
        "fecha_hora": pd.to_datetime(h["time"]),
        "temperatura_c": h["temperature_2m"],
        "humedad_pct": h["relative_humidity_2m"],
        "precipitacion_mm": h["precipitation"],
    })


def _parametros_base() -> dict:
    return {
        "latitude": config.LATITUD,
        "longitude": config.LONGITUD,
        "hourly": config.VARIABLES,
        "timezone": config.ZONA_HORARIA,
    }


def descargar_historico() -> pd.DataFrame:
    """Últimos MESES_HISTORICO meses, hasta el último día disponible en el archivo."""
    fin = date.today() - timedelta(days=config.RETRASO_ARCHIVO_DIAS)
    inicio = fin - timedelta(days=round(365 * config.MESES_HISTORICO / 12))
    params = _parametros_base() | {"start_date": inicio.isoformat(), "end_date": fin.isoformat()}
    datos = _pedir(config.URL_HISTORICO, params)
    _guardar_json(datos, "historico")
    return _a_dataframe(datos)


def descargar_incremental() -> pd.DataFrame:
    """Últimos DIAS_SOLAPE_INCREMENTAL días ya observados (se solapa a propósito)."""
    params = _parametros_base() | {"past_days": config.DIAS_SOLAPE_INCREMENTAL, "forecast_days": 1}
    datos = _pedir(config.URL_PRONOSTICO, params)
    _guardar_json(datos, "incremental")
    df = _a_dataframe(datos)
    # El servicio de pronóstico también devuelve horas futuras: se descartan.
    return df[df["fecha_hora"] <= datetime.now()].reset_index(drop=True)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    d = descargar_incremental()
    print(d.head(), f"\nfilas: {len(d)}")

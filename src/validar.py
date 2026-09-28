"""Reglas de calidad de datos (DataOps). Separa filas válidas de rechazadas."""
from datetime import datetime

import pandas as pd

import config

COLUMNAS = ["fecha_hora", "temperatura_c", "humedad_pct", "precipitacion_mm"]

# Orden de evaluación: el primer motivo que aplica a una fila es el que se registra.
MOTIVOS = [
    "campo_nulo",
    "temperatura_fuera_de_rango",
    "humedad_fuera_de_rango",
    "precipitacion_negativa",
    "duplicado_en_lote",
]


def validar(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Devuelve (validas, rechazadas). Rechazadas trae fecha_hora, motivo y valor_crudo."""
    df = df[COLUMNAS].copy().reset_index(drop=True)

    m_nulo = df.isna().any(axis=1)
    m_temp = ~df["temperatura_c"].between(config.TEMP_MIN_C, config.TEMP_MAX_C)
    m_hum = ~df["humedad_pct"].between(config.HUMEDAD_MIN, config.HUMEDAD_MAX)
    m_prec = df["precipitacion_mm"] < 0
    # Duplicados de fecha_hora dentro del lote: se conserva el último recibido.
    m_dup = df["fecha_hora"].notna() & df.duplicated("fecha_hora", keep="last")

    motivo = pd.Series(pd.NA, index=df.index, dtype="object")
    for nombre, mascara in reversed(list(zip(MOTIVOS, [m_nulo, m_temp, m_hum, m_prec, m_dup]))):
        motivo = motivo.mask(mascara, nombre)  # el motivo de mayor prioridad queda al final

    rechazada = motivo.notna()
    rechazadas = pd.DataFrame({
        "fecha_hora": df.loc[rechazada, "fecha_hora"],
        "motivo": motivo[rechazada],
        "valor_crudo": df.loc[rechazada, COLUMNAS].apply(lambda f: "|".join(map(str, f)), axis=1),
    }).reset_index(drop=True)
    validas = df.loc[~rechazada].reset_index(drop=True)
    return validas, rechazadas


def horas_desde_ultima_lectura(validas: pd.DataFrame, ahora: datetime | None = None) -> float | None:
    """Antigüedad en horas de la última lectura válida (None si no hay datos)."""
    if validas.empty:
        return None
    ahora = ahora or datetime.now()
    return (ahora - validas["fecha_hora"].max()).total_seconds() / 3600


def alerta_frescura(validas: pd.DataFrame, ahora: datetime | None = None) -> str | None:
    horas = horas_desde_ultima_lectura(validas, ahora)
    if horas is None:
        return "Sin lecturas válidas"
    if horas > config.FRESCURA_MAX_HORAS:
        return f"Última lectura con {horas:.0f} h de antigüedad (máximo {config.FRESCURA_MAX_HORAS} h)"
    return None

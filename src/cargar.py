"""Carga a SQL Server: raw -> clean (MERGE idempotente) + rechazos + log de ejecución."""
import logging

import pandas as pd
import pyodbc

import config
import validar

log = logging.getLogger(__name__)


def _filas(df: pd.DataFrame, columnas: list[str]) -> list[tuple]:
    """DataFrame -> lista de tuplas con NaN/NaT convertidos a None."""
    sub = df[columnas].astype(object).where(df[columnas].notna(), None)
    return [tuple(f) for f in sub.itertuples(index=False, name=None)]


def _registrar_error(tipo: str, mensaje: str) -> None:
    """Anota el fallo en ops.log_carga con una transacción propia (la original hizo rollback)."""
    with pyodbc.connect(config.CADENA_CONEXION) as cn:
        cn.execute(
            "INSERT INTO ops.log_carga (fin, tipo, estado, mensaje) VALUES (SYSDATETIME(), ?, 'error', ?)",
            tipo, mensaje[:500],
        )


def cargar(df: pd.DataFrame, tipo: str) -> dict:
    """Valida y carga df. tipo: 'historica' | 'incremental'. Devuelve estadísticas de la carga."""
    validas, rechazadas = validar.validar(df)
    alerta = validar.alerta_frescura(validas) if tipo == "incremental" else None
    try:
        cn = pyodbc.connect(config.CADENA_CONEXION, autocommit=False)
        cur = cn.cursor()
        cur.fast_executemany = True

        cur.execute(
            "INSERT INTO ops.log_carga (tipo, estado) OUTPUT INSERTED.id_carga VALUES (?, 'en_curso')", tipo
        )
        id_carga = cur.fetchone()[0]

        # 1) raw: todo tal como llegó
        cols = validar.COLUMNAS
        cur.executemany(
            "INSERT INTO raw.lectura_clima (fecha_hora, temperatura_c, humedad_pct, precipitacion_mm, id_carga) "
            "VALUES (?, ?, ?, ?, ?)",
            [f + (id_carga,) for f in _filas(df, cols)],
        )

        # 2) rechazos con su motivo
        if not rechazadas.empty:
            cur.executemany(
                "INSERT INTO ops.rechazos (id_carga, fecha_hora, motivo, valor_crudo) VALUES (?, ?, ?, ?)",
                [(id_carga,) + f for f in _filas(rechazadas, ["fecha_hora", "motivo", "valor_crudo"])],
            )

        # 3) clean: MERGE por fecha_hora (el último recibido actualiza al anterior)
        cur.execute(
            "CREATE TABLE #stg (fecha_hora DATETIME2(0) NOT NULL PRIMARY KEY, "
            "temperatura_c DECIMAL(5,2) NOT NULL, humedad_pct DECIMAL(5,2) NOT NULL, "
            "precipitacion_mm DECIMAL(6,2) NOT NULL)"
        )
        if not validas.empty:
            cur.executemany("INSERT INTO #stg VALUES (?, ?, ?, ?)", _filas(validas, cols))
        cur.execute(
            """
            MERGE clean.lectura_clima AS d
            USING #stg AS s ON d.fecha_hora = s.fecha_hora
            WHEN MATCHED AND (d.temperatura_c <> s.temperatura_c OR d.humedad_pct <> s.humedad_pct
                              OR d.precipitacion_mm <> s.precipitacion_mm)
                THEN UPDATE SET temperatura_c = s.temperatura_c, humedad_pct = s.humedad_pct,
                                precipitacion_mm = s.precipitacion_mm, fecha_carga = SYSDATETIME()
            WHEN NOT MATCHED THEN INSERT (fecha_hora, temperatura_c, humedad_pct, precipitacion_mm)
                VALUES (s.fecha_hora, s.temperatura_c, s.humedad_pct, s.precipitacion_mm);
            """
        )
        insertadas_o_actualizadas = cur.rowcount

        # 4) cierre del log
        cur.execute(
            "UPDATE ops.log_carga SET fin = SYSDATETIME(), filas_leidas = ?, filas_validas = ?, "
            "filas_rechazadas = ?, estado = 'ok', mensaje = ? WHERE id_carga = ?",
            len(df), len(validas), len(rechazadas), alerta, id_carga,
        )
        cn.commit()
        cn.close()
    except Exception as e:
        try:
            cn.rollback()
            cn.close()
        except Exception:
            pass
        log.error("Carga fallida: %s", e)
        _registrar_error(tipo, str(e))
        raise

    stats = {
        "id_carga": id_carga, "leidas": len(df), "validas": len(validas),
        "rechazadas": len(rechazadas), "nuevas_o_actualizadas": insertadas_o_actualizadas,
        "alerta": alerta,
    }
    log.info("Carga %s: %s", tipo, stats)
    return stats

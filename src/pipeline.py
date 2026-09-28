"""Punto de entrada del pipeline.

Uso:
    python src/pipeline.py historica     # carga base (12 meses)
    python src/pipeline.py incremental   # carga diaria programada
Código de salida: 0 = ok, 1 = error (lo registra el Programador de tareas).
"""
import logging
import sys
from datetime import datetime

import pyodbc

import cargar
import config
import extraer


def _configurar_log() -> None:
    config.DIR_LOGS.mkdir(parents=True, exist_ok=True)
    archivo = config.DIR_LOGS / f"pipeline_{datetime.now():%Y%m%d}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(archivo, encoding="utf-8"), logging.StreamHandler()],
    )


def _actualizar_agregados(dias_atras: int | None) -> None:
    with pyodbc.connect(config.CADENA_CONEXION) as cn:
        cn.execute(
            "EXEC agg.sp_actualizar_diario @dias_atras = ?, @umbral_calor_c = ?, @lecturas_por_dia = ?",
            dias_atras, config.UMBRAL_CALOR_EXTREMO_C, config.LECTURAS_POR_DIA,
        )


def ejecutar(tipo: str) -> None:
    if tipo == "historica":
        stats = cargar.cargar(extraer.descargar_historico(), "historica")
        _actualizar_agregados(None)
    elif tipo == "incremental":
        stats = cargar.cargar(extraer.descargar_incremental(), "incremental")
        _actualizar_agregados(config.DIAS_SOLAPE_INCREMENTAL + 3)
    else:
        raise SystemExit(f"Tipo desconocido: {tipo!r} (use 'historica' o 'incremental')")
    if stats["alerta"]:
        logging.getLogger("pipeline").warning("ALERTA DE CALIDAD: %s", stats["alerta"])


if __name__ == "__main__":
    _configurar_log()
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    try:
        ejecutar(sys.argv[1])
        logging.getLogger("pipeline").info("Pipeline %s terminó correctamente", sys.argv[1])
    except Exception:
        logging.getLogger("pipeline").exception("Pipeline %s falló", sys.argv[1])
        sys.exit(1)

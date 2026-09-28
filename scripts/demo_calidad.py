"""Demostración de calidad de datos (OPCIONAL, solo para documentar).

Envía al pipeline 6 filas 100 % inválidas, una por cada regla. Las filas llegan a raw, ops.rechazos
y ops.log_carga (tipo = 'demo_calidad'), pero NO entran a clean ni a agg porque ninguna es válida.

Uso:  python scripts/demo_calidad.py
"""
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import cargar  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

filas = pd.DataFrame({
    "fecha_hora": pd.to_datetime([
        "2030-01-01 00:00", "2030-01-01 01:00", "2030-01-01 02:00",
        "2030-01-01 03:00", "2030-01-01 04:00", "2030-01-01 04:00",
    ]),
    "temperatura_c":    [99.0, 27.0, 27.0, np.nan, 27.0, 27.0],   # fuera de rango / nulo
    "humedad_pct":      [80,   130,  80,   80,     80,   80],     # humedad fuera de rango
    "precipitacion_mm": [0,    0,    -2.0, 0,      -1.0, -1.0],   # precipitación negativa
})
# La última fila duplica la fecha_hora de la anterior; ambas son inválidas por otra regla,
# por eso 'duplicado_en_lote' no aparece aquí (lo cubre tests/test_validar.py).

print(cargar.cargar(filas, "demo_calidad"))

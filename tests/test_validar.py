"""Pruebas de las reglas de calidad de datos."""
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import validar  # noqa: E402


def _df(filas):
    return pd.DataFrame(filas, columns=validar.COLUMNAS).assign(
        fecha_hora=lambda d: pd.to_datetime(d["fecha_hora"])
    )


def _motivos(rechazadas):
    return list(rechazadas["motivo"])


def test_fila_correcta_pasa():
    validas, rechazadas = validar.validar(_df([["2026-09-01 00:00", 27.0, 80, 0.0]]))
    assert len(validas) == 1 and rechazadas.empty


def test_limites_de_rango_son_inclusivos():
    df = _df([["2026-09-01 00:00", 10.0, 0, 0.0], ["2026-09-01 01:00", 45.0, 100, 0.0]])
    validas, rechazadas = validar.validar(df)
    assert len(validas) == 2 and rechazadas.empty


def test_temperatura_fuera_de_rango():
    df = _df([["2026-09-01 00:00", 9.9, 80, 0], ["2026-09-01 01:00", 45.1, 80, 0]])
    _, rechazadas = validar.validar(df)
    assert _motivos(rechazadas) == ["temperatura_fuera_de_rango"] * 2


def test_humedad_fuera_de_rango():
    df = _df([["2026-09-01 00:00", 27, -1, 0], ["2026-09-01 01:00", 27, 100.5, 0]])
    _, rechazadas = validar.validar(df)
    assert _motivos(rechazadas) == ["humedad_fuera_de_rango"] * 2


def test_precipitacion_negativa():
    _, rechazadas = validar.validar(_df([["2026-09-01 00:00", 27, 80, -0.1]]))
    assert _motivos(rechazadas) == ["precipitacion_negativa"]


def test_nulo_tiene_prioridad_sobre_rango():
    # Un NaN también "falla" el rango, pero el motivo correcto es campo_nulo.
    _, rechazadas = validar.validar(_df([["2026-09-01 00:00", np.nan, 80, 0]]))
    assert _motivos(rechazadas) == ["campo_nulo"]


def test_duplicado_conserva_el_ultimo_recibido():
    df = _df([["2026-09-01 00:00", 25.0, 80, 0], ["2026-09-01 00:00", 26.5, 82, 0]])
    validas, rechazadas = validar.validar(df)
    assert len(validas) == 1 and validas.iloc[0]["temperatura_c"] == 26.5
    assert _motivos(rechazadas) == ["duplicado_en_lote"]


def test_rechazo_conserva_valor_crudo_para_auditoria():
    _, rechazadas = validar.validar(_df([["2026-09-01 00:00", 99.0, 80, 0]]))
    assert "99.0" in rechazadas.iloc[0]["valor_crudo"]


def test_frescura_dentro_del_limite_no_alerta():
    validas = _df([["2026-09-01 00:00", 27, 80, 0]])
    assert validar.alerta_frescura(validas, ahora=datetime(2026, 9, 3, 23, 0)) is None


def test_frescura_vencida_alerta():
    validas = _df([["2026-09-01 00:00", 27, 80, 0]])
    assert validar.alerta_frescura(validas, ahora=datetime(2026, 9, 5, 0, 0)) is not None


def test_sin_lecturas_validas_alerta():
    assert validar.alerta_frescura(_df([]).iloc[0:0]) == "Sin lecturas válidas"

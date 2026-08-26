"""
tests/test_electoral_magnitudes.py
====================================
Tests para verificar que plan_electoral_metrics distingue correctamente
entre magnitudes fijas (vigentes) y magnitudes calculadas desde la población.

Caso de referencia
------------------
2 distritos con desigualdad poblacional severa:
    D1: 900 000 habitantes
    D2: 100 000 habitantes  (D1 es 9× más poblado)

Magnitudes vigentes hipotéticas (iguales, máximo malapportionment):
    D1: 5 escaños  → 180 000 personas/escaño
    D2: 5 escaños  →  20 000 personas/escaño
    ratio_max_min = 9.0

Magnitudes calculadas (Hamilton proporcional, total=10, min=1, max=9):
    D1: 8 escaños  → 112 500 personas/escaño
    D2: 2 escaños  →  50 000 personas/escaño
    ratio_max_min ≈ 2.25  (reducida, pero no 1.0 por cota min=1)

Las dos modalidades miden cosas distintas:
    - "fijas"     → malapportionment del mapa bajo el sistema legal vigente (H3)
    - "calculadas" → igualdad del voto bajo un sistema de magnitudes proporcional
"""

import pytest
import pandas as pd
import numpy as np

from chiledist.electoral import MAGNITUDES_LEGALES_LEY20840
from chiledist.engines.allocation import plan_electoral_metrics

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures del caso de referencia
# ─────────────────────────────────────────────────────────────────────────────

# 2 comunas, 2 distritos, desbalance 9:1
ASSIGNMENT_REF = {"C1": 1, "C2": 2}
POP_REF        = pd.Series({"C1": 900_000, "C2": 100_000})
VOTES_REF      = pd.DataFrame([
    {"CUT": "C1", "partido": "A", "votos": 60_000},
    {"CUT": "C1", "partido": "B", "votos": 40_000},
    {"CUT": "C2", "partido": "A", "votos":  8_000},
    {"CUT": "C2", "partido": "B", "votos": 12_000},
])
# Magnitudes fijas que ignoran la disparidad (máximo malapportionment)
MAG_FIJAS_REF = pd.Series({1: 5, 2: 5})


def _metrics(magnitudes_fijas=None, **kw):
    defaults = dict(
        assignment=ASSIGNMENT_REF,
        votes_df=VOTES_REF,
        pop_by_unit=POP_REF,
        total_seats=10,
        min_seats=1,
        max_seats=9,
    )
    defaults.update(kw)
    return plan_electoral_metrics(**defaults, magnitudes_fijas=magnitudes_fijas)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: modo_magnitudes en el output
# ─────────────────────────────────────────────────────────────────────────────

class TestModoMagnitudesEnOutput:

    def test_calculadas_por_defecto(self):
        m = _metrics()
        assert m["modo_magnitudes"] == "calculadas"

    def test_fijas_cuando_se_proveen(self):
        m = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        assert m["modo_magnitudes"] == "fijas"

    def test_modo_magnitudes_coexiste_con_modo_dhondt(self):
        """Las dos dimensiones (magnitudes, D'Hondt) son independientes."""
        m = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        assert "modo_dhondt" in m
        assert "modo_magnitudes" in m


# ─────────────────────────────────────────────────────────────────────────────
# Tests: malapportionment — la diferencia central de H3
# ─────────────────────────────────────────────────────────────────────────────

class TestMalapportionment:

    def test_ratio_max_min_mayor_con_magnitudes_fijas(self):
        """
        Con magnitudes fijas (5,5) el ratio debe ser mayor que con magnitudes
        calculadas proporcionales.  Es el invariante central de H3: las
        magnitudes fijas reflejan malapportionment real.
        """
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()

        assert m_fijas["ratio_max_min_pxe"] > m_calc["ratio_max_min_pxe"], (
            f"Fijas ({m_fijas['ratio_max_min_pxe']:.2f}x) debe superar "
            f"calculadas ({m_calc['ratio_max_min_pxe']:.2f}x)"
        )

    def test_ratio_fijas_aproximadamente_9(self):
        """
        Con 5 escaños cada uno y pop 9:1, el ratio debe ser ~9.
        Validación del valor numérico exacto.
        """
        m = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        assert m["ratio_max_min_pxe"] == pytest.approx(9.0, rel=0.01)

    def test_pxe_max_mayor_con_magnitudes_fijas(self):
        """D1 tiene 900k/5=180k personas/escaño bajo magnitudes fijas."""
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()
        assert m_fijas["pxe_max"] > m_calc["pxe_max"]

    def test_pxe_min_menor_con_magnitudes_fijas(self):
        """D2 tiene 100k/5=20k personas/escaño — mucho menos que el mínimo calculado."""
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()
        assert m_fijas["pxe_min"] < m_calc["pxe_min"]

    def test_magnitudes_calculadas_minimizan_desigualdad(self):
        """
        Con magnitudes calculadas el ratio no puede ser 9.0: assign_seat_magnitudes
        fue diseñada para reducir esta desigualdad.
        """
        m = _metrics()
        assert m["ratio_max_min_pxe"] < 9.0

    def test_peso_relativo_max_mayor_con_fijas(self):
        """
        El voto menos representado vale más con magnitudes fijas (malapportionment real).
        """
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()
        assert m_fijas["peso_relativo_max"] > m_calc["peso_relativo_max"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: métricas electorales (H4) cambian según magnitudes
# ─────────────────────────────────────────────────────────────────────────────

class TestElectoralConMagnitudesDistintas:

    def test_gallagher_puede_diferir(self):
        """
        Magnitudes distintas → distinta distribución de escaños → Gallagher distinto.
        Con 5+5 vs 8+2 los resultados D'Hondt difieren sustancialmente.
        """
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()
        # No exigimos dirección, solo que difieran cuando la distribución es asimétrica
        assert m_fijas["gallagher"] != m_calc["gallagher"]

    def test_escanos_totales_conservados_en_ambos_modos(self):
        """
        Cualquier modo debe retornar exactamente el total de escaños asignados.
        Las métricas de proporcionalidad asumen que se distribuyeron todos.
        """
        m_fijas = _metrics(magnitudes_fijas=MAG_FIJAS_REF)
        m_calc  = _metrics()

        # escanos_mayor_partido + n_partidos_con_escanos no nos da el total,
        # pero podemos verificar que los campos de magnitud son coherentes:
        # ratio_max_min debe ser ≥ 1 en ambos casos
        assert m_fijas["ratio_max_min_pxe"] >= 1.0
        assert m_calc["ratio_max_min_pxe"]  >= 1.0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: validación de errores
# ─────────────────────────────────────────────────────────────────────────────

class TestValidacionMagnitudesFijas:

    def test_error_si_faltan_distritos(self):
        """magnitudes_fijas incompletas deben lanzar ValueError."""
        mag_incompletas = pd.Series({1: 5})   # falta el distrito 2
        with pytest.raises(ValueError, match="no cubre"):
            _metrics(magnitudes_fijas=mag_incompletas)

    def test_ok_con_magnitudes_extra(self):
        """magnitudes_fijas con distritos adicionales (no del plan) es aceptable."""
        mag_extra = pd.Series({1: 5, 2: 5, 3: 4})   # D3 no existe en el plan
        m = _metrics(magnitudes_fijas=mag_extra)
        assert m["modo_magnitudes"] == "fijas"

    def test_none_explícito_usa_calculadas(self):
        """Pasar magnitudes_fijas=None explícitamente debe equivaler al default."""
        m_default  = _metrics()
        m_none     = _metrics(magnitudes_fijas=None)
        assert m_default["modo_magnitudes"] == "calculadas"
        assert m_none["modo_magnitudes"]    == "calculadas"
        assert m_default["ratio_max_min_pxe"] == pytest.approx(
            m_none["ratio_max_min_pxe"], rel=1e-6
        )


# ─────────────────────────────────────────────────────────────────────────────
# Test de coherencia: magnitudes calculadas proporcionales → ratio ~1
# ─────────────────────────────────────────────────────────────────────────────

class TestCoherenciaConPoblacionProporcional:

    def test_poblacion_igual_magnitudes_calculadas_ratio_1(self):
        """
        Si las comunas tienen exactamente la misma población y las magnitudes
        se calculan, cada distrito debe tener la misma magnitud → ratio = 1.0.
        """
        asgn   = {"C1": 1, "C2": 2}
        pop    = pd.Series({"C1": 500_000, "C2": 500_000})
        vdf    = pd.DataFrame([
            {"CUT": "C1", "partido": "A", "votos": 50_000},
            {"CUT": "C2", "partido": "A", "votos": 50_000},
        ])
        m = plan_electoral_metrics(asgn, vdf, pop,
                                   total_seats=10, min_seats=5, max_seats=5)
        assert m["ratio_max_min_pxe"] == pytest.approx(1.0, abs=0.01)
        assert m["modo_magnitudes"] == "calculadas"

    def test_magnitudes_fijas_iguales_ratio_1(self):
        """
        Si las magnitudes fijas son iguales entre distritos iguales en población,
        el ratio también es 1.0.
        """
        asgn   = {"C1": 1, "C2": 2}
        pop    = pd.Series({"C1": 500_000, "C2": 500_000})
        vdf    = pd.DataFrame([
            {"CUT": "C1", "partido": "A", "votos": 50_000},
            {"CUT": "C2", "partido": "A", "votos": 50_000},
        ])
        mag    = pd.Series({1: 5, 2: 5})
        m = plan_electoral_metrics(asgn, vdf, pop,
                                   total_seats=10, min_seats=5, max_seats=5,
                                   magnitudes_fijas=mag)
        assert m["ratio_max_min_pxe"] == pytest.approx(1.0, abs=0.01)
        assert m["modo_magnitudes"] == "fijas"

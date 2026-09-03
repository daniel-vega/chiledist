"""
tests/test_metrics.py
========================
Unit tests for chiledist.engines.metrics: compactness (Polsby-Popper, Reock) and
redistricting metrics (population_balance, cut_edges), against synthetic
in-memory geometries only. No real shapefiles, no gerrychain.

Covers VALIDATION_PLAN.md Roadmap P0 #7, P0 #8, and P1 #3 (cut_edges) —
today only covered indirectly via tests/test_smoke.py and
tests/test_split_metrics.py.
"""
from __future__ import annotations

import numpy as np
import geopandas as gpd
import pytest
import scipy.sparse as sp
from shapely.geometry import Point, Polygon

from chiledist.domain.equivalence import CRS_METRIC
from chiledist.engines.metrics import (
    cut_edges, polsby_popper, population_balance, reock,
    plan_split_metrics, multi_level_split_metrics,
)


def _gdf(geom) -> gpd.GeoDataFrame:
    """Single-row GeoDataFrame in a metric CRS (avoids geographic-area warnings)."""
    return gpd.GeoDataFrame({"geometry": [geom]}, crs=CRS_METRIC)


# ── Synthetic geometries ────────────────────────────────────────────────────────

def _circulo() -> Point:
    return Point(0, 0).buffer(1.0, resolution=128)


def _cuadrado() -> Polygon:
    return Polygon([(0, 0), (1, 0), (1, 1), (0, 1)])


def _l_shape() -> Polygon:
    return Polygon([(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)])


# ── 1. Polsby-Popper — círculo perfecto (Roadmap P0 #7) ────────────────────────

def test_polsby_popper_circulo_perfecto():
    pp = polsby_popper(_gdf(_circulo())).iloc[0]
    assert abs(pp - 1.0) < 1e-3


# ── 2. Polsby-Popper — cuadrado unitario, caso conocido (Roadmap P0 #8) ────────

def test_polsby_popper_cuadrado_unitario():
    pp = polsby_popper(_gdf(_cuadrado())).iloc[0]
    assert abs(pp - np.pi / 4) < 1e-3


# ── 3. Polsby-Popper — L-shape, forma irregular (Roadmap P0 #8) ────────────────

def test_polsby_popper_l_shape_en_rango():
    gdf = _gdf(_l_shape())
    assert gdf.geometry.iloc[0].is_valid
    pp = polsby_popper(gdf).iloc[0]
    assert 0 < pp < 1


# ── 4. Reock — círculo perfecto, cuadrado (caso conocido) y L-shape ────────────

def test_reock_circulo_perfecto():
    r = reock(_gdf(_circulo())).iloc[0]
    assert abs(r - 1.0) < 1e-2


def test_reock_cuadrado_unitario():
    # Reock = área / área-del-círculo-mínimo-circunscrito. Para el cuadrado
    # unitario ese círculo pasa por sus 4 vértices: radio = diagonal/2 =
    # sqrt(2)/2, área = pi/2 -> reock = 1/(pi/2) = 2/pi ≈ 0.6366.
    # No es pi/4 (~0.785): ese es el valor de Polsby-Popper para el cuadrado
    # (área/círculo-de-igual-perímetro), una fórmula distinta con círculo de
    # referencia distinto.
    r = reock(_gdf(_cuadrado())).iloc[0]
    assert abs(r - 2 / np.pi) < 1e-2


def test_reock_l_shape_en_rango():
    r = reock(_gdf(_l_shape())).iloc[0]
    assert 0 < r < 1


# ── 5/6. population_balance — balanceada vs desbalanceada ─────────────────────
#
# population_balance() devuelve un pd.DataFrame (una fila por partición), no
# un escalar. El campo comparable a "el balance" es max_deviation_pct — la
# desviación porcentual máxima entre particiones, igual en todas las filas.

def _gdf_particion(grupos: list) -> gpd.GeoDataFrame:
    """4 unidades de 100 personas c/u, agrupadas según `grupos`."""
    geoms = [Point(i, 0).buffer(0.4) for i in range(4)]
    return gpd.GeoDataFrame(
        {"pop": [100, 100, 100, 100], "grupo": grupos, "geometry": geoms},
        crs=CRS_METRIC,
    )


def test_population_balance_particion_balanceada():
    gdf = _gdf_particion(["A", "A", "B", "B"])  # 200 / 200
    result = population_balance(gdf, pop_col="pop", partition_col="grupo")
    assert result["max_deviation_pct"].iloc[0] == 0.0


def test_population_balance_particion_desbalanceada():
    gdf = _gdf_particion(["A", "A", "A", "B"])  # 300 / 100
    result = population_balance(gdf, pop_col="pop", partition_col="grupo")
    assert result["max_deviation_pct"].iloc[0] > 0


# ── 7. cut_edges — grafo lineal de 3 nodos (Roadmap P1 #3) ─────────────────────

def test_cut_edges_grafo_lineal_tres_nodos():
    # 0 - 1 - 2 (línea); partición {0,1} vs {2} corta solo la arista (1,2).
    adj = sp.csr_matrix(np.array([
        [0, 1, 0],
        [1, 0, 1],
        [0, 1, 0],
    ]))
    id_list = ["u0", "u1", "u2"]
    assignment = {"u0": "A", "u1": "A", "u2": "B"}
    assert cut_edges(adj, assignment, id_list) == 1


# ── multi_level_split_metrics — integridad administrativa multinivel ──────────
#
# GDF sintético: 6 unidades de decisión (ID_DIST), 3 CUT (2 unidades c/u),
# 2 COD_REGION anidadas jerárquicamente sobre las CUT (C1,C2 -> R1; C3 -> R2,
# igual que comunas dentro de una región real) — necesario para poder
# construir asignaciones que no partan NINGÚN nivel (Caso 2) o que partan
# TODOS los niveles (Caso 3) con un solo assignment de 2 distritos:
#
#   ID_DIST   CUT   COD_REGION   viviendas
#     U1       C1       R1          100
#     U2       C1       R1          100
#     U3       C2       R1          100
#     U4       C2       R1          100
#     U5       C3       R2          100
#     U6       C3       R2          100

def _gdf_multinivel() -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame(
        {
            "ID_DIST":    ["U1", "U2", "U3", "U4", "U5", "U6"],
            "CUT":        ["C1", "C1", "C2", "C2", "C3", "C3"],
            "COD_REGION": ["R1", "R1", "R1", "R1", "R2", "R2"],
            "viviendas":  [100, 100, 100, 100, 100, 100],
            "geometry":   [Point(i, 0).buffer(0.4) for i in range(6)],
        },
        crs=CRS_METRIC,
    )


LEVELS = ["CUT", "COD_REGION"]
EXPECTED_COLUMNS = [
    "level", "n_partidas", "n_total", "share_partidas",
    "pop_afectada", "pop_total", "pop_afectada_pct",
]

# Caso 1 (general): parte C1 (U1 -> distrito 1, U2 -> distrito 2) mientras
# C2/C3 quedan enteras. Como resultado también parte R1 (contiene a C1 y C2).
ASGN_GENERAL = {"U1": 1, "U2": 2, "U3": 1, "U4": 1, "U5": 2, "U6": 2}

# Caso 2: distritos alineados exactamente a COD_REGION (más grueso que CUT)
# -> ninguna CUT ni ninguna REGION queda partida.
ASGN_NO_SPLIT = {"U1": 1, "U2": 1, "U3": 1, "U4": 1, "U5": 2, "U6": 2}

# Caso 3: cada CUT se reparte entre los 2 distritos -> las 3 CUT partidas,
# y por lo tanto también las 2 REGION (cada una contiene al menos una CUT
# partida entre ambos distritos).
ASGN_ALL_SPLIT = {"U1": 1, "U2": 2, "U3": 1, "U4": 2, "U5": 1, "U6": 2}


class TestMultiLevelSplitMetrics:

    def test_shape_and_columns_caso_general(self):
        gdf = _gdf_multinivel()
        result = multi_level_split_metrics(
            ASGN_GENERAL, gdf, levels=LEVELS,
            id_col="ID_DIST", pop_col="viviendas",
        )
        assert result.shape == (2, 7)
        assert list(result.columns) == EXPECTED_COLUMNS

    def test_share_partidas_in_valid_range_caso_general(self):
        gdf = _gdf_multinivel()
        result = multi_level_split_metrics(
            ASGN_GENERAL, gdf, levels=LEVELS,
            id_col="ID_DIST", pop_col="viviendas",
        )
        assert result["share_partidas"].between(0.0, 1.0).all()
        # Verifica tipos (float, no NaN/objeto) — trivial pero real.
        assert (result["pop_afectada_pct"] >= 0).all()
        assert result["pop_afectada_pct"].dtype.kind == "f"

    def test_caso_general_valores_esperados(self):
        """
        CUT: solo C1 (200 hab) partida de 3 -> share=1/3, pop_afectada=200,
             pop_afectada_pct=200/600*100.
        COD_REGION: solo R1 (400 hab) partida de 2 -> share=1/2,
             pop_afectada=400, pop_afectada_pct=400/600*100.
        """
        gdf = _gdf_multinivel()
        result = multi_level_split_metrics(
            ASGN_GENERAL, gdf, levels=LEVELS,
            id_col="ID_DIST", pop_col="viviendas",
        ).set_index("level")

        # pop_afectada/pop_afectada_pct se derivan de la fracción que ya
        # devuelve plan_split_metrics()/pop_afectada_pct() redondeada a 4
        # decimales (0.3333, no 1/3 exacto) — la tolerancia absoluta cubre
        # esa composición de redondeos (ver docstring de
        # multi_level_split_metrics: no se recalcula la fracción, se reusa).
        assert result.loc["CUT", "n_partidas"] == 1
        assert result.loc["CUT", "n_total"] == 3
        assert result.loc["CUT", "share_partidas"] == pytest.approx(1 / 3, abs=1e-4)
        assert result.loc["CUT", "pop_afectada"] == pytest.approx(200.0, abs=0.1)
        assert result.loc["CUT", "pop_total"] == pytest.approx(600.0)
        assert result.loc["CUT", "pop_afectada_pct"] == pytest.approx(200 / 600 * 100, abs=0.1)

        assert result.loc["COD_REGION", "n_partidas"] == 1
        assert result.loc["COD_REGION", "n_total"] == 2
        assert result.loc["COD_REGION", "share_partidas"] == pytest.approx(0.5)
        assert result.loc["COD_REGION", "pop_afectada"] == pytest.approx(400.0, abs=0.1)
        assert result.loc["COD_REGION", "pop_afectada_pct"] == pytest.approx(400 / 600 * 100, abs=0.1)

    def test_ninguna_unidad_partida_en_ningun_nivel(self):
        gdf = _gdf_multinivel()
        result = multi_level_split_metrics(
            ASGN_NO_SPLIT, gdf, levels=LEVELS,
            id_col="ID_DIST", pop_col="viviendas",
        )
        assert (result["share_partidas"] == 0.0).all()
        assert (result["n_partidas"] == 0).all()
        assert (result["pop_afectada"] == 0.0).all()
        assert (result["pop_afectada_pct"] == 0.0).all()

    def test_todas_las_unidades_partidas_en_todos_los_niveles(self):
        gdf = _gdf_multinivel()
        result = multi_level_split_metrics(
            ASGN_ALL_SPLIT, gdf, levels=LEVELS,
            id_col="ID_DIST", pop_col="viviendas",
        )
        assert (result["share_partidas"] == 1.0).all()
        # n_partidas == n_total para cada nivel (todas partidas)
        assert (result["n_partidas"] == result["n_total"]).all()
        # Toda la población está en unidades partidas -> fracción exacta 1.0,
        # sin error de redondeo (a diferencia del caso general). Se compara
        # elemento a elemento porque Series == pytest.approx(escalar) no
        # siempre hace la comparación elemento a elemento esperada.
        for pct in result["pop_afectada_pct"]:
            assert pct == pytest.approx(100.0)

    def test_un_solo_nivel_equivale_a_plan_split_metrics_directo(self):
        """
        levels=["CUT"] debe producir el mismo share_partidas que llamar
        plan_split_metrics(unit_col="CUT") directamente — sin duplicar la
        lógica de conteo, multi_level_split_metrics() solo la envuelve.
        """
        gdf = _gdf_multinivel()

        multi = multi_level_split_metrics(
            ASGN_GENERAL, gdf, levels=["CUT"],
            id_col="ID_DIST", pop_col="viviendas",
        )
        direct = plan_split_metrics(
            ASGN_GENERAL, gdf, unit_col="CUT",
            id_col="ID_DIST", pop_col="viviendas",
        )

        assert multi.shape == (1, 7)
        assert multi.loc[0, "level"] == "CUT"
        assert multi.loc[0, "share_partidas"] == pytest.approx(
            direct["share_comunas_partidas"]
        )
        assert multi.loc[0, "n_partidas"] == direct["n_comunas_partidas"]

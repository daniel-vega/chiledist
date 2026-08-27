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
import scipy.sparse as sp
from shapely.geometry import Point, Polygon

from chiledist.domain.equivalence import CRS_METRIC
from chiledist.engines.metrics import cut_edges, polsby_popper, population_balance, reock


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

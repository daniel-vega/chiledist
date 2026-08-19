"""
tests/test_hierarchy.py
========================
Unit tests for chiledist.hierarchy: validate_hierarchy() y
contract_to_decision_units(), contra GDFs sintéticos en memoria.
No shapefiles reales, no gerrychain.

Covers VALIDATION_PLAN.md Roadmap P0 #4 (validate_hierarchy detecta
violaciones APC/CUT) y P0 #5 (contracción CUT conserva Σ pop).

Nota: el Roadmap P1 #4 ("Contracción grafo: n_nodos == n_CUTs") es sobre
graph.py, no sobre hierarchy.py — el test de "n filas == n_CUTs" de este
archivo verifica el invariante análogo en contract_to_decision_units(),
pero no es el mismo test que P1 #4 del roadmap.
"""
from __future__ import annotations

import geopandas as gpd

from chiledist.equivalence import CRS_METRIC
from chiledist.hierarchy import contract_to_decision_units, validate_hierarchy
from shapely.geometry import Polygon


def _square(i: int) -> Polygon:
    """Cuadrado unitario en la posición i, sin solape con sus vecinos."""
    return Polygon([(i, 0), (i + 1, 0), (i + 1, 1), (i, 1)])


def _gdf_jerarquia() -> gpd.GeoDataFrame:
    """3 CUT x 3 ID_DIST (9 filas), ID_DIST únicos, viviendas=100 c/u."""
    rows = []
    i = 0
    for cut in ("C1", "C2", "C3"):
        for k in range(3):
            rows.append({
                "CUT": cut,
                "ID_DIST": f"{cut}-{k}",
                "viviendas": 100,
                "geometry": _square(i),
            })
            i += 1
    return gpd.GeoDataFrame(rows, crs=CRS_METRIC)


# ── 1/2/3. validate_hierarchy (Roadmap P0 #4) ──────────────────────────────────

def test_validate_hierarchy_gdf_limpio_no_reporta_violaciones():
    resultado = validate_hierarchy(_gdf_jerarquia(), "ID_DIST", "CUT")
    assert len(resultado) == 0


def test_validate_hierarchy_detecta_violacion():
    # validate_hierarchy() opera sobre atributos, no geometría: agrupa por
    # fine_col y cuenta valores únicos de coarse_col. Para provocar una
    # violación basta con que el mismo ID_DIST aparezca en dos filas con CUT
    # distinto — aquí, renombrando el ID_DIST de la primera fila de C2 para
    # que coincida con el de la primera fila de C1.
    gdf = _gdf_jerarquia()
    id_colisionado = gdf.loc[0, "ID_DIST"]
    gdf.loc[3, "ID_DIST"] = id_colisionado

    resultado = validate_hierarchy(gdf, "ID_DIST", "CUT")

    assert len(resultado) > 0
    assert id_colisionado in resultado["ID_DIST"].values


def test_validate_hierarchy_columnas_esperadas():
    # Firma real (chiledist/hierarchy.py): groupby(fine_col)[coarse_col]
    # .nunique().reset_index(name="n_coarse") -> columnas [fine_col, "n_coarse"].
    gdf = _gdf_jerarquia()
    gdf.loc[3, "ID_DIST"] = gdf.loc[0, "ID_DIST"]

    resultado = validate_hierarchy(gdf, "ID_DIST", "CUT")

    assert list(resultado.columns) == ["ID_DIST", "n_coarse"]


# ── 4/5. contract_to_decision_units — Σ pop y n_CUTs (Roadmap P0 #5) ───────────

def test_contract_to_decision_units_conserva_suma_viviendas():
    gdf = _gdf_jerarquia()
    gdf_cut = contract_to_decision_units(
        gdf, decision_unit="CUT", agg_spec={"viviendas": "sum"}
    )
    assert gdf_cut["viviendas"].sum() == 900


def test_contract_to_decision_units_produce_una_fila_por_cut():
    gdf = _gdf_jerarquia()
    gdf_cut = contract_to_decision_units(
        gdf, decision_unit="CUT", agg_spec={"viviendas": "sum"}
    )
    assert len(gdf_cut) == 3


# ── 6. Idempotencia ─────────────────────────────────────────────────────────────

def test_contract_to_decision_units_es_idempotente():
    # Al volver a contraer un GDF ya a nivel CUT, current_unit se infiere
    # como "CUT" (no hay columna ID_DIST) y decision_unit == current_unit,
    # así que contract_to_decision_units() devuelve una copia sin modificar
    # (ver hierarchy.py: "if decision_unit == current_unit: return gdf.copy()").
    gdf = _gdf_jerarquia()
    gdf_cut = contract_to_decision_units(
        gdf, decision_unit="CUT", agg_spec={"viviendas": "sum"}
    )
    gdf_cut2 = contract_to_decision_units(
        gdf_cut, decision_unit="CUT", agg_spec={"viviendas": "sum"}
    )

    assert gdf_cut2["viviendas"].sum() == gdf_cut["viviendas"].sum()
    assert len(gdf_cut2) == len(gdf_cut)

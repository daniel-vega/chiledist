"""
tests/test_graph_contraction.py
=================================
Unit tests for chiledist.graph: build_graph() y contract_graph(), contra
GDFs sintéticos en memoria (rejilla 3x3). No shapefiles reales, no
gerrychain.

Covers VALIDATION_PLAN.md Roadmap P1 #4 ("Contracción grafo: n_nodos ==
n_CUTs") y P1 #3 ("Queen es superconjunto de rook").

Nota sobre firmas reales (chiledist/graph.py):
- build_graph(gdf, id_col, method=..., ...) -> (G, adj, id_list): tupla,
  no solo el grafo. id_col es posicional/requerido, no hay default.
- contract_graph(G, gdf, id_col, group_col, agg_cols=None)
  -> (G_contracted, gdf_contracted): tupla. Los nodos del grafo contraído
  quedan etiquetados con el valor de group_col (ej. "C0"), no con un
  índice entero. contract_graph requiere que los nodos de G tengan un
  atributo "id" igual a gdf[id_col] -- lo que build_graph() ya hace por
  construcción, así que G debe venir de build_graph(), no de un
  nx.Graph armado a mano.
"""
from __future__ import annotations

import geopandas as gpd
import networkx as nx
from shapely.geometry import Polygon

from chiledist.equivalence import CRS_METRIC
from chiledist.graph import build_graph, contract_graph


def _grid_gdf() -> gpd.GeoDataFrame:
    """
    Rejilla 3x3 de cuadrados unitarios. 3 CUT (uno por fila) x 3 ID_DIST
    (uno por columna dentro de cada fila) = 9 nodos, viviendas=100 c/u.
    """
    rows = []
    for r in range(3):
        for c in range(3):
            geom = Polygon([(c, r), (c + 1, r), (c + 1, r + 1), (c, r + 1)])
            rows.append({
                "ID_DIST": f"D{r}{c}",
                "CUT": f"C{r}",
                "viviendas": 100,
                "geometry": geom,
            })
    return gpd.GeoDataFrame(rows, crs=CRS_METRIC)


def _build_and_contract():
    gdf = _grid_gdf()
    G, _adj, _id_list = build_graph(gdf, id_col="ID_DIST", method="queen")
    G_c, gdf_c = contract_graph(
        G, gdf, id_col="ID_DIST", group_col="CUT", agg_cols={"viviendas": "sum"}
    )
    return G, G_c, gdf_c


# ── 1. Contracción produce exactamente n_CUTs nodos (Roadmap P1 #4) ────────────

def test_contract_graph_produce_n_cuts_nodos():
    _G, G_c, _gdf_c = _build_and_contract()
    assert G_c.number_of_nodes() == 3


# ── 2. Contracción conserva conectividad ───────────────────────────────────────

def test_contract_graph_conserva_conectividad():
    G, G_c, _gdf_c = _build_and_contract()
    assert nx.is_connected(G)
    assert nx.is_connected(G_c)


# ── 3. Contracción elimina self-loops ──────────────────────────────────────────

def test_contract_graph_sin_self_loops():
    _G, G_c, _gdf_c = _build_and_contract()
    assert not any(u == v for u, v in G_c.edges())


# ── 4. Contracción conserva Σ viviendas en atributos de nodo ───────────────────

def test_contract_graph_conserva_suma_viviendas():
    _G, G_c, _gdf_c = _build_and_contract()
    assert all(G_c.nodes[n]["viviendas"] == 300 for n in G_c.nodes())


# ── 5. Queen es superconjunto de rook (Roadmap P1 #3) ───────────────────────────

def test_queen_es_superconjunto_de_rook():
    gdf = _grid_gdf()
    G_queen, _, _ = build_graph(gdf, id_col="ID_DIST", method="queen")
    G_rook, _, _ = build_graph(gdf, id_col="ID_DIST", method="rook")

    assert G_queen.number_of_edges() >= G_rook.number_of_edges()
    assert all(
        G_queen.degree(n) >= G_rook.degree(n) for n in G_queen.nodes()
    )

"""
graph.py
========
Construcción de grafos de adyacencia y matrices sparse para
unidades censales chilenas. Compatible con NetworkX, scipy.sparse
y gerrychain.
"""

from __future__ import annotations
import os
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
import scipy.sparse as sp
import networkx as nx
from libpysal.weights import Queen, Rook

from .equivalence import CRS_METRIC, get_optimal_crs


# ──────────────────────────────────────────────────────────────────────────────
# Construcción de grafo principal
# ──────────────────────────────────────────────────────────────────────────────

def build_graph(
    gdf: gpd.GeoDataFrame,
    id_col: str,
    method: str = "queen",
    island_policy: str = "nearest",
    island_threshold_km: float = 50.0,
    connect_islands: Optional[bool] = None,   # deprecated: use island_policy
    attr_cols: Optional[list] = None,
    crs_metric: Optional[str] = None,
) -> tuple:
    """
    Construye un grafo de adyacencia desde un GeoDataFrame.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
    id_col : str
        Columna con el identificador único.
    method : str
        'queen' o 'rook'.
    island_policy : str
        Política para unidades sin vecinos geométricos:
        - ``"nearest"``   — conecta al vecino más cercano (default)
        - ``"threshold"`` — conecta solo si distancia ≤ island_threshold_km
        - ``"none"``      — no conecta; la isla queda aislada
    island_threshold_km : float
        Umbral de distancia en km para ``island_policy="threshold"``.
    connect_islands : bool, opcional
        **Deprecado.** Equivale a ``island_policy="nearest"`` (True) o
        ``island_policy="none"`` (False). Tiene precedencia si se provee.
    attr_cols : list[str], opcional
        Columnas adicionales como atributos de nodo.
    crs_metric : str, opcional
        CRS métrico para cálculo de centroides y distancias.
        None = auto-detectar con ``get_optimal_crs``.

    Returns
    -------
    G       : nx.Graph
    adj     : sp.csr_matrix
    id_list : list
    """
    # Compatibilidad hacia atrás: connect_islands bool → island_policy
    if connect_islands is not None:
        import warnings
        warnings.warn(
            "connect_islands está deprecado. Usa island_policy='nearest'/'none'.",
            DeprecationWarning, stacklevel=2,
        )
        island_policy = "nearest" if connect_islands else "none"

    if crs_metric is None:
        crs_metric = get_optimal_crs(gdf)

    gdf = gdf.copy().reset_index(drop=True)
    gdf["geometry"] = gdf["geometry"].buffer(0)

    W_cls = Queen if method == "queen" else Rook
    w     = W_cls.from_dataframe(gdf, ids=id_col)

    id_list  = gdf[id_col].tolist()
    id_index = {id_: i for i, id_ in enumerate(id_list)}
    n        = len(id_list)

    # Identificar y conectar islas según la política configurada
    islands = [id_ for id_, nb in w.neighbors.items() if len(nb) == 0]
    connections = []
    if islands:
        print(f"  Unidades sin vecinos (islas): {len(islands)}")
        if island_policy == "none":
            print(f"  island_policy='none': islas no conectadas.")
        elif island_policy == "nearest":
            w, connections = _connect_islands(
                gdf, id_col, id_index, w, islands, crs_metric=crs_metric,
            )
            print(f"  Islas conectadas (nearest): {len(connections)}")
        elif island_policy == "threshold":
            w, connections = _connect_islands(
                gdf, id_col, id_index, w, islands,
                threshold_km=island_threshold_km, crs_metric=crs_metric,
            )
            n_conn   = len(connections)
            n_noconn = len(islands) - n_conn
            print(f"  Islas conectadas (threshold={island_threshold_km} km): "
                  f"{n_conn} conectadas, {n_noconn} fuera de umbral.")
        else:
            raise ValueError(
                f"island_policy '{island_policy}' no reconocida. "
                "Opciones: 'nearest', 'threshold', 'none'."
            )

    # Construir matriz sparse
    rows_idx, cols_idx = [], []
    for id_i, neighbors in w.neighbors.items():
        i = id_index[id_i]
        for id_j in neighbors:
            j = id_index[id_j]
            rows_idx.append(i)
            cols_idx.append(j)

    data = np.ones(len(rows_idx), dtype=np.int8)
    adj  = sp.csr_matrix((data, (rows_idx, cols_idx)), shape=(n, n))

    # Construir grafo NetworkX
    G = nx.from_scipy_sparse_array(adj)

    # Atributos de nodo — vectorizado, reproyectando a métrico para centroides
    default_attrs = ["N_REGION", "N_COMUNA", "TIPO_DISTRITO",
                     "N_DISTRITO", "N_PROVINCIA"]
    cols_to_add   = list(set((attr_cols or []) + default_attrs))
    cols_to_add   = [c for c in cols_to_add if c in gdf.columns]

    # Reproyectar para centroides correctos
    gdf_m     = gdf.to_crs(crs_metric)
    centroids = gdf_m.geometry.centroid
    xs        = centroids.x.tolist()
    ys        = centroids.y.tolist()
    id_vals   = gdf[id_col].tolist()
    col_data  = {c: gdf[c].tolist() for c in cols_to_add}

    for i in range(n):
        G.nodes[i]["id"] = id_vals[i]
        G.nodes[i]["x"]  = xs[i]
        G.nodes[i]["y"]  = ys[i]
        for c in cols_to_add:
            G.nodes[i][c] = col_data[c][i]

    print(f"  Grafo: {G.number_of_nodes():,} nodos · "
          f"{G.number_of_edges():,} aristas · "
          f"{nx.number_connected_components(G)} componentes")

    return G, adj, id_list


# ──────────────────────────────────────────────────────────────────────────────
# Conexión de islas
# ──────────────────────────────────────────────────────────────────────────────

def _connect_islands(
    gdf: gpd.GeoDataFrame,
    id_col: str,
    id_index: dict,
    w,
    islands: list,
    threshold_km: Optional[float] = None,
    crs_metric: str = CRS_METRIC,
) -> tuple:
    """
    Conecta islas al vecino más cercano.

    Parameters
    ----------
    threshold_km : float, opcional
        Si se provee, solo conecta si distancia_centroide ≤ threshold_km.
        None = sin umbral (nearest, siempre conecta).
    crs_metric : str
        CRS métrico para cálculo de distancias entre centroides.
    """
    gdf_m = gdf.to_crs(crs_metric).reset_index(drop=True)
    w_lil = _weights_to_lil(w, id_index, len(id_index))

    ids_array  = gdf_m[id_col].tolist()
    centroids  = gdf_m.geometry.centroid
    cx         = centroids.x.to_numpy()
    cy         = centroids.y.to_numpy()
    threshold_m = threshold_km * 1000.0 if threshold_km is not None else np.inf

    connections = []

    for island_id in islands:
        i           = id_index[island_id]
        vecinos_act = set(w_lil[i])

        dx   = cx - cx[i]
        dy   = cy - cy[i]
        dist = np.sqrt(dx * dx + dy * dy)
        orden = np.argsort(dist)

        for idx_cand in orden:
            if idx_cand == i:
                continue
            if dist[idx_cand] > threshold_m:
                break          # ya ordenado: ningún candidato posterior estará más cerca
            cand_id = ids_array[idx_cand]
            j       = id_index.get(cand_id)
            if j is None or j in vecinos_act:
                continue
            w_lil[i].append(j)
            w_lil[j].append(i)
            connections.append({
                "isla":    island_id,
                "vecino":  cand_id,
                "dist_km": round(float(dist[idx_cand]) / 1000.0, 1),
            })
            break

    # Reconstruir weights desde lil
    neighbors_new = {
        gdf[id_col].iloc[i]: [gdf[id_col].iloc[j] for j in nb]
        for i, nb in enumerate(w_lil)
    }
    w.neighbors = neighbors_new
    return w, connections


def _weights_to_lil(w, id_index: dict, n: int) -> list:
    """Convierte libpysal weights a lista de listas de índices."""
    lil = [[] for _ in range(n)]
    for id_i, neighbors in w.neighbors.items():
        i = id_index[id_i]
        for id_j in neighbors:
            j = id_index[id_j]
            lil[i].append(j)
    return lil


# ──────────────────────────────────────────────────────────────────────────────
# Contracción jerárquica
# ──────────────────────────────────────────────────────────────────────────────

def contract_graph(
    G: nx.Graph,
    gdf: gpd.GeoDataFrame,
    id_col: str,
    group_col: str,
    agg_cols: Optional[dict] = None,
) -> tuple:
    """
    Contrae el grafo agrupando nodos por una columna jerárquica superior.

    Parameters
    ----------
    G : nx.Graph
    gdf : gpd.GeoDataFrame
    id_col : str      columna ID de la unidad fina
    group_col : str   columna por la que agrupar (ej. "CUT")
    agg_cols : dict   {col: func} para agregar. Ej. {"viviendas": "sum"}

    Returns
    -------
    G_contracted : nx.Graph
    gdf_contracted : gpd.GeoDataFrame
    """
    from shapely.ops import unary_union

    if group_col not in gdf.columns:
        raise KeyError(f"Columna '{group_col}' no encontrada en el GeoDataFrame.")

    crs_orig = gdf.crs

    # ── Disolver geometrías ───────────────────────────────────────────────────
    # Columnas extra de nivel superior (sin duplicar group_col)
    superior_cols = ["N_REGION", "COD_REGION", "N_PROVINCIA", "COD_PROVINCIA"]
    extra_cols    = [
        c for c in superior_cols
        if c in gdf.columns and c != group_col
    ]

    # group_by_cols: solo group_col + columnas superiores únicas
    group_by_cols = list(dict.fromkeys([group_col] + extra_cols))

    # agg: geometría + columnas numéricas pedidas
    agg_dict = {"geometry": lambda x: unary_union(x.values)}
    if agg_cols:
        for col, func in agg_cols.items():
            if col in gdf.columns:
                agg_dict[col] = func

    # Seleccionar columnas para el groupby — excluir geometry del listado
    # explícito (ya está en el GeoDataFrame como columna activa)
    extra_data_cols = [c for c in agg_dict if c != "geometry" and c in gdf.columns]
    cols_select     = list(dict.fromkeys(group_by_cols + extra_data_cols))

    gdf_sub = gdf[cols_select].copy()
    gdf_sub["geometry"] = gdf["geometry"].values  # agregar geometry una sola vez

    gdf_c = (
        gdf_sub
        .groupby(group_by_cols, as_index=False)
        .agg(agg_dict)
    )

    # Reconstruir GeoDataFrame con geometría activa explícita
    gdf_c = gpd.GeoDataFrame(
        gdf_c,
        geometry="geometry",
        crs=crs_orig,
    )
    gdf_c["geometry"] = gdf_c["geometry"].buffer(0)

    # ── Grafo contraído ───────────────────────────────────────────────────────
    node_to_group = dict(zip(gdf[id_col].tolist(), gdf[group_col].tolist()))

    gdf_m  = gdf_c.to_crs(CRS_METRIC)
    G_c    = nx.Graph()
    groups = gdf_c[group_col].tolist()

    for idx, g in enumerate(groups):
        cent = gdf_m.geometry.iloc[idx].centroid
        G_c.add_node(g, x=cent.x, y=cent.y, id=g)
        for col in extra_cols:
            if col in gdf_c.columns:
                G_c.nodes[g][col] = gdf_c[col].iloc[idx]
        if agg_cols:
            for col in agg_cols:
                if col in gdf_c.columns:
                    G_c.nodes[g][col] = gdf_c[col].iloc[idx]

    for u, v in G.edges():
        g_u = node_to_group.get(G.nodes[u].get("id"))
        g_v = node_to_group.get(G.nodes[v].get("id"))
        if g_u is not None and g_v is not None and g_u != g_v:
            G_c.add_edge(g_u, g_v)

    print(f"  Grafo contraído a '{group_col}': "
          f"{G_c.number_of_nodes()} nodos · "
          f"{G_c.number_of_edges()} aristas")

    return G_c, gdf_c


# ──────────────────────────────────────────────────────────────────────────────
# Persistencia
# ──────────────────────────────────────────────────────────────────────────────

def save_graph(
    adj: sp.csr_matrix,
    id_list: list,
    gdf: gpd.GeoDataFrame,
    id_col: str,
    prefix: str,
    islands_df: Optional[pd.DataFrame] = None,
) -> None:
    """Guarda matriz, índice y opcionalmente conexiones de islas."""
    sp.save_npz(f"{prefix}_matriz.npz", adj)
    print(f"  Guardado: {prefix}_matriz.npz")

    meta_cols = [id_col] + [
        c for c in ["CUT", "N_DISTRITO", "N_COMUNA", "N_REGION",
                    "N_PROVINCIA", "TIPO_DISTRITO", "COD_DISTRITO",
                    "viviendas", "total_edificaciones"]
        if c in gdf.columns and c != id_col
    ]
    indice = gdf[meta_cols].copy()
    indice["fila_col"] = range(len(id_list))
    indice.to_csv(f"{prefix}_indice.csv", index=False)
    print(f"  Guardado: {prefix}_indice.csv")

    if islands_df is not None:
        islands_df.to_csv(f"{prefix}_islas.csv", index=False)
        print(f"  Guardado: {prefix}_islas.csv")


def load_graph(prefix: str) -> tuple:
    """Carga una matriz guardada con save_graph y reconstruye el grafo."""
    adj    = sp.load_npz(f"{prefix}_matriz.npz")
    indice = pd.read_csv(f"{prefix}_indice.csv")
    G      = nx.from_scipy_sparse_array(adj)

    for i, row in indice.iterrows():
        for col in indice.columns:
            G.nodes[i][col] = row[col]

    return adj, indice, G


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def graph_stats(G: nx.Graph, adj: sp.csr_matrix) -> pd.DataFrame:
    """Estadísticas del grafo como DataFrame."""
    degrees = np.array(adj.sum(axis=1)).flatten()
    n       = G.number_of_nodes()

    stats = {
        "nodos":          n,
        "aristas":        G.number_of_edges(),
        "componentes":    nx.number_connected_components(G),
        "grado_promedio": round(float(degrees.mean()), 3),
        "grado_mediana":  float(np.median(degrees)),
        "grado_max":      int(degrees.max()),
        "grado_min":      int(degrees.min()),
        "densidad":       round(nx.density(G), 6),
        "es_conexo":      nx.is_connected(G),
    }

    if nx.is_connected(G) and n < 5000:
        stats["diametro"] = nx.diameter(G)
    else:
        stats["diametro"] = "N/A"

    return pd.DataFrame([stats]).T.rename(columns={0: "valor"})


def to_edgelist(
    G: nx.Graph,
    id_col: str = "id",
    extra_cols: Optional[list] = None,
) -> pd.DataFrame:
    """Exporta el grafo como lista de aristas con metadatos."""
    rows = []
    for u, v in G.edges():
        row = {"nodo_a": G.nodes[u].get(id_col),
               "nodo_b": G.nodes[v].get(id_col)}
        for c in (extra_cols or []):
            row[f"{c}_a"] = G.nodes[u].get(c)
            row[f"{c}_b"] = G.nodes[v].get(c)
        rows.append(row)
    return pd.DataFrame(rows)


def subgraph_region(
    G: nx.Graph,
    region: str,
    region_col: str = "N_REGION",
) -> nx.Graph:
    """Extrae el subgrafo de una región."""
    nodes = [
        n for n in G.nodes()
        if str(G.nodes[n].get(region_col, "")) == str(region)
    ]
    return G.subgraph(nodes).copy()
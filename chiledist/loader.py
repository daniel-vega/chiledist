"""
loader.py
=========
Carga unificada de todas las capas APC 2023 desde las 16 carpetas
regionales. Normaliza nombres de columnas truncados por DBF,
construye identificadores únicos y agrega población desde manzanas.

Estrategias de carga nacional:
    block_diagonal  → procesa región por región y concatena matrices
                      (recomendado para manzanas y redistritaje)
    full            → carga todo junto con adyacencias inter-región
                      (recomendado para distritos y comunas)
"""

from __future__ import annotations
import glob
import os
from typing import Optional

import geopandas as gpd
import pandas as pd
import numpy as np
import scipy.sparse as sp
import networkx as nx

from .equivalence import DBF_COLUMN_MAP, POPULATION_FIELDS


# ──────────────────────────────────────────────────────────────────────────────
# Constantes
# ──────────────────────────────────────────────────────────────────────────────

LAYER_FILENAMES = {
    "comunal":        "Comunal.shp",
    "distrital":      "Distrital.shp",
    "limite_urbano":  "Limite_Urbano_Censal.shp",
    "aldea":          "Aldea.shp",
    "eje_vial":       "Eje_Vial.shp",
    "manzana_urbana": "Manzana_Urbana.shp",
    "manzana_aldea":  "Manzana_Aldea.shp",
    "puntos_rural":   "Puntos_Edificacion_Rural.shp",
}

# ID por defecto para cada capa
DEFAULT_ID = {
    "comunal":        "CUT",
    "distrital":      "ID_DIST",
    "limite_urbano":  "N_URBANO",
    "aldea":          "N_ALDEA",
    "manzana_urbana": "MANZENT",
    "manzana_aldea":  "MANZENT",
    "puntos_rural":   None,
    "eje_vial":       None,
}

CRS_METRIC = "EPSG:32719"   # UTM zona 19S — cubre todo Chile
CRS_GEO    = "EPSG:4326"    # WGS84 geográfico


# ──────────────────────────────────────────────────────────────────────────────
# Carga de una capa
# ──────────────────────────────────────────────────────────────────────────────

def load_layer(
    layer: str,
    base_dir: str = ".",
    regions: Optional[list[int]] = None,
    add_ids: bool = True,
    fix_geometry: bool = True,
    to_metric: bool = False,
) -> gpd.GeoDataFrame:
    """
    Carga una capa APC desde todas las carpetas regionales disponibles.

    Parameters
    ----------
    layer : str
        Nombre de la capa. Uno de:
        'comunal', 'distrital', 'limite_urbano', 'aldea',
        'eje_vial', 'manzana_urbana', 'manzana_aldea', 'puntos_rural'.
    base_dir : str
        Directorio raíz donde están las carpetas SHP_APC2023_R*.
    regions : list[int], optional
        Regiones a cargar (ej. [13, 5]). None = todas.
    add_ids : bool
        Agrega columnas de ID estandarizadas (ID_DIST, COD_REGION, etc.).
    fix_geometry : bool
        Aplica buffer(0) para sanear geometrías inválidas.
    to_metric : bool
        Reproyecta a UTM zona 19S (EPSG:32719).

    Returns
    -------
    gpd.GeoDataFrame

    Examples
    --------
    >>> distritos = load_layer("distrital", base_dir="./datos")
    >>> comunas   = load_layer("comunal",   base_dir="./datos")
    >>> mz_rm     = load_layer("manzana_urbana", base_dir="./datos",
    ...                         regions=[13])
    """
    layer = layer.lower()
    if layer not in LAYER_FILENAMES:
        raise ValueError(
            f"Capa '{layer}' no reconocida. "
            f"Opciones: {list(LAYER_FILENAMES.keys())}"
        )

    filename = LAYER_FILENAMES[layer]
    pattern  = os.path.join(base_dir, "**", filename)
    paths    = sorted(glob.glob(pattern, recursive=True))

    if not paths:
        raise FileNotFoundError(
            f"No se encontró '{filename}' bajo '{base_dir}'. "
            f"Verifica que base_dir apunte a la carpeta con las "
            f"subcarpetas SHP_APC2023_R*."
        )

    # Filtrar por región
    if regions:
        filtered = []
        for p in paths:
            for r in regions:
                if f"_R{r:02d}" in p or f"_R{r}/" in p:
                    filtered.append(p)
                    break
        paths = filtered
        if not paths:
            raise FileNotFoundError(
                f"No se encontraron archivos para las regiones {regions}."
            )

    print(f"  Cargando '{layer}' ({len(paths)} archivo(s))...")

    gdfs = [gpd.read_file(p, engine="pyogrio") for p in paths]
    gdf  = gpd.GeoDataFrame(
        pd.concat(gdfs, ignore_index=True),
        crs=gdfs[0].crs
    )

    # Normalizar columnas truncadas por DBF
    gdf = gdf.rename(columns={
        k: v for k, v in DBF_COLUMN_MAP.items() if k in gdf.columns
    })

    # Sanear geometrías
    if fix_geometry and "geometry" in gdf.columns:
        gdf["geometry"] = gdf["geometry"].buffer(0)

    # Eliminar duplicados
    gdf = _deduplicate(gdf, layer)

    # IDs estandarizados
    if add_ids:
        gdf = _add_standard_ids(gdf, layer)

    if to_metric:
        gdf = gdf.to_crs(CRS_METRIC)

    print(f"  → {len(gdf):,} registros.")
    return gdf.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Carga nacional con estrategia configurable
# ──────────────────────────────────────────────────────────────────────────────

def build_national(
    layer: str,
    base_dir: str = ".",
    strategy: str = "block_diagonal",
    id_col: Optional[str] = None,
    connect_islands: bool = True,
    attr_cols: Optional[list[str]] = None,
    save_prefix: Optional[str] = None,
) -> dict:
    """
    Procesa todas las regiones y construye el grafo nacional.

    Parameters
    ----------
    layer : str
        Capa a cargar (ver load_layer).
    base_dir : str
        Directorio raíz con las carpetas SHP_APC2023_R*.
    strategy : str
        'block_diagonal'
            Procesa región por región y concatena las matrices en una
            matriz block-diagonal. Recomendado para:
            - Manzanas (~200k registros)
            - Redistritaje (los distritos no cruzan regiones)
            - Análisis intraurbano por ciudad
            Ventajas: bajo uso de memoria, paralelizable, permite
            acceder al resultado de cada región individualmente.

        'full'
            Carga todo Chile junto y construye el grafo con adyacencias
            inter-región. Recomendado para:
            - Comunas (~346 nodos, manejable)
            - Distritos (~2.768 nodos, manejable)
            - Análisis de zonas limítrofes entre regiones
    id_col : str, optional
        Columna identificadora única. Si None, usa el default de la capa
        (CUT para comunal, ID_DIST para distrital, MANZENT para manzanas).
    connect_islands : bool
        Conectar unidades sin vecinos al vecino más cercano.
    attr_cols : list[str], optional
        Columnas adicionales a incluir como atributos de nodo.
    save_prefix : str, optional
        Si se especifica, guarda matrices e índices en disco.
        Archivos generados (block_diagonal):
            {prefix}_R{r:02d}_matriz.npz   por cada región
            {prefix}_R{r:02d}_indice.csv
            {prefix}_nacional_matriz.npz   matrix block-diagonal
            {prefix}_nacional_indice.csv
        Archivos generados (full):
            {prefix}_matriz.npz
            {prefix}_indice.csv

    Returns
    -------
    dict con claves:
        'G'          : nx.Graph nacional
        'adj'        : sp.csr_matrix (block-diagonal o completa)
        'ids'        : list de IDs en orden de filas/columnas
        'indice'     : pd.DataFrame con metadatos de todas las unidades
        'por_region' : dict {r: {'G', 'adj', 'ids', 'gdf'}}
                       (solo strategy='block_diagonal', None si 'full')

    Examples
    --------
    >>> # Redistritaje distrital nacional
    >>> res = build_national("distrital", base_dir="./datos",
    ...                       strategy="block_diagonal",
    ...                       save_prefix="distrital_nac")
    >>> G, adj, ids = res["G"], res["adj"], res["ids"]
    >>> rm = res["por_region"][13]   # acceso directo a RM

    >>> # Comunas con adyacencias inter-región
    >>> res = build_national("comunal", base_dir="./datos",
    ...                       strategy="full",
    ...                       save_prefix="comunal_nac")

    >>> # Manzanas nacionales (procesamiento por región obligatorio)
    >>> res = build_national("manzana_urbana", base_dir="./datos",
    ...                       strategy="block_diagonal",
    ...                       save_prefix="manzana_nac")
    """
    from .graph import build_graph, save_graph

    layer  = layer.lower()
    id_col = id_col or DEFAULT_ID.get(layer)
    if id_col is None:
        raise ValueError(
            f"Especifica id_col para la capa '{layer}'. "
            f"No hay un ID por defecto para esta capa."
        )

    # ── Estrategia full ───────────────────────────────────────────────────────
    if strategy == "full":
        print(f"\nEstrategia: full")
        print(f"Cargando '{layer}' — todas las regiones juntas...")

        gdf = load_layer(layer, base_dir=base_dir, add_ids=True)
        G, adj, ids = build_graph(
            gdf, id_col=id_col,
            connect_islands=connect_islands,
            attr_cols=attr_cols,
        )
        indice = _build_indice(gdf, id_col)
        indice["fila_col"] = range(len(ids))

        if save_prefix:
            save_graph(adj, ids, gdf, id_col, prefix=save_prefix)
            indice.to_csv(f"{save_prefix}_indice.csv", index=False)

        _print_national_summary(adj, ids, strategy, n_bloques=1)

        return {
            "G":          G,
            "adj":        adj,
            "ids":        ids,
            "indice":     indice,
            "por_region": None,
        }

    # ── Estrategia block_diagonal ─────────────────────────────────────────────
    print(f"\nEstrategia: block_diagonal")
    print(f"Procesando '{layer}' región por región (R01–R16)...")

    por_region = {}
    matrices   = []
    ids_global = []
    indices    = []
    G_global   = nx.Graph()
    offset     = 0

    for r in range(1, 17):
        print(f"\n── R{r:02d} {'─'*40}")
        try:
            gdf_r = load_layer(
                layer, base_dir=base_dir, regions=[r], add_ids=True
            )
        except FileNotFoundError:
            print(f"  ⚠ Región {r:02d} no encontrada — saltando.")
            continue

        if len(gdf_r) == 0:
            print(f"  ⚠ Región {r:02d} vacía — saltando.")
            continue

        G_r, adj_r, ids_r = build_graph(
            gdf_r, id_col=id_col,
            connect_islands=connect_islands,
            attr_cols=attr_cols,
        )

        # Acumular matrices e IDs
        matrices.append(adj_r)
        ids_global.extend(ids_r)

        # Acumular índice con número de región
        idx_r = _build_indice(gdf_r, id_col)
        idx_r["region_num"] = r
        indices.append(idx_r)

        # Agregar al grafo global con offset de índice
        for node in G_r.nodes():
            G_global.add_node(node + offset, **G_r.nodes[node])
        for u, v in G_r.edges():
            G_global.add_edge(u + offset, v + offset)

        por_region[r] = {
            "G":   G_r,
            "adj": adj_r,
            "ids": ids_r,
            "gdf": gdf_r,
        }

        # Guardar región en disco si se pide
        if save_prefix:
            save_graph(
                adj_r, ids_r, gdf_r, id_col,
                prefix=f"{save_prefix}_R{r:02d}"
            )

        offset += len(ids_r)

    if not matrices:
        raise RuntimeError(
            "No se encontró ninguna región. Verifica base_dir."
        )

    # Matriz block-diagonal nacional
    adj_nacional = sp.block_diag(matrices, format="csr")
    indice_nac   = pd.concat(indices, ignore_index=True)
    indice_nac["fila_col"] = range(len(ids_global))

    if save_prefix:
        sp.save_npz(f"{save_prefix}_nacional_matriz.npz", adj_nacional)
        indice_nac.to_csv(f"{save_prefix}_nacional_indice.csv", index=False)
        print(f"\n  Guardado: {save_prefix}_nacional_matriz.npz")
        print(f"  Guardado: {save_prefix}_nacional_indice.csv")

    _print_national_summary(adj_nacional, ids_global, strategy,
                            n_bloques=len(por_region))

    return {
        "G":          G_global,
        "adj":        adj_nacional,
        "ids":        ids_global,
        "indice":     indice_nac,
        "por_region": por_region,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Carga múltiple de capas
# ──────────────────────────────────────────────────────────────────────────────

def load_all(
    base_dir: str = ".",
    layers: Optional[list[str]] = None,
    regions: Optional[list[int]] = None,
    to_metric: bool = False,
) -> dict[str, gpd.GeoDataFrame]:
    """
    Carga múltiples capas APC de una vez.

    Parameters
    ----------
    layers : list[str], optional
        Capas a cargar. Default: ['comunal', 'distrital',
        'manzana_urbana', 'manzana_aldea'].
    regions : list[int], optional
        Regiones a cargar. None = todas.

    Returns
    -------
    dict {nombre_capa: GeoDataFrame}
    """
    if layers is None:
        layers = ["comunal", "distrital", "manzana_urbana", "manzana_aldea"]

    result = {}
    for layer in layers:
        try:
            result[layer] = load_layer(
                layer, base_dir=base_dir,
                regions=regions, to_metric=to_metric
            )
        except FileNotFoundError as e:
            print(f"  ⚠ {e}")

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Agregación de población
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_population(
    manzanas: gpd.GeoDataFrame,
    level: str,
    source: str = "urbana",
) -> pd.DataFrame:
    """
    Agrega conteos de edificaciones desde manzanas al nivel deseado.

    Parameters
    ----------
    manzanas : gpd.GeoDataFrame
        Capa de manzanas con columnas de conteo.
    level : str
        Nivel de agregación: 'manzana', 'zona', 'distrito',
        'comuna', 'region'.
    source : str
        'urbana' para Manzana_Urbana, 'aldea' para Manzana_Aldea.

    Returns
    -------
    pd.DataFrame con conteos agregados.
    """
    fields  = POPULATION_FIELDS[
        "Manzana_Urbana" if source == "urbana" else "Manzana_Aldea"
    ]
    viv_col = fields.get("viviendas")
    col_col = fields.get("colectivas")
    uso_col = fields.get("otros_usos")

    agg_cols = {
        c: "sum" for c in [viv_col, col_col, uso_col]
        if c and c in manzanas.columns
    }

    group_keys = {
        "manzana":  [fields["id"]],
        "zona":     (["CUT", "COD_ZONA"] if "COD_ZONA" in manzanas.columns
                     else ["CUT"]),
        "distrito": (["CUT", "COD_DISTRITO"]
                     if "COD_DISTRITO" in manzanas.columns
                     else (["ID_DIST"] if "ID_DIST" in manzanas.columns
                           else ["CUT"])),
        "comuna":   ["CUT"],
        "region":   (["COD_REGION"] if "COD_REGION" in manzanas.columns
                     else ["N_REGION"]),
    }

    key = group_keys.get(level.lower())
    if not key:
        raise ValueError(
            f"Nivel '{level}' no soportado. "
            f"Opciones: {list(group_keys.keys())}"
        )

    key    = [k for k in key if k in manzanas.columns]
    if not key:
        raise KeyError(
            f"Ninguna columna de agrupación para nivel '{level}' "
            f"está en el GeoDataFrame."
        )

    result = manzanas.groupby(key).agg(agg_cols).reset_index()

    rename = {}
    if viv_col and viv_col in result.columns:
        rename[viv_col] = "viviendas"
    if col_col and col_col in result.columns:
        rename[col_col] = "viv_colectivas"
    if uso_col and uso_col in result.columns:
        rename[uso_col] = "otros_usos"
    result = result.rename(columns=rename)

    if "viviendas" in result.columns:
        result["total_edificaciones"] = (
            result["viviendas"]
            + result.get("viv_colectivas", pd.Series(0, index=result.index))
            + result.get("otros_usos",    pd.Series(0, index=result.index))
        )

    return result


def aggregate_rural_proxy(
    puntos_rural: gpd.GeoDataFrame,
    cut_col: str = "CUT",
    uso_col: str = "USO_EDIFICACION",
    categorias_vivienda: tuple = ("VIVIENDA", "VIVIENDA COLECTIVA"),
) -> pd.Series:
    """
    Conteo de edificaciones rurales por CUT, filtrado a categorías de
    vivienda (excluye 'EDIFICACION' y 'OTRO USO', no residenciales).

    Puntos_Edificacion_Rural solo trae CUT (nivel comuna) — a diferencia
    de Manzana_Urbana/Manzana_Aldea, no tiene COD_DISTRITO/ID_DIST — así
    que este proxy solo puede calcularse a nivel comuna, no distrito.
    Pensado como fallback en apply_rural_proxy_fallback() para comunas
    sin ninguna manzana urbana ni de aldea (proxy=0 desde ambas fuentes;
    caso real: Lago Verde, CUT 11102, ver tests/test_integration_r11.py).

    Parameters
    ----------
    puntos_rural : gpd.GeoDataFrame
        Capa Puntos_Edificacion_Rural (cd.load_layer("puntos_rural", ...)).
    cut_col : str
        Columna de comuna en puntos_rural.
    uso_col : str
        Columna de uso de la edificación.
    categorias_vivienda : tuple
        Valores de uso_col considerados residenciales.

    Returns
    -------
    pd.Series indexada por CUT, valores int (conteo de edificaciones).
    """
    mask = puntos_rural[uso_col].isin(categorias_vivienda)
    return (
        puntos_rural.loc[mask]
        .groupby(cut_col)
        .size()
        .astype(int)
        .rename("viviendas_rural")
    )


def apply_rural_proxy_fallback(
    pop: pd.DataFrame,
    puntos_rural: Optional[gpd.GeoDataFrame],
    cut_col: str = "CUT",
    viv_col: str = "viviendas",
) -> pd.DataFrame:
    """
    Sustituye el proxy de población por conteo de edificaciones rurales
    (aggregate_rural_proxy) para comunas cuyo TOTAL de viv_col — sumado
    sobre todas sus filas, p.ej. todos los distritos APC de esa comuna —
    es 0. No modifica comunas que ya tienen proxy > 0 desde manzanas.

    Si pop está a nivel distrito (una fila por CUT+COD_DISTRITO), el
    conteo rural de una comuna se reparte equitativamente entre sus
    distritos APC — aproximación razonable dado que Puntos_Edificacion_
    Rural no trae COD_DISTRITO (ver aggregate_rural_proxy). No-op si
    puntos_rural es None, está vacío, o no cubre la comuna afectada.

    Parameters
    ----------
    pop : pd.DataFrame
        Debe tener al menos [cut_col, viv_col] — una fila por comuna o
        por distrito, según el nivel en el que se esté trabajando.
    puntos_rural : gpd.GeoDataFrame | None
        Capa Puntos_Edificacion_Rural, o None si no está disponible (la
        capa es opcional — ver analizar_region() en scripts/redistritaje.py).
    cut_col, viv_col : str
        Nombres de columnas en pop.

    Returns
    -------
    pd.DataFrame — copia de pop con viv_col corregido donde aplica.
    """
    if puntos_rural is None or len(puntos_rural) == 0:
        return pop

    pop = pop.copy()
    comuna_totales = pop.groupby(cut_col)[viv_col].sum()
    cuts_sin_proxy = comuna_totales[comuna_totales == 0].index
    if len(cuts_sin_proxy) == 0:
        return pop

    rural_proxy = aggregate_rural_proxy(puntos_rural)

    for cut in cuts_sin_proxy:
        if cut not in rural_proxy.index:
            continue
        mask = pop[cut_col] == cut
        n_filas_cut = int(mask.sum())
        if n_filas_cut == 0:
            continue
        # Redondeado a entero: viv_col es una columna de conteo (siempre
        # int en el resto del pipeline). El reparto equitativo entre
        # n_filas_cut filas puede perder/ganar hasta ~n_filas_cut unidades
        # en total por el redondeo — aceptable dado que ya es una
        # aproximación (sin COD_DISTRITO en Puntos_Edificacion_Rural no
        # hay forma de repartir con más precisión).
        valor_repartido = int(round(rural_proxy.loc[cut] / n_filas_cut))
        pop.loc[mask, viv_col] = valor_repartido
        print(
            f"  Proxy rural aplicado: CUT {cut} → {rural_proxy.loc[cut]} "
            f"edificaciones rurales repartidas entre {n_filas_cut} fila(s)"
        )

    return pop


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def list_available_layers(base_dir: str = ".") -> pd.DataFrame:
    """Lista las capas disponibles con conteo de archivos por región."""
    rows = []
    for layer, filename in LAYER_FILENAMES.items():
        paths = sorted(glob.glob(
            os.path.join(base_dir, "**", filename), recursive=True
        ))
        rows.append({
            "capa":        layer,
            "archivo":     filename,
            "id_default":  DEFAULT_ID.get(layer, "—"),
            "n_regiones":  len(paths),
            "disponible":  len(paths) > 0,
            "estrategia":  _recommended_strategy(layer),
        })
    return pd.DataFrame(rows)


def _recommended_strategy(layer: str) -> str:
    """Estrategia recomendada para build_national() según la capa."""
    return {
        "comunal":        "full",
        "distrital":      "block_diagonal",
        "manzana_urbana": "block_diagonal",
        "manzana_aldea":  "block_diagonal",
        "limite_urbano":  "full",
        "aldea":          "block_diagonal",
        "eje_vial":       "—",
        "puntos_rural":   "—",
    }.get(layer, "—")


def summarize(gdf: gpd.GeoDataFrame, layer: str = "") -> None:
    """Imprime un resumen de un GeoDataFrame APC."""
    print(f"\n{'─'*60}")
    print(f"  Resumen: {layer or 'GeoDataFrame'}")
    print(f"{'─'*60}")
    print(f"  Filas        : {len(gdf):,}")
    print(f"  Columnas     : {gdf.columns.tolist()}")
    print(f"  CRS          : {gdf.crs}")
    if "N_REGION" in gdf.columns:
        print(f"  Regiones     : {gdf['N_REGION'].nunique()}")
    if "CUT" in gdf.columns:
        print(f"  Comunas (CUT): {gdf['CUT'].nunique()}")
    if "TIPO_DISTRITO" in gdf.columns:
        print(f"  Tipo distrito:")
        for t, n in gdf["TIPO_DISTRITO"].value_counts().items():
            print(f"    {t}: {n:,}")
    if "viviendas" in gdf.columns:
        print(f"  Total viviendas: {gdf['viviendas'].sum():,.0f}")
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _deduplicate(gdf: gpd.GeoDataFrame, layer: str) -> gpd.GeoDataFrame:
    keys = {
        "comunal":        ["CUT"],
        "distrital":      ["CUT", "COD_DISTRITO"],
        "limite_urbano":  ["CUT", "N_URBANO"],
        "aldea":          ["CUT", "N_ALDEA"],
        "eje_vial":       None,
        "manzana_urbana": ["MANZENT"],
        "manzana_aldea":  ["MANZENT"],
        "puntos_rural":   None,
    }
    key = keys.get(layer)
    if key:
        before = len(gdf)
        key    = [k for k in key if k in gdf.columns]
        if key:
            gdf = gdf.drop_duplicates(subset=key)
        after  = len(gdf)
        if before != after:
            print(f"  → {before - after} duplicados eliminados.")
    return gdf


def _add_standard_ids(gdf: gpd.GeoDataFrame, layer: str) -> gpd.GeoDataFrame:
    if "CUT" in gdf.columns:
        cut = gdf["CUT"].astype(str).str.zfill(5)
        gdf["COD_REGION"]    = cut.str[:2].astype(int)
        gdf["COD_PROVINCIA"] = cut.str[:3].astype(int)

    if layer == "distrital" and "COD_DISTRITO" in gdf.columns:
        cut_str  = gdf["CUT"].astype(str).str.zfill(5)
        dist_str = gdf["COD_DISTRITO"].astype(int).astype(str).str.zfill(3)
        gdf["ID_DIST"] = cut_str + "_" + dist_str

    if layer in ("manzana_urbana", "manzana_aldea"):
        if "MANZENT" in gdf.columns:
            gdf["MANZENT_STR"] = gdf["MANZENT"].astype(str)

    return gdf


def _build_indice(gdf: gpd.GeoDataFrame, id_col: str) -> pd.DataFrame:
    meta_cols = [id_col] + [
        c for c in ["CUT", "N_DISTRITO", "N_COMUNA", "N_REGION",
                    "N_PROVINCIA", "TIPO_DISTRITO", "COD_DISTRITO",
                    "COD_REGION", "viviendas", "total_edificaciones"]
        if c in gdf.columns and c != id_col
    ]
    return gdf[meta_cols].copy()


def _print_national_summary(
    adj: sp.csr_matrix,
    ids: list,
    strategy: str,
    n_bloques: int,
) -> None:
    print(f"\n{'='*55}")
    print(f"  Resultado nacional — estrategia: {strategy}")
    print(f"{'='*55}")
    print(f"  Unidades totales : {len(ids):,}")
    print(f"  Matriz           : {adj.shape[0]:,} × {adj.shape[1]:,}")
    print(f"  Entradas no-cero : {adj.nnz:,}")
    print(f"  Memoria sparse   : {adj.data.nbytes / 1024 / 1024:.1f} MB")
    print(f"  Bloques/regiones : {n_bloques}")
    print(f"{'='*55}")

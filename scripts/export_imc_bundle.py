"""
scripts/export_imc_bundle.py
============================
Exporta un bundle IMC Plan Lab compatible con redistritaje interactivo.

Genera la carpeta imc_bundle_<level>_<scope>/ con:
    units.geojson   — geometrías + atributos en EPSG:4326
    adjacency.json  — lista de pares adyacentes (formato imc-adjacency-v1)
    metadata.json   — metadatos del bundle (formato imc-planlab-bundle-v1)
    README.md       — descripción del bundle

Uso:
    # Nacional, nivel distrital
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital

    # Nacional, nivel comunal
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level comunal

    # Solo RM, nivel distrital
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital --regiones 13

    # Varias regiones
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital --regiones 5,8,13

    # Sin compacidad (más rápido)
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level comunal --no-compacidad

    # Directorio de salida personalizado
    python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital --output-dir ./bundles
"""

import argparse
import json
import os
import sys
import warnings
from datetime import datetime, timezone

warnings.filterwarnings("ignore")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import numpy as np
import pandas as pd
import geopandas as gpd
import scipy.sparse as sp

import chiledist as cd

CRS_OUT = "EPSG:4326"


# ──────────────────────────────────────────────────────────────────────────────
# Argumentos
# ──────────────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description="Exporta bundle IMC Plan Lab desde datos APC 2023."
    )
    p.add_argument(
        "--base-dir", default=".",
        help="Directorio raíz con carpetas SHP_APC2023_R* (default: .)"
    )
    p.add_argument(
        "--level", default="distrital",
        choices=["comunal", "distrital"],
        help="Nivel de análisis: comunal o distrital (default: distrital)"
    )
    p.add_argument(
        "--regiones", default=None,
        help="Regiones a incluir: número, lista (5,8,13) o None para nacional"
    )
    p.add_argument(
        "--output-dir", default=".",
        help="Directorio donde se creará la carpeta del bundle (default: .)"
    )
    p.add_argument(
        "--no-compacidad", action="store_true",
        help="Omitir cálculo de métricas de compacidad (más rápido)"
    )
    p.add_argument(
        "--no-poblacion", action="store_true",
        help="Omitir agregación de población desde manzanas"
    )
    p.add_argument(
        "--no-readme", action="store_true",
        help="Omitir generación de README.md"
    )
    p.add_argument(
        "--connect-islands", default=True, action=argparse.BooleanOptionalAction,
        help="Conectar islas sin vecinos al vecino más cercano (default: True)"
    )
    return p.parse_args()


def parse_regiones(s: str | None) -> list[int] | None:
    if s is None or s.strip().lower() in ("", "none", "nacional", "todas"):
        return None
    return [int(r.strip()) for r in s.split(",")]


# ──────────────────────────────────────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────────────────────────────────────

def export_imc_planlab_bundle(
    level: str = "distrital",
    base_dir: str = ".",
    output_dir: str = ".",
    regions: list[int] | None = None,
    include_compactness: bool = True,
    include_population: bool = True,
    connect_islands: bool = True,
    include_readme: bool = True,
) -> str:
    """
    Exporta un bundle IMC Plan Lab.

    Parameters
    ----------
    level : str
        "comunal" o "distrital"
    base_dir : str
        Directorio raíz con carpetas SHP_APC2023_R*.
    output_dir : str
        Directorio donde se creará la carpeta del bundle.
    regions : list[int] | None
        Regiones a incluir. None = nacional.
    include_compactness : bool
        Calcular e incluir métricas de compacidad.
    include_population : bool
        Agregar población desde manzanas.
    connect_islands : bool
        Conectar islas al vecino más cercano.
    include_readme : bool
        Generar README.md.

    Returns
    -------
    str  Ruta de la carpeta del bundle generada.
    """
    # ── Nombre y carpeta de salida ─────────────────────────────────────────────
    scope      = "nacional" if regions is None else f"R{'_'.join(str(r) for r in sorted(regions))}"
    bundle_dir = os.path.join(output_dir, f"imc_bundle_{level}_{scope}")
    os.makedirs(bundle_dir, exist_ok=True)

    print(f"\nchiledist — Export IMC Plan Lab Bundle")
    print(f"  level      : {level}")
    print(f"  scope      : {scope}")
    print(f"  regions    : {regions or 'todas'}")
    print(f"  output     : {bundle_dir}")

    # ── 1. Cargar capa geográfica ──────────────────────────────────────────────
    print(f"\n[1/6] Cargando capa '{level}'...")

    gdf = cd.load_layer(level, base_dir=base_dir, regions=regions, add_ids=True)
    print(f"      {len(gdf):,} unidades cargadas")

    # ── 2. Agregar población ───────────────────────────────────────────────────
    if include_population:
        print(f"\n[2/6] Agregando población...")
        try:
            mz_urb = cd.load_layer("manzana_urbana", base_dir=base_dir,
                                    regions=regions)
            mz_ald = cd.load_layer("manzana_aldea",  base_dir=base_dir,
                                    regions=regions)

            pop_urb = cd.aggregate_population(mz_urb, level="distrito"
                                               if level == "distrital" else "comuna",
                                               source="urbana")
            pop_ald = cd.aggregate_population(mz_ald, level="distrito"
                                               if level == "distrital" else "aldea",
                                               source="aldea")

            merge_keys = (["CUT", "COD_DISTRITO"] if level == "distrital"
                          else ["CUT"])
            pop = (
                pop_urb.merge(pop_ald, on=merge_keys,
                               how="outer", suffixes=("_urb", "_ald"))
                .fillna(0)
            )
            pop["viviendas"] = (
                pop.get("viviendas_urb", 0) + pop.get("viviendas_ald", 0)
            )
            gdf = gdf.merge(pop[merge_keys + ["viviendas"]],
                             on=merge_keys, how="left")
            gdf["viviendas"] = gdf["viviendas"].fillna(0).astype(int)
            print(f"      viviendas totales: {gdf['viviendas'].sum():,}")
        except Exception as e:
            print(f"      ⚠ No se pudo agregar población: {e}")
            gdf["viviendas"] = 0
    else:
        print(f"\n[2/6] Población omitida (--no-poblacion)")
        gdf["viviendas"] = 0

    # ── 3. Calcular compacidad ─────────────────────────────────────────────────
    id_col = "ID_DIST" if level == "distrital" else "CUT"

    if include_compactness:
        print(f"\n[3/6] Calculando métricas de compacidad...")
        try:
            metricas = cd.all_compactness(gdf, id_col=id_col)
            gdf = gdf.merge(
                metricas[[id_col, "polsby_popper", "reock",
                           "convex_hull_ratio", "schwartzberg",
                           "compactness_mean"]],
                on=id_col, how="left"
            )
            print(f"      PP mediana: {gdf['polsby_popper'].median():.3f}")
        except Exception as e:
            print(f"      ⚠ No se pudo calcular compacidad: {e}")
    else:
        print(f"\n[3/6] Compacidad omitida (--no-compacidad)")

    # ── 4. Construir grafo de adyacencia ───────────────────────────────────────
    print(f"\n[4/6] Construyendo grafo de adyacencia...")
    G, adj, id_list = cd.build_graph(
        gdf, id_col=id_col,
        method="queen",
        connect_islands=connect_islands,
    )
    stats = cd.graph_stats(G, adj)
    print(f"      nodos: {G.number_of_nodes():,}  "
          f"aristas: {G.number_of_edges():,}  "
          f"componentes: {stats.loc['componentes','valor']}")

    # ── 5. Construir archivos del bundle ───────────────────────────────────────
    print(f"\n[5/6] Construyendo archivos del bundle...")

    # ── units.geojson ─────────────────────────────────────────────────────────
    gdf_out = _build_units(gdf, level, id_col, include_compactness,
                            include_population)

    # Validaciones
    _validate_units(gdf_out)

    # Reproyectar a EPSG:4326
    if gdf_out.crs is None or str(gdf_out.crs) != CRS_OUT:
        gdf_out = gdf_out.to_crs(CRS_OUT)

    units_path = os.path.join(bundle_dir, "units.geojson")
    gdf_out.to_file(units_path, driver="GeoJSON")
    print(f"      units.geojson  — {len(gdf_out):,} features")

    # ── adjacency.json ────────────────────────────────────────────────────────
    unit_ids_set = set(gdf_out["unit_id"].tolist())
    edges        = _build_edges(adj, id_list, unit_ids_set)

    adjacency = {
        "format":       "imc-adjacency-v1",
        "directed":     False,
        "unit_id_field": "unit_id",
        "edges":        edges,
    }

    # Validar edges
    _validate_edges(edges, unit_ids_set)

    adj_path = os.path.join(bundle_dir, "adjacency.json")
    with open(adj_path, "w", encoding="utf-8") as f:
        json.dump(adjacency, f, ensure_ascii=False, separators=(",", ":"))
    print(f"      adjacency.json — {len(edges):,} edges")

    # ── metadata.json ─────────────────────────────────────────────────────────
    import networkx as nx
    degrees   = [d for _, d in G.degree()]
    n_islands = sum(1 for d in degrees if d == 0)

    metadata = {
        "format":     "imc-planlab-bundle-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name":            "APC 2023",
            "institution":     "INE Chile",
            "url":             "https://www.ine.gob.cl",
            "library":         "chiledist",
            "library_version": cd.__version__,
        },
        "level":        level,
        "scope":        "nacional" if regions is None else "regional",
        "regions":      regions,
        "crs":          CRS_OUT,
        "id_field":     "unit_id",
        "name_field":   "name",
        "region_field": "region_id",
        "graph": {
            "nodes":            G.number_of_nodes(),
            "edges":            G.number_of_edges(),
            "average_degree":   round(float(np.mean(degrees)), 3),
            "connected_components": nx.number_connected_components(G),
            "isolated_nodes":   n_islands,
        },
        "files": {
            "units":     "units.geojson",
            "adjacency": "adjacency.json",
        },
        "generation_parameters": {
            "level":               level,
            "regions":             regions,
            "strategy":            "full" if regions is None else "regional",
            "connect_islands":     connect_islands,
            "include_compactness": include_compactness,
            "include_population":  include_population,
        },
    }

    meta_path = os.path.join(bundle_dir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"      metadata.json")

    # ── README.md ─────────────────────────────────────────────────────────────
    if include_readme:
        readme = _build_readme(metadata, gdf_out, edges)
        readme_path = os.path.join(bundle_dir, "README.md")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme)
        print(f"      README.md")

    # ── 6. Resumen final ───────────────────────────────────────────────────────
    print(f"\n[6/6] Validación final...")
    _validate_bundle(bundle_dir, gdf_out, edges, unit_ids_set)

    print(f"\n{'='*55}")
    print(f"  Bundle generado: {bundle_dir}")
    print(f"{'='*55}")
    print(f"  units.geojson  : {len(gdf_out):,} features  ({_file_size(units_path)})")
    print(f"  adjacency.json : {len(edges):,} edges      ({_file_size(adj_path)})")
    print(f"  metadata.json  : {_file_size(meta_path)}")
    if include_readme:
        print(f"  README.md      : {_file_size(readme_path)}")

    return bundle_dir


# ──────────────────────────────────────────────────────────────────────────────
# Construcción de units.geojson
# ──────────────────────────────────────────────────────────────────────────────

def _build_units(
    gdf: gpd.GeoDataFrame,
    level: str,
    id_col: str,
    include_compactness: bool,
    include_population: bool,
) -> gpd.GeoDataFrame:
    """Construye el GeoDataFrame de units con campos estandarizados."""

    out = gdf[["geometry"]].copy()

    # ── Campos obligatorios ───────────────────────────────────────────────────
    out["unit_id"] = gdf[id_col].astype(str)
    out["level"]   = level

    if level == "distrital":
        out["name"] = gdf.get("N_DISTRITO", gdf.get("N_COMUNA", "")).fillna("")
    else:
        out["name"] = gdf.get("N_COMUNA", "").fillna("")

    out["region_id"]   = gdf.get("COD_REGION", "").astype(str).str.zfill(2)
    out["region_name"] = gdf.get("N_REGION",   "").fillna("")

    # ── Campos específicos por nivel ──────────────────────────────────────────
    if level == "distrital":
        _add_if_exists(out, gdf, "ID_DIST")
        _add_if_exists(out, gdf, "N_DISTRITO")
        _add_if_exists(out, gdf, "CUT",       cast=str)
        _add_if_exists(out, gdf, "N_COMUNA")
        _add_if_exists(out, gdf, "N_REGION")
        _add_if_exists(out, gdf, "COD_REGION")
        _add_if_exists(out, gdf, "TIPO_DISTRITO")
        _add_if_exists(out, gdf, "COD_DISTRITO")
    else:
        _add_if_exists(out, gdf, "CUT",        cast=str)
        _add_if_exists(out, gdf, "N_COMUNA")
        _add_if_exists(out, gdf, "N_REGION")
        _add_if_exists(out, gdf, "COD_REGION")
        _add_if_exists(out, gdf, "N_PROVINCIA")

    # ── Población ─────────────────────────────────────────────────────────────
    if include_population and "viviendas" in gdf.columns:
        out["viviendas"]  = gdf["viviendas"].fillna(0).astype(int)
        out["population"] = out["viviendas"]   # alias para compatibilidad IMC

    # ── Compacidad ────────────────────────────────────────────────────────────
    if include_compactness:
        for col in ["polsby_popper", "reock", "convex_hull_ratio",
                    "schwartzberg", "compactness_mean"]:
            if col in gdf.columns:
                out[col] = gdf[col].round(6)

    return out.reset_index(drop=True)


def _add_if_exists(
    out: gpd.GeoDataFrame,
    src: gpd.GeoDataFrame,
    col: str,
    cast=None,
) -> None:
    """Agrega una columna de src a out si existe, con cast opcional."""
    if col in src.columns:
        vals = src[col]
        if cast is not None:
            vals = vals.astype(cast)
        out[col] = vals.values


# ──────────────────────────────────────────────────────────────────────────────
# Construcción de edges
# ──────────────────────────────────────────────────────────────────────────────

def _build_edges(
    adj: sp.csr_matrix,
    id_list: list,
    unit_ids_set: set,
) -> list[list[str]]:
    """
    Construye lista de pares adyacentes desde la matriz sparse.
    - Cada par aparece una sola vez (i < j)
    - Sin self-loops
    - Solo IDs que existen en unit_ids_set
    """
    adj_coo = adj.tocoo()
    edges   = []
    seen    = set()

    for i, j in zip(adj_coo.row, adj_coo.col):
        if i >= j:
            continue
        id_i = str(id_list[i])
        id_j = str(id_list[j])
        if id_i not in unit_ids_set or id_j not in unit_ids_set:
            continue
        pair = (min(id_i, id_j), max(id_i, id_j))
        if pair in seen:
            continue
        seen.add(pair)
        edges.append([id_i, id_j])

    return edges


# ──────────────────────────────────────────────────────────────────────────────
# Validaciones
# ──────────────────────────────────────────────────────────────────────────────

def _validate_units(gdf: gpd.GeoDataFrame) -> None:
    """Valida el GeoDataFrame de units antes de exportar."""
    errors = []

    # unit_id sin nulos
    if gdf["unit_id"].isna().any():
        n = gdf["unit_id"].isna().sum()
        errors.append(f"unit_id tiene {n} valor(es) nulo(s)")

    # unit_id único
    dupes = gdf["unit_id"].duplicated().sum()
    if dupes:
        errors.append(f"unit_id tiene {dupes} valor(es) duplicado(s)")

    # Geometrías válidas
    invalid = (~gdf.geometry.is_valid).sum()
    if invalid:
        print(f"  ⚠ {invalid} geometría(s) inválida(s) — se aplicará buffer(0)")
        gdf["geometry"] = gdf["geometry"].buffer(0)

    if errors:
        raise ValueError("Validación de units.geojson falló:\n  " +
                         "\n  ".join(errors))
    print(f"      ✓ units.geojson válido")


def _validate_edges(edges: list, unit_ids_set: set) -> None:
    """Valida la lista de edges."""
    errors   = []
    seen     = set()
    id_extra = set()

    for edge in edges:
        a, b = edge[0], edge[1]

        # Self-loops
        if a == b:
            errors.append(f"Self-loop: {a}")

        # IDs fuera de units
        for uid in (a, b):
            if uid not in unit_ids_set:
                id_extra.add(uid)

        # Duplicados
        pair = (min(a, b), max(a, b))
        if pair in seen:
            errors.append(f"Edge duplicado: {pair}")
        seen.add(pair)

    if id_extra:
        errors.append(f"IDs en edges no encontrados en units: "
                       f"{list(id_extra)[:5]}{'...' if len(id_extra)>5 else ''}")

    if errors:
        raise ValueError("Validación de adjacency.json falló:\n  " +
                         "\n  ".join(errors[:10]))
    print(f"      ✓ adjacency.json válido")


def _validate_bundle(
    bundle_dir: str,
    gdf: gpd.GeoDataFrame,
    edges: list,
    unit_ids_set: set,
) -> None:
    """Validación cruzada del bundle completo."""
    errors = []

    # CRS
    if str(gdf.crs) != CRS_OUT:
        errors.append(f"CRS incorrecto: {gdf.crs} (esperado {CRS_OUT})")

    # Todos los archivos existen
    for fname in ["units.geojson", "adjacency.json", "metadata.json"]:
        if not os.path.exists(os.path.join(bundle_dir, fname)):
            errors.append(f"Archivo faltante: {fname}")

    # IDs en edges están en units
    edge_ids = set()
    for a, b in edges:
        edge_ids.add(a)
        edge_ids.add(b)
    missing = edge_ids - unit_ids_set
    if missing:
        errors.append(f"IDs en edges no encontrados en units: {len(missing)}")

    if errors:
        print(f"\n  ⚠ Advertencias de validación:")
        for e in errors:
            print(f"    • {e}")
    else:
        print(f"      ✓ Bundle completo y válido")


# ──────────────────────────────────────────────────────────────────────────────
# README
# ──────────────────────────────────────────────────────────────────────────────

def _build_readme(
    metadata: dict,
    gdf: gpd.GeoDataFrame,
    edges: list,
) -> str:
    level   = metadata["level"]
    scope   = metadata["scope"]
    regions = metadata["regions"]
    graph   = metadata["graph"]
    created = metadata["created_at"][:10]

    region_str = ("todas las regiones" if regions is None
                  else f"región(es) {regions}")

    compactness_cols = [c for c in ["polsby_popper","reock",
                                     "convex_hull_ratio","schwartzberg"]
                        if c in gdf.columns]
    pop_str = ("incluida" if "viviendas" in gdf.columns
               and gdf["viviendas"].sum() > 0 else "no incluida")

    return f"""# IMC Plan Lab Bundle — {level.capitalize()} / {scope.capitalize()}

Generado por **chiledist v{metadata['source']['library_version']}**
Fuente: {metadata['source']['name']} ({metadata['source']['institution']})
Fecha: {created}

## Contenido

| Archivo | Descripción |
|---------|-------------|
| `units.geojson` | {graph['nodes']:,} unidades geográficas en EPSG:4326 |
| `adjacency.json` | {graph['edges']:,} pares de unidades adyacentes |
| `metadata.json` | Metadatos y parámetros de generación |

## Parámetros

- **Nivel**: `{level}` ({region_str})
- **CRS**: `{CRS_OUT}`
- **ID campo**: `unit_id`
- **Población**: {pop_str}
- **Compacidad**: {', '.join(compactness_cols) if compactness_cols else 'no incluida'}
- **Islas conectadas**: {metadata['generation_parameters']['connect_islands']}

## Grafo de adyacencia

| Métrica | Valor |
|---------|-------|
| Nodos | {graph['nodes']:,} |
| Aristas | {graph['edges']:,} |
| Grado promedio | {graph['average_degree']} |
| Componentes conexos | {graph['connected_components']} |
| Nodos aislados | {graph['isolated_nodes']} |

## Campos en units.geojson

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `unit_id` | string | Identificador único estable |
| `level` | string | Nivel: `{level}` |
| `name` | string | Nombre legible |
| `region_id` | string | Código de región (2 dígitos) |
| `region_name` | string | Nombre de región |
{'| `viviendas` | integer | Total de viviendas (proxy poblacional) |' if 'viviendas' in gdf.columns else ''}
{'| `population` | integer | Alias de viviendas (compatibilidad IMC) |' if 'viviendas' in gdf.columns else ''}
{chr(10).join(f'| `{c}` | float | Métrica de compacidad |' for c in compactness_cols)}

## Formato adjacency.json

```json
{{
  "format": "imc-adjacency-v1",
  "directed": false,
  "unit_id_field": "unit_id",
  "edges": [["id_a", "id_b"], ...]
}}
```

## Uso rápido

```python
import geopandas as gpd, json, networkx as nx

units = gpd.read_file("units.geojson")
adj   = json.load(open("adjacency.json"))

G = nx.Graph()
G.add_nodes_from(units["unit_id"])
G.add_edges_from(adj["edges"])

print(f"{{len(G.nodes)}} nodos · {{len(G.edges)}} aristas")
```

## Equivalencia censal

| USA Census | Chile INE | Campo ID |
|-----------|-----------|----------|
| Census Tract | Distrito APC | `ID_DIST` |
| Municipality | Comuna | `CUT` |

---
Generado con [chiledist](https://github.com/chiledist) · Datos: APC 2023, INE Chile
"""


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades
# ──────────────────────────────────────────────────────────────────────────────

def _file_size(path: str) -> str:
    """Retorna el tamaño de un archivo en formato legible."""
    size = os.path.getsize(path)
    if size < 1024:
        return f"{size} B"
    elif size < 1024 ** 2:
        return f"{size/1024:.1f} KB"
    else:
        return f"{size/1024**2:.1f} MB"


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():
    args    = parse_args()
    regions = parse_regiones(args.regiones)

    export_imc_planlab_bundle(
        level               = args.level,
        base_dir            = args.base_dir,
        output_dir          = args.output_dir,
        regions             = regions,
        include_compactness = not args.no_compacidad,
        include_population  = not args.no_poblacion,
        connect_islands     = args.connect_islands,
        include_readme      = not args.no_readme,
    )


if __name__ == "__main__":
    main()

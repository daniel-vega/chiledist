"""
hierarchy.py
============
Contracción y explosión de unidades censales entre niveles de la
jerarquía APC. Permite cambiar la unidad de decisión del redistritaje
sin cambiar los datos de observación.

Ejemplo de uso:
    # Contraer APC → comunas (modo legal)
    comunas = contract_to_decision_units(
        distritos_apc,
        decision_unit="CUT",
        agg_spec={"viviendas": "sum"},
    )

    # Validar que ID_DIST → CUT es una función inyectiva
    validate_hierarchy(distritos_apc, "ID_DIST", "CUT")
"""

from __future__ import annotations
from typing import Optional

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.ops import unary_union


# ──────────────────────────────────────────────────────────────────────────────
# Normalización de códigos CUT
# ──────────────────────────────────────────────────────────────────────────────

def normalize_cut(value) -> str:
    """
    Normaliza un código CUT a su forma canónica: string de 5 dígitos con
    cero a la izquierda cuando corresponda (ej. 1101 -> "01101",
    "1101" -> "01101", "01101" -> "01101"). Acepta int, str o cualquier
    valor numérico (incluye floats tipo 1101.0, típicos de columnas leídas
    desde CSV).

    No es necesario decidir si una fuente de datos usa CUT de 4 o 5
    dígitos: distintas fuentes (shapefiles APC, Censo 2024, SERVEL,
    datos/asignacion_vigente.json, datos/pacto_map_2025.json) pueden
    representarlo con o sin cero inicial, o como int en vez de string.
    Pasar el CUT de ambos lados de un cruce por esta función antes de
    comparar/mergear los hace equivalentes sin importar el formato de
    origen — evita joins que fallan en silencio cuando dos fuentes
    difieren solo en el padding (ver README.md § Datos externos).

    Parameters
    ----------
    value : int | str | float
        Código CUT en cualquier representación.

    Returns
    -------
    str
        CUT normalizado a 5 dígitos.
    """
    return f"{int(float(value)):05d}"


# ──────────────────────────────────────────────────────────────────────────────
# Contracción al nivel de decisión
# ──────────────────────────────────────────────────────────────────────────────

def contract_to_decision_units(
    gdf: gpd.GeoDataFrame,
    decision_unit: str,
    current_unit: Optional[str] = None,
    agg_spec: Optional[dict] = None,
    preserve_cols: Optional[list[str]] = None,
) -> gpd.GeoDataFrame:
    """
    Contrae el GeoDataFrame desde la unidad actual hasta la unidad de decisión.

    Si decision_unit == current_unit, devuelve una copia sin modificar.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Capa de unidades de observación (ej. distritos APC).
    decision_unit : str
        Columna de la unidad destino (ej. "CUT").
    current_unit : str, optional
        Columna de la unidad actual. Si None, se infiere buscando
        'ID_DIST', 'CUT', 'MANZENT' en ese orden.
    agg_spec : dict, optional
        Especificación de agregación {col: func}.
        Default: {"viviendas": "sum"} si existe la columna.
    preserve_cols : list[str], optional
        Columnas de nivel superior a preservar con "first".
        Default: COD_REGION, N_REGION, N_PROVINCIA, COD_PROVINCIA.

    Returns
    -------
    gpd.GeoDataFrame con decision_unit como columna de ID.

    Examples
    --------
    >>> comunas = contract_to_decision_units(
    ...     distritos, decision_unit="CUT",
    ...     agg_spec={"viviendas": "sum"},
    ... )
    """
    if current_unit is None:
        for candidate in ("ID_DIST", "CUT", "MANZENT"):
            if candidate in gdf.columns:
                current_unit = candidate
                break
        if current_unit is None:
            raise ValueError(
                "No se pudo inferir current_unit. "
                "Especifica current_unit explícitamente."
            )

    if decision_unit == current_unit:
        return gdf.copy()

    if decision_unit not in gdf.columns:
        raise KeyError(
            f"Columna '{decision_unit}' no encontrada en el GeoDataFrame. "
            f"Columnas disponibles: {list(gdf.columns)}"
        )

    crs_orig = gdf.crs

    if agg_spec is None:
        agg_spec = {}
        if "viviendas" in gdf.columns:
            agg_spec["viviendas"] = "sum"

    # Columnas jerárquicamente superiores a preservar
    _default_preserve = [
        "COD_REGION", "N_REGION",
        "N_PROVINCIA", "COD_PROVINCIA",
    ]
    if preserve_cols is None:
        preserve_cols = [
            c for c in _default_preserve
            if c in gdf.columns and c != decision_unit
        ]

    # Construir dict de agregación
    agg_dict: dict = {}
    for col, func in agg_spec.items():
        if col in gdf.columns and col != decision_unit:
            agg_dict[col] = func
    for col in preserve_cols:
        if col not in agg_dict:
            agg_dict[col] = "first"
    agg_dict["geometry"] = lambda x: unary_union(x.values)

    # Seleccionar columnas necesarias
    cols_data = [
        c for c in agg_dict if c != "geometry" and c in gdf.columns
    ]
    cols_select = list(dict.fromkeys([decision_unit] + cols_data))
    gdf_sub = gdf[cols_select].copy()
    gdf_sub["geometry"] = gdf["geometry"].values

    result = (
        gdf_sub
        .groupby(decision_unit, as_index=False)
        .agg(agg_dict)
    )

    result = gpd.GeoDataFrame(result, geometry="geometry", crs=crs_orig)
    result["geometry"] = result["geometry"].buffer(0)

    print(f"  Contraído: {len(gdf):,} {current_unit} "
          f"→ {len(result):,} {decision_unit}")

    return result.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Atajo de alto nivel
# ──────────────────────────────────────────────────────────────────────────────

def build_decision_layer(
    gdf: gpd.GeoDataFrame,
    decision_unit: str,
    pop_col: Optional[str] = None,
    extra_agg: Optional[dict] = None,
) -> gpd.GeoDataFrame:
    """
    Construye el GeoDataFrame de la unidad de decisión desde la capa APC.
    Combina contract_to_decision_units con agregación estándar.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Capa de observación (ej. distritos APC con viviendas).
    decision_unit : str
        Columna de la unidad de decisión destino (ej. "CUT").
    pop_col : str, optional
        Columna de población a sumar. Si None, busca 'viviendas'.
    extra_agg : dict, optional
        Columnas adicionales a agregar {col: func}.

    Returns
    -------
    gpd.GeoDataFrame listo para build_graph().

    Examples
    --------
    >>> comunas = build_decision_layer(distritos, "CUT")
    >>> # columnas: CUT, viviendas, geometry, COD_REGION, N_REGION, ...
    """
    pc = pop_col or ("viviendas" if "viviendas" in gdf.columns else None)
    agg: dict = {}
    if pc and pc in gdf.columns:
        agg[pc] = "sum"
    if extra_agg:
        agg.update({k: v for k, v in extra_agg.items()
                    if k in gdf.columns})

    return contract_to_decision_units(
        gdf, decision_unit=decision_unit, agg_spec=agg
    )


# ──────────────────────────────────────────────────────────────────────────────
# Validación de jerarquía
# ──────────────────────────────────────────────────────────────────────────────

def validate_hierarchy(
    gdf: gpd.GeoDataFrame,
    fine_col: str,
    coarse_col: str,
) -> pd.DataFrame:
    """
    Verifica que cada unidad fina pertenezca a exactamente una unidad gruesa.
    Útil para confirmar que ID_DIST → CUT es una función inyectiva
    (condición necesaria para que la restricción de preservación tenga sentido).

    Returns
    -------
    pd.DataFrame con las unidades que violan la jerarquía (vacío = OK).
    """
    if fine_col not in gdf.columns:
        raise KeyError(f"Columna '{fine_col}' no encontrada.")
    if coarse_col not in gdf.columns:
        raise KeyError(f"Columna '{coarse_col}' no encontrada.")

    counts = (
        gdf.groupby(fine_col)[coarse_col]
        .nunique()
        .reset_index(name="n_coarse")
    )
    violations = counts[counts["n_coarse"] > 1].copy()

    if violations.empty:
        print(f"  Jerarquía {fine_col} → {coarse_col}: OK "
              f"({len(counts):,} unidades, todas con un único {coarse_col}).")
    else:
        print(
            f"  AVISO: {len(violations)} unidades de '{fine_col}' "
            f"pertenecen a más de una unidad de '{coarse_col}'."
        )

    return violations


# ──────────────────────────────────────────────────────────────────────────────
# Utilidades de herencia de atributos
# ──────────────────────────────────────────────────────────────────────────────

def propagate_district_assignment(
    assignment_coarse: dict,
    gdf_fine: gpd.GeoDataFrame,
    fine_col: str,
    coarse_col: str,
) -> dict:
    """
    Expande una asignación a nivel grueso hacia las unidades finas.

    Útil para, dado un plan a nivel comunal (CUT → district),
    obtener el plan equivalente a nivel APC (ID_DIST → district).

    Parameters
    ----------
    assignment_coarse : dict
        {coarse_id: district_id}
    gdf_fine : gpd.GeoDataFrame
        Capa fina con columnas fine_col y coarse_col.
    fine_col : str
        Columna de la unidad fina (ej. "ID_DIST").
    coarse_col : str
        Columna de la unidad gruesa (ej. "CUT").

    Returns
    -------
    dict {fine_id: district_id}
    """
    coarse_to_district = assignment_coarse
    result = {}
    for _, row in gdf_fine[[fine_col, coarse_col]].iterrows():
        fine_id   = row[fine_col]
        coarse_id = row[coarse_col]
        if coarse_id in coarse_to_district:
            result[fine_id] = coarse_to_district[coarse_id]
    return result

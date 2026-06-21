"""
chiledist/scenario_comparison.py
=================================
Funciones para comparar ensembles de redistritaje entre distintos escenarios.

API principal
-------------
    compare_ensembles(ensembles, baseline)    -> DataFrame resumen con deltas
    scenario_delta(df_comp, baseline)         -> DataFrame + columnas delta_*
    rank_scenarios(df_comp, weights)          -> DataFrame ordenado por score
    plot_tradeoff_frontier(...)               -> Figure scatter + Pareto
    plot_boxplots_comparativos(...)           -> Figure boxplots por métrica
    load_ensembles_from_disk(...)             -> dict {nombre: DataFrame}
    split_frequency_table(results_dir, ...)   -> DataFrame frecuencia de cortes
"""

from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

# ── Constantes de visualización ───────────────────────────────────────────────

COLORES_DEFAULT: Dict[str, str] = {
    # nombres ScenarioConfig (actuales)
    "legal":                     "#1D6A96",
    "apc_free":                  "#D85A30",
    "apc_soft":                  "#6A3D9A",
    # aliases de compatibilidad
    "legal_comunas":             "#1D6A96",
    "experimental_apc_libre":    "#D85A30",
    "experimental_apc_soft_cut": "#6A3D9A",
}

NOMBRES_CORTOS: Dict[str, str] = {
    "legal":                     "Legal (CUT)",
    "apc_free":                  "APC libre",
    "apc_soft":                  "APC soft",
    # aliases de compatibilidad
    "legal_comunas":             "Legal (CUT)",
    "experimental_apc_libre":    "APC libre",
    "experimental_apc_soft_cut": "APC soft",
}

_BG = "#F8F7F4"

# (columna_ensemble, etiqueta_humana, dirección_óptima)
METRICAS_STD: List[Tuple[str, str, str]] = [
    ("max_dev_pob_pct",    "Balance pob. — desv. máx (%)",  "min"),
    ("pp_promedio",        "Compacidad Polsby-Popper",        "max"),
    ("cut_edges",          "Aristas cortadas",                "min"),
    ("n_comunas_partidas", "Comunas partidas",                "min"),
    ("split_severity",     "Severidad de cortes",             "min"),
]

PESOS_DEFAULT: Dict[str, float] = {
    "max_dev_pob_pct":    0.35,
    "pp_promedio":        0.25,
    "cut_edges":          0.20,
    "n_comunas_partidas": 0.15,
    "split_severity":     0.05,
}

# ──────────────────────────────────────────────────────────────────────────────
# ScoringConfig — configuración de puntaje compuesto
# ──────────────────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class ScoringConfig:
    """
    Encapsula la configuración del puntaje compuesto para rank_scenarios.

    Attributes
    ----------
    weights : dict {col: float}
        Pesos relativos por métrica (no necesitan sumar 1.0 — son relativos).
    directions : dict {col: "min"|"max"}
        Dirección óptima de cada métrica.
    normalization : str
        Estrategia de normalización al intervalo [0, 1]:
        - "minmax" : (x − min) / (max − min)   [default]
        - "zscore" : z-score escalado a [0, 1]
        - "rank"   : percentil de rango

    Examples
    --------
    >>> sc = ScoringConfig.default()
    >>> sc_custom = ScoringConfig.from_weights({"pp_promedio": 0.6,
    ...                                          "max_dev_pob_pct": 0.4})
    """
    weights:       Dict[str, float]
    directions:    Dict[str, str]
    normalization: str = "minmax"

    def __post_init__(self):
        valid_dirs   = {"min", "max"}
        valid_norms  = {"minmax", "zscore", "rank"}
        for col, d in self.directions.items():
            if d not in valid_dirs:
                raise ValueError(
                    f"Dirección inválida '{d}' para '{col}'. Use 'min' o 'max'."
                )
        if self.normalization not in valid_norms:
            raise ValueError(
                f"normalization debe ser 'minmax', 'zscore' o 'rank'. "
                f"Recibido: '{self.normalization}'."
            )

    @classmethod
    def default(cls) -> "ScoringConfig":
        """Configuración por defecto desde PESOS_DEFAULT y METRICAS_STD."""
        return cls(
            weights    = dict(PESOS_DEFAULT),
            directions = {col: d for col, _, d in METRICAS_STD},
        )

    @classmethod
    def from_weights(
        cls,
        weights: Dict[str, float],
        extra_directions: Optional[Dict[str, str]] = None,
        normalization: str = "minmax",
    ) -> "ScoringConfig":
        """
        Crea ScoringConfig desde un dict de pesos.

        Infiere las direcciones de METRICAS_STD para las métricas conocidas.
        Las métricas no encontradas en METRICAS_STD usan dirección "min".

        Parameters
        ----------
        weights : dict
            Pesos por columna base (ej. {"pp_promedio": 0.6}).
        extra_directions : dict, opcional
            Sobreescribe o añade direcciones para métricas no en METRICAS_STD.
        """
        directions = {col: d for col, _, d in METRICAS_STD}
        for col in weights:
            if col not in directions:
                directions[col] = "min"
        if extra_directions:
            directions.update(extra_directions)
        return cls(weights=weights, directions=directions, normalization=normalization)


_REGION_NOMBRES = {
    1: "R01_TARAPACA",    2: "R02_ANTOFAGASTA",
    3: "R03_ATACAMA",     4: "R04_COQUIMBO",
    5: "R05_VALPARAISO",  6: "R06_OHIGGINS",
    7: "R07_MAULE",       8: "R08_BIOBIO",
    9: "R09_ARAUCANIA",  10: "R10_LOS_LAGOS",
    11: "R11_AYSEN",     12: "R12_MAGALLANES",
    13: "R13_METROPOLITANA", 14: "R14_LOS_RIOS",
    15: "R15_ARICA",     16: "R16_NUBLE",
}


# ──────────────────────────────────────────────────────────────────────────────
# Carga de datos
# ──────────────────────────────────────────────────────────────────────────────

def load_ensembles_from_disk(
    output_base: str,
    region_code: int | str,
    scenario_names: List[str],
) -> Dict[str, pd.DataFrame]:
    """
    Lee ensemble_stats.csv para cada escenario desde disco.

    Parameters
    ----------
    output_base : str
        Directorio base de salida (contiene datos/<REGION>/redistritaje/…).
    region_code : int | str
        Código de región (int) o nombre de subcarpeta (str).
    scenario_names : list[str]
        Nombres de escenarios (subcarpetas en redistritaje/).

    Returns
    -------
    dict {scenario_name: DataFrame} — solo los encontrados en disco.
    """
    if isinstance(region_code, int):
        region_name = _REGION_NOMBRES.get(region_code, f"R{region_code:02d}")
    else:
        region_name = str(region_code)

    ensembles: Dict[str, pd.DataFrame] = {}
    for sc_name in scenario_names:
        path = (Path(output_base) / region_name
                / "redistritaje" / sc_name / "ensemble_stats.csv")
        if path.exists():
            try:
                ensembles[sc_name] = pd.read_csv(path)
            except Exception as e:
                print(f"  ⚠ No se pudo leer {path}: {e}")
        else:
            print(f"  ⚠ No encontrado: {path}")
    return ensembles


# ──────────────────────────────────────────────────────────────────────────────
# compare_ensembles
# ──────────────────────────────────────────────────────────────────────────────

def compare_ensembles(
    ensembles: Dict[str, pd.DataFrame],
    baseline: str = "legal_comunas",
    percentiles: Tuple[float, float] = (0.25, 0.75),
) -> pd.DataFrame:
    """
    Resume y compara estadísticas de ensemble entre escenarios.

    Calcula mediana, p25 y p75 de cada métrica estándar, luego agrega
    columnas delta_* con la diferencia respecto al escenario baseline.

    Parameters
    ----------
    ensembles : dict {scenario_name: DataFrame}
        DataFrames de ensemble_stats.csv indexados por nombre de escenario.
    baseline : str
        Nombre del escenario de referencia para los deltas.
    percentiles : (float, float)
        Percentiles inferior y superior a reportar.

    Returns
    -------
    DataFrame con una fila por escenario y columnas:
        escenario, <col>_median, <col>_p25, <col>_p75, delta_<col>_median.
    """
    rows = []
    for sc_name, df in ensembles.items():
        row: Dict = {"escenario": sc_name}
        for col, _, _ in METRICAS_STD:
            if col in df.columns:
                vals = df[col].dropna()
                if len(vals):
                    row[f"{col}_median"] = round(float(vals.median()), 4)
                    row[f"{col}_p25"]    = round(float(vals.quantile(percentiles[0])), 4)
                    row[f"{col}_p75"]    = round(float(vals.quantile(percentiles[1])), 4)
                else:
                    row[f"{col}_median"] = None
                    row[f"{col}_p25"]    = None
                    row[f"{col}_p75"]    = None
            else:
                row[f"{col}_median"] = None
                row[f"{col}_p25"]    = None
                row[f"{col}_p75"]    = None
        rows.append(row)

    df_comp = pd.DataFrame(rows)
    if df_comp.empty:
        return df_comp

    return scenario_delta(df_comp, baseline=baseline)


# ──────────────────────────────────────────────────────────────────────────────
# scenario_delta
# ──────────────────────────────────────────────────────────────────────────────

def scenario_delta(
    df_comp: pd.DataFrame,
    baseline: str = "legal_comunas",
    metric_cols: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Agrega columnas delta_<col> con diferencia respecto al escenario baseline.

    Delta = valor_escenario − valor_baseline.
    Para métricas donde "menor es mejor", delta negativo = mejora.

    Parameters
    ----------
    df_comp : DataFrame
        Salida de compare_ensembles() o tabla con columnas *_median.
    baseline : str
        Escenario de referencia (debe existir en df_comp["escenario"]).
    metric_cols : list[str], opcional
        Columnas a diferenciar. Por defecto: todas las columnas *_median.
    """
    if baseline not in df_comp["escenario"].values:
        return df_comp

    df_out = df_comp.copy()
    baseline_row = df_out[df_out["escenario"] == baseline].iloc[0]

    if metric_cols is None:
        metric_cols = [f"{col}_median" for col, _, _ in METRICAS_STD
                       if f"{col}_median" in df_out.columns]

    for col in metric_cols:
        if col not in df_out.columns:
            continue
        ref = baseline_row.get(col)
        if ref is None or pd.isna(ref):
            continue
        df_out[f"delta_{col}"] = (df_out[col].astype(float) - float(ref)).round(4)

    return df_out


# ──────────────────────────────────────────────────────────────────────────────
# rank_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def rank_scenarios(
    df_comp: pd.DataFrame,
    weights: Optional[Dict[str, float]] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> pd.DataFrame:
    """
    Ordena escenarios por score compuesto ponderado.

    Cada métrica se normaliza a [0, 1] según la estrategia de ScoringConfig;
    el score parcial es val_norm (max-better) o 1 − val_norm (min-better).
    La suma ponderada forma el composite_score (mayor = mejor).

    Parameters
    ----------
    weights : dict, opcional
        Pesos por columna base, ej. {"max_dev_pob_pct": 0.4}.
        Si None y scoring_config es None, usa PESOS_DEFAULT.
        Ignorado si scoring_config está presente.
    scoring_config : ScoringConfig, opcional
        Configuración completa (pesos + direcciones + normalización).
        Tiene precedencia sobre `weights`.

    Returns
    -------
    df_comp con columnas adicionales:
        composite_score  — puntaje total (mayor = mejor)
        rank             — posición ordinal (1 = mejor)
        score_<col>      — contribución parcial de cada métrica al score

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.rank_scenarios(tabla)

    >>> # Priorizar compacidad
    >>> sc = cd.ScoringConfig.from_weights({"pp_promedio": 0.7,
    ...                                     "max_dev_pob_pct": 0.3})
    >>> cd.rank_scenarios(tabla, scoring_config=sc)
    """
    if scoring_config is None:
        if weights is not None:
            scoring_config = ScoringConfig.from_weights(weights)
        else:
            scoring_config = ScoringConfig.default()

    df_out = df_comp.copy()
    score  = pd.Series(np.zeros(len(df_out)), index=df_out.index)

    for col, w in scoring_config.weights.items():
        if w == 0.0:
            continue
        median_col = f"{col}_median"
        if median_col not in df_out.columns:
            continue
        vals = pd.to_numeric(df_out[median_col], errors="coerce")
        if vals.isna().all():
            continue

        direction = scoring_config.directions.get(col, "min")

        if scoring_config.normalization == "minmax":
            vmin, vmax = vals.min(), vals.max()
            if abs(vmax - vmin) < 1e-12:
                norm = pd.Series(0.5, index=vals.index)
            else:
                norm = (vals - vmin) / (vmax - vmin)

        elif scoring_config.normalization == "zscore":
            std = vals.std()
            if std < 1e-12:
                norm = pd.Series(0.5, index=vals.index)
            else:
                z = (vals - vals.mean()) / std
                zmin, zmax = z.min(), z.max()
                norm = (z - zmin) / (zmax - zmin + 1e-12)

        elif scoring_config.normalization == "rank":
            norm = vals.rank(pct=True, na_option="keep")

        partial = norm if direction == "max" else (1.0 - norm)
        partial = partial.fillna(0.0)
        score += w * partial
        df_out[f"score_{col}"] = (w * partial).round(4)

    df_out["composite_score"] = score.round(4)
    df_out["rank"] = df_out["composite_score"].rank(ascending=False).astype(int)
    return df_out.sort_values("rank").reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Frontera de Pareto N-dimensional
# ──────────────────────────────────────────────────────────────────────────────

def pareto_frontier_nd(
    points: Union[np.ndarray, pd.DataFrame],
    minimize: Optional[Union[np.ndarray, List[bool], Dict[str, bool]]] = None,
) -> np.ndarray:
    """
    Índices de los puntos no-dominados en un espacio N-dimensional.

    Un punto i es dominado por j si j es igual-o-mejor en TODOS los objetivos
    y estrictamente mejor en AL MENOS UNO.

    Parameters
    ----------
    points : array-like shape (n_points, n_objectives) o DataFrame
        Matriz de valores; una fila por punto, una columna por objetivo.
    minimize : array-like de bool, dict {col: bool} o None
        True = minimizar ese objetivo, False = maximizar.
        None → minimizar todos.
        Si points es DataFrame y minimize es dict, usa nombres de columna.

    Returns
    -------
    np.ndarray de índices (int) de los puntos no-dominados.

    Examples
    --------
    >>> pts = np.array([[0.1, 5], [0.2, 3], [0.3, 2], [0.1, 6]])
    >>> pareto_frontier_nd(pts, minimize=[True, True])
    array([0, 1, 2])   # [0.3, 2] domina a [0.1, 6] en y pero no en x
    """
    if isinstance(points, pd.DataFrame):
        cols = points.columns.tolist()
        if isinstance(minimize, dict):
            minimize = np.array([minimize.get(c, True) for c in cols])
        pts = points.values.astype(float)
    else:
        pts = np.asarray(points, dtype=float)

    n, m = pts.shape

    if minimize is None:
        minimize = np.ones(m, dtype=bool)
    else:
        minimize = np.asarray(minimize, dtype=bool)

    # Convertir todo a minimización: voltear los ejes de maximización
    work = pts.copy()
    work[:, ~minimize] *= -1

    is_pareto = np.ones(n, dtype=bool)
    for i in range(n):
        if not is_pareto[i]:
            continue
        # j domina a i si j <= i en todo y j < i en algo
        better_or_equal = np.all(work <= work[i], axis=1)   # (n,)
        strictly_better = np.any(work  < work[i], axis=1)   # (n,)
        dominated_by    = better_or_equal & strictly_better
        dominated_by[i] = False
        if dominated_by.any():
            is_pareto[i] = False

    return np.where(is_pareto)[0]


# Alias interno para compatibilidad con plot_tradeoff_frontier
def _pareto_frontier(
    x: np.ndarray,
    y: np.ndarray,
    minimize_x: bool = True,
    minimize_y: bool = True,
) -> np.ndarray:
    pts = np.column_stack([x, y])
    return pareto_frontier_nd(pts, minimize=[minimize_x, minimize_y])


# ──────────────────────────────────────────────────────────────────────────────
# pareto_optimal_scenarios
# ──────────────────────────────────────────────────────────────────────────────

def pareto_optimal_scenarios(
    df_comp: pd.DataFrame,
    metric_cols: Optional[List[str]] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> pd.DataFrame:
    """
    Devuelve las filas de df_comp (salida de compare_ensembles) que son
    Pareto-óptimas entre los escenarios comparados.

    Un escenario es Pareto-óptimo si no existe otro que sea igual-o-mejor
    en todas las métricas y estrictamente mejor en al menos una.

    Parameters
    ----------
    df_comp : DataFrame
        Tabla de compare_ensembles() con columnas <col>_median.
    metric_cols : list[str], opcional
        Métricas base a considerar (sin sufijo _median).
        None → usa todas las de METRICAS_STD que estén disponibles.
    scoring_config : ScoringConfig, opcional
        Si se provee, sus `directions` sobreescriben las de METRICAS_STD.

    Returns
    -------
    DataFrame con las filas Pareto-óptimas (puede ser un subconjunto o todo).

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.pareto_optimal_scenarios(tabla)
    """
    if metric_cols is None:
        metric_cols = [col for col, _, _ in METRICAS_STD]

    directions = {col: d for col, _, d in METRICAS_STD}
    if scoring_config is not None:
        directions.update(scoring_config.directions)

    avail   = [c for c in metric_cols if f"{c}_median" in df_comp.columns]
    med_cols = [f"{c}_median" for c in avail]

    if not avail:
        return df_comp.copy()

    pts = df_comp[med_cols].values.astype(float)
    minimize = np.array([directions.get(c, "min") == "min" for c in avail])

    idx = pareto_frontier_nd(pts, minimize=minimize)
    return df_comp.iloc[idx].copy().reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# plot_tradeoff_frontier
# ──────────────────────────────────────────────────────────────────────────────

def plot_tradeoff_frontier(
    ensembles: Dict[str, pd.DataFrame],
    x_col: str = "n_comunas_partidas",
    y_col: str = "max_dev_pob_pct",
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    title: Optional[str] = None,
    show_pareto: bool = True,
    minimize_x: bool = True,
    minimize_y: bool = True,
    colores: Optional[Dict[str, str]] = None,
    nombres: Optional[Dict[str, str]] = None,
    ax: Optional[plt.Axes] = None,
    figsize: Tuple[int, int] = (10, 6),
    alpha_scatter: float = 0.35,
    point_size: int = 8,
) -> plt.Figure:
    """
    Scatter de tradeoff entre dos métricas con frontera de Pareto opcional.

    Cada escenario aparece en su color; las medianas se marcan con diamantes.
    Los puntos no-dominados se conectan con una línea discontinua.

    Parameters
    ----------
    ensembles : dict {scenario_name: DataFrame}
    x_col, y_col : str
        Columnas del ensemble a cruzar (ej. "n_comunas_partidas", "pp_promedio").
    show_pareto : bool
        Si True, dibuja la frontera de Pareto dentro de cada escenario.
    minimize_x, minimize_y : bool
        Dirección óptima para cada eje (True = menor es mejor).
    ax : Axes, opcional
        Si se provee, dibuja en ese eje; si no, crea figura nueva.

    Returns
    -------
    matplotlib.figure.Figure
    """
    colores = colores or COLORES_DEFAULT
    nombres = nombres or NOMBRES_CORTOS

    col_to_label = {col: lbl for col, lbl, _ in METRICAS_STD}
    x_label = x_label or col_to_label.get(x_col, x_col)
    y_label = y_label or col_to_label.get(y_col, y_col)

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
        fig.patch.set_facecolor(_BG)
    else:
        fig = ax.figure
    ax.set_facecolor(_BG)

    for sc_name, df in ensembles.items():
        if x_col not in df.columns or y_col not in df.columns:
            continue
        mask = df[x_col].notna() & df[y_col].notna()
        if mask.sum() < 2:
            continue
        x = df.loc[mask, x_col].values.astype(float)
        y = df.loc[mask, y_col].values.astype(float)
        color = colores.get(sc_name, "#888880")
        label = nombres.get(sc_name, sc_name)

        ax.scatter(x, y, alpha=alpha_scatter, s=point_size,
                   color=color, label=label, zorder=2)

        xm, ym = float(np.median(x)), float(np.median(y))
        ax.scatter([xm], [ym], s=160, marker="D",
                   color=color, zorder=5, edgecolors="white", linewidths=1.2)
        ax.annotate(
            f"{label}\n({xm:.1f}, {ym:.2f})",
            xy=(xm, ym), xytext=(8, 4), textcoords="offset points",
            fontsize=7, color=color, zorder=6,
        )

        if show_pareto and len(x) >= 3:
            idx_p = _pareto_frontier(x, y, minimize_x, minimize_y)
            if len(idx_p) >= 2:
                px, py = x[idx_p], y[idx_p]
                order  = np.argsort(px)
                ax.plot(px[order], py[order], color=color,
                        linewidth=1.5, linestyle="--", alpha=0.7, zorder=3)

    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel(y_label, fontsize=11)
    ax.set_title(title or f"Tradeoff: {x_label} vs {y_label}",
                 fontsize=12, fontweight="bold")
    ax.legend(fontsize=10, framealpha=0.8)
    ax.spines[["top", "right"]].set_visible(False)
    plt.tight_layout()
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# plot_boxplots_comparativos
# ──────────────────────────────────────────────────────────────────────────────

def plot_boxplots_comparativos(
    ensembles: Dict[str, pd.DataFrame],
    metric_cols: Optional[List[str]] = None,
    metric_labels: Optional[Dict[str, str]] = None,
    colores: Optional[Dict[str, str]] = None,
    nombres: Optional[Dict[str, str]] = None,
    title: Optional[str] = None,
    figsize: Tuple[int, int] = (16, 5),
) -> plt.Figure:
    """
    Boxplots comparativos de varias métricas entre escenarios.

    Parameters
    ----------
    metric_cols : list[str], opcional
        Columnas a graficar. Por defecto: max_dev_pob_pct, pp_promedio, cut_edges.

    Returns
    -------
    matplotlib.figure.Figure
    """
    colores = colores or COLORES_DEFAULT
    nombres = nombres or NOMBRES_CORTOS

    if metric_cols is None:
        metric_cols = ["max_dev_pob_pct", "pp_promedio", "cut_edges"]

    col_to_label = {col: lbl for col, lbl, _ in METRICAS_STD}
    if metric_labels is None:
        metric_labels = {c: col_to_label.get(c, c) for c in metric_cols}

    n_metrics = len(metric_cols)
    fig, axes = plt.subplots(1, n_metrics, figsize=figsize)
    if n_metrics == 1:
        axes = [axes]
    fig.patch.set_facecolor(_BG)

    for ax, col in zip(axes, metric_cols):
        ax.set_facecolor(_BG)
        ax.spines[["top", "right"]].set_visible(False)
        data_list, label_list, color_list = [], [], []

        for sc_name, df in ensembles.items():
            if col not in df.columns:
                continue
            vals = df[col].dropna()
            if vals.empty:
                continue
            data_list.append(vals.tolist())
            label_list.append(nombres.get(sc_name, sc_name))
            color_list.append(colores.get(sc_name, "#888880"))

        if not data_list:
            ax.axis("off")
            continue

        bp = ax.boxplot(
            data_list, patch_artist=True,
            medianprops={"color": "black", "linewidth": 1.5},
            whiskerprops={"linewidth": 0.8},
            flierprops={"markersize": 3, "alpha": 0.5},
        )
        for patch, color in zip(bp["boxes"], color_list):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)

        ax.set_xticks(range(1, len(label_list) + 1))
        ax.set_xticklabels(label_list, fontsize=9, rotation=10, ha="right")
        ax.set_ylabel(metric_labels.get(col, col), fontsize=10)
        ax.set_title(metric_labels.get(col, col), fontsize=10, fontweight="bold")

    if title:
        fig.suptitle(title, fontsize=12, fontweight="bold")
    plt.tight_layout()
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# plot_radar_comparativo
# ──────────────────────────────────────────────────────────────────────────────

def plot_radar_comparativo(
    df_comp: pd.DataFrame,
    scenario_col: str = "escenario",
    metric_cols: Optional[List[str]] = None,
    scoring_config: Optional[ScoringConfig] = None,
    colores: Optional[Dict[str, str]] = None,
    nombres: Optional[Dict[str, str]] = None,
    title: Optional[str] = None,
    figsize: Tuple[int, int] = (7, 7),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Gráfico de araña (radar) comparando escenarios en múltiples métricas.

    Cada eje representa una métrica normalizada a [0, 1] donde 1 = mejor
    rendimiento (mín transformado a máx para métricas donde menor es mejor).

    Parameters
    ----------
    df_comp : DataFrame
        Salida de compare_ensembles() o rank_scenarios(); debe tener
        columnas <col>_median y columna de escenario.
    scenario_col : str
        Columna con el nombre de cada escenario.
    metric_cols : list[str], opcional
        Columnas base a incluir en el radar.
        None → usa todas las de METRICAS_STD disponibles.
    scoring_config : ScoringConfig, opcional
        Si se provee, usa sus `directions` para la transformación de ejes.
    colores, nombres : dict, opcional
        Override de colores y etiquetas de escenario.
    save_path : str, opcional
        Ruta para guardar la figura.

    Returns
    -------
    matplotlib.figure.Figure

    Examples
    --------
    >>> tabla = cd.compare_ensembles(ensembles)
    >>> cd.plot_radar_comparativo(tabla, save_path="radar.png")
    """
    colores = colores or COLORES_DEFAULT
    nombres = nombres or NOMBRES_CORTOS

    if metric_cols is None:
        metric_cols = [col for col, _, _ in METRICAS_STD]

    directions = {col: d for col, _, d in METRICAS_STD}
    if scoring_config is not None:
        directions.update(scoring_config.directions)

    col_to_label = {col: lbl for col, lbl, _ in METRICAS_STD}

    # Filtrar métricas disponibles
    avail = [c for c in metric_cols if f"{c}_median" in df_comp.columns]
    if not avail:
        raise ValueError("Ninguna de las métricas está en df_comp.")

    labels    = [col_to_label.get(c, c) for c in avail]
    n_metrics = len(avail)

    # Normalizar cada métrica a [0, 1] con 1 = mejor
    norm_matrix = {}
    for col in avail:
        med_col = f"{col}_median"
        vals = pd.to_numeric(df_comp[med_col], errors="coerce")
        vmin, vmax = vals.min(), vals.max()
        if abs(vmax - vmin) < 1e-12:
            norm = pd.Series(0.5, index=vals.index)
        else:
            norm = (vals - vmin) / (vmax - vmin)
        if directions.get(col, "min") == "min":
            norm = 1.0 - norm          # invertir: menor original = mayor en radar
        norm_matrix[col] = norm.values

    # Ángulos del radar (cerrar el polígono repitiendo el primero)
    angles  = np.linspace(0, 2 * np.pi, n_metrics, endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=figsize,
                           subplot_kw={"projection": "polar"})
    fig.patch.set_facecolor(_BG)
    ax.set_facecolor(_BG)

    # Cuadrícula y ejes
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_yticks([0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0.25", "0.50", "0.75", "1.00"], fontsize=7, alpha=0.6)
    ax.spines["polar"].set_visible(False)
    ax.grid(color="gray", linestyle="--", linewidth=0.5, alpha=0.4)

    for idx, row in df_comp.iterrows():
        sc_name = row[scenario_col]
        values  = [norm_matrix[c][idx] for c in avail]
        values += values[:1]           # cerrar polígono

        color = colores.get(sc_name, "#888880")
        label = nombres.get(sc_name, sc_name)

        ax.plot(angles, values, color=color, linewidth=2.0, label=label)
        ax.fill(angles, values, color=color, alpha=0.12)

        # Marcar el mejor eje de cada escenario
        best_idx = int(np.argmax(values[:-1]))
        ax.scatter([angles[best_idx]], [values[best_idx]],
                   s=60, color=color, zorder=5, edgecolors="white", linewidths=0.8)

    ax.legend(
        loc="upper right",
        bbox_to_anchor=(1.35, 1.15),
        fontsize=9, framealpha=0.8,
    )
    ax.set_title(
        title or "Comparación de escenarios — métricas normalizadas",
        fontsize=11, fontweight="bold", pad=20,
    )

    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# split_frequency_table
# ──────────────────────────────────────────────────────────────────────────────

def split_frequency_table(
    results_dir: str,
    scenario_names: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Tabla de frecuencia de comunas partidas consolidada por escenario.

    Lee comunas_partidas.csv (mejor plan) de cada subdirectorio de escenario.
    Devuelve una fila por CUT con cuántos escenarios la parten y cuáles.

    Parameters
    ----------
    results_dir : str
        Directorio con subcarpetas por escenario
        (ej. datos/<REGION>/redistritaje/).
    scenario_names : list[str], opcional
        Si None, lee todos los subdirectorios existentes.

    Returns
    -------
    DataFrame: CUT, nombre, n_escenarios_partida, escenarios_donde_parte,
               pop_total, split_severity_max.
    """
    base = Path(results_dir)
    if scenario_names is None:
        scenario_names = [d.name for d in base.iterdir() if d.is_dir()]

    frames: List[pd.DataFrame] = []
    for sc_name in scenario_names:
        csv_path = base / sc_name / "comunas_partidas.csv"
        if csv_path.exists():
            try:
                df_sc = pd.read_csv(csv_path)
                df_sc["escenario"] = sc_name
                frames.append(df_sc)
            except Exception:
                pass

    if not frames:
        return pd.DataFrame()

    df_all = pd.concat(frames, ignore_index=True)

    cut_col = "CUT"      if "CUT"      in df_all.columns else df_all.columns[0]
    nom_col = "nombre"   if "nombre"   in df_all.columns else None
    pop_col = "pop_total" if "pop_total" in df_all.columns else None
    sev_col = "split_severity" if "split_severity" in df_all.columns else None

    agg: Dict = {"escenario": list}
    if pop_col:
        agg[pop_col] = "max"
    if sev_col:
        agg[sev_col] = "max"
    if nom_col:
        agg[nom_col] = "first"

    grp = df_all.groupby(cut_col).agg(agg).reset_index()
    grp["n_escenarios_partida"]  = grp["escenario"].apply(len)
    grp["escenarios_donde_parte"] = grp["escenario"].apply(
        lambda x: "; ".join(sorted(set(x)))
    )
    grp = grp.drop(columns=["escenario"])
    if sev_col:
        grp = grp.rename(columns={sev_col: "split_severity_max"})
    grp = grp.sort_values("n_escenarios_partida", ascending=False)

    return grp.reset_index(drop=True)

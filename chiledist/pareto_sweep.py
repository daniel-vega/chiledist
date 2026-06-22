"""
pareto_sweep.py
===============
Análisis continuo de la frontera Pareto en el espacio de tradeoffs de redistritaje.

Flujo:
    Ensembles por nivel de penalización → Pool consolidado → Frontera Pareto real →
    Bandas bootstrap → Detección de knee point → Figuras publicables

Diferencia con scripts/pareto_sweep.py
---------------------------------------
Este módulo opera sobre **planes individuales** (no medianas por escenario):
cada plan del ensemble es un punto en el espacio de objetivos. La frontera
Pareto resultante es la verdadera envolvente eficiente del espacio de búsqueda.

Nota metodológica
-----------------
En el barrido de apc_soft, el parámetro ``split_penalty`` NO modifica la
distribución muestreada por la cadena ReCom — solo afecta el puntaje con
que se selecciona el plan de referencia.  Por eso el pool de planes de todos
los niveles de penalización es estadísticamente equivalente: la frontera
Pareto del pool consolida es la verdadera envolvente eficiente alcanzable.

Uso rápido
----------
    import chiledist as cd
    import numpy as np, pandas as pd

    penalties = np.linspace(0, 1, 11)
    ensembles = {
        p: pd.read_csv(f"datos/R13_METROPOLITANA/redistritaje/apc_soft_p{p:.2f}/ensemble_stats.csv")
        for p in penalties
    }

    sweep_df       = cd.sweep_split_penalty(ensembles)
    frontier_res   = cd.build_tradeoff_frontier(sweep_df)
    knee           = cd.detect_knee_point(frontier_res["frontier"])
    fig            = cd.plot_tradeoff_curve(sweep_df, frontier_res, knee)
    summary        = cd.summarize_tradeoff(sweep_df, frontier_res, knee)
"""

from __future__ import annotations

from typing import Optional, Union

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as mcm
import matplotlib.colors as mcolors
import matplotlib.patches as mpatches

from .scenario_comparison import pareto_frontier_nd

_BG           = "#F8F7F4"
_COLOR_MAIN   = "#1D9E75"
_COLOR_PARETO = "#1A5C8A"
_COLOR_KNEE   = "#D85A30"

# Métricas estándar del barrido
SWEEP_METRICS: list[str] = [
    "max_dev_pob_pct",
    "n_comunas_partidas",
    "split_severity",
    "pp_promedio",
    "pop_afectada_pct",
    "cut_edges",
]

# Dirección óptima para cada métrica (True = minimizar)
METRIC_DIRECTIONS: dict[str, bool] = {
    "max_dev_pob_pct":    True,
    "n_comunas_partidas": True,
    "split_severity":     True,
    "pp_promedio":        False,   # maximizar compacidad
    "pop_afectada_pct":   True,
    "cut_edges":          True,
}

# Etiquetas humanas
METRIC_LABELS: dict[str, str] = {
    "max_dev_pob_pct":    "Desviación pob. máx (%)",
    "n_comunas_partidas": "Comunas partidas",
    "split_severity":     "Severidad de cortes",
    "pp_promedio":        "Compacidad Polsby-Popper",
    "pop_afectada_pct":   "Pob. afectada (%)",
    "cut_edges":          "Aristas cortadas",
}


# ──────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ──────────────────────────────────────────────────────────────────────────────

def _styled_ax(ax: plt.Axes) -> None:
    ax.set_facecolor(_BG)
    ax.spines[["top", "right"]].set_visible(False)


def _infer_direction(metric: str, default: bool = True) -> bool:
    return METRIC_DIRECTIONS.get(metric, default)


def _per_penalty_stats(
    sweep_df: pd.DataFrame,
    metrics: list[str],
) -> pd.DataFrame:
    """Media, std, percentiles por nivel de penalización."""
    agg: dict[str, object] = {}
    for m in metrics:
        if m in sweep_df.columns:
            agg[m] = ["count", "mean", "std",
                      ("p5",  lambda x: np.percentile(x.dropna(), 5)  if len(x.dropna()) else np.nan),
                      ("p25", lambda x: np.percentile(x.dropna(), 25) if len(x.dropna()) else np.nan),
                      ("p75", lambda x: np.percentile(x.dropna(), 75) if len(x.dropna()) else np.nan),
                      ("p95", lambda x: np.percentile(x.dropna(), 95) if len(x.dropna()) else np.nan)]

    if not agg or "penalty" not in sweep_df.columns:
        return pd.DataFrame()

    stats = sweep_df.groupby("penalty")[list(agg.keys())].agg(
        ["count", "mean", "std",
         ("p5",  lambda x: float(np.percentile(x.dropna(), 5))  if len(x.dropna()) else np.nan),
         ("p25", lambda x: float(np.percentile(x.dropna(), 25)) if len(x.dropna()) else np.nan),
         ("p75", lambda x: float(np.percentile(x.dropna(), 75)) if len(x.dropna()) else np.nan),
         ("p95", lambda x: float(np.percentile(x.dropna(), 95)) if len(x.dropna()) else np.nan)]
    )
    stats.columns = ["_".join(c).strip() for c in stats.columns]
    return stats.reset_index()


def _bootstrap_bands(
    sweep_df: pd.DataFrame,
    x_metric: str,
    y_metric: str,
    minimize_x: bool,
    minimize_y: bool,
    n_bootstrap: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Bandas de incertidumbre del bootstrap sobre la frontera Pareto.

    Remuestrea planes por nivel de penalización (bootstrap estratificado),
    recalcula la frontera Pareto e interpola sobre una grilla fija en x.
    Devuelve percentiles de y en cada punto de la grilla.
    """
    valid = sweep_df[[x_metric, y_metric]].dropna()
    if len(valid) < 4:
        return pd.DataFrame()

    pts = valid[[x_metric, y_metric]].values.astype(float)
    pidx = pareto_frontier_nd(pts, minimize=[minimize_x, minimize_y])
    frontier = pts[pidx]
    frontier = frontier[frontier[:, 0].argsort()]
    if len(frontier) < 2:
        return pd.DataFrame()

    x_min, x_max = frontier[:, 0].min(), frontier[:, 0].max()
    if x_min >= x_max:
        return pd.DataFrame()
    x_grid = np.linspace(x_min, x_max, 60)

    has_penalty = "penalty" in sweep_df.columns

    y_samples: list[np.ndarray] = []
    for _ in range(n_bootstrap):
        if has_penalty:
            groups = [
                grp.sample(len(grp), replace=True,
                           random_state=int(rng.integers(0, 1_000_000)))
                for _, grp in sweep_df.groupby("penalty")
                if len(grp) >= 2
            ]
            if not groups:
                continue
            sample = pd.concat(groups, ignore_index=True)
        else:
            sample = sweep_df.sample(len(sweep_df), replace=True,
                                     random_state=int(rng.integers(0, 1_000_000)))

        s_valid = sample[[x_metric, y_metric]].dropna()
        if len(s_valid) < 4:
            continue
        s_pts = s_valid[[x_metric, y_metric]].values.astype(float)
        try:
            b_idx = pareto_frontier_nd(s_pts, minimize=[minimize_x, minimize_y])
        except Exception:
            continue

        b_front = s_pts[b_idx]
        b_front = b_front[b_front[:, 0].argsort()]
        if len(b_front) < 2:
            continue

        y_interp = np.interp(
            x_grid,
            b_front[:, 0], b_front[:, 1],
            left=b_front[0, 1], right=b_front[-1, 1],
        )
        y_samples.append(y_interp)

    if len(y_samples) < 10:
        return pd.DataFrame()

    y_arr = np.array(y_samples)
    return pd.DataFrame({
        "x_grid":  x_grid,
        "y_p5":    np.percentile(y_arr, 5,  axis=0),
        "y_p25":   np.percentile(y_arr, 25, axis=0),
        "y_p50":   np.percentile(y_arr, 50, axis=0),
        "y_p75":   np.percentile(y_arr, 75, axis=0),
        "y_p95":   np.percentile(y_arr, 95, axis=0),
    })


# ──────────────────────────────────────────────────────────────────────────────
# sweep_split_penalty
# ──────────────────────────────────────────────────────────────────────────────

def sweep_split_penalty(
    ensembles_by_penalty: dict[float, pd.DataFrame],
    metrics: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Consolida ensembles por nivel de penalización en un único DataFrame.

    Cada plan del ensemble queda como una fila etiquetada con su nivel de
    ``split_penalty``.  El resultado es el pool de planes individuales sobre
    el que se construye la frontera Pareto real.

    Parameters
    ----------
    ensembles_by_penalty : dict {float: pd.DataFrame}
        Cada valor es un ``ensemble_stats.csv`` (una fila por plan).
        La clave es el valor de ``split_penalty`` usado para ese ensemble.
    metrics : list[str], optional
        Columnas de métricas a conservar.  Default: :data:`SWEEP_METRICS`.

    Returns
    -------
    pd.DataFrame
        Columna ``penalty`` + métricas disponibles.  Una fila por plan de
        todos los niveles de penalización concatenados.

    Examples
    --------
    >>> penalties = [0.0, 0.25, 0.5, 1.0]
    >>> dfs = {p: pd.read_csv(f"ensemble_p{p}.csv") for p in penalties}
    >>> pool = sweep_split_penalty(dfs)
    >>> pool["penalty"].unique()
    array([0.  , 0.25, 0.5 , 1.  ])
    """
    if metrics is None:
        metrics = SWEEP_METRICS

    if not ensembles_by_penalty:
        return pd.DataFrame(columns=["penalty"] + metrics)

    frames: list[pd.DataFrame] = []
    for penalty, df in ensembles_by_penalty.items():
        df_c = df.copy()
        df_c["penalty"] = float(penalty)
        keep = ["penalty"] + [c for c in metrics if c in df_c.columns]
        frames.append(df_c[keep])

    return pd.concat(frames, ignore_index=True)


# ──────────────────────────────────────────────────────────────────────────────
# build_tradeoff_frontier
# ──────────────────────────────────────────────────────────────────────────────

def build_tradeoff_frontier(
    sweep_df: pd.DataFrame,
    x_metric: str = "max_dev_pob_pct",
    y_metric: str = "n_comunas_partidas",
    minimize_x: Optional[bool] = None,
    minimize_y: Optional[bool] = None,
    n_bootstrap: int = 200,
    random_state: int = 42,
) -> dict:
    """
    Construye la frontera Pareto real a partir de planes individuales.

    A diferencia del análisis por escenarios (que usa medianas), este método
    trata cada plan como un punto independiente en el espacio de objetivos.
    La frontera resultante es la verdadera envolvente eficiente.

    Parameters
    ----------
    sweep_df : pd.DataFrame
        Salida de :func:`sweep_split_penalty`.
    x_metric, y_metric : str
        Objetivos para el espacio bidimensional.
    minimize_x, minimize_y : bool, optional
        Dirección de optimización.  ``None`` → inferida de
        :data:`METRIC_DIRECTIONS`.
    n_bootstrap : int
        Remuestreos para bandas de incertidumbre.  0 = desactivar.
    random_state : int
        Semilla reproducible.

    Returns
    -------
    dict con claves:

    ``frontier``
        DataFrame de planes Pareto-óptimos (filas de ``sweep_df``).
    ``all_plans``
        ``sweep_df`` con columna ``is_pareto`` añadida.
    ``per_penalty_stats``
        DataFrame — media/std/percentiles por nivel de penalización.
    ``bootstrap_bands``
        DataFrame — bandas de incertidumbre sobre la frontera Pareto.
        Vacío si ``n_bootstrap == 0`` o hay pocos datos.
    ``metadata``
        dict — ``{x_metric, y_metric, n_plans, n_pareto, minimize_x,
        minimize_y}``.
    """
    if minimize_x is None:
        minimize_x = _infer_direction(x_metric)
    if minimize_y is None:
        minimize_y = _infer_direction(y_metric)

    plans = sweep_df.copy()
    plans["is_pareto"] = False

    valid_mask = plans[x_metric].notna() & plans[y_metric].notna()
    valid_idx  = plans.index[valid_mask]
    pts = plans.loc[valid_mask, [x_metric, y_metric]].values.astype(float)

    if len(pts) >= 2:
        pareto_local = pareto_frontier_nd(pts, minimize=[minimize_x, minimize_y])
        plans.loc[valid_idx[pareto_local], "is_pareto"] = True

    frontier = plans[plans["is_pareto"]].copy()

    avail_metrics = [c for c in SWEEP_METRICS if c in sweep_df.columns]
    per_stats = _per_penalty_stats(sweep_df, avail_metrics) if "penalty" in sweep_df.columns else pd.DataFrame()

    rng = np.random.default_rng(random_state)
    boot_bands = pd.DataFrame()
    if n_bootstrap > 0:
        boot_bands = _bootstrap_bands(
            sweep_df, x_metric, y_metric,
            minimize_x, minimize_y, n_bootstrap, rng,
        )

    return {
        "frontier":          frontier,
        "all_plans":         plans,
        "per_penalty_stats": per_stats,
        "bootstrap_bands":   boot_bands,
        "metadata": {
            "x_metric":   x_metric,
            "y_metric":   y_metric,
            "minimize_x": minimize_x,
            "minimize_y": minimize_y,
            "n_plans":    int(valid_mask.sum()),
            "n_pareto":   int(plans["is_pareto"].sum()),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# detect_knee_point
# ──────────────────────────────────────────────────────────────────────────────

def detect_knee_point(
    frontier_df: pd.DataFrame,
    x_metric: str = "max_dev_pob_pct",
    y_metric: str = "n_comunas_partidas",
    method: str = "normalized_distance",
    diminishing_threshold: float = 0.5,
) -> dict:
    """
    Detecta el knee point y regiones de rendimientos decrecientes.

    El **knee point** es el punto de la frontera Pareto con máxima distancia
    perpendicular a la línea que une los extremos.  Representa el punto de
    máxima eficiencia: el tradeoff donde ambos objetivos están simultáneamente
    más cerca de su óptimo.

    Parameters
    ----------
    frontier_df : pd.DataFrame
        Subconjunto de planes Pareto-óptimos (clave ``'frontier'`` de la
        salida de :func:`build_tradeoff_frontier`).
    x_metric, y_metric : str
        Columnas a usar.
    method : {'normalized_distance', 'raw_distance'}
        ``'normalized_distance'``: calcula distancias en el espacio
        normalizado [0,1]×[0,1] — recomendado cuando las unidades de los
        dos ejes son diferentes.
        ``'raw_distance'``: distancias en el espacio original.
    diminishing_threshold : float
        Fracción de la tasa de retorno media por debajo de la cual se
        considera que comienzan los rendimientos decrecientes.
        Default 0.5 → detecta cuando la mejora marginal cae al 50%.

    Returns
    -------
    dict con claves:

    ``knee_idx``
        Posición (0-based) del knee dentro del DataFrame ordenado.
    ``knee_x``, ``knee_y``
        Coordenadas del knee en el espacio original.
    ``knee_penalty``
        Valor de ``split_penalty`` en el knee (``None`` si no disponible).
    ``distances``
        Array de distancias perpendiculares para cada punto de la frontera.
    ``diminishing_mask``
        Array booleano: ``True`` donde hay rendimientos decrecientes.
    ``diminishing_start_x``
        Valor de x donde comienzan los rendimientos decrecientes
        (``None`` si no detectado).
    ``method``
        Método usado.

    Examples
    --------
    >>> frontier = result["frontier"]
    >>> knee = detect_knee_point(frontier, method="normalized_distance")
    >>> print(f"Knee en penalty={knee['knee_penalty']:.2f}: "
    ...       f"({knee['knee_x']:.2f}, {knee['knee_y']:.1f})")
    """
    empty = {
        "knee_idx": None, "knee_x": None, "knee_y": None,
        "knee_penalty": None, "distances": np.array([]),
        "diminishing_mask": np.array([], dtype=bool),
        "diminishing_start_x": None, "method": method,
    }

    if frontier_df is None or len(frontier_df) == 0:
        return empty
    if x_metric not in frontier_df.columns or y_metric not in frontier_df.columns:
        return empty

    df = (
        frontier_df[[c for c in [x_metric, y_metric, "penalty"]
                     if c in frontier_df.columns]]
        .dropna(subset=[x_metric, y_metric])
        .sort_values(x_metric)
        .reset_index(drop=True)
    )

    if len(df) == 0:
        return empty

    x = df[x_metric].values.astype(float)
    y = df[y_metric].values.astype(float)

    if len(x) == 1:
        penalty = float(df["penalty"].iloc[0]) if "penalty" in df.columns else None
        return {**empty,
                "knee_idx": 0, "knee_x": float(x[0]), "knee_y": float(y[0]),
                "knee_penalty": penalty,
                "distances": np.array([0.0]),
                "diminishing_mask": np.array([False])}

    if method == "normalized_distance":
        x_range = x.max() - x.min()
        y_range = y.max() - y.min()
        xn = (x - x.min()) / x_range if x_range > 1e-12 else np.zeros_like(x)
        yn = (y - y.min()) / y_range if y_range > 1e-12 else np.zeros_like(y)
    else:
        xn, yn = x, y

    x0, y0 = xn[0],  yn[0]
    x1, y1 = xn[-1], yn[-1]
    line_len = np.hypot(x1 - x0, y1 - y0)

    if line_len < 1e-12:
        distances = np.zeros(len(x))
        knee_idx  = 0
    else:
        distances = np.abs(
            (y1 - y0) * xn - (x1 - x0) * yn + x1 * y0 - y1 * x0
        ) / line_len
        knee_idx = int(np.argmax(distances))

    # Rendimientos decrecientes: tasa de mejora en y por unidad de costo en x
    dx = np.diff(x)
    dy = np.diff(y)   # esperado: negativo si y disminuye con más x

    with np.errstate(divide="ignore", invalid="ignore"):
        return_rate = np.where(dx > 1e-12, -dy / dx, np.nan)

    pos_rates = return_rate[np.isfinite(return_rate) & (return_rate > 0)]
    if len(pos_rates) > 0:
        mean_rate = float(np.mean(pos_rates))
        seg_dim = (return_rate < diminishing_threshold * mean_rate)
        seg_dim = np.where(np.isfinite(return_rate), seg_dim, False)
        dim_mask = np.zeros(len(x), dtype=bool)
        for i, is_dim in enumerate(seg_dim):
            if is_dim:
                dim_mask[i + 1] = True
        # First point in diminishing region
        dim_starts = np.where(dim_mask)[0]
        dim_start_x = float(x[dim_starts[0]]) if len(dim_starts) > 0 else None
    else:
        dim_mask    = np.zeros(len(x), dtype=bool)
        dim_start_x = None

    knee_penalty = None
    if "penalty" in df.columns:
        knee_penalty = float(df["penalty"].iloc[knee_idx])

    return {
        "knee_idx":            knee_idx,
        "knee_x":              float(x[knee_idx]),
        "knee_y":              float(y[knee_idx]),
        "knee_penalty":        knee_penalty,
        "distances":           distances,
        "diminishing_mask":    dim_mask,
        "diminishing_start_x": dim_start_x,
        "method":              method,
    }


# ──────────────────────────────────────────────────────────────────────────────
# plot_tradeoff_curve
# ──────────────────────────────────────────────────────────────────────────────

def plot_tradeoff_curve(
    sweep_df: pd.DataFrame,
    frontier_result: dict,
    knee_result: Optional[dict] = None,
    x_metric: str = "max_dev_pob_pct",
    y_metric: str = "n_comunas_partidas",
    x_label: Optional[str] = None,
    y_label: Optional[str] = None,
    title: Optional[str] = None,
    show_scatter: bool = True,
    show_density_bands: bool = True,
    show_diminishing: bool = True,
    figsize: tuple = (10, 7),
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Figura publicable de la curva de tradeoff con frontera Pareto e incertidumbre.

    Capas del gráfico (de atrás a adelante):
    1. Región de rendimientos decrecientes (si ``show_diminishing=True``).
    2. Bandas bootstrap (IC 95% y 50%) de la frontera Pareto.
    3. Scatter de planes individuales, coloreado por ``split_penalty``.
    4. Línea de la frontera Pareto.
    5. Marker del knee point con anotación.

    Parameters
    ----------
    sweep_df : pd.DataFrame
        Salida de :func:`sweep_split_penalty`.
    frontier_result : dict
        Salida de :func:`build_tradeoff_frontier`.
    knee_result : dict, optional
        Salida de :func:`detect_knee_point`.
    x_metric, y_metric : str
        Columnas a graficar (deben estar en ``sweep_df``).
    x_label, y_label : str, optional
        Etiquetas de eje.  Default: etiqueta de :data:`METRIC_LABELS`.
    title : str, optional
        Título del gráfico.
    show_scatter : bool
        Si True, dibuja todos los planes individuales (semi-transparentes).
    show_density_bands : bool
        Si True, dibuja las bandas bootstrap de la frontera.
    show_diminishing : bool
        Si True, sombrea la región de rendimientos decrecientes.
    figsize : tuple
    save_path : str, optional

    Returns
    -------
    matplotlib.figure.Figure
    """
    fig, ax = plt.subplots(figsize=figsize)
    fig.patch.set_facecolor(_BG)
    _styled_ax(ax)

    frontier = frontier_result.get("frontier", pd.DataFrame())
    boot     = frontier_result.get("bootstrap_bands", pd.DataFrame())
    all_plans = frontier_result.get("all_plans", sweep_df)

    x_label = x_label or METRIC_LABELS.get(x_metric, x_metric)
    y_label = y_label or METRIC_LABELS.get(y_metric, y_metric)

    has_penalty = "penalty" in sweep_df.columns and sweep_df["penalty"].notna().any()

    # ── 1. Region de rendimientos decrecientes ────────────────────────────────
    if show_diminishing and knee_result and knee_result.get("diminishing_start_x") is not None:
        dim_x = knee_result["diminishing_start_x"]
        ax.axvspan(dim_x, sweep_df[x_metric].max() * 1.05,
                   color="#BA7517", alpha=0.08, zorder=1,
                   label="Rendimientos decrecientes")

    # ── 2. Bandas bootstrap ───────────────────────────────────────────────────
    if show_density_bands and not boot.empty and "x_grid" in boot.columns:
        ax.fill_between(
            boot["x_grid"], boot["y_p5"], boot["y_p95"],
            color=_COLOR_PARETO, alpha=0.12, zorder=2, label="IC 90% bootstrap"
        )
        ax.fill_between(
            boot["x_grid"], boot["y_p25"], boot["y_p75"],
            color=_COLOR_PARETO, alpha=0.22, zorder=2, label="IC 50% bootstrap"
        )

    # ── 3. Scatter individual ─────────────────────────────────────────────────
    if show_scatter and x_metric in all_plans.columns and y_metric in all_plans.columns:
        non_pareto = all_plans[~all_plans.get("is_pareto", pd.Series(False, index=all_plans.index))]
        valid_np   = non_pareto[[x_metric, y_metric]].dropna()

        if has_penalty and not valid_np.empty:
            p_vals = non_pareto.loc[valid_np.index, "penalty"].values
            norm   = mcolors.Normalize(vmin=sweep_df["penalty"].min(),
                                       vmax=sweep_df["penalty"].max())
            cmap   = plt.colormaps.get_cmap("viridis")
            sc = ax.scatter(
                valid_np[x_metric], valid_np[y_metric],
                c=p_vals, cmap=cmap, norm=norm,
                alpha=0.18, s=12, zorder=3, linewidths=0,
            )
            cbar = fig.colorbar(sc, ax=ax, pad=0.01, shrink=0.7)
            cbar.set_label("split_penalty", fontsize=9)
        else:
            ax.scatter(
                valid_np[x_metric], valid_np[y_metric],
                color="#888880", alpha=0.20, s=12, zorder=3, linewidths=0,
                label="Planes (no Pareto)",
            )

    # ── 4. Frontera Pareto ────────────────────────────────────────────────────
    if not frontier.empty and x_metric in frontier.columns and y_metric in frontier.columns:
        front_sorted = (
            frontier[[x_metric, y_metric]]
            .dropna()
            .sort_values(x_metric)
        )
        if len(front_sorted) >= 2:
            ax.step(
                front_sorted[x_metric], front_sorted[y_metric],
                where="post", color=_COLOR_PARETO, linewidth=2.2,
                zorder=5, label="Frontera Pareto",
            )
        ax.scatter(
            front_sorted[x_metric], front_sorted[y_metric],
            color=_COLOR_PARETO, s=40, zorder=6,
            edgecolors="white", linewidths=0.8,
        )

    # ── 5. Knee point ─────────────────────────────────────────────────────────
    if knee_result and knee_result.get("knee_x") is not None:
        kx, ky = knee_result["knee_x"], knee_result["knee_y"]
        kp     = knee_result.get("knee_penalty")
        klabel = f"Knee (p={kp:.2f})" if kp is not None else "Knee point"
        ax.scatter([kx], [ky], color=_COLOR_KNEE, s=180, zorder=8,
                   marker="*", edgecolors="white", linewidths=1.0, label=klabel)
        ax.annotate(
            klabel, (kx, ky),
            xytext=(10, 8), textcoords="offset points",
            fontsize=9, color=_COLOR_KNEE, fontweight="bold",
            arrowprops={"arrowstyle": "->", "color": _COLOR_KNEE, "lw": 1.2},
        )

    ax.set_xlabel(x_label, fontsize=11)
    ax.set_ylabel(y_label, fontsize=11)
    ax.set_title(
        title or f"Frontera Pareto: {x_label} × {y_label}\n(planes individuales — H8)",
        fontsize=11, fontweight="bold",
    )
    ax.legend(fontsize=8, framealpha=0.9, loc="upper right")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=_BG)
    return fig


# ──────────────────────────────────────────────────────────────────────────────
# summarize_tradeoff
# ──────────────────────────────────────────────────────────────────────────────

def summarize_tradeoff(
    sweep_df: pd.DataFrame,
    frontier_result: dict,
    knee_result: Optional[dict] = None,
    metrics: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Resumen estadístico del barrido paramétrico por nivel de penalización.

    Combina estadísticas del pool completo, marcadores de la frontera Pareto
    y la posición del knee point en un único DataFrame tabulado.

    Parameters
    ----------
    sweep_df : pd.DataFrame
        Salida de :func:`sweep_split_penalty`.
    frontier_result : dict
        Salida de :func:`build_tradeoff_frontier`.
    knee_result : dict, optional
        Salida de :func:`detect_knee_point`.
    metrics : list[str], optional
        Métricas a incluir.  Default: :data:`SWEEP_METRICS`.

    Returns
    -------
    pd.DataFrame
        Indexado por ``penalty``.  Columnas principales por métrica
        (``{metric}_mean``, ``{metric}_std``, ``{metric}_p5``,
        ``{metric}_p95``), más:

        ``n_planes``
            Total de planes en ese nivel de penalización.
        ``n_pareto``
            Planes Pareto-óptimos en ese nivel.
        ``pct_pareto``
            Porcentaje de planes Pareto-óptimos.
        ``is_knee``
            ``True`` en el nivel de penalización del knee point (si lo hay).
    """
    if metrics is None:
        metrics = [c for c in SWEEP_METRICS if c in sweep_df.columns]

    if "penalty" not in sweep_df.columns:
        return pd.DataFrame()

    all_plans = frontier_result.get("all_plans", sweep_df)

    # Estadísticas por penalización
    stat_fns = {
        "mean": "mean",
        "std":  "std",
        "p5":   lambda x: float(np.percentile(x.dropna(), 5))  if len(x.dropna()) else np.nan,
        "p25":  lambda x: float(np.percentile(x.dropna(), 25)) if len(x.dropna()) else np.nan,
        "p75":  lambda x: float(np.percentile(x.dropna(), 75)) if len(x.dropna()) else np.nan,
        "p95":  lambda x: float(np.percentile(x.dropna(), 95)) if len(x.dropna()) else np.nan,
    }

    rows: list[dict] = []
    for penalty, grp in sweep_df.groupby("penalty"):
        row: dict = {"penalty": float(penalty)}
        row["n_planes"] = len(grp)
        for m in metrics:
            if m not in grp.columns:
                continue
            vals = grp[m].dropna()
            row[f"{m}_mean"] = round(float(vals.mean()), 6)  if len(vals) else np.nan
            row[f"{m}_std"]  = round(float(vals.std()),  6)  if len(vals) > 1 else np.nan
            row[f"{m}_p5"]   = round(float(np.percentile(vals, 5)),  6) if len(vals) else np.nan
            row[f"{m}_p95"]  = round(float(np.percentile(vals, 95)), 6) if len(vals) else np.nan
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    summary = pd.DataFrame(rows).set_index("penalty")

    # Contar planes Pareto por penalización
    if "is_pareto" in all_plans.columns and "penalty" in all_plans.columns:
        pareto_counts = (
            all_plans.groupby("penalty")["is_pareto"]
            .agg(n_pareto=lambda s: int(s.sum()),
                 n_total=lambda s: len(s))
            .rename(columns={"n_total": "_drop"})
        )
        pareto_counts["pct_pareto"] = (
            pareto_counts["n_pareto"] / pareto_counts["_drop"] * 100
        ).round(1)
        pareto_counts = pareto_counts.drop(columns=["_drop"])
        summary = summary.join(pareto_counts, how="left")

    # Marcar el knee
    summary["is_knee"] = False
    if knee_result and knee_result.get("knee_penalty") is not None:
        kp = knee_result["knee_penalty"]
        if kp in summary.index:
            summary.loc[kp, "is_knee"] = True
        else:
            closest = summary.index[np.argmin(np.abs(summary.index - kp))]
            summary.loc[closest, "is_knee"] = True

    return summary

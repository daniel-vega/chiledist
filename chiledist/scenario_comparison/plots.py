"""
scenario_comparison.plots
============================
Visualización de tradeoffs entre escenarios: scatter con frontera de
Pareto, boxplots comparativos y radar de métricas normalizadas.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from .scoring import ScoringConfig, COLORES_DEFAULT, NOMBRES_CORTOS, METRICAS_STD
from .compare import pareto_frontier_nd

_BG = "#F8F7F4"


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

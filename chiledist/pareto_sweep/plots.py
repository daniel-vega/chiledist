"""
pareto_sweep.plots
====================
Figura publicable de la curva de tradeoff: frontera Pareto, bandas
bootstrap, scatter de planes individuales y knee point.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

from .._plot_style import BG, COLOR_PARETO, COLOR_KNEE, styled_ax
from .frontier import METRIC_LABELS


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
    fig.patch.set_facecolor(BG)
    styled_ax(ax)

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
            color=COLOR_PARETO, alpha=0.12, zorder=2, label="IC 90% bootstrap"
        )
        ax.fill_between(
            boot["x_grid"], boot["y_p25"], boot["y_p75"],
            color=COLOR_PARETO, alpha=0.22, zorder=2, label="IC 50% bootstrap"
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
                where="post", color=COLOR_PARETO, linewidth=2.2,
                zorder=5, label="Frontera Pareto",
            )
        ax.scatter(
            front_sorted[x_metric], front_sorted[y_metric],
            color=COLOR_PARETO, s=40, zorder=6,
            edgecolors="white", linewidths=0.8,
        )

    # ── 5. Knee point ─────────────────────────────────────────────────────────
    if knee_result and knee_result.get("knee_x") is not None:
        kx, ky = knee_result["knee_x"], knee_result["knee_y"]
        kp     = knee_result.get("knee_penalty")
        klabel = f"Knee (p={kp:.2f})" if kp is not None else "Knee point"
        ax.scatter([kx], [ky], color=COLOR_KNEE, s=180, zorder=8,
                   marker="*", edgecolors="white", linewidths=1.0, label=klabel)
        ax.annotate(
            klabel, (kx, ky),
            xytext=(10, 8), textcoords="offset points",
            fontsize=9, color=COLOR_KNEE, fontweight="bold",
            arrowprops={"arrowstyle": "->", "color": COLOR_KNEE, "lw": 1.2},
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
        fig.savefig(save_path, dpi=150, bbox_inches="tight", facecolor=BG)
    return fig

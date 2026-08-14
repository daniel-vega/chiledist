"""
electoral_ensemble.plots
==========================
Visualización de las distribuciones producidas por
:func:`chiledist.electoral_ensemble.run_electoral_ensemble`.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

from .._plot_style import BG, COLOR_MAIN, COLOR_OBS, styled_ax


def plot_ensemble_histogram(
    ensemble_results: pd.DataFrame,
    metric: str = "gallagher",
    observed: Optional[float] = None,
    bins: int = 30,
    title: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Histograma de la distribución de una métrica electoral sobre el ensemble.

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.
    metric : str
        Columna a graficar.
    observed : float, optional
        Valor del plan observado.  Se dibuja como línea vertical y se muestra
        su percentil dentro del ensemble.
    bins : int
        Número de intervalos del histograma.
    title : str, optional
        Título del gráfico.  Por defecto: ``f"Distribución ensemble: {metric}"``.
    ax : matplotlib.Axes, optional
        Eje existente donde dibujar.  Si ``None``, se crea una nueva figura.
    save_path : str, optional
        Ruta para guardar la figura (solo si ``ax=None``).

    Returns
    -------
    matplotlib.figure.Figure
    """
    if metric not in ensemble_results.columns:
        raise ValueError(f"Métrica '{metric}' no encontrada en ensemble_results.")

    fig_created = ax is None
    if fig_created:
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor(BG)
    else:
        fig = ax.get_figure()

    styled_ax(ax)
    vals = ensemble_results[metric].dropna()
    ax.hist(vals, bins=bins, color=COLOR_MAIN, alpha=0.72, edgecolor="white", linewidth=0.5)

    if observed is not None:
        pct = float(np.mean(vals.values <= observed)) * 100
        ax.axvline(
            observed, color=COLOR_OBS, linewidth=2, linestyle="--",
            label=f"Observado: {observed:.3f}  (pct. {pct:.1f}%)",
        )
        ax.legend(fontsize=9)

    ax.set_xlabel(metric, fontsize=10)
    ax.set_ylabel("Frecuencia", fontsize=10)
    ax.set_title(title or f"Distribución ensemble: {metric}", fontsize=11, fontweight="bold")

    if save_path and fig_created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_ensemble_violin(
    ensemble_results: pd.DataFrame,
    metrics: Optional[list[str]] = None,
    observed: Optional[dict[str, float]] = None,
    title: Optional[str] = None,
    figsize: Optional[tuple[int, int]] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    Violin plots para múltiples métricas electorales del ensemble.

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.
    metrics : list[str], optional
        Columnas a graficar.  Por defecto: gallagher, loosemore_hanby, rae,
        enp_votos, enp_escanos.
    observed : dict {metric: value}, optional
        Valores observados del plan actual; se dibujan como líneas horizontales.
    title : str, optional
        Título general de la figura.
    figsize : tuple, optional
        Tamaño de la figura.  Por defecto: (4 × n_metrics, 5).
    save_path : str, optional
        Ruta para guardar la figura.

    Returns
    -------
    matplotlib.figure.Figure
    """
    if metrics is None:
        metrics = [
            c for c in ["gallagher", "loosemore_hanby", "rae", "enp_votos", "enp_escanos"]
            if c in ensemble_results.columns
        ]
    if not metrics:
        raise ValueError("No hay métricas disponibles para graficar.")

    n       = len(metrics)
    figsize = figsize or (4 * n, 5)
    fig, axes = plt.subplots(1, n, figsize=figsize)
    if n == 1:
        axes = [axes]
    fig.patch.set_facecolor(BG)

    for ax, metric in zip(axes, metrics):
        styled_ax(ax)
        if metric not in ensemble_results.columns:
            ax.text(0.5, 0.5, f"'{metric}'\nno encontrada",
                    ha="center", va="center", transform=ax.transAxes, fontsize=9)
            ax.set_title(metric, fontsize=10, fontweight="bold")
            continue

        vals = ensemble_results[metric].dropna().tolist()
        if len(vals) < 3:
            ax.text(0.5, 0.5, "Sin datos\nsuficientes",
                    ha="center", va="center", transform=ax.transAxes, fontsize=9)
            ax.set_title(metric, fontsize=10, fontweight="bold")
            continue

        vp = ax.violinplot(vals, positions=[1], showmedians=True, showextrema=True)
        for body in vp["bodies"]:
            body.set_facecolor(COLOR_MAIN)
            body.set_alpha(0.72)
        vp["cmedians"].set_color("black")
        for part in ("cmins", "cmaxes", "cbars"):
            vp[part].set_color("#888880")
            vp[part].set_linewidth(1.0)

        if observed and metric in observed:
            obs_val = observed[metric]
            ax.axhline(obs_val, color=COLOR_OBS, linewidth=2, linestyle="--",
                       label=f"Obs: {obs_val:.3f}")
            ax.legend(fontsize=8)

        ax.set_xticks([1])
        ax.set_xticklabels([metric], fontsize=9)
        ax.set_title(metric, fontsize=10, fontweight="bold")

    if title:
        fig.suptitle(title, fontsize=12, fontweight="bold")
    plt.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig


def plot_ensemble_ecdf(
    ensemble_results: pd.DataFrame,
    metric: str = "gallagher",
    observed: Optional[float] = None,
    title: Optional[str] = None,
    ax: Optional[plt.Axes] = None,
    save_path: Optional[str] = None,
) -> plt.Figure:
    """
    ECDF (Función de Distribución Empírica Acumulada) de una métrica.

    Permite determinar visualmente qué proporción del ensemble tiene valores
    menores o mayores al del plan observado.

    Parameters
    ----------
    ensemble_results : pd.DataFrame
        Salida de :func:`run_electoral_ensemble`.
    metric : str
        Columna a graficar.
    observed : float, optional
        Valor del plan observado; se marca con líneas y se muestra el percentil.
    title : str, optional
        Título del gráfico.
    ax : matplotlib.Axes, optional
        Eje existente.  Si ``None``, se crea una nueva figura.
    save_path : str, optional
        Ruta para guardar la figura (solo si ``ax=None``).

    Returns
    -------
    matplotlib.figure.Figure
    """
    if metric not in ensemble_results.columns:
        raise ValueError(f"Métrica '{metric}' no encontrada en ensemble_results.")

    fig_created = ax is None
    if fig_created:
        fig, ax = plt.subplots(figsize=(8, 5))
        fig.patch.set_facecolor(BG)
    else:
        fig = ax.get_figure()

    styled_ax(ax)
    sorted_vals = np.sort(ensemble_results[metric].dropna().values)
    n = len(sorted_vals)
    ecdf_y = np.arange(1, n + 1) / n

    ax.step(sorted_vals, ecdf_y, where="post", color=COLOR_MAIN, linewidth=2)

    if observed is not None and n > 0:
        pct = float(np.mean(sorted_vals <= observed))
        ax.axvline(observed, color=COLOR_OBS, linewidth=2, linestyle="--",
                   label=f"Observado: {observed:.3f} (pct. {pct*100:.1f}%)")
        ax.axhline(pct, color=COLOR_OBS, linewidth=1, linestyle=":", alpha=0.5)
        ax.legend(fontsize=9)

    ax.set_xlabel(metric, fontsize=10)
    ax.set_ylabel("F(x)", fontsize=10)
    ax.set_ylim(-0.02, 1.05)
    ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=1, decimals=0))
    ax.set_title(title or f"ECDF ensemble: {metric}", fontsize=11, fontweight="bold")

    if save_path and fig_created:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
    return fig

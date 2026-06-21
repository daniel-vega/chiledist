"""
chiledist.samplers.diagnostics
==============================
Diagnósticos de convergencia para cadenas de Markov ReCom.

Las cadenas ReCom no producen muestras i.i.d. — para evaluar si el ensemble
es representativo del espacio de planes se necesita:

  1. Múltiples cadenas independientes (distintas semillas)
  2. Gelman-Rubin (R-hat): convergencia entre cadenas. R-hat < 1.1 = aceptable
  3. Tamaño efectivo de muestra (ESS): equivalente en muestras independientes
  4. ACF: velocidad de decorrelación de la cadena

Para SMC (muestras independientes) estos diagnósticos no son necesarios —
ver samplers.smc.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


RHAT_THRESHOLD  = 1.1
MIN_CHAINS_RHAT = 2


# ──────────────────────────────────────────────────────────────────────────────
# Estadísticos de convergencia
# ──────────────────────────────────────────────────────────────────────────────

def autocorrelation_function(
    series: np.ndarray | pd.Series,
    max_lag: int = 50,
) -> np.ndarray:
    """
    Función de autocorrelación (ACF) de una serie temporal.

    Returns
    -------
    np.ndarray shape (max_lag+1,) con ACF[0] = 1.0.
    """
    x   = np.asarray(series, dtype=float)
    x   = x - x.mean()
    n   = len(x)
    var = np.dot(x, x)

    if var == 0:
        return np.zeros(max_lag + 1)

    max_lag = min(max_lag, n - 1)
    acf = np.array([
        np.dot(x[:n - lag], x[lag:]) / var
        for lag in range(max_lag + 1)
    ])
    return acf


def effective_sample_size(
    series: np.ndarray | pd.Series,
    max_lag: int = 200,
) -> float:
    """
    Tamaño efectivo de muestra: ESS = N / (1 + 2 × Σ ρ_k).

    La suma se trunca en el primer rezago con ρ_k < 0.05 o negativo.
    """
    x   = np.asarray(series, dtype=float)
    n   = len(x)
    acf = autocorrelation_function(x, max_lag=min(max_lag, n // 2))

    cutoff = 1
    for k in range(1, len(acf)):
        if acf[k] < 0.05 or acf[k] < 0:
            break
        cutoff = k

    rho_sum = 2 * acf[1:cutoff + 1].sum()
    return float(n / max(1 + rho_sum, 1.0))


def gelman_rubin(
    chains: list[pd.DataFrame | pd.Series],
    metric_col: Optional[str] = None,
) -> float:
    """
    Estadístico Gelman-Rubin (R-hat) para múltiples cadenas.

    Parameters
    ----------
    chains : list
        Lista de Series o DataFrames de métricas por cadena.
    metric_col : str, opcional
        Columna a usar si chains son DataFrames.

    Returns
    -------
    float  R-hat. Valor < 1.1 indica convergencia aceptable.

    Raises
    ------
    ValueError  Si hay menos de 2 cadenas o son muy cortas.
    """
    if len(chains) < MIN_CHAINS_RHAT:
        raise ValueError(
            f"Se necesitan al menos {MIN_CHAINS_RHAT} cadenas para "
            f"Gelman-Rubin. Recibidas: {len(chains)}."
        )

    data = []
    for c in chains:
        if isinstance(c, pd.DataFrame):
            if metric_col is None:
                raise ValueError("metric_col requerido cuando chains son DataFrames.")
            data.append(c[metric_col].dropna().values)
        else:
            data.append(c.dropna().values)

    n = min(len(d) for d in data)
    if n < 4:
        raise ValueError(f"Cadenas demasiado cortas (n={n}). Necesitan ≥ 4 valores.")

    data = np.array([d[:n] for d in data], dtype=float)  # (K, N)
    K, N = data.shape

    chain_means = data.mean(axis=1)
    grand_mean  = chain_means.mean()

    B = N / (K - 1) * ((chain_means - grand_mean) ** 2).sum()
    W = data.var(axis=1, ddof=1).mean()

    if W == 0:
        return float("nan")

    V_hat = (N - 1) / N * W + (K + 1) / (K * N) * B
    return float(np.sqrt(V_hat / W))


def mixing_diagnostics(
    chain_metrics: list[pd.DataFrame],
    metrics: Optional[list[str]] = None,
) -> pd.DataFrame:
    """
    Tabla resumen de convergencia para múltiples cadenas.

    Parameters
    ----------
    chain_metrics : list[pd.DataFrame]
        DataFrames de métricas por cadena, cada uno con columna 'step'.
    metrics : list[str], opcional
        Columnas a evaluar. None = todas las numéricas excepto 'step'.

    Returns
    -------
    pd.DataFrame con columnas:
        metrica, n_cadenas, n_muestras_por_cadena,
        rhat, convergido, ess_promedio, acf_lag1_promedio.
    """
    if not chain_metrics:
        raise ValueError("chain_metrics está vacía.")

    if metrics is None:
        num_cols = chain_metrics[0].select_dtypes(include=np.number).columns.tolist()
        metrics  = [c for c in num_cols if c != "step"]

    rows = []
    for metric in metrics:
        series_list = [df[metric].dropna() for df in chain_metrics
                       if metric in df.columns]
        if not series_list:
            continue

        n_chains  = len(series_list)
        n_samples = min(len(s) for s in series_list)

        ess_vals  = [effective_sample_size(s.values) for s in series_list]
        acf1_vals = [float(autocorrelation_function(s.values, max_lag=1)[1])
                     for s in series_list]

        if n_chains >= MIN_CHAINS_RHAT:
            try:
                rhat = gelman_rubin(series_list)
            except ValueError:
                rhat = float("nan")
        else:
            rhat = float("nan")

        rows.append({
            "metrica":               metric,
            "n_cadenas":             n_chains,
            "n_muestras_por_cadena": n_samples,
            "rhat":                  round(rhat, 4),
            "convergido":            rhat < RHAT_THRESHOLD if not np.isnan(rhat) else None,
            "ess_promedio":          round(float(np.mean(ess_vals)), 1),
            "acf_lag1_promedio":     round(float(np.mean(acf1_vals)), 4),
        })

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Visualizaciones
# ──────────────────────────────────────────────────────────────────────────────

def plot_trace(
    chain_metrics: list[pd.DataFrame],
    metrics: Optional[list[str]] = None,
    labels: Optional[list[str]] = None,
    save_path: Optional[str] = None,
    figsize: Optional[tuple] = None,
) -> plt.Figure:
    """Gráfico de trazas para múltiples cadenas y métricas."""
    if metrics is None:
        num_cols = chain_metrics[0].select_dtypes(include=np.number).columns.tolist()
        metrics  = [c for c in num_cols if c != "step"]

    if labels is None:
        labels = [f"Cadena {i+1}" for i in range(len(chain_metrics))]

    n_met = len(metrics)
    if figsize is None:
        figsize = (10, max(3 * n_met, 4))

    fig, axes = plt.subplots(n_met, 1, figsize=figsize, sharex=False)
    if n_met == 1:
        axes = [axes]

    colors = plt.cm.tab10.colors

    for ax, metric in zip(axes, metrics):
        for i, (df, label) in enumerate(zip(chain_metrics, labels)):
            if metric not in df.columns:
                continue
            ax.plot(df["step"], df[metric],
                    color=colors[i % len(colors)],
                    alpha=0.8, linewidth=1.2, label=label)
        ax.set_ylabel(metric, fontsize=9)
        ax.grid(True, alpha=0.3)
        if ax is axes[0]:
            ax.legend(fontsize=8, ncol=min(len(chain_metrics), 4))

    axes[-1].set_xlabel("Paso de la cadena", fontsize=9)
    fig.suptitle("Trazas de cadenas ReCom", fontsize=11, fontweight="bold")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Guardado: {save_path}")

    return fig


def plot_acf(
    chain_metrics: list[pd.DataFrame],
    metric: str,
    max_lag: int = 30,
    labels: Optional[list[str]] = None,
    save_path: Optional[str] = None,
    figsize: tuple = (10, 4),
) -> plt.Figure:
    """Gráfico de ACF por cadena para una métrica dada."""
    if labels is None:
        labels = [f"Cadena {i+1}" for i in range(len(chain_metrics))]

    n_chains = len(chain_metrics)
    fig, axes = plt.subplots(1, n_chains, figsize=figsize, sharey=True)
    if n_chains == 1:
        axes = [axes]

    colors = plt.cm.tab10.colors

    for ax, df, label, color in zip(axes, chain_metrics, labels, colors):
        if metric not in df.columns:
            ax.set_title(f"{label}\n(sin datos)", fontsize=8)
            continue

        acf  = autocorrelation_function(df[metric].values, max_lag=max_lag)
        lags = np.arange(len(acf))

        ax.bar(lags, acf, color=color, alpha=0.7, width=0.8)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.axhline(0.05, color="red", linestyle="--", linewidth=0.8, alpha=0.6)
        ax.set_xlabel("Rezago", fontsize=8)
        ax.set_title(label, fontsize=9)
        ax.grid(True, alpha=0.2)
        ess = effective_sample_size(df[metric].values)
        ax.text(0.97, 0.95, f"ESS={ess:.0f}", transform=ax.transAxes,
                ha="right", va="top", fontsize=8)

    axes[0].set_ylabel("Autocorrelación", fontsize=9)
    fig.suptitle(f"ACF — {metric}", fontsize=11, fontweight="bold")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Guardado: {save_path}")

    return fig


def plot_gelman_rubin_evolution(
    chain_metrics: list[pd.DataFrame],
    metrics: Optional[list[str]] = None,
    window: int = 10,
    save_path: Optional[str] = None,
    figsize: Optional[tuple] = None,
) -> plt.Figure:
    """Evolución del R-hat a medida que se acumulan muestras."""
    if len(chain_metrics) < MIN_CHAINS_RHAT:
        raise ValueError(
            f"Se necesitan al menos {MIN_CHAINS_RHAT} cadenas. "
            f"Recibidas: {len(chain_metrics)}."
        )

    if metrics is None:
        num_cols = chain_metrics[0].select_dtypes(include=np.number).columns.tolist()
        metrics  = [c for c in num_cols if c != "step"]

    n_met = len(metrics)
    if figsize is None:
        figsize = (10, max(3 * n_met, 4))

    fig, axes = plt.subplots(n_met, 1, figsize=figsize)
    if n_met == 1:
        axes = [axes]

    for ax, metric in zip(axes, metrics):
        series_list = [df[metric].dropna().values for df in chain_metrics
                       if metric in df.columns]
        if not series_list:
            continue

        n_max = min(len(s) for s in series_list)
        steps = list(range(window, n_max + 1))
        rhats = []

        for t in steps:
            try:
                rhat = gelman_rubin([pd.Series(s[:t]) for s in series_list])
            except (ValueError, ZeroDivisionError):
                rhat = float("nan")
            rhats.append(rhat)

        ax.plot(steps, rhats, color="steelblue", linewidth=1.5)
        ax.axhline(RHAT_THRESHOLD, color="red", linestyle="--",
                   linewidth=1, label=f"Umbral R-hat={RHAT_THRESHOLD}")
        ax.axhline(1.0, color="green", linestyle=":", linewidth=0.8, alpha=0.5)
        ax.set_ylabel(f"R-hat ({metric})", fontsize=9)
        ax.set_ylim(bottom=0.9)
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    axes[-1].set_xlabel("Muestras acumuladas por cadena", fontsize=9)
    fig.suptitle("Evolución del estadístico Gelman-Rubin",
                 fontsize=11, fontweight="bold")
    fig.tight_layout()

    if save_path:
        fig.savefig(save_path, dpi=150, bbox_inches="tight")
        print(f"  Guardado: {save_path}")

    return fig


# ──────────────────────────────────────────────────────────────────────────────
# Wrapper multi-cadena
# ──────────────────────────────────────────────────────────────────────────────

def run_multiple_chains(
    gdf,
    n_chains: int,
    id_col: str,
    pop_col: str,
    n_districts: int,
    n_steps: int = 10_000,
    pop_tolerance: float = 0.05,
    initial_assignment: Optional[dict] = None,
    preserve_col: Optional[str] = None,
    base_seed: int = 42,
    save_every: int = 500,
    output_dir: str = ".",
) -> tuple[list[list[dict]], list[pd.DataFrame]]:
    """
    Ejecuta N cadenas ReCom independientes con semillas base_seed + k.

    Returns
    -------
    (all_plans, chain_metrics)
        all_plans : list[list[dict]] — una lista de planes por cadena
        chain_metrics : list[pd.DataFrame] — métricas por cadena
    """
    from .recom import run_recom

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_plans    : list[list[dict]]    = []
    chain_metrics: list[pd.DataFrame] = []

    for k in range(n_chains):
        seed   = base_seed + k
        prefix = str(output_dir / f"cadena_{k+1:02d}")

        print(f"\n{'='*60}")
        print(f"Cadena {k+1}/{n_chains}  (seed={seed})")
        print(f"{'='*60}")

        plans = run_recom(
            gdf,
            id_col=id_col,
            pop_col=pop_col,
            n_districts=n_districts,
            n_steps=n_steps,
            pop_tolerance=pop_tolerance,
            initial_assignment=initial_assignment,
            preserve_col=preserve_col,
            random_seed=seed,
            save_every=save_every,
            output_prefix=prefix,
        )

        metrics_path = f"{prefix}_metricas.csv"
        if Path(metrics_path).exists():
            df_m = pd.read_csv(metrics_path)
            df_m["chain"] = k + 1
        else:
            df_m = pd.DataFrame(columns=["step", "chain"])

        all_plans.append(plans)
        chain_metrics.append(df_m)
        print(f"  Cadena {k+1}: {len(plans)} planes, "
              f"{len(df_m)} registros de métricas")

    return all_plans, chain_metrics

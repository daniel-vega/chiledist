"""
chiledist.diagnostics
=====================
Módulo de compatibilidad — re-exporta desde chiledist.samplers.diagnostics y smc.

La lógica de diagnósticos se encuentra en:
    chiledist.samplers.diagnostics  — R-hat, ESS, ACF, multi-cadena
    chiledist.samplers.smc          — bridge R/redist (SMC)
"""

from .samplers.diagnostics import (
    autocorrelation_function,
    effective_sample_size,
    gelman_rubin,
    mixing_diagnostics,
    plot_trace,
    plot_acf,
    plot_gelman_rubin_evolution,
    run_multiple_chains,
    RHAT_THRESHOLD,
)
from .samplers.smc import (
    generate_redist_script,
    load_redist_results,
)

__all__ = [
    "autocorrelation_function", "effective_sample_size", "gelman_rubin",
    "mixing_diagnostics", "plot_trace", "plot_acf",
    "plot_gelman_rubin_evolution", "run_multiple_chains", "RHAT_THRESHOLD",
    "generate_redist_script", "load_redist_results",
]

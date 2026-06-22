"""
chiledist.samplers
==================
Subpaquete de muestreo para redistritaje electoral.

Módulos
-------
    recom        — Cadenas de Markov ReCom (gerrychain)
    smc          — Bridge R/redist para SMC (ALARM Harvard)
    diagnostics  — Convergencia MCMC: R-hat, ESS, ACF, multi-cadena

Uso rápido
----------
    # ReCom
    from chiledist.samplers.recom import run_recom, analyze_ensemble
    planes = run_recom(gdf, id_col="ID_DIST", pop_col="personas",
                       n_districts=8, n_steps=10_000)

    # Multi-cadena con diagnósticos
    from chiledist.samplers.diagnostics import run_multiple_chains, mixing_diagnostics
    all_plans, chain_metrics = run_multiple_chains(gdf, n_chains=4, ...)
    tabla = mixing_diagnostics(chain_metrics)

    # SMC vía R
    from chiledist.samplers.smc import generate_redist_script, load_redist_results
    r_script = generate_redist_script(gdf, id_col="ID_DIST", pop_col="personas",
                                       n_districts=8, output_dir="datos/R13")
"""

from .recom import (
    initial_partition,
    run_recom,
    run_recom_chain,
    analyze_ensemble,
    chile_constraints,
)

from .smc import (
    export_to_redist,
    generate_redist_script,
    load_redist_results,
)

from .diagnostics import (
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

__all__ = [
    # recom
    "initial_partition", "run_recom", "run_recom_chain",
    "analyze_ensemble", "chile_constraints",
    # smc
    "export_to_redist", "generate_redist_script", "load_redist_results",
    # diagnostics
    "autocorrelation_function", "effective_sample_size", "gelman_rubin",
    "mixing_diagnostics", "plot_trace", "plot_acf",
    "plot_gelman_rubin_evolution", "run_multiple_chains", "RHAT_THRESHOLD",
]

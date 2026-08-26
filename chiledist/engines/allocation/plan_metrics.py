"""
electoral.plan_metrics
========================
Métricas electorales completas de un plan de redistritaje: combina
asignación de magnitudes, D'Hondt (uni o binivel) e índices de
proporcionalidad y malapportionment en un solo diccionario.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from chiledist.rules.electoral_rules import TOTAL_ESCANOS_CAMARA, MIN_ESCANOS_DISTRITO, MAX_ESCANOS_DISTRITO
from .magnitudes import assign_seat_magnitudes
from .dhondt import (
    aggregate_votes,
    run_electoral_plan,
    run_electoral_plan_binivel,
    national_shares,
)
from chiledist.evaluation.proportionality import (
    gallagher_index,
    loosemore_hanby,
    rae_index,
    effective_number_of_parties,
    seat_bonus,
)
from chiledist.evaluation.district_malapportionment import personas_por_escano, peso_relativo_del_voto


def plan_electoral_metrics(
    assignment: dict,
    votes_df: pd.DataFrame,
    pop_by_unit: pd.Series,
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
    threshold: float = 0.0,
    unit_col: str = "CUT",
    partido_col: str = "partido",
    votos_col: str = "votos",
    pacto_map: Optional[dict] = None,
    magnitudes_fijas: Optional[pd.Series] = None,
) -> dict:
    """
    Calcula métricas electorales completas para un plan de redistritaje.

    Combina asignación de magnitudes, D'Hondt e índices de proporcionalidad
    en un solo diccionario listo para agregar a `ensemble_stats`.

    Parameters
    ----------
    assignment : dict {unit_id: district_num}
        Plan de redistritaje (salida de un paso de la cadena ReCom).
    votes_df : pd.DataFrame
        Votos con columnas unit_col, partido_col, votos_col.
        Típicamente la salida de sv.votos_por_comuna().
    pop_by_unit : pd.Series
        Población por unidad (indexed by unit_id).
        Siempre necesaria para las métricas de malapportionment (H3).
        Si magnitudes_fijas es None, también se usa para calcular magnitudes.
    total_seats, min_seats, max_seats : int
        Parámetros para assign_seat_magnitudes().
        Ignorados cuando magnitudes_fijas no es None.
    threshold : float
        Umbral mínimo de votos para D'Hondt.
    unit_col, partido_col, votos_col : str
        Nombres de columnas en votes_df.
    pacto_map : dict {partido: pacto}, optional
        Mapa de partidos a coaliciones electorales.  Si se provee, usa
        D'Hondt binivel (sistema real chileno Ley 18.700): primero distribuye
        escaños entre pactos, luego entre partidos dentro de cada pacto.
        Si es None, usa D'Hondt uninivel (modo retro-compatible).
    magnitudes_fijas : pd.Series {district_id: n_escaños}, optional
        Magnitudes externas (ej. MAGNITUDES_LEGALES_LEY20840 reindexadas).
        Si se provee, se usan directamente sin recalcular desde la población.

        **Cuándo usar cada modo:**

        ``magnitudes_fijas=None`` (default — "calculadas"):
            Responde: "Si este plan se adoptara y los escaños se distribuyeran
            proporcionalmente a la nueva geografía, ¿cómo quedarían las métricas?"
            Útil para comparar planes en igualdad de condiciones (ensemble).
            Las métricas de malapportionment tenderán a ser bajas porque
            assign_seat_magnitudes está diseñada para minimizarlas.

        ``magnitudes_fijas=<Series>`` (modo "fijas"):
            Responde: "Con los escaños actuales fijos, ¿qué malapportionment
            introduce este mapa?" Correcto para análisis H3 donde se quiere
            medir la desigualdad estructural del mapa, no del sistema de
            asignación.  También es el modo correcto para simular resultados
            electorales bajo el sistema legal vigente.

    Returns
    -------
    dict con claves:
        gallagher, loosemore_hanby, rae,
        enp_votos, enp_escanos,
        escanos_mayor_partido (int),
        n_partidos_con_escanos (int),
        pxe_max, pxe_min, ratio_max_min_pxe,
        peso_relativo_max, peso_relativo_min,
        seat_bonus_max,
        modo_dhondt  ("binivel" | "uninivel"),
        modo_magnitudes ("fijas" | "calculadas").

    Raises
    ------
    ValueError
        Si magnitudes_fijas no cubre todos los distritos del plan.
    """
    # Población por circunscripción
    pop_map = pop_by_unit.to_dict()
    pop_by_d = pd.Series(
        {d: sum(pop_map.get(u, 0) for u, dd in assignment.items() if dd == d)
         for d in set(assignment.values())}
    )

    if magnitudes_fijas is not None:
        # Verificar cobertura: todos los distritos del plan deben tener magnitud
        districts_plan = set(pop_by_d.index)
        districts_mag  = set(magnitudes_fijas.index)
        missing = districts_plan - districts_mag
        if missing:
            raise ValueError(
                f"magnitudes_fijas no cubre {len(missing)} distrito(s) del plan: "
                f"{sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}. "
                "Asegúrate de que el índice de magnitudes_fijas coincida con los "
                "valores del assignment."
            )
        magnitudes    = magnitudes_fijas.reindex(pop_by_d.index)
        modo_mag      = "fijas"
    else:
        magnitudes    = assign_seat_magnitudes(pop_by_d, total_seats, min_seats, max_seats)
        modo_mag      = "calculadas"
    votes_dist = aggregate_votes(votes_df, assignment, unit_col, partido_col, votos_col)

    if pacto_map is not None:
        # Sistema real: D'Hondt binivel (pactos → partidos)
        votes_dist["pacto"] = (
            votes_dist["partido"].map(pacto_map).fillna(votes_dist["partido"])
        )
        results = run_electoral_plan_binivel(
            votes_dist, magnitudes,
            pacto_col="pacto",
            partido_col="partido",
            votos_col="votos",
            threshold=threshold,
        )
        modo = "binivel"
    else:
        # Modo retro-compatible: D'Hondt uninivel
        results = run_electoral_plan(votes_dist, magnitudes, threshold)
        modo = "uninivel"

    v_sh, s_sh = national_shares(results)

    escanos_por_partido = results.groupby("partido")["escanos"].sum()

    # Malapportionment (H3)
    pxe  = personas_por_escano(pop_by_d, magnitudes)
    prv  = peso_relativo_del_voto(pop_by_d, magnitudes)
    sbon = seat_bonus(v_sh, s_sh)

    pxe_max  = float(pxe.max())  if not pxe.empty  else float("nan")
    pxe_min  = float(pxe.min())  if not pxe.empty  else float("nan")
    prv_max  = float(prv.max())  if not prv.empty  else float("nan")
    prv_min  = float(prv.min())  if not prv.empty  else float("nan")
    ratio_pm = round(pxe_max / pxe_min, 4) if pxe_min and pxe_min > 0 else float("nan")

    return {
        "gallagher":              round(gallagher_index(v_sh, s_sh), 4),
        "loosemore_hanby":        round(loosemore_hanby(v_sh, s_sh), 4),
        "rae":                    round(rae_index(v_sh, s_sh), 4),
        "enp_votos":              round(effective_number_of_parties(v_sh), 4),
        "enp_escanos":            round(effective_number_of_parties(s_sh), 4),
        "escanos_mayor_partido":  int(escanos_por_partido.max()),
        "n_partidos_con_escanos": int((escanos_por_partido > 0).sum()),
        # H3 — malapportionment
        "pxe_max":                round(pxe_max, 0) if not np.isnan(pxe_max) else float("nan"),
        "pxe_min":                round(pxe_min, 0) if not np.isnan(pxe_min) else float("nan"),
        "ratio_max_min_pxe":      ratio_pm,
        "peso_relativo_max":      round(prv_max, 4) if not np.isnan(prv_max) else float("nan"),
        "peso_relativo_min":      round(prv_min, 4) if not np.isnan(prv_min) else float("nan"),
        "seat_bonus_max":         round(float(sbon.abs().max()), 4) if not sbon.empty else float("nan"),
        "modo_dhondt":            modo,
        "modo_magnitudes":        modo_mag,
    }

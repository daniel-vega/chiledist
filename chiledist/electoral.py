"""
chiledist/electoral.py
======================
Asignación de escaños por D'Hondt e índices de proporcionalidad.

Para análisis de redistritaje: dado un plan (asignación de distritos APC
a circunscripciones electorales) y datos de votos por partido a nivel
comunal, calcula resultados electorales e índices de proporcionalidad.

Flujo típico
------------
    import chiledist.electoral as elec
    import chiledist.data.servel as sv

    # 1. Cargar votos comunales (salida de sv.votos_por_comuna)
    votos = sv.votos_por_comuna(resultados_df)          # CUT, partido, votos

    # 2. Asignar magnitudes de escaño según población del plan
    magnitudes = elec.assign_seat_magnitudes(
        pop_by_district, total_seats=155, min_seats=3, max_seats=8
    )

    # 3. Agregar votos al nivel de circunscripción electoral
    votos_dist = elec.aggregate_votes(
        votos, assignment=plan_assignment, unit_col="CUT"
    )

    # 4. Correr D'Hondt por circunscripción
    resultados = elec.run_electoral_plan(votos_dist, magnitudes)

    # 5. Índices nacionales de proporcionalidad
    summary = elec.proportionality_summary(
        *elec.national_shares(resultados)
    )

Sistema electoral chileno
-------------------------
Diputados (155 escaños, 28 circunscripciones, M∈[3,8]).
Método: D'Hondt por lista/pacto; sin umbral legal explícito.
Fuente legal: Ley N°18.700 art. 109 bis (texto post reforma 2015).
"""

from __future__ import annotations

from typing import Optional
import numpy as np
import pandas as pd


# ── Constantes ────────────────────────────────────────────────────────────────

TOTAL_ESCANOS_CAMARA = 155
MIN_ESCANOS_DISTRITO = 3
MAX_ESCANOS_DISTRITO = 8


# ──────────────────────────────────────────────────────────────────────────────
# Algoritmo D'Hondt
# ──────────────────────────────────────────────────────────────────────────────

def dhondt(
    votes: dict[str, int | float],
    seats: int,
    threshold: float = 0.0,
) -> dict[str, int]:
    """
    Asignación de escaños por el método D'Hondt.

    Parameters
    ----------
    votes : dict {partido: n_votos}
        Votos por partido en la circunscripción. Valores negativos se tratan
        como cero.
    seats : int
        Escaños a distribuir.
    threshold : float
        Umbral mínimo de votos como fracción del total (ej. 0.05 = 5 %).
        0.0 implica sin umbral (default — sistema chileno sin umbral legal).

    Returns
    -------
    dict {partido: escaños_obtenidos}
        Todos los partidos del input aparecen; los excluidos por umbral
        reciben 0.

    Examples
    --------
    >>> dhondt({"A": 100, "B": 80, "C": 30}, seats=3)
    {'A': 2, 'B': 1, 'C': 0}
    """
    if seats <= 0:
        return {p: 0 for p in votes}

    votes = {p: max(0, v) for p, v in votes.items()}
    total = sum(votes.values())

    if total == 0:
        return {p: 0 for p in votes}

    # Filtrar por umbral
    eligible = {p: v for p, v in votes.items() if v / total >= threshold}
    if not eligible:
        return {p: 0 for p in votes}

    seat_counts = {p: 0 for p in eligible}

    for _ in range(seats):
        # Cociente D'Hondt; desempate: más votos, luego nombre (determinístico)
        best = max(
            eligible,
            key=lambda p: (eligible[p] / (seat_counts[p] + 1), eligible[p], p),
        )
        seat_counts[best] += 1

    result = {p: 0 for p in votes}
    result.update(seat_counts)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Asignación de magnitudes (escaños por distrito)
# ──────────────────────────────────────────────────────────────────────────────

def assign_seat_magnitudes(
    pop_by_district: pd.Series,
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
) -> pd.Series:
    """
    Asigna magnitudes de escaño a circunscripciones electorales por población.

    Usa el método Hamilton (resto mayor) con cotas mínima y máxima por
    distrito, que es el método estándar en la Ley 18.700.

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción electoral (indexed by district id).
    total_seats : int
        Total de escaños a distribuir (default: 155 para Cámara de Diputados).
    min_seats, max_seats : int
        Cotas por distrito (default: 3 / 8 según Ley 18.700).

    Returns
    -------
    pd.Series (mismos índices que pop_by_district): escaños asignados (int).

    Raises
    ------
    ValueError
        Si el total de escaños no alcanza para asignar min_seats a cada
        distrito.
    """
    n = len(pop_by_district)
    if n == 0:
        return pd.Series(dtype=int)

    if total_seats < n * min_seats:
        raise ValueError(
            f"total_seats ({total_seats}) insuficiente para {n} distritos "
            f"con min_seats={min_seats} (requiere ≥ {n * min_seats})."
        )

    total_pop = pop_by_district.sum()
    if total_pop == 0:
        return pd.Series(min_seats, index=pop_by_district.index)

    # Cada distrito parte con mínimo garantizado
    seats = pd.Series(min_seats, index=pop_by_district.index, dtype=int)
    remaining = total_seats - n * min_seats
    capacity  = max_seats - min_seats  # escaños adicionales máximos

    if remaining == 0:
        return seats

    # Parte entera proporcional (con cota de capacidad)
    ideal     = pop_by_district / total_pop * remaining
    base_add  = ideal.apply(np.floor).astype(int).clip(upper=capacity)
    remainders = ideal - base_add

    seats    += base_add
    remaining -= int(base_add.sum())

    # Distribuir restantes por mayor resto, respetando max_seats
    if remaining > 0:
        puede_recibir = seats < max_seats
        orden = remainders[puede_recibir].sort_values(ascending=False)
        for idx in orden.index[:remaining]:
            seats[idx] += 1

    return seats


# ──────────────────────────────────────────────────────────────────────────────
# Agregación de votos al nivel de circunscripción
# ──────────────────────────────────────────────────────────────────────────────

def aggregate_votes(
    votes_df: pd.DataFrame,
    assignment: dict,
    unit_col: str = "CUT",
    partido_col: str = "partido",
    votos_col: str = "votos",
) -> pd.DataFrame:
    """
    Agrega votos comunales a nivel de circunscripción electoral.

    Parameters
    ----------
    votes_df : pd.DataFrame
        Votos a nivel de unidad (commune o APC district).
        Debe tener columnas: unit_col, partido_col, votos_col.
    assignment : dict {unit_id: district_num}
        Asignación de unidades a circunscripciones (salida de un plan ReCom).
    unit_col : str
        Nombre de la columna de unidad (default: "CUT").
    partido_col, votos_col : str
        Nombres de columnas de partido y votos.

    Returns
    -------
    pd.DataFrame con columnas: district, partido, votos — listo para
    pasarlo a run_electoral_plan().
    """
    df = votes_df.copy()
    df["district"] = df[unit_col].map(assignment)
    missing = df["district"].isna().sum()
    if missing > 0:
        n_units = df[unit_col].nunique()
        n_missing = df.loc[df["district"].isna(), unit_col].nunique()
        print(f"  ⚠ {n_missing}/{n_units} unidades sin asignación de distrito "
              f"({missing} filas) → excluidas")
        df = df[df["district"].notna()]

    return (
        df.groupby(["district", partido_col])[votos_col]
        .sum()
        .reset_index()
        .rename(columns={partido_col: "partido", votos_col: "votos"})
        .sort_values(["district", "votos"], ascending=[True, False])
        .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Ejecución del plan electoral completo
# ──────────────────────────────────────────────────────────────────────────────

def run_electoral_plan(
    votes_by_district: pd.DataFrame,
    seat_magnitudes: pd.Series,
    threshold: float = 0.0,
) -> pd.DataFrame:
    """
    Ejecuta D'Hondt para todas las circunscripciones de un plan.

    Parameters
    ----------
    votes_by_district : pd.DataFrame
        Salida de aggregate_votes(): columnas district, partido, votos.
    seat_magnitudes : pd.Series
        Escaños por circunscripción (salida de assign_seat_magnitudes()).
        Index = district id, values = n_escaños.
    threshold : float
        Umbral mínimo de votos para participar (0.0 = sin umbral).

    Returns
    -------
    pd.DataFrame con columnas:
        district, partido, votos, escanos, escanos_pct, votos_pct.
    """
    rows = []

    for district, grp in votes_by_district.groupby("district"):
        seats = int(seat_magnitudes.get(district, 0))
        if seats == 0:
            continue

        votos_dict = dict(zip(grp["partido"], grp["votos"]))
        escanos    = dhondt(votos_dict, seats, threshold=threshold)
        total_v    = sum(votos_dict.values())

        for partido, v in votos_dict.items():
            rows.append({
                "district":    district,
                "partido":     partido,
                "votos":       int(v),
                "escanos":     escanos[partido],
                "votos_pct":   round(v / total_v * 100, 4) if total_v else 0.0,
                "escanos_pct": round(
                    escanos[partido] / seats * 100, 4
                ) if seats else 0.0,
            })

    return (
        pd.DataFrame(rows)
        .sort_values(["district", "escanos", "votos"], ascending=[True, False, False])
        .reset_index(drop=True)
    )


def national_shares(
    results: pd.DataFrame,
    partido_col: str = "partido",
) -> tuple[pd.Series, pd.Series]:
    """
    Calcula cuotas nacionales de votos y escaños a partir de los resultados.

    Returns
    -------
    (vote_shares, seat_shares) — Series indexed by partido, values in [0,1].
    """
    v = results.groupby(partido_col)["votos"].sum()
    s = results.groupby(partido_col)["escanos"].sum()

    vote_shares = v / v.sum()
    seat_shares = s / s.sum()
    return vote_shares, seat_shares


# ──────────────────────────────────────────────────────────────────────────────
# Índices de proporcionalidad
# ──────────────────────────────────────────────────────────────────────────────

def gallagher_index(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de desproporcionalidad de Gallagher (Least Squares Index).

    LSq = sqrt( Σ (v_i - s_i)² / 2 )

    Rango [0, 100]: 0 = perfectamente proporcional.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float(np.sqrt(((v - s) ** 2).sum() / 2))


def loosemore_hanby(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de Loosemore-Hanby.

    LH = Σ |v_i - s_i| / 2

    Rango [0, 100]: 0 = perfectamente proporcional.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float((v - s).abs().sum() / 2)


def rae_index(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> float:
    """
    Índice de Rae (promedio de diferencias absolutas).

    Rae = Σ |v_i - s_i| / n_parties

    Rango [0, 100].
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return float((v - s).abs().mean())


def effective_number_of_parties(shares: pd.Series) -> float:
    """
    Número efectivo de partidos (Laakso-Taagepera).

    ENP = 1 / Σ p_i²

    Útil como ENP_votos (con vote_shares) y ENP_escaños (con seat_shares).
    """
    s = shares[shares > 0]
    if len(s) == 0:
        return float("nan")
    return float(1 / (s ** 2).sum())


def proportionality_summary(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> pd.DataFrame:
    """
    Tabla resumen con todos los índices de proporcionalidad.

    Parameters
    ----------
    vote_shares, seat_shares : pd.Series
        Cuotas nacionales en [0,1] por partido (salida de national_shares()).

    Returns
    -------
    pd.DataFrame con columnas: indice, valor, descripcion.
    """
    rows = [
        {
            "indice":      "gallagher",
            "valor":       round(gallagher_index(vote_shares, seat_shares), 4),
            "descripcion": "Índice Gallagher (LSq) — menor = más proporcional",
        },
        {
            "indice":      "loosemore_hanby",
            "valor":       round(loosemore_hanby(vote_shares, seat_shares), 4),
            "descripcion": "Índice Loosemore-Hanby — menor = más proporcional",
        },
        {
            "indice":      "rae",
            "valor":       round(rae_index(vote_shares, seat_shares), 4),
            "descripcion": "Índice Rae — menor = más proporcional",
        },
        {
            "indice":      "enp_votos",
            "valor":       round(effective_number_of_parties(vote_shares), 4),
            "descripcion": "N° efectivo de partidos (votos)",
        },
        {
            "indice":      "enp_escanos",
            "valor":       round(effective_number_of_parties(seat_shares), 4),
            "descripcion": "N° efectivo de partidos (escaños)",
        },
    ]
    return pd.DataFrame(rows)


# ──────────────────────────────────────────────────────────────────────────────
# Análisis electoral de un plan completo
# ──────────────────────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────────────────────
# Malapportionment: igualdad del voto estructural
# ──────────────────────────────────────────────────────────────────────────────

def personas_por_escano(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> pd.Series:
    """
    Personas por escaño por circunscripción electoral.

    Métrica central de malapportionment: cuántas personas debe representar
    cada diputado según la distribución geográfica del plan.

    Parameters
    ----------
    pop_by_district : pd.Series
        Población por circunscripción (indexed by district_id).
    magnitudes : pd.Series
        Escaños asignados por circunscripción (indexed by district_id).

    Returns
    -------
    pd.Series (mismos índices) con personas / escaño por circunscripción.
    """
    common = pop_by_district.index.intersection(magnitudes.index)
    pop = pop_by_district.reindex(common)
    mag = magnitudes.reindex(common).replace(0, np.nan)
    return (pop / mag).rename("personas_por_escano")


def peso_relativo_del_voto(
    pop_by_district: pd.Series,
    magnitudes: pd.Series,
) -> pd.Series:
    """
    Peso relativo del voto respecto a la media nacional.

    peso = (personas_por_escano_i) / media_nacional

    Interpretación:
        peso < 1.0 → ese voto vale MÁS que el promedio (subrepresentado en pop)
        peso > 1.0 → ese voto vale MENOS que el promedio (sobrerrepresentado en pop)
        peso = 0.5 → un voto en este distrito equivale a dos votos promedio

    Este es el estándar internacional de malapportionment (Samuels & Snyder 2001).

    Returns
    -------
    pd.Series (mismos índices).
    """
    common = pop_by_district.index.intersection(magnitudes.index)
    pop    = pop_by_district.reindex(common)
    mag    = magnitudes.reindex(common)

    # Media nacional correcta: total_pop / total_seats (no media aritmética de cocientes).
    # Las dos difieren cuando los distritos tienen tamaños distintos — que es siempre el caso.
    # Estándar: Samuels & Snyder (2001), Cox & Katz (2002).
    valid         = mag > 0
    total_pop     = pop[valid].sum()
    total_seats   = mag[valid].sum()

    if total_seats == 0 or total_pop == 0:
        pxe = personas_por_escano(pop_by_district, magnitudes)
        return pd.Series(np.nan, index=pxe.index, name="peso_relativo_del_voto")

    media_nacional = total_pop / total_seats
    pxe = personas_por_escano(pop_by_district, magnitudes)
    return (pxe / media_nacional).rename("peso_relativo_del_voto")


def comparar_magnitudes(
    pop_by_district: pd.Series,
    magnitudes_vigentes: "dict[int, int] | pd.Series",
    total_seats: int = TOTAL_ESCANOS_CAMARA,
    min_seats: int = MIN_ESCANOS_DISTRITO,
    max_seats: int = MAX_ESCANOS_DISTRITO,
) -> pd.DataFrame:
    """
    Compara las magnitudes vigentes con las que resultarían de reasignar
    escaños según la población actualizada (método Hamilton acotado).

    Útil para el análisis contrafactual de H3: ¿qué cambiaría si se
    actualizaran las magnitudes con el Censo 2024?

    Parameters
    ----------
    pop_by_district : pd.Series
        Población actualizada por circunscripción (Censo 2024 recomendado).
        El índice debe contener los mismos district_ids que magnitudes_vigentes.
    magnitudes_vigentes : dict | pd.Series
        Magnitudes actuales (ej. MAGNITUDES_LEGALES_LEY20840).
    total_seats, min_seats, max_seats : int
        Parámetros de assign_seat_magnitudes().

    Returns
    -------
    pd.DataFrame con columnas:
        distrito, magnitud_vigente, magnitud_nueva, delta,
        pop_vigente_pxe (personas/escaño con magnitud vigente),
        pop_nueva_pxe   (personas/escaño con magnitud nueva).
    """
    if isinstance(magnitudes_vigentes, dict):
        mag_vig = pd.Series(magnitudes_vigentes)
    else:
        mag_vig = magnitudes_vigentes.copy()

    mag_nueva = assign_seat_magnitudes(
        pop_by_district.reindex(mag_vig.index, fill_value=0),
        total_seats=total_seats,
        min_seats=min_seats,
        max_seats=max_seats,
    )

    pop_aligned = pop_by_district.reindex(mag_vig.index, fill_value=0)

    df = pd.DataFrame({
        "distrito":          mag_vig.index,
        "magnitud_vigente":  mag_vig.values,
        "magnitud_nueva":    mag_nueva.reindex(mag_vig.index, fill_value=min_seats).values,
    })
    df["delta"] = df["magnitud_nueva"] - df["magnitud_vigente"]

    df["pop"] = pop_aligned.values
    # Indexing directo sobre las columnas del df (sin .values) para evitar
    # alineación posicional frágil tras posibles reordenamientos.
    df["pop_vigente_pxe"] = (df["pop"] / df["magnitud_vigente"].replace(0, np.nan)).round(0).astype("Int64")
    df["pop_nueva_pxe"]   = (df["pop"] / df["magnitud_nueva"].replace(0, np.nan)).round(0).astype("Int64")

    return df.sort_values("delta", ascending=False).reset_index(drop=True)


def umbral_efectivo(magnitud: int) -> float:
    """
    Umbral superior (T_U) de Taagepera para un distrito de M escaños.

    Fórmula: T_U = 1 / (M + 1)

    T_U es el umbral más exigente: un partido con menos del T_U% de votos
    prácticamente NO puede ganar un escaño bajo D'Hondt.  No confundir con:
        T_L = 1/(2M)           — umbral inferior (mínimo para ganar)
        T_e = √(T_L × T_U)    — umbral efectivo geométrico (Taagepera 1998)

    Esta función implementa T_U porque es la cota conservadora estándar para
    análisis de barreras de entrada. T_U sobreestima la barrera en ~20–30%
    respecto a T_e; si necesitas el umbral geométrico calcula √(T_U × T_U/2).

    Ejemplos:
        M=3 → 25.0%   (T_e ≈ 20.4%)
        M=5 → 16.7%   (T_e ≈ 12.9%)
        M=8 → 11.1%   (T_e ≈  8.3%)

    Returns
    -------
    float en (0, 1].
    """
    if magnitud <= 0:
        return 1.0
    return round(1.0 / (magnitud + 1), 4)


def margen_ultimo_escano(
    votes: "dict[str, int | float]",
    seats: int,
    threshold: float = 0.0,
) -> dict:
    """
    Margen del último escaño en una circunscripción electoral.

    Calcula la diferencia entre el cociente D'Hondt del último escaño
    asignado y el cociente más alto de los no ganadores.  Un margen
    pequeño indica que el resultado es altamente sensible a pequeños
    cambios en votos o geografía distrital.

    Parameters
    ----------
    votes : dict {lista_o_partido: n_votos}
    seats : int
    threshold : float
        Umbral mínimo de votos (0.0 = sin umbral).

    Returns
    -------
    dict con:
        ultimo_ganador   : nombre del partido/lista que ganó el último escaño
        primer_perdedor  : nombre del que no ganó por menor cociente
        cociente_ganador : cociente D'Hondt del último escaño (votos/n_escaños)
        cociente_perdedor: mejor cociente de los perdedores
        margen_cociente  : diferencia de cocientes (ganador − perdedor)
        margen_pct       : margen como % del cociente ganador
    """
    if seats <= 0 or not votes:
        return {}

    votes = {p: max(0, v) for p, v in votes.items()}
    total = sum(votes.values())
    if total == 0:
        return {}

    eligible = {p: v for p, v in votes.items() if v / total >= threshold}
    if not eligible:
        return {}

    # Simular D'Hondt paso a paso registrando cocientes
    seat_counts: dict[str, int] = {p: 0 for p in eligible}
    cocientes_asignados = []

    for _ in range(seats):
        cocientes_actuales = {
            p: eligible[p] / (seat_counts[p] + 1) for p in eligible
        }
        best = max(cocientes_actuales,
                   key=lambda p: (cocientes_actuales[p], eligible[p], p))
        cocientes_asignados.append((best, cocientes_actuales[best]))
        seat_counts[best] += 1

    ultimo_ganador, cociente_ganador = cocientes_asignados[-1]

    # Cociente que cada partido tendría en la siguiente asignación.
    # Para los perdedores (seat_counts sin cambio tras el último paso),
    # este cociente coincide con el que tenían EN el último paso.
    cocientes_siguientes = {
        p: eligible[p] / (seat_counts[p] + 1) for p in eligible
    }
    # Excluir explícitamente al ultimo_ganador: queremos el mejor cociente
    # entre quienes NO ganaron el último escaño.
    primer_perdedor = max(
        [p for p in eligible if p != ultimo_ganador],
        key=lambda p: cocientes_siguientes[p],
        default=None,
    )

    if primer_perdedor is None:
        return {
            "ultimo_ganador":    ultimo_ganador,
            "primer_perdedor":   None,
            "cociente_ganador":  round(cociente_ganador, 2),
            "cociente_perdedor": None,
            "margen_cociente":   None,
            "margen_pct":        None,
        }

    cociente_perdedor = cocientes_siguientes[primer_perdedor]
    margen = cociente_ganador - cociente_perdedor

    return {
        "ultimo_ganador":    ultimo_ganador,
        "primer_perdedor":   primer_perdedor,
        "cociente_ganador":  round(cociente_ganador, 2),
        "cociente_perdedor": round(cociente_perdedor, 2),
        "margen_cociente":   round(margen, 2),
        "margen_pct":        round(margen / cociente_ganador * 100, 2)
                             if cociente_ganador > 0 else None,
    }


def seat_bonus(
    vote_shares: pd.Series,
    seat_shares: pd.Series,
) -> pd.Series:
    """
    Prima de escaños: diferencia (escaños% − votos%) por partido o pacto.

    Positivo → sobrerepresentado (más escaños de los que corresponden
               por votos).
    Negativo → subrepresentado.

    Bajo proporcionalidad perfecta, todos los valores son 0.

    Parameters
    ----------
    vote_shares, seat_shares : pd.Series
        Cuotas en [0, 1] (salida de national_shares()).

    Returns
    -------
    pd.Series indexed by partido/pacto, valores en puntos porcentuales.
    """
    parties = vote_shares.index.union(seat_shares.index)
    v = vote_shares.reindex(parties, fill_value=0.0) * 100
    s = seat_shares.reindex(parties, fill_value=0.0) * 100
    return (s - v).rename("seat_bonus").round(4)


# ──────────────────────────────────────────────────────────────────────────────
# D'Hondt binivel — sistema electoral chileno real
# ──────────────────────────────────────────────────────────────────────────────

def dhondt_binivel(
    votos_por_partido: "dict[str, int | float]",
    pacto_map: "dict[str, str]",
    seats: int,
    threshold: float = 0.0,
) -> "dict[str, int]":
    """
    D'Hondt en dos niveles: pactos → partidos.

    Implementa el sistema electoral chileno real (Ley 18.700):

    Nivel 1:
        Suma los votos de todos los partidos de cada pacto.
        Aplica D'Hondt entre pactos para determinar escaños por pacto.

    Nivel 2:
        Para cada pacto ganador, aplica D'Hondt entre sus partidos
        (aproximación de lista abierta cuando no hay datos de candidatos).

    Nota metodológica
    -----------------
    El sistema real asigna los escaños del pacto a sus candidatos más
    votados individualmente (no a partidos).  Cuando solo se dispone de
    datos agregados por partido, el D'Hondt interno entre partidos es la
    aproximación estándar en análisis electoral comparado.

    Parameters
    ----------
    votos_por_partido : dict {partido: n_votos}
    pacto_map : dict {partido: pacto}
        Mapeo de partido a su coalición.  Los partidos no mapeados se tratan
        como pactos independientes (pacto = partido).
    seats : int
        Escaños a distribuir en la circunscripción.
    threshold : float
        Umbral de votos del pacto sobre el total (0.0 = sin umbral, sistema
        chileno no tiene umbral legal).

    Returns
    -------
    dict {partido: escaños_obtenidos}
        Todos los partidos del input aparecen; excluidos por umbral reciben 0.

    Examples
    --------
    >>> votos = {"PS": 30000, "PPD": 20000, "RN": 40000, "UDI": 25000}
    >>> pactos = {"PS": "Apruebo", "PPD": "Apruebo", "RN": "Chile Vamos", "UDI": "Chile Vamos"}
    >>> dhondt_binivel(votos, pactos, seats=3)
    {'PS': 1, 'PPD': 0, 'RN': 1, 'UDI': 1}
    """
    if seats <= 0:
        return {p: 0 for p in votos_por_partido}

    votos_por_partido = {p: max(0, v) for p, v in votos_por_partido.items()}

    # Agrupar votos por pacto
    pacto_votes: dict[str, float] = {}
    pacto_to_parties: dict[str, dict[str, float]] = {}
    for partido, votos in votos_por_partido.items():
        pacto = pacto_map.get(partido, partido)
        pacto_votes[pacto]                          = pacto_votes.get(pacto, 0) + votos
        pacto_to_parties.setdefault(pacto, {})[partido] = votos

    total = sum(pacto_votes.values())
    if total == 0:
        return {p: 0 for p in votos_por_partido}

    # Nivel 1: D'Hondt entre pactos
    pacto_seats = dhondt(pacto_votes, seats, threshold)

    # Nivel 2: D'Hondt dentro de cada pacto
    result = {p: 0 for p in votos_por_partido}
    for pacto, n in pacto_seats.items():
        if n == 0:
            continue
        parties = pacto_to_parties.get(pacto, {})
        if not parties:
            continue
        for partido, s in dhondt(parties, n).items():
            result[partido] = s

    return result


def run_electoral_plan_binivel(
    votes_by_district: pd.DataFrame,
    seat_magnitudes: pd.Series,
    pacto_col: str = "pacto",
    partido_col: str = "partido",
    votos_col: str = "votos",
    threshold: float = 0.0,
) -> pd.DataFrame:
    """
    Ejecuta D'Hondt binivel para todas las circunscripciones de un plan.

    Versión binivel de run_electoral_plan() que implementa el sistema
    electoral chileno real: asignación primero entre pactos, luego entre
    partidos dentro de cada pacto.

    Parameters
    ----------
    votes_by_district : pd.DataFrame
        Columnas requeridas: district, pacto_col, partido_col, votos_col.
        Salida típica de aggregate_votes() enriquecida con columna de pacto.
    seat_magnitudes : pd.Series
        Escaños por circunscripción (indexed by district_id).
    pacto_col : str
        Columna de coalición electoral (default "pacto").
    partido_col, votos_col : str
        Nombres de columnas de partido y votos.
    threshold : float
        Umbral mínimo de votos del pacto (0.0 = sin umbral).

    Returns
    -------
    pd.DataFrame con columnas:
        district, pacto, partido, votos, escanos,
        escanos_pacto, votos_pct, escanos_pct.
    """
    rows = []

    for district, grp in votes_by_district.groupby("district"):
        seats = int(seat_magnitudes.get(district, 0))
        if seats == 0:
            continue

        # groupby().sum/first en lugar de dict(zip) para manejar correctamente
        # filas duplicadas (mismo partido en el mismo distrito).
        votos_grp  = grp.groupby(partido_col, sort=False)[votos_col].sum()
        votos_dict = votos_grp.to_dict()
        pacto_dict = grp.groupby(partido_col, sort=False)[pacto_col].first().to_dict()

        escanos = dhondt_binivel(votos_dict, pacto_dict, seats, threshold)

        # Escaños por pacto (para reportar)
        escanos_pacto: dict[str, int] = {}
        for partido, s in escanos.items():
            pacto = pacto_dict.get(partido, partido)
            escanos_pacto[pacto] = escanos_pacto.get(pacto, 0) + s

        total_v = sum(v for v in votos_dict.values() if v > 0)

        for partido, v in votos_dict.items():
            pacto = pacto_dict.get(partido, partido)
            rows.append({
                "district":     district,
                "pacto":        pacto,
                partido_col:    partido,
                "votos":        int(v),
                "escanos":      escanos[partido],
                "escanos_pacto": escanos_pacto.get(pacto, 0),
                "votos_pct":    round(v / total_v * 100, 4) if total_v else 0.0,
                "escanos_pct":  round(escanos[partido] / seats * 100, 4) if seats else 0.0,
            })

    return (
        pd.DataFrame(rows)
        .sort_values(["district", "escanos", "votos"], ascending=[True, False, False])
        .reset_index(drop=True)
    )


# ──────────────────────────────────────────────────────────────────────────────
# Configuración legal actual (28 circunscripciones, post-reforma 2015)
# ──────────────────────────────────────────────────────────────────────────────

MAGNITUDES_LEGALES_LEY20840 = {
    # 28 distritos electorales según Art. 179 Ley 18.700 modificada por Ley 20.840.
    # Fuente: BCN, Ley 20.840 (05-MAY-2015). Sin cambios en elecciones 2017, 2021, 2025.
    # Art. 179 bis: SERVEL actualiza cada 10 años según último censo (próxima actualización
    # basada en Censo 2024; sin modificación para la elección de noviembre 2025).
     1: 3,   # Arica, Camarones, Putre, General Lagos
     2: 3,   # Iquique, Alto Hospicio, Huara, Camiña, Colchane, Pica, Pozo Almonte
     3: 5,   # Tocopilla, Calama, Antofagasta, Mejillones, Taltal y otras
     4: 5,   # Chañaral, Copiapó, Vallenar y otras (Atacama)
     5: 7,   # La Serena, Coquimbo, Ovalle, Illapel y otras (Coquimbo)
     6: 8,   # Quillota, Quilpué, Los Andes, San Felipe y otras (interior V región)
     7: 8,   # Valparaíso, Viña del Mar, San Antonio y otras (litoral V región)
     8: 8,   # Maipú, Pudahuel, Quilicura, Colina y otras (RM poniente-norte)
     9: 7,   # Conchalí, Renca, Recoleta, Independencia y otras (RM norte)
    10: 8,   # Providencia, Santiago, Ñuñoa, Macul y otras (RM centro)
    11: 6,   # Las Condes, Vitacura, Lo Barnechea, La Reina, Peñalolén (RM oriente)
    12: 7,   # La Florida, Puente Alto, La Pintana y otras (RM sur-oriente)
    13: 5,   # El Bosque, La Cisterna, San Miguel, Lo Espejo y otras (RM sur)
    14: 6,   # San Bernardo, Melipilla, Talagante, Buin y otras (RM sur-poniente)
    15: 5,   # Rancagua, Rengo, Machalí y otras (O'Higgins norte)
    16: 4,   # San Fernando, Pichilemu, Santa Cruz y otras (O'Higgins sur)
    17: 7,   # Curicó, Talca, Constitución y otras (Maule norte)
    18: 4,   # Linares, Parral, Cauquenes y otras (Maule sur)
    19: 5,   # Chillán, Yumbel, Bulnes y otras (Ñuble)
    20: 8,   # Concepción, Talcahuano, Coronel y otras (Biobío costa)
    21: 5,   # Lota, Arauco, Los Ángeles y otras (Biobío interior)
    22: 4,   # Angol, Traiguén, Victoria y otras (Araucanía norte)
    23: 7,   # Temuco, Villarrica, Pucón y otras (Araucanía sur)
    24: 5,   # Valdivia, La Unión, Panguipulli y otras (Los Ríos)
    25: 4,   # Osorno, Puerto Varas y otras (Los Lagos norte)
    26: 5,   # Puerto Montt, Castro, Ancud, Chiloé y otras (Los Lagos sur)
    27: 3,   # Coihaique y otras (Aysén)
    28: 3,   # Punta Arenas y otras (Magallanes)
}
assert sum(MAGNITUDES_LEGALES_LEY20840.values()) == 155

# Alias histórico: las magnitudes de Ley 20.840 no fueron modificadas en
# las elecciones de 2017, 2021 ni 2025. Son igualmente válidas para 2026.
# Art. 179 bis establece revisión cada 10 años con el último censo disponible;
# SERVEL aún no ha emitido modificación basada en el Censo 2024.
# Usar MAGNITUDES_LEGALES_LEY20840 en código nuevo; este alias existe solo
# para compatibilidad con scripts que lo referencian por año de elección.
MAGNITUDES_LEGALES_2021 = MAGNITUDES_LEGALES_LEY20840

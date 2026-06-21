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
        Usado para calcular magnitudes de escaño.
    total_seats, min_seats, max_seats : int
        Parámetros para assign_seat_magnitudes().
    threshold : float
        Umbral mínimo de votos para D'Hondt.
    unit_col, partido_col, votos_col : str
        Nombres de columnas en votes_df.

    Returns
    -------
    dict con claves:
        gallagher, loosemore_hanby, rae,
        enp_votos, enp_escanos,
        escanos_mayor_partido (int),
        n_partidos_con_escanos (int).
    """
    # Población por circunscripción
    pop_map = pop_by_unit.to_dict()
    pop_by_d = pd.Series(
        {d: sum(pop_map.get(u, 0) for u, dd in assignment.items() if dd == d)
         for d in set(assignment.values())}
    )

    magnitudes  = assign_seat_magnitudes(pop_by_d, total_seats, min_seats, max_seats)
    votes_dist  = aggregate_votes(votes_df, assignment, unit_col, partido_col, votos_col)
    results     = run_electoral_plan(votes_dist, magnitudes, threshold)
    v_sh, s_sh  = national_shares(results)

    escanos_por_partido = results.groupby("partido")["escanos"].sum()

    return {
        "gallagher":              round(gallagher_index(v_sh, s_sh), 4),
        "loosemore_hanby":        round(loosemore_hanby(v_sh, s_sh), 4),
        "rae":                    round(rae_index(v_sh, s_sh), 4),
        "enp_votos":              round(effective_number_of_parties(v_sh), 4),
        "enp_escanos":            round(effective_number_of_parties(s_sh), 4),
        "escanos_mayor_partido":  int(escanos_por_partido.max()),
        "n_partidos_con_escanos": int((escanos_por_partido > 0).sum()),
    }


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

"""
electoral.dhondt
==================
Algoritmo D'Hondt (uni y binivel/pactos) y ejecución de un plan electoral
completo a partir de votos agregados por circunscripción.
"""

from __future__ import annotations

import pandas as pd

from chiledist.domain.utils import normalize_party_name


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


def dhondt_con_tope(
    votes: dict[str, int | float],
    seats: int,
    max_seats: dict[str, int],
    threshold: float = 0.0,
) -> dict[str, int]:
    """
    D'Hondt con tope de escaños por partido/lista.

    Igual que dhondt(), pero un partido nunca recibe más escaños que
    los indicados en `max_seats` — el excedente que le correspondería
    por cociente D'Hondt pasa al partido con el siguiente cociente más
    alto que aún tenga cupo disponible. Uso típico: `max_seats` =
    número de candidatos inscritos por partido en la lista, para que
    un partido no "gane" un escaño que no tiene a quién asignarle (ver
    dhondt_binivel_cl()).

    Parameters
    ----------
    votes : dict {partido: n_votos}
    seats : int
    max_seats : dict {partido: tope_de_escaños}
        Un partido de `votes` sin entrada aquí se trata como sin tope
        (equivalente a dhondt() para ese partido).
    threshold : float

    Returns
    -------
    dict {partido: escaños_obtenidos}

    Examples
    --------
    >>> dhondt_con_tope({"A": 100, "B": 20, "C": 15}, seats=3, max_seats={"A": 1})
    {'A': 1, 'B': 1, 'C': 1}
    >>> dhondt({"A": 100, "B": 20, "C": 15}, seats=3)  # sin tope, A se lleva todo
    {'A': 3, 'B': 0, 'C': 0}
    """
    if seats <= 0:
        return {p: 0 for p in votes}

    votes = {p: max(0, v) for p, v in votes.items()}
    total = sum(votes.values())

    if total == 0:
        return {p: 0 for p in votes}

    eligible = {p: v for p, v in votes.items() if v / total >= threshold}
    if not eligible:
        return {p: 0 for p in votes}

    seat_counts = {p: 0 for p in eligible}
    caps = {p: max_seats.get(p, seats) for p in eligible}

    for _ in range(seats):
        # Solo compiten los partidos que todavía no llegaron a su tope.
        candidates = {p: v for p, v in eligible.items() if seat_counts[p] < caps[p]}
        if not candidates:
            break
        best = max(
            candidates,
            key=lambda p: (candidates[p] / (seat_counts[p] + 1), candidates[p], p),
        )
        seat_counts[best] += 1

    result = {p: 0 for p in votes}
    result.update(seat_counts)
    return result


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

    Limitación verificada (agosto 2026, ver VALIDATION_REPORT.md §3):
    a esta aproximación le falta un tope de candidatos disponibles por
    partido — un partido no puede ganar más escaños dentro de su pacto
    que candidatos registró, pero el Nivel 2 actual no lo aplica. Causa
    raíz confirmada de 3 de los 28 distritos que no validan contra las
    proclamaciones oficiales TRICEL 2025 (`scripts/validar_tricel.py`):
    reproducido exactamente (7/7 pactos en disputa) con un D'Hondt de
    partidos con tope `min(D'Hondt, n_candidatos_del_partido)`,
    redistribuyendo el excedente a los siguientes cocientes más altos.
    No implementado — requeriría un parámetro opcional
    `candidatos_por_partido: dict[str, int]` y que todos los llamadores
    (`run_electoral_plan_binivel()`, `run_electoral_ensemble()`,
    `validate_election()`) puedan proveerlo.

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

    # Normalizar las claves de pacto_map (minúsculas, sin tildes) para que el
    # lookup no dependa de si la fuente de votos usa MAYÚSCULAS SIN TILDES
    # (típico de SERVEL, ej. "EVOLUCION POLITICA") o formato título con
    # tildes (típico de un pacto_map curado a mano, ej. "Evolución Política")
    # — sin esto, un mismatch de mayúsculas/tildes hace que pacto_map.get()
    # nunca encuentre la clave y cada partido termine en su propio pacto de
    # tamaño 1, degradando el binivel a uninivel en silencio.
    pacto_map_norm = {normalize_party_name(k): v for k, v in pacto_map.items()}

    # Agrupar votos por pacto
    pacto_votes: dict[str, float] = {}
    pacto_to_parties: dict[str, dict[str, float]] = {}
    for partido, votos in votos_por_partido.items():
        pacto = pacto_map_norm.get(normalize_party_name(partido), partido)
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


def dhondt_binivel_cl(
    votos_por_partido: "dict[str, int | float]",
    pacto_map: "dict[str, str]",
    seats: int,
    candidatos_por_partido: "dict[str, int]",
    threshold: float = 0.0,
) -> "dict[str, int]":
    """
    D'Hondt binivel chileno con tope de candidatos disponibles por partido.

    Variante de dhondt_binivel() que corrige una limitación de esa
    función: el Nivel 2 (reparto intra-pacto entre partidos) puede
    asignarle a un partido más escaños que candidatos tiene inscritos
    en esa lista — imposible en la realidad, porque no hay una persona
    física para ocupar el escaño sobrante; ese escaño pasa al partido
    con el siguiente cociente más alto que sí tenga candidato
    disponible.

    Por qué es una función separada y no un flag de dhondt_binivel()
    ------------------------------------------------------------------
    No se modificó dhondt_binivel() in-place — sigue disponible tal
    cual para comparación metodológica y para escenarios sin lista de
    candidatos real (dhondt_binivel() opera solo sobre votos agregados
    por partido; esta función además requiere `candidatos_por_partido`,
    dato que no existe para un plan de redistritaje sintético/ensemble
    hipotético, solo tiene sentido al reproducir una elección real con
    candidatos ya inscritos).

    ¿Es esto una particularidad de la Ley 18.700, o del D'Hondt binivel
    en general? Verificado, no asumido (agosto 2026): no se encontró un
    texto del art. 121 de la Ley 18.700 que codifique esta regla como
    exclusiva de Chile — la Biblioteca del Congreso Nacional no fue
    accesible para verificación directa en el entorno de esta sesión, y
    las copias de la ley disponibles por otras vías eran versiones
    anteriores a la reforma de 2015 (sin D'Hondt). La evidencia más
    fuerte disponible es el cálculo D'Hondt oficial de TRICEL (hoja
    DETERMINACION de cada TRICEL_2025/Distrito-XX.xlsx — el cálculo del
    organismo, no una interpretación de terceros): reproducido
    exactamente (7/7 pactos en disputa de Distrito 3, 5 y 19, ver
    VALIDATION_REPORT.md §3) aplicando este tope. Razonamiento general:
    un partido no puede elegir más personas que las que postuló — esto
    es una necesidad lógica de cualquier D'Hondt binivel aplicado sobre
    listas de candidatos reales, no exclusiva de Chile; simplemente se
    manifiesta pocas veces porque la mayoría de los partidos postulan
    suficientes candidatos. dhondt_binivel() nunca estuvo "mal" como
    método abstracto de votos-por-partido — está incompleto solo
    cuando se le pide reproducir una elección real con listas de
    candidatos conocidas y limitadas, que es exactamente el caso de
    scripts/validar_tricel.py.

    Nivel 1 (pactos → escaños): igual que dhondt_binivel(), sin tope —
        un pacto no tiene "candidatos propios", son sus partidos
        miembros los que los tienen.
    Nivel 2 (partidos dentro de pacto): dhondt_con_tope() con
        max_seats = candidatos_por_partido.

    Parameters
    ----------
    votos_por_partido : dict {partido: n_votos}
    pacto_map : dict {partido: pacto}
    seats : int
    candidatos_por_partido : dict {partido: n_candidatos_inscritos}
        Requerido — sin este dato no hay tope que aplicar, y esta
        función existe específicamente para aplicarlo (usar
        dhondt_binivel() si no se tiene). Ver
        chiledist.domain.data.tricel.import_candidate_counts() como
        fuente verificada para datos reales de la elección 2025 — NO
        derivar esto de chiledist.domain.data.servel.import_candidates()
        ni de servel_2025_candidatos.csv, fuentes con conteo de
        candidatos no confiable (deuda técnica documentada en
        VALIDATION_REPORT.md §3: 1.378 filas agrupadas vs 1.096
        candidatos reales). Un partido de `votos_por_partido` sin
        entrada aquí se trata como sin tope (ver dhondt_con_tope()) —
        no es un error, pero anula el propósito de esta función para
        ese partido específico.
    threshold : float

    Returns
    -------
    dict {partido: escaños_obtenidos}

    Ver también
    -----------
    dhondt_binivel() — método D'Hondt binivel genérico, sin tope de
        candidatos, preservado sin cambios.
    VALIDATION_REPORT.md §3, §5 — evidencia completa de la
        verificación contra TRICEL_2025 y el camino a EXACT_REPRODUCTION.

    Examples
    --------
    >>> votos = {"Liberal": 74910, "PPD": 13687, "PC": 10977, "Radical": 11973, "PDC": 1773, "FA": 8518}
    >>> pactos = {p: "UNIDAD POR CHILE" for p in votos}
    >>> candidatos = {p: 1 for p in votos}
    >>> dhondt_binivel_cl(votos, pactos, seats=3, candidatos_por_partido=candidatos)
    {'Liberal': 1, 'PPD': 1, 'PC': 0, 'Radical': 1, 'PDC': 0, 'FA': 0}
    """
    if seats <= 0:
        return {p: 0 for p in votos_por_partido}

    votos_por_partido = {p: max(0, v) for p, v in votos_por_partido.items()}

    # Ver dhondt_binivel() para la explicación de esta normalización.
    pacto_map_norm = {normalize_party_name(k): v for k, v in pacto_map.items()}

    pacto_votes: dict[str, float] = {}
    pacto_to_parties: dict[str, dict[str, float]] = {}
    for partido, votos in votos_por_partido.items():
        pacto = pacto_map_norm.get(normalize_party_name(partido), partido)
        pacto_votes[pacto]                          = pacto_votes.get(pacto, 0) + votos
        pacto_to_parties.setdefault(pacto, {})[partido] = votos

    total = sum(pacto_votes.values())
    if total == 0:
        return {p: 0 for p in votos_por_partido}

    # Nivel 1: D'Hondt entre pactos, sin tope (un pacto no tiene "candidatos propios")
    pacto_seats = dhondt(pacto_votes, seats, threshold)

    # Nivel 2: D'Hondt con tope de candidatos disponibles dentro de cada pacto
    result = {p: 0 for p in votos_por_partido}
    for pacto, n in pacto_seats.items():
        if n == 0:
            continue
        parties = pacto_to_parties.get(pacto, {})
        if not parties:
            continue
        max_seats_pacto = {p: candidatos_por_partido.get(p, n) for p in parties}
        for partido, s in dhondt_con_tope(parties, n, max_seats_pacto).items():
            result[partido] = s

    return result


def run_electoral_plan_binivel(
    votes_by_district: pd.DataFrame,
    seat_magnitudes: pd.Series,
    pacto_col: str = "pacto",
    partido_col: str = "partido",
    votos_col: str = "votos",
    threshold: float = 0.0,
    candidatos_por_partido: "pd.DataFrame | None" = None,
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
    candidatos_por_partido : pd.DataFrame, opcional
        Columnas: district, partido_col, "n_candidatos". Si se provee,
        usa dhondt_binivel_cl() (tope de candidatos disponibles por
        partido dentro de cada pacto) en vez de dhondt_binivel() —
        explícito, no es un cambio de comportamiento por defecto: si no
        se pasa (default None), el resultado es idéntico al de antes de
        que existiera este parámetro. Ver dhondt_binivel_cl() para por
        qué existe como variante separada y VALIDATION_REPORT.md §3
        para la evidencia de por qué es necesaria al reproducir un
        resultado electoral real (no al simular un ensemble sin
        candidatos reales).

    Returns
    -------
    pd.DataFrame con columnas:
        district, pacto, partido, votos, escanos,
        escanos_pacto, votos_pct, escanos_pct.
    """
    rows = []

    candidatos_lookup: dict = {}
    if candidatos_por_partido is not None:
        for district, grp in candidatos_por_partido.groupby("district"):
            candidatos_lookup[district] = dict(zip(grp[partido_col], grp["n_candidatos"]))

    for district, grp in votes_by_district.groupby("district"):
        seats = int(seat_magnitudes.get(district, 0))
        if seats == 0:
            continue

        # groupby().sum/first en lugar de dict(zip) para manejar correctamente
        # filas duplicadas (mismo partido en el mismo distrito).
        votos_grp  = grp.groupby(partido_col, sort=False)[votos_col].sum()
        votos_dict = votos_grp.to_dict()
        pacto_dict = grp.groupby(partido_col, sort=False)[pacto_col].first().to_dict()

        if candidatos_por_partido is not None:
            escanos = dhondt_binivel_cl(
                votos_dict, pacto_dict, seats,
                candidatos_lookup.get(district, {}), threshold,
            )
        else:
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

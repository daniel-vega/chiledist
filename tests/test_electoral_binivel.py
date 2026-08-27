"""
tests/test_electoral_binivel.py
================================
Tests que demuestran la diferencia entre D'Hondt uninivel y binivel,
y que plan_electoral_metrics refleja el sistema electoral chileno real
cuando se provee pacto_map.

El caso de referencia en todos los tests:

    Distrito único, 4 escaños.
    Pacto Apruebo (A):  PS=15%, PPD=10% → total 25%
    Pacto ChileVamos (B): RN=40%, UDI=35% → total 75%

Resultados esperados:
    Uninivel → RN=2, PS=1, PPD=0 ó UDI=2... varía, pero PS queda fuera.
    Binivel  → Apruebo=1 escaño (PS), ChileVamos=3 (RN=2, UDI=1)
               o Apruebo=2 (PS=1,PPD=1), ChileVamos=2 (RN=1,UDI=1) dependiendo
               del cociente de pactos.

El punto central: PS siempre GANA un escaño en binivel (protegido por el pacto)
y siempre LO PIERDE en uninivel (no puede competir directamente con RN/UDI).
"""

import pytest
import numpy as np
import pandas as pd

from chiledist.domain.utils import normalize_party_name
from chiledist.engines.allocation import (
    dhondt,
    dhondt_binivel,
    run_electoral_plan,
    run_electoral_plan_binivel,
    plan_electoral_metrics,
    national_shares,
)
from chiledist.evaluation import (
    gallagher_index,
    seat_bonus,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures del caso de referencia
# ─────────────────────────────────────────────────────────────────────────────

VOTOS_REF = {"PS": 15, "PPD": 10, "RN": 40, "UDI": 35}
PACTOS_REF = {"PS": "Apruebo", "PPD": "Apruebo",
              "RN": "ChileVamos", "UDI": "ChileVamos"}
SEATS_REF = 4


# ─────────────────────────────────────────────────────────────────────────────
# Tests: dhondt vs dhondt_binivel
# ─────────────────────────────────────────────────────────────────────────────

class TestDhondtBinivelDiverge:
    """El escenario de referencia DEBE producir resultados distintos."""

    def test_ps_obtiene_escano_solo_en_binivel(self):
        """PS tiene 15% de votos. Sin pacto no gana nada; con pacto gana 1."""
        uni = dhondt(VOTOS_REF, SEATS_REF)
        bi  = dhondt_binivel(VOTOS_REF, PACTOS_REF, SEATS_REF)

        assert uni["PS"] == 0, "uninivel: PS sin votos suficientes para ganar solo"
        assert bi["PS"] == 1, "binivel: PS protegido por el pacto Apruebo"

    def test_udi_pierde_un_escano_en_binivel(self):
        """UDI tiene 35% de votos pero el pacto B sólo puede ganar 3/4 escaños."""
        uni = dhondt(VOTOS_REF, SEATS_REF)
        bi  = dhondt_binivel(VOTOS_REF, PACTOS_REF, SEATS_REF)

        assert uni["UDI"] == 2, "uninivel: UDI gana 2 escaños directo"
        assert bi["UDI"] == 1,  "binivel: UDI comparte pacto con RN, solo 1"

    def test_total_escanos_conservado(self):
        """La suma total de escaños debe ser SEATS_REF en ambos métodos."""
        uni = dhondt(VOTOS_REF, SEATS_REF)
        bi  = dhondt_binivel(VOTOS_REF, PACTOS_REF, SEATS_REF)

        assert sum(uni.values()) == SEATS_REF
        assert sum(bi.values())  == SEATS_REF

    def test_partidos_en_output_coinciden_con_input(self):
        """Todos los partidos del input deben aparecer en el output."""
        bi = dhondt_binivel(VOTOS_REF, PACTOS_REF, SEATS_REF)
        assert set(bi.keys()) == set(VOTOS_REF.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Tests: run_electoral_plan vs run_electoral_plan_binivel
# ─────────────────────────────────────────────────────────────────────────────

def _make_votes_df(votos: dict, district: int = 1) -> pd.DataFrame:
    return pd.DataFrame([
        {"district": district, "partido": p, "votos": v}
        for p, v in votos.items()
    ])


def _make_votes_df_binivel(votos: dict, pactos: dict, district: int = 1) -> pd.DataFrame:
    rows = []
    for p, v in votos.items():
        rows.append({
            "district": district,
            "pacto":    pactos.get(p, p),
            "partido":  p,
            "votos":    v,
        })
    return pd.DataFrame(rows)


class TestRunElectoralPlanBinivel:

    def test_escanos_totales_conservados(self):
        mags = pd.Series({1: SEATS_REF})
        df   = _make_votes_df_binivel(VOTOS_REF, PACTOS_REF)
        res  = run_electoral_plan_binivel(df, mags)
        assert res["escanos"].sum() == SEATS_REF

    def test_diferencia_con_uninivel(self):
        mags   = pd.Series({1: SEATS_REF})
        df_uni = _make_votes_df(VOTOS_REF)
        df_bi  = _make_votes_df_binivel(VOTOS_REF, PACTOS_REF)

        res_uni = run_electoral_plan(df_uni, mags)
        res_bi  = run_electoral_plan_binivel(df_bi, mags)

        uni_ps = res_uni[res_uni["partido"] == "PS"]["escanos"].sum()
        bi_ps  = res_bi[res_bi["partido"] == "PS"]["escanos"].sum()

        assert uni_ps == 0, "uninivel: PS no gana escaños"
        assert bi_ps  == 1, "binivel: PS gana 1 escaño vía pacto"

    def test_gallagher_menor_en_binivel(self):
        """Binivel es más proporcional (menor Gallagher) en este escenario."""
        mags   = pd.Series({1: SEATS_REF})
        df_uni = _make_votes_df(VOTOS_REF)
        df_bi  = _make_votes_df_binivel(VOTOS_REF, PACTOS_REF)

        v_sh_uni, s_sh_uni = national_shares(run_electoral_plan(df_uni, mags))
        v_sh_bi,  s_sh_bi  = national_shares(run_electoral_plan_binivel(df_bi, mags))

        g_uni = gallagher_index(v_sh_uni, s_sh_uni)
        g_bi  = gallagher_index(v_sh_bi,  s_sh_bi)

        assert g_bi < g_uni, (
            f"Binivel debe ser más proporcional: g_bi={g_bi:.4f} debe ser "
            f"menor que g_uni={g_uni:.4f}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: plan_electoral_metrics con pacto_map
# ─────────────────────────────────────────────────────────────────────────────

def _make_input_for_plan_metrics(votos: dict, pactos: dict = None):
    """Construye los inputs mínimos para plan_electoral_metrics."""
    assignment = {"C1": 1}
    pop        = pd.Series({"C1": 2000})

    rows = [{"CUT": "C1", "partido": p, "votos": v} for p, v in votos.items()]
    votes_df = pd.DataFrame(rows)
    return assignment, votes_df, pop


class TestPlanElectoralMetricsBinivel:

    def test_modo_uninivel_por_defecto(self):
        """Sin pacto_map, el modo debe ser 'uninivel'."""
        asgn, vdf, pop = _make_input_for_plan_metrics(VOTOS_REF)
        m = plan_electoral_metrics(asgn, vdf, pop,
                                   total_seats=SEATS_REF,
                                   min_seats=SEATS_REF,
                                   max_seats=SEATS_REF)
        assert m["modo_dhondt"] == "uninivel"

    def test_modo_binivel_con_pacto_map(self):
        """Con pacto_map, el modo debe ser 'binivel'."""
        asgn, vdf, pop = _make_input_for_plan_metrics(VOTOS_REF)
        m = plan_electoral_metrics(asgn, vdf, pop,
                                   total_seats=SEATS_REF,
                                   min_seats=SEATS_REF,
                                   max_seats=SEATS_REF,
                                   pacto_map=PACTOS_REF)
        assert m["modo_dhondt"] == "binivel"

    def test_gallagher_difiere_entre_modos(self):
        """Gallagher debe diferir entre uninivel y binivel en el caso asimétrico."""
        asgn, vdf, pop = _make_input_for_plan_metrics(VOTOS_REF)

        m_uni = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF)
        m_bi  = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF,
                                       pacto_map=PACTOS_REF)

        assert m_uni["gallagher"] != m_bi["gallagher"], (
            "Gallagher debe diferir entre uninivel y binivel con pactos asimétricos"
        )
        assert m_bi["gallagher"] < m_uni["gallagher"], (
            f"Binivel más proporcional: g_bi={m_bi['gallagher']:.4f} "
            f"debe ser < g_uni={m_uni['gallagher']:.4f}"
        )

    def test_n_partidos_con_escanos_difiere_entre_modos(self):
        """Binivel da escaños a PS (partido protegido); uninivel no."""
        asgn, vdf, pop = _make_input_for_plan_metrics(VOTOS_REF)

        m_uni = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF)
        m_bi  = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF,
                                       pacto_map=PACTOS_REF)

        assert m_uni["n_partidos_con_escanos"] < m_bi["n_partidos_con_escanos"], (
            "Binivel debe incluir más partidos con escaños que uninivel"
        )
        # Concretamente: uninivel=2 (RN, PS), binivel=3 (PS, RN, UDI)
        assert m_bi["n_partidos_con_escanos"] - m_uni["n_partidos_con_escanos"] >= 1

    def test_seat_bonus_max_menor_en_binivel(self):
        """La prima máxima de escaños es menor en binivel (distribución más equitativa)."""
        asgn, vdf, pop = _make_input_for_plan_metrics(VOTOS_REF)

        m_uni = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF)
        m_bi  = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=SEATS_REF,
                                       min_seats=SEATS_REF,
                                       max_seats=SEATS_REF,
                                       pacto_map=PACTOS_REF)

        assert m_bi["seat_bonus_max"] < m_uni["seat_bonus_max"], (
            f"seat_bonus_max: binivel={m_bi['seat_bonus_max']:.2f} "
            f"debe ser < uninivel={m_uni['seat_bonus_max']:.2f}"
        )

    def test_escenario_simetrico_coincide(self):
        """
        Cuando los pactos tienen igual número de partidos y votos balanceados
        entre partidos del mismo pacto, uninivel y binivel deben producir
        el mismo Gallagher.

        PS=PPD=RN=UDI=25% → 4 partidos equidistribuidos, 2 por pacto.
        Cualquier algoritmo D'Hondt debe repartir 1 escaño a cada uno.
        """
        votos_sym = {"PS": 25, "PPD": 25, "RN": 25, "UDI": 25}
        asgn, vdf, pop = _make_input_for_plan_metrics(votos_sym)

        m_uni = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=4,
                                       min_seats=4,
                                       max_seats=4)
        m_bi  = plan_electoral_metrics(asgn, vdf, pop,
                                       total_seats=4,
                                       min_seats=4,
                                       max_seats=4,
                                       pacto_map=PACTOS_REF)

        assert m_uni["gallagher"] == pytest.approx(m_bi["gallagher"], abs=0.01), (
            "Con votos perfectamente iguales, gallagher debe coincidir"
        )

    def test_partido_sin_pacto_map_actua_como_pacto_independiente(self):
        """
        Un partido ausente de pacto_map actúa como su propio pacto.
        Esto preserva el comportamiento de dhondt_binivel.
        """
        votos_ind = {"PS": 15, "PPD": 10, "RN": 40, "UDI": 35}
        pacto_parcial = {"PS": "Apruebo", "PPD": "Apruebo", "RN": "ChileVamos"}
        # UDI no está en pacto_parcial → actúa como pacto "UDI" solo

        asgn, vdf, pop = _make_input_for_plan_metrics(votos_ind)
        m = plan_electoral_metrics(asgn, vdf, pop,
                                   total_seats=SEATS_REF,
                                   min_seats=SEATS_REF,
                                   max_seats=SEATS_REF,
                                   pacto_map=pacto_parcial)

        # Debe ejecutar sin excepción
        assert m["modo_dhondt"] == "binivel"
        assert isinstance(m["gallagher"], float)


# ─────────────────────────────────────────────────────────────────────────────
# normalize_party_name / dhondt_binivel case-and-accent tolerance
# ─────────────────────────────────────────────────────────────────────────────
#
# Bug real (detectado por scripts/validar_datos_externos.py): SERVEL entrega
# nombres de partido en MAYÚSCULAS SIN TILDES ("EVOLUCION POLITICA"), mientras
# un pacto_map curado a mano (ej. datos/pacto_map_2025.json) usa formato
# título con tildes ("Evolución Política"). Antes del fix, el lookup
# case/tilde-sensible en dhondt_binivel() nunca encontraba la clave, así que
# cada partido terminaba en su propio pacto de tamaño 1 — degradando el
# binivel a uninivel en silencio para prácticamente todos los partidos.

class TestNormalizePartyName:

    def test_uppercase_no_accents_and_titlecase_with_accents_are_equal(self):
        assert normalize_party_name("Evolución Política") == normalize_party_name(
            "EVOLUCION POLITICA"
        )

    def test_normalized_form_is_lowercase_no_accents(self):
        assert normalize_party_name("Evolución Política") == "evolucion politica"
        assert normalize_party_name("EVOLUCION POLITICA") == "evolucion politica"

    def test_strips_surrounding_whitespace(self):
        assert normalize_party_name("  Partido Comunista de Chile  ") == \
            "partido comunista de chile"

    def test_already_normalized_input_is_unchanged(self):
        assert normalize_party_name("union democratica") == "union democratica"

    def test_distinct_parties_remain_distinct_after_normalization(self):
        """Normalizing must not accidentally collapse different parties."""
        assert normalize_party_name("UDI") != normalize_party_name("RN")


class TestDhondtBinivelCaseAccentTolerance:

    def test_pacto_map_matches_regardless_of_case_and_accents(self):
        """
        pacto_map keyed with proper-case/accented names must still group
        SERVEL-style UPPERCASE/unaccented votes into the same pacto.
        """
        votos = {
            "UDI": 12000,
            "RENOVACION NACIONAL": 11000,
            "EVOLUCION POLITICA": 10000,        # UDI+RN+EVOP share one pacto
            "PARTIDO SOCIALISTA DE CHILE": 20000,  # solo, no shared pacto
        }
        pacto_map = {
            "UDI": "Chile Grande y Unido",
            "Renovación Nacional": "Chile Grande y Unido",
            "Evolución Política": "Chile Grande y Unido",
            "Partido Socialista de Chile": "Unidad por Chile",
        }

        resultado = dhondt_binivel(votos, pacto_map, seats=4)

        # Sin la normalización, cada partido del pacto compite solo y el
        # partido en solitario (más votos individuales) se queda con 2
        # escaños en vez de 1 — ver test_case_mismatch_reproduces_the_bug.
        assert resultado == {
            "UDI": 1,
            "RENOVACION NACIONAL": 1,
            "EVOLUCION POLITICA": 1,
            "PARTIDO SOCIALISTA DE CHILE": 1,
        }

    def test_case_mismatch_reproduces_the_bug_when_unnormalized(self):
        """
        Documents the failure mode this fix closes: same inputs as above,
        but simulating "no pacto_map matched" (as an unnormalized,
        case-sensitive lookup would see it) by passing an empty map —
        every party competes alone, and the solo party wins an extra seat
        at the expense of the smallest member of what should have been a
        shared pacto.
        """
        votos = {
            "UDI": 12000,
            "RENOVACION NACIONAL": 11000,
            "EVOLUCION POLITICA": 10000,
            "PARTIDO SOCIALISTA DE CHILE": 20000,
        }
        resultado_sin_agrupar = dhondt_binivel(votos, {}, seats=4)

        assert resultado_sin_agrupar == {
            "UDI": 1,
            "RENOVACION NACIONAL": 1,
            "EVOLUCION POLITICA": 0,
            "PARTIDO SOCIALISTA DE CHILE": 2,
        }
        assert resultado_sin_agrupar != {
            "UDI": 1,
            "RENOVACION NACIONAL": 1,
            "EVOLUCION POLITICA": 1,
            "PARTIDO SOCIALISTA DE CHILE": 1,
        }

    def test_real_pacto_map_2025_covers_all_servel_parties(self):
        """
        End-to-end regression against the real files in datos/, if present:
        every party in servel_2025_por_cut.csv must resolve to a real pacto
        (not fall back to being its own pacto) once names are normalized.
        """
        import json
        import os

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        servel_path = os.path.join(root, "datos", "servel_2025_por_cut.csv")
        pacto_path  = os.path.join(root, "datos", "pacto_map_2025.json")

        if not (os.path.exists(servel_path) and os.path.exists(pacto_path)):
            pytest.skip("datos/servel_2025_por_cut.csv or "
                        "datos/pacto_map_2025.json not present in this checkout")

        df = pd.read_csv(servel_path)
        with open(pacto_path, encoding="utf-8") as f:
            pacto_map = json.load(f)

        partidos = sorted(df["partido"].dropna().unique())
        pacto_map_norm = {normalize_party_name(k) for k in pacto_map}
        sin_pacto = [p for p in partidos
                     if normalize_party_name(p) not in pacto_map_norm]

        assert sin_pacto == [], (
            f"{len(sin_pacto)} partido(s) de servel_2025_por_cut.csv no "
            f"resuelven a un pacto ni siquiera normalizando: {sin_pacto}"
        )

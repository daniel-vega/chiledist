"""
tests/test_dhondt_binivel_cl.py
=================================
Tests de dhondt_con_tope() y dhondt_binivel_cl() — variante chilena del
D'Hondt binivel con tope de candidatos disponibles por partido en el
reparto intra-pacto (ver VALIDATION_REPORT.md §3 y el docstring de
dhondt_binivel_cl()).

Los datos de TestPactosRealesD3D5D19 son los 7 pactos en disputa entre
partidos de Distrito 3, 5 y 19 en la elección de Diputados 2025 —
votos, candidatos inscritos y resultado oficial leídos directamente de
la hoja DETERMINACION de cada TRICEL_2025/Distrito-XX.xlsx (el cálculo
D'Hondt oficial del organismo, agosto 2026). Son la evidencia empírica
que motivó dhondt_binivel_cl(): reproducirlos exactamente es lo que
prueba que el tope de candidatos es la causa raíz correcta, no una
hipótesis — si alguien modifica dhondt_con_tope()/dhondt_binivel_cl()
de forma que alguno de estos 7 casos deje de coincidir con el
resultado oficial, es una regresión real, no un falso positivo de test.
"""

import pandas as pd
import pytest

from chiledist.engines.allocation import (
    dhondt,
    dhondt_con_tope,
    dhondt_binivel,
    dhondt_binivel_cl,
    run_electoral_plan_binivel,
)
from chiledist.validation import validate_election


# ─────────────────────────────────────────────────────────────────────────────
# dhondt_con_tope() — primitivo genérico
# ─────────────────────────────────────────────────────────────────────────────

class TestDhondtConTope:
    def test_sin_tope_activo_igual_a_dhondt(self):
        """Si ningún tope se alcanza, el resultado debe ser idéntico a dhondt()."""
        votes = {"A": 100, "B": 80, "C": 30}
        assert dhondt_con_tope(votes, seats=3, max_seats={"A": 5, "B": 5, "C": 5}) \
            == dhondt(votes, seats=3)

    def test_tope_redistribuye_al_siguiente_cociente(self):
        """Ejemplo del docstring: A domina en votos pero solo tiene 1 candidato."""
        votes = {"A": 100, "B": 20, "C": 15}
        assert dhondt_con_tope(votes, seats=3, max_seats={"A": 1}) == {
            "A": 1, "B": 1, "C": 1,
        }

    def test_partido_sin_entrada_en_max_seats_no_tiene_tope(self):
        votes = {"A": 100, "B": 20}
        # A sin entrada en max_seats -> se comporta como dhondt() para A.
        assert dhondt_con_tope(votes, seats=2, max_seats={"B": 5}) == dhondt(votes, seats=2)

    def test_zero_seats(self):
        assert dhondt_con_tope({"A": 10}, seats=0, max_seats={}) == {"A": 0}

    def test_total_escanos_asignados_nunca_excede_seats(self):
        votes = {"A": 100, "B": 20, "C": 15}
        result = dhondt_con_tope(votes, seats=3, max_seats={"A": 1, "B": 1, "C": 1})
        # 3 escaños, 3 partidos con tope 1 cada uno -> exactamente 1 cada uno.
        assert result == {"A": 1, "B": 1, "C": 1}
        assert sum(result.values()) == 3

    def test_topes_insuficientes_deja_escanos_sin_asignar(self):
        """Si la suma de topes es menor que seats, no se puede asignar todo."""
        votes = {"A": 100, "B": 20}
        result = dhondt_con_tope(votes, seats=5, max_seats={"A": 1, "B": 1})
        assert sum(result.values()) == 2


# ─────────────────────────────────────────────────────────────────────────────
# dhondt_binivel() NO cambió — guarda de regresión explícita
# ─────────────────────────────────────────────────────────────────────────────

class TestDhondtBinivelSinTopeNoCambio:
    """
    dhondt_binivel() se preserva sin cambios (ver docstring de
    dhondt_binivel_cl() para por qué). Este test falla si alguien
    "corrige" dhondt_binivel() in-place en vez de usar la función
    separada — que es exactamente lo que la salvedad de diseño de esta
    tarea pidió evitar.
    """

    def test_liberal_se_lleva_los_3_escanos_sin_tope(self):
        votos = {"Liberal": 74910, "PPD": 13687, "PC": 10977,
                 "Radical": 11973, "PDC": 1773, "FA": 8518}
        pactos = {p: "UNIDAD POR CHILE" for p in votos}
        result = dhondt_binivel(votos, pactos, seats=3)
        assert result == {"Liberal": 3, "PPD": 0, "PC": 0,
                           "Radical": 0, "PDC": 0, "FA": 0}


# ─────────────────────────────────────────────────────────────────────────────
# dhondt_binivel_cl() — los 7 pactos reales de D3/D5/D19 (TRICEL DETERMINACION)
# ─────────────────────────────────────────────────────────────────────────────

# Cada entrada: (distrito, pacto, votos_por_partido, candidatos_por_partido,
# escaños_del_pacto, resultado_oficial_TRICEL). Fuente: hoja DETERMINACION de
# TRICEL_2025/Distrito-{03,05,19}.xlsx, verificado agosto 2026.
PACTOS_REALES_D3_D5_D19 = [
    (
        3, "UNIDAD POR CHILE",
        {"PARTIDO LIBERAL DE CHILE": 74910, "PARTIDO POR LA DEMOCRACIA": 13687,
         "PARTIDO COMUNISTA DE CHILE": 10977, "PARTIDO RADICAL DE CHILE": 11973,
         "PARTIDO DEMOCRATA CRISTIANO": 1773, "FRENTE AMPLIO": 8518},
        {"PARTIDO LIBERAL DE CHILE": 1, "PARTIDO POR LA DEMOCRACIA": 1,
         "PARTIDO COMUNISTA DE CHILE": 1, "PARTIDO RADICAL DE CHILE": 1,
         "PARTIDO DEMOCRATA CRISTIANO": 1, "FRENTE AMPLIO": 1},
        3,
        {"PARTIDO LIBERAL DE CHILE": 1, "PARTIDO POR LA DEMOCRACIA": 1,
         "PARTIDO COMUNISTA DE CHILE": 0, "PARTIDO RADICAL DE CHILE": 1,
         "PARTIDO DEMOCRATA CRISTIANO": 0, "FRENTE AMPLIO": 0},
    ),
    (
        5, "UNIDAD POR CHILE",
        {"FRENTE AMPLIO": 15199, "PARTIDO SOCIALISTA DE CHILE": 95526,
         "PARTIDO COMUNISTA DE CHILE": 23333, "PARTIDO POR LA DEMOCRACIA": 9665,
         "PARTIDO RADICAL DE CHILE": 9188, "PARTIDO DEMOCRATA CRISTIANO": 9987},
        {"FRENTE AMPLIO": 1, "PARTIDO SOCIALISTA DE CHILE": 1,
         "PARTIDO COMUNISTA DE CHILE": 2, "PARTIDO POR LA DEMOCRACIA": 1,
         "PARTIDO RADICAL DE CHILE": 1, "PARTIDO DEMOCRATA CRISTIANO": 1},
        4,
        {"FRENTE AMPLIO": 1, "PARTIDO SOCIALISTA DE CHILE": 1,
         "PARTIDO COMUNISTA DE CHILE": 2, "PARTIDO POR LA DEMOCRACIA": 0,
         "PARTIDO RADICAL DE CHILE": 0, "PARTIDO DEMOCRATA CRISTIANO": 0},
    ),
    (
        5, "PARTIDO DE LA GENTE",
        {"PARTIDO DE LA GENTE": 65831}, {"PARTIDO DE LA GENTE": 7}, 1,
        {"PARTIDO DE LA GENTE": 1},
    ),
    (
        5, "CHILE GRANDE Y UNIDO",
        {"UNION DEMOCRATA INDEPENDIENTE": 37907, "RENOVACION NACIONAL": 29332,
         "EVOLUCION POLITICA": 5897, "PARTIDO DEMOCRATAS CHILE": 3764},
        {"UNION DEMOCRATA INDEPENDIENTE": 2, "RENOVACION NACIONAL": 2,
         "EVOLUCION POLITICA": 2, "PARTIDO DEMOCRATAS CHILE": 3},
        1,
        {"UNION DEMOCRATA INDEPENDIENTE": 1, "RENOVACION NACIONAL": 0,
         "EVOLUCION POLITICA": 0, "PARTIDO DEMOCRATAS CHILE": 0},
    ),
    (
        5, "CAMBIO POR CHILE",
        {"PARTIDO SOCIAL CRISTIANO": 20326, "PARTIDO NACIONAL LIBERTARIO": 31957,
         "PARTIDO REPUBLICANO DE CHILE": 25654},
        {"PARTIDO SOCIAL CRISTIANO": 4, "PARTIDO NACIONAL LIBERTARIO": 3,
         "PARTIDO REPUBLICANO DE CHILE": 2},
        1,
        {"PARTIDO SOCIAL CRISTIANO": 0, "PARTIDO NACIONAL LIBERTARIO": 1,
         "PARTIDO REPUBLICANO DE CHILE": 0},
    ),
    (
        19, "UNIDAD POR CHILE",
        {"PARTIDO DEMOCRATA CRISTIANO": 38958, "FRENTE AMPLIO": 11860,
         "PARTIDO LIBERAL DE CHILE": 2232, "PARTIDO RADICAL DE CHILE": 9552,
         "PARTIDO SOCIALISTA DE CHILE": 15857, "PARTIDO POR LA DEMOCRACIA": 3131},
        {"PARTIDO DEMOCRATA CRISTIANO": 1, "FRENTE AMPLIO": 1,
         "PARTIDO LIBERAL DE CHILE": 1, "PARTIDO RADICAL DE CHILE": 1,
         "PARTIDO SOCIALISTA DE CHILE": 4, "PARTIDO POR LA DEMOCRACIA": 1},
        2,
        {"PARTIDO DEMOCRATA CRISTIANO": 1, "FRENTE AMPLIO": 0,
         "PARTIDO LIBERAL DE CHILE": 0, "PARTIDO RADICAL DE CHILE": 0,
         "PARTIDO SOCIALISTA DE CHILE": 1, "PARTIDO POR LA DEMOCRACIA": 0},
    ),
    (
        19, "CHILE GRANDE Y UNIDO",
        {"UNION DEMOCRATA INDEPENDIENTE": 44271, "RENOVACION NACIONAL": 44679,
         "PARTIDO DEMOCRATAS CHILE": 23538},
        {"UNION DEMOCRATA INDEPENDIENTE": 2, "RENOVACION NACIONAL": 2,
         "PARTIDO DEMOCRATAS CHILE": 1},
        2,
        {"UNION DEMOCRATA INDEPENDIENTE": 1, "RENOVACION NACIONAL": 1,
         "PARTIDO DEMOCRATAS CHILE": 0},
    ),
    (
        19, "CAMBIO POR CHILE",
        {"PARTIDO SOCIAL CRISTIANO": 25563, "PARTIDO REPUBLICANO DE CHILE": 24559,
         "PARTIDO NACIONAL LIBERTARIO": 13903},
        {"PARTIDO SOCIAL CRISTIANO": 4, "PARTIDO REPUBLICANO DE CHILE": 2,
         "PARTIDO NACIONAL LIBERTARIO": 1},
        1,
        {"PARTIDO SOCIAL CRISTIANO": 1, "PARTIDO REPUBLICANO DE CHILE": 0,
         "PARTIDO NACIONAL LIBERTARIO": 0},
    ),
]


class TestPactosRealesD3D5D19:
    """
    Regresión permanente: los 7 pactos que documentó VALIDATION_REPORT.md
    §3 como evidencia de la causa raíz. dhondt_con_tope() se llama
    directamente sobre los partidos de cada pacto (no dhondt_binivel_cl()
    completo) porque cada caso ya viene aislado a un solo pacto — igual
    al Nivel 2 que dhondt_binivel_cl() ejecuta internamente.
    """

    @pytest.mark.parametrize(
        "distrito,pacto,votos,candidatos,escanos,esperado",
        PACTOS_REALES_D3_D5_D19,
        ids=[f"D{d}-{p}" for d, p, *_ in PACTOS_REALES_D3_D5_D19],
    )
    def test_reproduce_resultado_oficial_tricel(
        self, distrito, pacto, votos, candidatos, escanos, esperado
    ):
        result = dhondt_con_tope(votos, escanos, candidatos)
        assert result == esperado, (
            f"Distrito {distrito}, pacto {pacto!r}: {result} != {esperado} "
            f"(oficial TRICEL, hoja DETERMINACION)"
        )

    @pytest.mark.parametrize(
        "distrito,pacto,votos,candidatos,escanos,esperado",
        PACTOS_REALES_D3_D5_D19,
        ids=[f"D{d}-{p}" for d, p, *_ in PACTOS_REALES_D3_D5_D19],
    )
    def test_suma_escanos_asignados_igual_a_escanos_del_pacto(
        self, distrito, pacto, votos, candidatos, escanos, esperado
    ):
        result = dhondt_con_tope(votos, escanos, candidatos)
        assert sum(result.values()) == escanos

    def test_d3_unidad_por_chile_via_dhondt_binivel_cl_completo(self):
        """
        Igual que el primer caso de PACTOS_REALES_D3_D5_D19, pero
        pasando por dhondt_binivel_cl() completo (Nivel 1 + Nivel 2),
        no solo dhondt_con_tope() — confirma que el pipeline de dos
        niveles no introduce ninguna diferencia para un caso de un solo
        pacto en disputa.
        """
        votos = {"PARTIDO LIBERAL DE CHILE": 74910, "PARTIDO POR LA DEMOCRACIA": 13687,
                 "PARTIDO COMUNISTA DE CHILE": 10977, "PARTIDO RADICAL DE CHILE": 11973,
                 "PARTIDO DEMOCRATA CRISTIANO": 1773, "FRENTE AMPLIO": 8518}
        pactos = {p: "UNIDAD POR CHILE" for p in votos}
        candidatos = {"PARTIDO LIBERAL DE CHILE": 1, "PARTIDO POR LA DEMOCRACIA": 1,
                      "PARTIDO COMUNISTA DE CHILE": 1, "PARTIDO RADICAL DE CHILE": 1,
                      "PARTIDO DEMOCRATA CRISTIANO": 1, "FRENTE AMPLIO": 1}
        result = dhondt_binivel_cl(votos, pactos, seats=3, candidatos_por_partido=candidatos)
        assert result == {
            "PARTIDO LIBERAL DE CHILE": 1, "PARTIDO POR LA DEMOCRACIA": 1,
            "PARTIDO COMUNISTA DE CHILE": 0, "PARTIDO RADICAL DE CHILE": 1,
            "PARTIDO DEMOCRATA CRISTIANO": 0, "FRENTE AMPLIO": 0,
        }


# ─────────────────────────────────────────────────────────────────────────────
# run_electoral_plan_binivel() — parámetro candidatos_por_partido explícito
# ─────────────────────────────────────────────────────────────────────────────

class TestRunElectoralPlanBinivelCandidatosPorPartido:
    def test_default_none_preserva_comportamiento_anterior(self):
        """Sin candidatos_por_partido, el resultado debe ser idéntico al
        de antes de que existiera el parámetro (dhondt_binivel, sin tope)."""
        votes_by_district = pd.DataFrame([
            {"district": 1, "pacto": "P", "partido": "Liberal", "votos": 74910},
            {"district": 1, "pacto": "P", "partido": "PPD", "votos": 13687},
            {"district": 1, "pacto": "P", "partido": "PC", "votos": 10977},
        ])
        seat_magnitudes = pd.Series({1: 3})

        sin_param = run_electoral_plan_binivel(votes_by_district, seat_magnitudes)
        con_none = run_electoral_plan_binivel(
            votes_by_district, seat_magnitudes, candidatos_por_partido=None
        )
        pd.testing.assert_frame_equal(sin_param, con_none)
        # Liberal domina sin tope: se lleva los 3 escaños (dhondt_binivel puro).
        assert sin_param.set_index("partido")["escanos"].to_dict() == {
            "Liberal": 3, "PPD": 0, "PC": 0,
        }

    def test_con_candidatos_por_partido_aplica_tope(self):
        votes_by_district = pd.DataFrame([
            {"district": 1, "pacto": "P", "partido": "Liberal", "votos": 74910},
            {"district": 1, "pacto": "P", "partido": "PPD", "votos": 13687},
            {"district": 1, "pacto": "P", "partido": "PC", "votos": 10977},
        ])
        seat_magnitudes = pd.Series({1: 3})
        candidatos_por_partido = pd.DataFrame([
            {"district": 1, "partido": "Liberal", "n_candidatos": 1},
            {"district": 1, "partido": "PPD", "n_candidatos": 1},
            {"district": 1, "partido": "PC", "n_candidatos": 1},
        ])

        res = run_electoral_plan_binivel(
            votes_by_district, seat_magnitudes,
            candidatos_por_partido=candidatos_por_partido,
        )
        assert res.set_index("partido")["escanos"].to_dict() == {
            "Liberal": 1, "PPD": 1, "PC": 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# validate_election() — parámetro candidatos_por_partido explícito
# ─────────────────────────────────────────────────────────────────────────────

class TestValidateElectionCandidatosPorPartido:
    def _base_kwargs(self):
        candidates_servel = pd.DataFrame([
            {"district_id": 1, "candidate_id": 1, "candidate_name": "A",
             "party_id": "liberal", "list_id": "PACTO", "votes": 74910},
            {"district_id": 1, "candidate_id": 2, "candidate_name": "B",
             "party_id": "ppd", "list_id": "PACTO", "votes": 13687},
            {"district_id": 1, "candidate_id": 3, "candidate_name": "C",
             "party_id": "pc", "list_id": "PACTO", "votes": 10977},
        ])
        proclamations_tricel = pd.DataFrame([
            {"election_id": "T", "district_id": 1, "candidate_id": 1,
             "candidate_name": "A", "party_id": "liberal", "list_id": "PACTO",
             "votes_final": 74910, "officially_elected": True},
            {"election_id": "T", "district_id": 1, "candidate_id": 2,
             "candidate_name": "B", "party_id": "ppd", "list_id": "PACTO",
             "votes_final": 13687, "officially_elected": True},
            {"election_id": "T", "district_id": 1, "candidate_id": 3,
             "candidate_name": "C", "party_id": "pc", "list_id": "PACTO",
             "votes_final": 10977, "officially_elected": True},
        ])
        return dict(
            candidates_servel=candidates_servel,
            proclamations_tricel=proclamations_tricel,
            assignment={"CUT1": 1},
            magnitudes={1: 3},
            # Los 3 partidos deben compartir un solo pacto — con pacto_map={}
            # cada partido cae en su propio "pacto" de 1 (fallback a su
            # propio nombre), y el Nivel 1 (D'Hondt entre pactos) ya le
            # habría dado los 3 escaños a "liberal" antes de llegar al
            # Nivel 2 que este test quiere ejercitar.
            pacto_map={"liberal": "PACTO", "ppd": "PACTO", "pc": "PACTO"},
        )

    def test_sin_candidatos_por_partido_liberal_se_lleva_todo_y_falla(self):
        """
        Sin el tope, dhondt_binivel() le da los 3 escaños a "liberal" (el
        partido más votado) — pero la proclamación real tiene un ganador
        por cada uno de los 3 partidos, así que la validación NO debe
        pasar 3/3 candidatos. Confirma el comportamiento (roto) sin el
        fix, para contrastar con el siguiente test.
        """
        report = validate_election(**self._base_kwargs())
        assert report.candidate_proclamations < report.candidate_proclamations_total

    def test_con_candidatos_por_partido_reproduce_exacto(self):
        kwargs = self._base_kwargs()
        kwargs["candidatos_por_partido"] = pd.DataFrame([
            {"district_id": 1, "party_id": "liberal", "n_candidatos": 1},
            {"district_id": 1, "party_id": "ppd", "n_candidatos": 1},
            {"district_id": 1, "party_id": "pc", "n_candidatos": 1},
        ])
        report = validate_election(**kwargs)
        assert report.candidate_proclamations == report.candidate_proclamations_total == 3
        assert report.status == "EXACT_REPRODUCTION"

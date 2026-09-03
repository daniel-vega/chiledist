"""
tests/test_split_penalty_multinivel.py
=========================================
Unit tests for the multi-level generalization of the "soft" preservation
mechanics (Etapa 2 de preservación jerárquica multinivel):

    - engines.samplers.updaters.make_split_severity_updater() now returns
      a dict {columna: severidad} instead of a single summed float.
    - engines.samplers.accept.make_split_penalty_accept() now takes a
      dict {columna: peso} (ScenarioConfig.resolved_split_penalty()) and
      computes a per-column weighted Metropolis criterion.
    - engines.samplers.accept.score_with_split_penalty() weights each
      soft column's severity by its own resolved split_penalty.

No live gerrychain chain is needed for the accept()/updater unit tests —
a lightweight fake graph/partition duck-types the small surface these
functions actually touch (.nodes, .degree via a plain dict-of-dicts
adjacency, .graph, .assignment, .parent, and __getitem__ for updater
values), matching the same pattern used by the rest of the engines
tests for gerrychain-free coverage.

Numerical-equivalence checks: for a single preserved column with a
uniform weight (the historical shape used by SCENARIO_APC_SOFT), the new
per-column weighted formulas must reproduce the old single-scalar
formulas exactly — algebra: weighted_delta = peso × (severity_new -
severity_old) == split_penalty × Δseveridad (viejo criterio).
"""

from __future__ import annotations

import math

import geopandas as gpd
import networkx as nx
import pytest
from shapely.geometry import box

from chiledist.domain.scenario import ScenarioConfig
from chiledist.engines.samplers.accept import (
    make_split_penalty_accept,
    score_with_split_penalty,
)
from chiledist.engines.samplers.updaters import make_split_severity_updater


# ─── Fixtures compartidas ──────────────────────────────────────────────────────

def _make_multinivel_gdf() -> gpd.GeoDataFrame:
    """
    6 unidades de decisión (ID_DIST-equivalentes) repartidas en 2 comunas
    (CUT) y 2 regiones (REGION), población uniforme (100 c/u) para que las
    fracciones de severidad sean fáciles de verificar a mano:

        A1, A2 -> CUT=C1, REGION=R1
        A3     -> CUT=C1, REGION=R1
        B1, B2 -> CUT=C2, REGION=R1
        B3     -> CUT=C2, REGION=R2
    """
    return gpd.GeoDataFrame(
        {
            "ID_DIST":   ["A1", "A2", "A3", "B1", "B2", "B3"],
            "CUT":       ["C1", "C1", "C1", "C2", "C2", "C2"],
            "REGION":    ["R1", "R1", "R1", "R1", "R1", "R2"],
            "viviendas": [100, 100, 100, 100, 100, 100],
            "geometry":  [box(i, 0, i + 1, 1) for i in range(6)],
        },
        crs="EPSG:4326",
    )


# ─── make_split_severity_updater — dict por columna ────────────────────────────

class TestSplitSeverityUpdaterReturnsDict:

    def _build_graph(self):
        """
        Grafo simple con atributos de nodo CUT/REGION/viviendas, misma
        estructura conceptual que la que build_graph()/gc.Graph produciría
        para engines.samplers.updaters (solo se usa .nodes con atributos y
        grado, no aristas geométricas reales).
        """
        g = nx.path_graph(6)  # 6 nodos, conectados en cadena (no importa acá)
        nodes_data = [
            ("CUT", "C1", "REGION", "R1"),
            ("CUT", "C1", "REGION", "R1"),
            ("CUT", "C1", "REGION", "R1"),
            ("CUT", "C2", "REGION", "R1"),
            ("CUT", "C2", "REGION", "R1"),
            ("CUT", "C2", "REGION", "R2"),
        ]
        for i, (_, cut, _, region) in enumerate(nodes_data):
            g.nodes[i]["CUT"] = cut
            g.nodes[i]["REGION"] = region
            g.nodes[i]["viviendas"] = 100
        return g

    class _FakePartition:
        def __init__(self, graph, assignment):
            self.graph = graph
            self.assignment = assignment

    def test_two_columns_independent_severity(self):
        graph = self._build_graph()
        # Partición que parte C1 (nodos 0,1 -> distrito 1; nodo 2 -> distrito 2)
        # y también parte R2 trivialmente (R2 solo tiene el nodo 5, no se puede
        # partir con un solo nodo) -> severity REGION debe ser 0.
        assignment = {0: 1, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2}

        updater = make_split_severity_updater(["CUT", "REGION"], "viviendas")
        partition = self._FakePartition(graph, assignment)
        severity = updater(partition)

        assert set(severity.keys()) == {"CUT", "REGION"}
        # C1 (300 hab, 3 nodos) partido en 2 fragmentos: severity = (2-1) * (300/600) = 0.5
        assert severity["CUT"] == pytest.approx(0.5)
        # R1 (500 hab: nodos 0-4) todo en distrito 1 o 2 -> partido también
        # (nodos 0,1 en distrito1; nodos 2,3,4 en distrito2) -> 2 fragmentos:
        # severity = (2-1) * (500/600)
        assert severity["REGION"] == pytest.approx(500 / 600)

    def test_single_column_matches_old_scalar_sum(self):
        """
        Con un solo unit_col, sum(dict.values()) debe reproducir exactamente
        el escalar que devolvía la versión anterior de este updater.
        """
        graph = self._build_graph()
        assignment = {0: 1, 1: 1, 2: 2, 3: 2, 4: 2, 5: 2}

        updater = make_split_severity_updater(["CUT"], "viviendas")
        partition = self._FakePartition(graph, assignment)
        severity = updater(partition)

        assert list(severity.keys()) == ["CUT"]
        assert sum(severity.values()) == pytest.approx(0.5)


# ─── make_split_penalty_accept — Metropolis ponderado por columna ─────────────

class TestMakeSplitPenaltyAccept:

    class _FakePartition:
        def __init__(self, severity: dict, parent=None):
            self._severity = severity
            self.parent = parent

        def __getitem__(self, key):
            assert key == "split_severity"
            return self._severity

    def test_root_partition_always_accepted(self):
        accept = make_split_penalty_accept({"CUT": 0.25})
        root = self._FakePartition({"CUT": 0.0}, parent=None)
        assert accept(root) is True

    def test_non_increasing_weighted_severity_always_accepted(self):
        accept = make_split_penalty_accept({"CUT": 0.25})
        parent = self._FakePartition({"CUT": 0.5})
        # Severidad igual o menor -> aceptar siempre, sin importar random.random()
        same = self._FakePartition({"CUT": 0.5}, parent=parent)
        lower = self._FakePartition({"CUT": 0.3}, parent=parent)
        assert accept(same) is True
        assert accept(lower) is True

    def test_single_column_matches_old_scalar_formula(self, monkeypatch):
        """
        Equivalencia numérica exacta con el criterio anterior (split_penalty
        escalar × Δseveridad) para el caso de una sola columna — el shape
        histórico usado por SCENARIO_APC_SOFT.
        """
        split_penalty = 0.25
        severity_old = 0.20
        severity_new = 0.35  # aumenta -> criterio probabilístico

        accept = make_split_penalty_accept({"CUT": split_penalty})
        parent = self._FakePartition({"CUT": severity_old})
        child = self._FakePartition({"CUT": severity_new}, parent=parent)

        # Fijar random.random() para verificar el umbral exacto, no solo que
        # sea probabilístico.
        threshold = math.exp(-split_penalty * (severity_new - severity_old))

        monkeypatch.setattr(
            "chiledist.engines.samplers.accept.random.random",
            lambda: threshold - 1e-9,
        )
        assert bool(accept(child)) is True

        monkeypatch.setattr(
            "chiledist.engines.samplers.accept.random.random",
            lambda: threshold + 1e-9,
        )
        assert bool(accept(child)) is False

    def test_multi_column_weighted_sum(self, monkeypatch):
        """
        Dos columnas con pesos distintos: la decisión debe basarse en la
        SUMA ponderada de deltas, no en cada columna por separado.
        """
        resolved_penalty = {"CUT": 0.25, "REGION": 0.10}
        parent = self._FakePartition({"CUT": 0.20, "REGION": 0.50})
        child = self._FakePartition(
            {"CUT": 0.35, "REGION": 0.50}, parent=parent
        )  # solo CUT aumenta

        weighted_old = 0.25 * 0.20 + 0.10 * 0.50
        weighted_new = 0.25 * 0.35 + 0.10 * 0.50
        threshold = math.exp(-(weighted_new - weighted_old))

        accept = make_split_penalty_accept(resolved_penalty)

        monkeypatch.setattr(
            "chiledist.engines.samplers.accept.random.random",
            lambda: threshold - 1e-9,
        )
        assert bool(accept(child)) is True

        monkeypatch.setattr(
            "chiledist.engines.samplers.accept.random.random",
            lambda: threshold + 1e-9,
        )
        assert bool(accept(child)) is False

    def test_missing_column_in_resolved_penalty_treated_as_zero_weight(self):
        """Una columna presente en split_severity pero sin peso asignado
        (ej. hard/none) no debe aportar a la severidad ponderada."""
        accept = make_split_penalty_accept({"CUT": 0.25})  # sin "OTRA"
        parent = self._FakePartition({"CUT": 0.20, "OTRA": 0.0})
        child = self._FakePartition({"CUT": 0.20, "OTRA": 999.0}, parent=parent)
        # OTRA no tiene peso -> no debe afectar la decisión pese a su valor enorme
        assert accept(child) is True


# ─── score_with_split_penalty — ponderación post-hoc por columna ─────────────

class TestScoreWithSplitPenalty:

    def test_hard_scenario_returns_base_score_unchanged(self):
        gdf = _make_multinivel_gdf()
        scenario = ScenarioConfig(
            decision_unit="ID_DIST",
            preserve_units=["CUT"],
            preserve_mode="hard",
            pop_col="viviendas",
        )
        assignment = {"A1": 1, "A2": 1, "A3": 2, "B1": 2, "B2": 2, "B3": 2}
        assert score_with_split_penalty(10.0, assignment, gdf, scenario) == 10.0

    def test_single_soft_column_matches_old_uniform_formula(self):
        gdf = _make_multinivel_gdf()
        scenario = ScenarioConfig(
            decision_unit="ID_DIST",
            preserve_units=["CUT"],
            preserve_mode="soft",
            split_penalty=0.25,
            pop_col="viviendas",
        )
        # Parte C1: A1,A2 -> distrito 1; A3 -> distrito 2
        assignment = {"A1": 1, "A2": 1, "A3": 2, "B1": 2, "B2": 2, "B3": 2}

        from chiledist.engines.metrics import split_severity_index
        severity_cut = split_severity_index(
            assignment, gdf, unit_col="CUT", id_col="ID_DIST", pop_col="viviendas"
        )
        expected = 10.0 - 0.25 * severity_cut

        result = score_with_split_penalty(10.0, assignment, gdf, scenario)
        assert result == pytest.approx(expected)

    def test_multi_column_soft_weights_each_column_independently(self):
        gdf = _make_multinivel_gdf()
        scenario = ScenarioConfig(
            decision_unit="ID_DIST",
            preserve_units=["CUT", "REGION"],
            preserve_mode={"CUT": "soft", "REGION": "soft"},
            split_penalty={"CUT": 0.25, "REGION": 0.10},
            pop_col="viviendas",
        )
        # Parte tanto CUT (C1) como REGION (R1)
        assignment = {"A1": 1, "A2": 1, "A3": 2, "B1": 2, "B2": 2, "B3": 2}

        from chiledist.engines.metrics import split_severity_index
        sev_cut = split_severity_index(
            assignment, gdf, unit_col="CUT", id_col="ID_DIST", pop_col="viviendas"
        )
        sev_region = split_severity_index(
            assignment, gdf, unit_col="REGION", id_col="ID_DIST", pop_col="viviendas"
        )
        expected = 10.0 - (0.25 * sev_cut + 0.10 * sev_region)

        result = score_with_split_penalty(10.0, assignment, gdf, scenario)
        assert result == pytest.approx(expected)

    def test_mixed_hard_and_soft_only_weights_soft_column(self):
        gdf = _make_multinivel_gdf()
        scenario = ScenarioConfig(
            decision_unit="ID_DIST",
            preserve_units=["CUT", "REGION"],
            preserve_mode={"CUT": "hard", "REGION": "soft"},
            split_penalty={"REGION": 0.10},
            pop_col="viviendas",
        )
        assignment = {"A1": 1, "A2": 1, "A3": 2, "B1": 2, "B2": 2, "B3": 2}

        from chiledist.engines.metrics import split_severity_index
        sev_region = split_severity_index(
            assignment, gdf, unit_col="REGION", id_col="ID_DIST", pop_col="viviendas"
        )
        expected = 10.0 - 0.10 * sev_region

        result = score_with_split_penalty(10.0, assignment, gdf, scenario)
        assert result == pytest.approx(expected)

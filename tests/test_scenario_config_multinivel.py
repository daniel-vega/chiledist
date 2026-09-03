"""
tests/test_scenario_config_multinivel.py
==========================================
Unit tests for the ScenarioConfig generalization that lets
preserve_mode/split_penalty be either a single str/float (uniform across
preserve_units, historical behavior) or a dict {column: value} (per-level
preservation, ej. {"CUT": "hard", "COD_REGION": "soft"}).

Covers:
    - resolved_preserve_mode() / resolved_split_penalty() normalization
    - New validate() checks for the dict form (missing/extra columns,
      invalid mode values)
    - New decision_unit-finer-than-hard-column UserWarning
    - Regression: SCENARIO_LEGAL, SCENARIO_APC_SOFT, SCENARIO_APC_FREE
      behave exactly as before (str form, no new warnings)

No external data or gerrychain required.
"""

import warnings

import pytest

from chiledist.domain.scenario import ScenarioConfig
from chiledist.rules.scenario_rules import (
    SCENARIO_LEGAL,
    SCENARIO_APC_STRICT,
    SCENARIO_APC_SOFT,
    SCENARIO_APC_FREE,
)


# ─── resolved_preserve_mode() ──────────────────────────────────────────────────

class TestResolvedPreserveMode:

    def test_str_uniform_expands_to_dict(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode="hard",
        )
        assert cfg.resolved_preserve_mode() == {"CUT": "hard", "COD_REGION": "hard"}

    def test_dict_passthrough(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
        )
        assert cfg.resolved_preserve_mode() == {"CUT": "hard", "COD_REGION": "soft"}

    def test_dict_passthrough_is_a_copy(self):
        original = {"CUT": "hard"}
        cfg = ScenarioConfig(decision_unit="CUT", preserve_units=["CUT"],
                              preserve_mode=original)
        resolved = cfg.resolved_preserve_mode()
        resolved["CUT"] = "soft"
        assert original["CUT"] == "hard"

    def test_empty_preserve_units_with_str_mode_gives_empty_dict(self):
        cfg = ScenarioConfig(decision_unit="ID_DIST", preserve_units=[],
                              preserve_mode="none")
        assert cfg.resolved_preserve_mode() == {}


# ─── resolved_split_penalty() ──────────────────────────────────────────────────

class TestResolvedSplitPenalty:

    def test_str_uniform_only_applies_to_soft_columns(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
            split_penalty=0.25,
        )
        # "CUT" es hard, no soft -> no debe recibir peso de penalización
        assert cfg.resolved_split_penalty() == {"COD_REGION": 0.25}

    def test_dict_passthrough(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "soft", "COD_REGION": "soft"},
            split_penalty={"CUT": 0.1, "COD_REGION": 0.5},
        )
        assert cfg.resolved_split_penalty() == {"CUT": 0.1, "COD_REGION": 0.5}

    def test_all_hard_gives_empty_penalty_dict(self):
        cfg = ScenarioConfig(decision_unit="CUT", preserve_units=["CUT"],
                              preserve_mode="hard", split_penalty=0.3)
        assert cfg.resolved_split_penalty() == {}


# ─── validate() — forma dict de preserve_mode ──────────────────────────────────

class TestValidateDictPreserveMode:

    def test_valid_dict_passes(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
            split_penalty={"COD_REGION": 0.25},
        )
        cfg.validate()  # no debe lanzar

    def test_extra_key_not_in_preserve_units_raises(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
        )
        with pytest.raises(ValueError, match="no están en preserve_units"):
            cfg.validate()

    def test_missing_column_in_preserve_mode_raises(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard"},  # falta COD_REGION
        )
        with pytest.raises(ValueError, match="modo explícito"):
            cfg.validate()

    def test_invalid_mode_value_raises(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT"],
            preserve_mode={"CUT": "estricto"},  # no es hard/soft/none
        )
        with pytest.raises(ValueError, match="no reconocidos"):
            cfg.validate()

    def test_dict_split_penalty_zero_on_soft_column_warns(self):
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
            split_penalty={"COD_REGION": 0.0},
        )
        with pytest.warns(UserWarning, match="split_penalty=0.0"):
            cfg.validate()


# ─── validate() — warning decision_unit más fino que columna hard ─────────────

class TestFinenessWarning:

    def test_decision_unit_finer_than_hard_column_warns(self):
        # Mismo patrón que apc_strict: decision_unit="CUT" (comuna) es más
        # fino que "COD_REGION" (región), preservada en modo hard.
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["COD_REGION"],
            preserve_mode="hard",
        )
        with pytest.warns(UserWarning, match="apc_strict"):
            cfg.validate()

    def test_decision_unit_equal_to_hard_column_does_not_warn(self):
        # Caso trivial (ej. legal_comunas): decision_unit == columna
        # preservada -> nada que partir por construcción. pop_col="personas"
        # para aislar esto del warning (no relacionado) de pop_col="viviendas".
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["CUT"],
            preserve_mode="hard",
            pop_col="personas",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            cfg.validate()

    def test_decision_unit_coarser_than_hard_column_does_not_warn(self):
        # decision_unit más grueso que la columna preservada: no aplica el
        # riesgo (no es el patrón de apc_strict). decision_unit debe ser uno
        # de los valores válidos hoy (CUT/ID_DIST/MANZENT); "CUT" (rank 2)
        # es más grueso que "ID_DIST" (rank 1) en _UNIT_HIERARCHY.
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["ID_DIST"],
            preserve_mode="hard",
            pop_col="personas",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            cfg.validate()

    def test_soft_column_does_not_trigger_fineness_warning(self):
        # El riesgo de warm-up infinito es específico de constraints duros;
        # soft no rechaza propuestas, solo penaliza en la aceptación.
        cfg = ScenarioConfig(
            decision_unit="CUT",
            preserve_units=["COD_REGION"],
            preserve_mode="soft",
            split_penalty=0.1,
            pop_col="personas",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", UserWarning)
            cfg.validate()


# ─── Regresión: escenarios existentes sin cambios ──────────────────────────────

class TestBackwardCompatibilityExistingScenarios:
    """
    SCENARIO_LEGAL, SCENARIO_APC_SOFT y SCENARIO_APC_FREE siguen pasando
    preserve_mode/split_penalty como str/float uniforme (no dict) — deben
    seguir funcionando exactamente igual: validate() sin excepciones ni
    warnings nuevos, y resolved_preserve_mode()/resolved_split_penalty()
    reproducen el comportamiento uniforme histórico.
    """

    def test_scenario_legal_no_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            SCENARIO_LEGAL.validate()
        assert SCENARIO_LEGAL.resolved_preserve_mode() == {"CUT": "hard"}
        assert SCENARIO_LEGAL.resolved_split_penalty() == {}

    def test_scenario_apc_soft_no_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            SCENARIO_APC_SOFT.validate()
        assert SCENARIO_APC_SOFT.resolved_preserve_mode() == {"CUT": "soft"}
        assert SCENARIO_APC_SOFT.resolved_split_penalty() == {"CUT": 0.25}

    def test_scenario_apc_free_no_warnings(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            SCENARIO_APC_FREE.validate()
        assert SCENARIO_APC_FREE.resolved_preserve_mode() == {}
        assert SCENARIO_APC_FREE.resolved_split_penalty() == {}

    def test_scenario_apc_strict_now_gets_fineness_warning(self):
        """
        apc_strict (decision_unit="ID_DIST", preserve_units=["CUT"], hard)
        es exactamente el caso documentado de warm-up infinito. No está en
        la lista de escenarios que deben quedar sin cambios de
        comportamiento — al contrario, validate() debe advertir sobre él
        ahora explícitamente.
        """
        with pytest.warns(UserWarning, match="apc_strict"):
            SCENARIO_APC_STRICT.validate()

    def test_load_scenario_roundtrip_dict_mode(self, tmp_path):
        """
        load_scenario()/save_scenario() deben soportar preserve.mode como
        mapping YAML sin cambios de código (ya son transparentes al tipo).
        """
        from chiledist.domain.scenario import load_scenario, save_scenario

        cfg = ScenarioConfig(
            name="test_multinivel",
            decision_unit="CUT",
            preserve_units=["CUT", "COD_REGION"],
            preserve_mode={"CUT": "hard", "COD_REGION": "soft"},
            split_penalty={"COD_REGION": 0.25},
        )
        path = tmp_path / "test_multinivel.yml"
        save_scenario(cfg, str(path))

        loaded = load_scenario(str(path))
        assert loaded.preserve_mode == {"CUT": "hard", "COD_REGION": "soft"}
        assert loaded.split_penalty == {"COD_REGION": 0.25}
        assert loaded.resolved_preserve_mode() == cfg.resolved_preserve_mode()

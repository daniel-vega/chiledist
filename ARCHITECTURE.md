# Arquitectura de chiledist

Este documento describe la arquitectura de 5 capas resultante de la
refactorización B1 (Etapas 1-3). Antes de esta refactorización, el código
estaba organizado por **dominio funcional** (`electoral/`, `malapportionment/`,
`scenario_comparison/`, ...); ahora está organizado por **responsabilidad
arquitectónica** — qué tipo de decisión encierra cada pieza de código, no de
qué tema habla.

---

## 1. Diagrama de capas y flujo de dependencias

```
                    ┌─────────────────────────────────────┐
                    │   chiledist/__init__.py (facade)      │
                    │   import chiledist as cd               │
                    └──────────────────┬────────────────────┘
                                       │ importa de las 5 capas
                                       ▼
  capa 4   ┌───────────────────────────────────────────────────────┐
  EVALUATION│  evaluation/   — juicio político/normativo             │
            │  scoring.py (PESOS_DEFAULT, rank_scenarios) framing.py │
            │  proportionality.py, district_malapportionment.py,     │
            │  malapportionment/ (índices descriptivos)              │
            └───────────────────────┬───────────────────────────────┘
                                    │▲
                     consume ───────┘└─── fórmulas descriptivas
                     (normal)            (inversión documentada, §4)
                                    │
  capa 3   ┌─────────────────────────▼─────────────────────────────┐
  INFERENCE │  inference/    — contrafactuales y comparación         │
            │  comparison.py, sensitivity.py, plots.py                │
            │  pareto_sweep/, electoral_ensemble/                     │
            └───────────────────────┬───────────────────────────────┘
                                    │
  capa 2   ┌─────────────────────────▼─────────────────────────────┐
  ENGINES   │  engines/      — motores de cómputo                    │
            │  metrics.py, fairshare.py, samplers/ (ReCom/SMC),       │
            │  allocation/ (D'Hondt, magnitudes, plan_metrics)        │
            └───────────────────────┬───────────────────────────────┘
                                    │
  capa 1   ┌─────────────────────────▼─────────────────────────────┐
  RULES     │  rules/        — legal-as-code                         │
            │  feasibility.py, constraints.py, scenario_rules.py,     │
            │  split_rules.py, electoral_rules.py                     │
            └───────────────────────┬───────────────────────────────┘
                                    │
  capa 0   ┌─────────────────────────▼─────────────────────────────┐
  DOMAIN    │  domain/       — modelo de datos                       │
            │  equivalence.py, loader.py, graph.py, hierarchy.py,     │
            │  scenario.py, map.py, persistence.py, ensemble_store.py,│
            │  data/ (census2024, servel)                             │
            └─────────────────────────────────────────────────────┘

  Dirección de dependencia permitida:  domain → rules → engines → inference → evaluation
  (cada capa puede importar de sí misma y de cualquier capa a su izquierda)
```

`config.py`, `constraints.py`, `split_metrics.py`, `electoral/` y
`scenario_comparison/` — los 5 módulos que en la Etapa 0 mezclaban capas —
**ya no existen**: se dividieron íntegramente entre las 5 carpetas de arriba
(Etapa 2). `chiledist/__init__.py` sigue siendo la única fachada plana
(`import chiledist as cd`); internamente no hay compatibilidad hacia atrás
("Opción B", sin shims) — cada consumidor importa directamente desde la
ubicación final.

---

## 2. Capa → paquete → responsabilidad → símbolo de ejemplo

| Capa | Paquete | Responsabilidad | Símbolo de ejemplo |
|---|---|---|---|
| 0 — Domain | `domain/` | Modelo de datos: carga geoespacial/demográfica, equivalencia de unidades censales, grafos de adyacencia, contenedor de estado, persistencia, I/O de ensembles. Sin lógica de reglas ni algoritmos. | `ChileDistMap`, `build_graph`, `load_ensembles_from_disk` |
| 1 — Rules | `rules/` | Reglas legales codificadas como funciones/constantes deterministas: qué es legal, qué escenarios existen, qué cuenta como "partición", magnitudes de la Ley 20.840. | `check_population_feasibility`, `SCENARIO_LEGAL`, `MAGNITUDES_LEGALES_LEY20840` |
| 2 — Engines | `engines/` | Motores de cómputo: muestreo de planes (ReCom/SMC), métricas de compacidad/splits, asignación D'Hondt de escaños, fair share. | `run_recom_chain`, `polsby_popper`, `dhondt`, `count_split_units` |
| 3 — Inference | `inference/` | Análisis distribucional y contrafactual sobre ensembles: comparación entre escenarios, sensibilidad metodológica, barrido de Pareto, distribuciones electorales. | `compare_ensembles`, `pareto_frontier_nd`, `sweep_split_penalty`, `run_electoral_ensemble` |
| 4 — Evaluation | `evaluation/` | Interpretación normativa: índices de (des)proporcionalidad/malapportionment, puntaje compuesto ponderado, encuadre legislativo. | `gallagher_index`, `personas_por_escano`, `rank_scenarios`, `reforma_context` |

---

## 3. Reglas de dependencia

**Regla general:** cada capa importa solo de sí misma o de una capa a su
izquierda en `domain → rules → engines → inference → evaluation`.

| Capa | Puede importar de | NO puede importar de |
|---|---|---|
| `domain/` | `domain/` (y el módulo hoja `_version.py` de la raíz) | `rules/`, `engines/`, `inference/`, `evaluation/` |
| `rules/` | `rules/`, `domain/` | `engines/`, `inference/`, `evaluation/` |
| `engines/` | `engines/`, `rules/`, `domain/` | `inference/`, `evaluation/` (con una excepción documentada, §4) |
| `inference/` | `inference/`, `engines/`, `rules/`, `domain/` | — (consume de `evaluation/` por la excepción documentada, §4) |
| `evaluation/` | cualquier capa | — (capa terminal: nada depende de ella salvo el facade) |

`tests/test_architecture.py::TestLayerBoundaries` verifica automáticamente
(leyendo el AST de cada archivo, sin ejecutar el paquete) que `domain/` y
`rules/` — las dos fronteras más críticas, origen de los 3 ciclos de import
resueltos en la Etapa 1 — no violan esta regla.

`config.py`, `constraints.py` y `split_metrics.py` desaparecieron
precisamente porque violaban esto: mezclaban una capa baja (el dato/la regla)
con una capa alta (el motor o el juicio normativo) en el mismo archivo.

---

## 4. Inversión de dependencia documentada

`engines/` e `inference/` importan de `evaluation/` en varios puntos:

```
engines/allocation/plan_metrics.py       → evaluation.proportionality, evaluation.district_malapportionment
inference/electoral_ensemble/core.py     → evaluation.proportionality, evaluation.district_malapportionment
inference/comparison.py                  → evaluation.scoring (METRICAS_STD, ScoringConfig)
inference/sensitivity.py                 → evaluation.scoring (METRICAS_STD)
inference/plots.py                       → evaluation.scoring (METRICAS_STD, ScoringConfig, ...)
```

Esto es formalmente una inversión respecto a `domain → rules → engines →
inference → evaluation`. Se investigó y se decidió **aceptarla y
documentarla**, no resolverla, por lo siguiente:

`evaluation/` mezcla dos tipos de contenido con comportamiento
arquitectónico distinto:

- **Fórmulas descriptivas reutilizables** — `gallagher_index`,
  `loosemore_hanby`, `personas_por_escano`, `peso_relativo_del_voto`,
  `umbral_efectivo`, y el registro `METRICAS_STD` (columna → etiqueta →
  dirección óptima). Dado un plan, computan un número; no encierran una
  ponderación política. Son vocabulario compartido, análogo a una fórmula
  matemática — el mismo tipo de dependencia "hacia adelante" que ya existía
  en el árbol de imports desde la Etapa 1.
- **Contenido genuinamente normativo** — `PESOS_DEFAULT` (cuánto pesa cada
  métrica al decidir qué escenario es "mejor"), `rank_scenarios`,
  `reforma_context` (encuadre legislativo). Esto sí es el juicio político
  real, el verdadero final de la tubería 0→4.

Verificación (repetible): ningún archivo de `domain/`, `rules/`, `engines/`
ni `inference/` importa `PESOS_DEFAULT`, `rank_scenarios` ni
`reforma_context` — solo aparecen en comentarios/docstrings, nunca en un
`import`. La inversión real está acotada estrictamente a la categoría
"fórmula descriptiva"; el contenido normativo de `evaluation/` es un
consumidor terminal sin dependientes hacia abajo.

```bash
grep -rn "PESOS_DEFAULT\|rank_scenarios\|reforma_context" \
  chiledist/domain chiledist/rules chiledist/engines chiledist/inference --include="*.py"
# → solo coincide dentro de docstrings/comentarios, nunca en una línea "import"
```

Resolverla de raíz implicaría partir `evaluation/` en dos sub-capas (fórmulas
vs. pesos) — no se hizo en esta refactorización porque no fue parte del
alcance de las Etapas 1-2, y porque duplicar el registro `METRICAS_STD` para
evitar el import cruzado arriesgaría que las dos copias diverjan
numéricamente. Si una etapa futura quiere eliminarla del todo, la palanca es
esa: extraer `proportionality.py`, `district_malapportionment.py` y
`METRICAS_STD` a una capa compartida entre `engines/` e `inference/`
(por ejemplo `engines/indices.py`), dejando `evaluation/` solo con
`PESOS_DEFAULT`/`rank_scenarios`/`reforma_context`.

### 4.1 Excepción resuelta: `normalize_party_name()`

Durante la refactorización de la capa de datos electorales SERVEL,
`domain/data/servel/__init__.py::import_candidates()` necesitó reutilizar
`normalize_party_name()` (la misma normalización que usa `dhondt_binivel()`
para resolver `pacto_map`), que en ese momento vivía en
`engines/allocation/utils.py` — una inversión `domain/ → engines/` más
severa que la de §4 (aquí sí era la capa 0 importando de la capa 2, sin
la categoría "fórmula descriptiva neutral" que justifica §4). Se
documentó como excepción puntual y explícita mientras se evaluaba.

**Resuelta**: `normalize_party_name()` se movió a `domain/utils.py` — es
vocabulario de dominio (normalización de texto), no un algoritmo de
motor, del mismo tipo que `domain.hierarchy.normalize_cut()`. No quedó
ninguna excepción pendiente en `domain/`; `TestLayerBoundaries` no
necesita ningún allowlist.

---

## 5. Símbolos públicos principales por capa

Todos accesibles vía `import chiledist as cd; cd.<símbolo>` — la fachada
plana no cambió durante la refactorización, solo su implementación interna.

**domain** — `ChileDistMap`, `ScenarioConfig`, `load_scenario`,
`save_scenario`, `build_graph`, `contract_graph`, `load_layer`,
`build_national`, `contract_to_decision_units`, `PlanEnsemble`,
`save_assignments_parquet`, `load_ensembles_from_disk`,
`assess_comparison_completeness`, `get_optimal_crs`, `normalize_party_name`,
`data` (subpaquete)

**rules** — `check_population_feasibility`, `make_preserve_constraint`,
`build_constraints_for_scenario`, `SCENARIO_LEGAL`, `SCENARIO_APC_FREE`,
`SCENARIOS`, `TOTAL_ESCANOS_CAMARA`, `MAGNITUDES_LEGALES_LEY20840`,
`MAGNITUDES_CENSO2024_2026`

**engines** — `polsby_popper`, `reock`, `population_balance`, `cut_edges`,
`plan_split_metrics`, `count_split_units`, `dhondt`, `dhondt_binivel`,
`assign_seat_magnitudes`, `run_recom`,
`run_recom_chain`, `analyze_ensemble`, `fair_share_matrix`,
`build_updaters_for_scenario`, `make_split_penalty_accept`

**inference** — `compare_ensembles`, `scenario_delta`, `pareto_frontier_nd`,
`pareto_optimal_scenarios`, `sweep_split_penalty`, `build_tradeoff_frontier`,
`detect_knee_point`, `compare_sensitivity`, `ranking_concordance`,
`run_electoral_ensemble`, `ensemble_gallagher`

**evaluation** — `gallagher_index`, `loosemore_hanby`, `rae_index`,
`personas_por_escano`, `peso_relativo_del_voto`, `umbral_efectivo`,
`seat_bonus`, `ScoringConfig`, `rank_scenarios`, `PESOS_DEFAULT`,
`reforma_context`, `samuels_snyder_index`, `international_comparison`

---

## 6. Guía: dónde va código nuevo

Pregúntate, en orden:

1. **¿Es un dato o un contenedor de estado, sin decisión ni juicio?**
   ("cargar tal shapefile", "guardar tal manifiesto", "representar un
   escenario como objeto") → **`domain/`**. Ejemplo: agregar soporte para
   cargar un nuevo shapefile del INE va en `domain/loader.py`, porque es
   pura carga de datos, no decide nada.

2. **¿Codifica lo que la ley permite/exige, o una constante fijada por
   norma?** ("¿esto viola la Ley 18.700?", "¿cuántos escaños tiene el
   distrito 5 según la Ley 20.840?") → **`rules/`**. Ejemplo: si SERVEL
   publica una nueva tabla de magnitudes tras el Censo 2024, la constante
   va en `rules/electoral_rules.py`, junto a `MAGNITUDES_LEGALES_LEY20840`
   — no en `engines/`, porque no es un algoritmo, es un hecho legal.

3. **¿Es un algoritmo/cómputo que produce un resultado a partir de reglas y
   datos, sin comparar entre planes ni juzgar cuál es mejor?** ("computar
   D'Hondt para un distrito", "generar un plan con ReCom", "calcular
   Polsby-Popper de una geometría") → **`engines/`**. Ejemplo: un nuevo
   índice de compacidad (ej. Convex Hull Ratio ya existe, pero un
   hipotético "X-Symmetry index") va en `engines/metrics.py` — computa un
   número desde una geometría, no compara escenarios ni pondera nada.

4. **¿Compara/resume una distribución de planes o escenarios, sin decidir
   cuál es "mejor" en términos ponderados?** ("¿cómo cambia el Gallagher
   entre 500 planes del ensemble?", "¿el mapa vigente está Pareto-dominado?",
   "¿el ranking es robusto a cambiar la fuente de población?") →
   **`inference/`**. Ejemplo: una nueva prueba de robustez metodológica
   (análoga a `compare_sensitivity`) va en `inference/sensitivity.py`.

5. **¿Es un índice normativo/descriptivo sobre proporcionalidad o
   representación, o un juicio de valor explícito sobre qué escenario es
   preferible?** ("índice de desproporcionalidad nuevo", "cambiar cuánto
   pesa la compacidad frente al balance poblacional", "texto para explicar
   un escenario a una comisión legislativa") → **`evaluation/`**. Un índice
   descriptivo nuevo (ej. otro índice de malapportionment de la literatura)
   va en `evaluation/malapportionment/indices.py`; un cambio a los pesos
   por defecto va en `evaluation/scoring.py::PESOS_DEFAULT`.

**Visualización** (`plots.py`, `viz.py`, `_plot_style.py`): es una
preocupación transversal, no una capa 0-4. Por convención ya establecida,
cada paquete analítico que produce resultados dignos de graficarse tiene su
propio `plots.py` junto al código que calcula lo que grafica (ej.
`inference/plots.py` junto a `inference/comparison.py`). Una función de
visualización nueva va en el `plots.py` de la capa cuyo resultado grafica.

**Si dudas entre dos capas:** el criterio decisivo es *quién depende de
quién*, no *de qué habla el código*. `evaluation/malapportionment/` y
`rules/electoral_rules.py` hablan ambos de "escaños" — pero uno es un índice
descriptivo (capa 4) y el otro es una constante legal (capa 1). Pregúntate
qué pasaría si la Ley 20.840 cambiara mañana: si tu código cambiaría de
resultado automáticamente porque lee una constante legal, esa constante va
en `rules/`; si tu código seguiría funcionando igual pero interpretando un
número distinto, probablemente está en la capa correcta ya.

**Después de agregar el símbolo:** expórtalo también desde
`chiledist/__init__.py` (bloque de import + `__all__`) para que quede
accesible vía `cd.<símbolo>`, y agrégalo a la lista explícita o al loop de
`tests/test_architecture.py::TestPublicAPI` si es un símbolo central que
merece un assert nombrado.

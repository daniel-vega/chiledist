# Auditoría de Capacidades — ChileDist vs H1–H5

> **Estado:** revisado — la mayoría de las brechas P0/P1 identificadas en el borrador original ya están implementadas
> **Fecha:** 2026-08-14 (revisión; borrador original 2026-06-21)
> **Rol:** investigador senior en redistritaje computacional
> **Contexto:** Auditoría crítica de qué puede y no puede hacer ChileDist para responder las cinco preguntas científicas centrales del proyecto. Todo juicio se ancla en el código fuente inspeccionado, no en la documentación declarada.
>
> **Nota de esta revisión:** el borrador de 2026-06-21 quedó desactualizado por el ritmo de desarrollo — casi todas las brechas marcadas P0 y la mayoría de las P1 para H1–H5 ya están resueltas. Cada ítem resuelto queda marcado **✓ Implementado**, con la referencia exacta al módulo/función. Solo se preservan como brecha genuina los ítems que siguen sin implementación tras verificación directa contra el código.

---

## 1. Auditoría de capacidades actuales

### H1 — ¿Cuál es el costo de la indivisibilidad comunal?

**Pregunta operativa:** ¿cuánto balance poblacional se sacrifica al imponer que las comunas sean indivisibles? ¿Qué proporción de la población queda afectada por esa restricción?

**Lo que ya funciona:**

- Los tres escenarios (legal / apc_free / apc_soft) son la arquitectura correcta para esta pregunta: `legal` impone la restricción, `apc_free` la elimina, la comparación entre ambos *es* la medida del costo. Esto está bien diseñado.
- `split_metrics.py` provee: `count_split_units`, `split_severity_index`, `split_unit_summary`, `small_fragment_count`, `plan_split_metrics`, **y `pop_afectada_pct`** (ver más abajo).
- `compare_ensembles()` y `scenario_delta()` permiten comparar medianas y percentiles entre escenarios.
- **✓ Implementado — `pop_afectada_pct(assignment, gdf, unit_col, id_col, pop_col)`** (`chiledist/split_metrics.py:260`): fracción de la población total que reside en comunas partidas, exactamente la métrica que el borrador original pedía como "lo que falta completamente". Se calcula dentro de `plan_split_metrics()` (`chiledist/split_metrics.py:311`, campo `pop_afectada_pct`) y se exporta en `chiledist/__init__.py`.
- **✓ Implementado — `n_comunas_partidas`, `split_severity`, `pop_afectada_pct` por plan en `ensemble_stats.csv`**: `scripts/redistritaje.py` llama a `cd.plan_split_metrics()` por plan del ensemble y almacena estas tres columnas en `df_ensemble` (que se serializa como `ensemble_stats.csv`), tanto en el flujo normal como en el de respaldo. Esto responde el ítem que el borrador listaba como P0 ("split_metrics por plan en ensemble_stats.csv").
- **✓ Implementado — barrido de `split_penalty`**: `chiledist/pareto_sweep/` (`sweep_split_penalty`, `build_tradeoff_frontier`, `detect_knee_point`, `summarize_tradeoff`) y el script `scripts/pareto_sweep.py` corren automáticamente N configuraciones de `split_penalty` y consolidan sus distribuciones. Ya no es un experimento manual.

**Lo que sigue parcialmente implementado:**

- `split_severity_index` sigue mezclando severidad de la partición y tamaño relativo de la comuna en una sola fórmula (`Σ (n_frags - 1) × pop_share_comunal`). Esto no cambió, pero `pop_afectada_pct` (ahora implementado) cubre exactamente la interpretación política más directa ("qué fracción de la población vive en comunas partidas"), así que la ambigüedad de `split_severity_index` es un problema menor de nomenclatura, no una brecha funcional.

**Lo que sigue faltando:**

- **Tasa de intercambio explícita como función**: sigue sin existir un `costo_restriccion()` (o equivalente) que calcule `(median_max_dev_legal − median_max_dev_apc_free) / median_max_dev_apc_free` como una función reutilizable. `scenario_delta()` (`chiledist/scenario_comparison/compare.py`) calcula deltas absolutos respecto a un baseline, pero no esta razón normalizada específica. Es un cálculo derivado trivial de `compare_ensembles()`, no una brecha de infraestructura.

**Componentes que no aportan a H1:**

- `autocorrelacion.py` (Moran global, LISA, G*): mide clustering espacial de viviendas o densidad en los datos de entrada. No dice nada sobre el costo de restringir comunas. Prescindible para H1.
- `export_imc_bundle.py`: formato para herramienta interactiva externa. No aporta nada analítico a H1.
- `equivalence.py` (tabla USA↔Chile): referencia conceptual, no analítica. No aporta a H1.

---

### H2 — ¿Existe una frontera de Pareto entre igualdad del voto e integridad administrativa?

**Pregunta operativa:** ¿tiene la curva de intercambio (balance vs splits) una forma característica? ¿Es el mapa vigente Pareto-dominado?

**Lo que ya funciona:**

- `pareto_frontier_nd()` implementa la frontera Pareto N-dimensional. Funciona correctamente sobre DataFrames con métricas.
- `plot_tradeoff_frontier()` (`chiledist/scenario_comparison/plots.py`) genera un scatter 2D con la frontera.
- `pareto_optimal_scenarios()` identifica escenarios no dominados.
- Los tres escenarios proveen puntos extremos de la distribución: `legal` maximiza integridad comunal, `apc_free` minimiza restricciones.
- **✓ Implementado — barrido de `split_penalty` para frontera continua**: `chiledist/pareto_sweep/frontier.py::sweep_split_penalty` + `build_tradeoff_frontier` corren automáticamente el rango de valores y consolidan el dataset. `scripts/pareto_sweep.py` es el entrypoint CLI. Ya no hace falta correr el pipeline manualmente valor por valor.
- **✓ Implementado — posicionamiento del mapa vigente**: `position_plan_vigente()` (`chiledist/scenario_comparison/sensitivity.py:96`) calcula el mismo vector de métricas (max_dev_pob_pct, pp_promedio, cut_edges, métricas de split) para el mapa vigente y lo posiciona junto a los ensembles, respondiendo directamente si el vigente es Pareto-dominado.
- **✓ Implementado — caracterización de la forma de la frontera**: `detect_knee_point()` (`chiledist/pareto_sweep/frontier.py:331`) detecta el punto de codo / retornos decrecientes sobre la frontera trazada por el barrido.
- **✓ Implementado — bandas de confianza en la frontera**: `build_tradeoff_frontier()` acepta bootstrap y calcula `bootstrap_bands` (`chiledist/pareto_sweep/frontier.py:93-176, 305-309`) — cada punto de la frontera lleva su banda de incertidumbre, no solo la mediana puntual.

**Lo que ya es suficiente para H2:**

Con las cuatro capacidades de arriba, la infraestructura de H2 está completa: frontera Pareto N-dimensional, barrido continuo de `split_penalty`, posicionamiento del vigente, forma de la frontera (codo) y bandas de confianza. No queda ninguna brecha de infraestructura identificada para H2.

**Componentes que no aportan a H2:**

- Diagnósticos MCMC (R-hat, ESS): miden calidad del sampler, no la forma de la frontera.
- `viz.py` (plot_layer, plot_compactness): exploración, no inferencia sobre la frontera.

---

### H3 — ¿Cómo afecta la asignación de magnitudes y la distribución poblacional a la igualdad del voto?

**Pregunta operativa:** ¿cuánto "vale" un voto en el Distrito 1 vs el Distrito 14? ¿Qué cambiaría si los escaños se reasignaran con Censo 2024?

**Lo que ya funciona:**

- `assign_seat_magnitudes()` implementa el método Hamilton acotado (min=3, max=8, total=155). Esto es correcto y reproduce la lógica del Art. 179 bis de la Ley 18.700.
- `MAGNITUDES_LEGALES_LEY20840` está codificado correctamente con `assert sum == 155`.
- `population_balance()` calcula desviación respecto al ideal dentro de un plan.
- **✓ Implementado — `personas_por_escano(pop_by_district, magnitudes)`** (`chiledist/electoral/district_malapportionment.py:16`): la métrica fundamental de H3, personas representadas por escaño en cada circunscripción.
- **✓ Implementado — `peso_relativo_del_voto(pop_by_district, magnitudes)`** (`chiledist/electoral/district_malapportionment.py:43`): razón `personas_por_escano_i / media_nacional`, la medida estándar de malapportionment comparado (Samuels & Snyder 2001).
- **✓ Implementado — comparación contrafactual de magnitudes**: `comparar_magnitudes()` (`chiledist/electoral/magnitudes.py:87`) compara las magnitudes vigentes (`MAGNITUDES_LEGALES_LEY20840`) contra las que resultarían del método Hamilton bajo una población actualizada — el experimento contrafactual central de H3. Ahora existe además `datos/asignacion_vigente.json` (346 comunas → 28 distritos, ver sección "Datos externos" del README) como el mapa vigente real con el que alimentar esta comparación desde `scripts/malapportionment.py --assignment-path`.
- **✓ Implementado — Índice de Gini de representación**: `gini_personas_por_escano()` (`chiledist/malapportionment/indices.py:144`), junto con un módulo completo (`samuels_snyder_index`, `max_min_representation_ratio`, `malapportionment_summary`, `international_comparison` con benchmarks internacionales) que excede lo que pedía el borrador original.

**Distinción que sigue siendo válida (no es una brecha, es una precisión conceptual):**

- `population_balance()` mide equidad interna de un plan de redistritaje (¿cuánto se desvía cada distrito del plan respecto al ideal?), lo cual **no es lo mismo** que malapportionment del mapa vigente (¿cuántas personas representa cada escaño?). Ambos conceptos ahora tienen soporte: el primero vía `population_balance()`, el segundo vía `personas_por_escano()`/`peso_relativo_del_voto()`.

**Componentes que no aportan a H3:**

- `split_metrics.py`: H3 no trata sobre splits sino sobre la relación población-escaños. No es relevante.
- `polsby_popper`, `reock`, etc.: compacidad no se relaciona con malapportionment.

---

### H4 — ¿Cómo afecta la geografía distrital a la conversión votos→escaños bajo D'Hondt y pactos?

**Pregunta operativa:** ¿qué geografía distrital favorece o perjudica a cada pacto electoral? ¿Con cuántos votos adicionales cambia la asignación de escaños?

**Lo que ya funciona:**

- `dhondt()` implementa correctamente D'Hondt de un nivel. Determinístico, validado.
- `aggregate_votes()`, `run_electoral_plan()`, `national_shares()` forman un pipeline coherente.
- `gallagher_index()`, `loosemore_hanby()`, `rae_index()`, `effective_number_of_parties()`: índices de proporcionalidad implementados correctamente.
- `plan_electoral_metrics()`: integra el pipeline en una función, y acepta `pacto_map` para el caso binivel.
- **✓ Implementado — D'Hondt binivel (pactos → partidos)**: `dhondt_binivel()` y `run_electoral_plan_binivel()` (`chiledist/electoral/dhondt.py:207,291`) implementan el mecanismo real chileno de dos etapas — D'Hondt entre pactos y luego asignación intra-pacto por mayor votación individual. Era la brecha más crítica del borrador original ("sin él, cualquier análisis con datos reales produce asignaciones incorrectas") y ya no existe.
- **✓ Implementado — `chiledist/electoral_ensemble/` (módulo completo, no mencionado en el borrador original)**: `run_electoral_ensemble()` (`chiledist/electoral_ensemble/core.py:87`) corre D'Hondt (uni- o binivel, según si se pasa `pacto_map`) sobre cada plan de un ensemble; `ensemble_gallagher()`, `ensemble_seat_bonus()`, `ensemble_enp()`, `ensemble_effective_threshold()`, `summarize_electoral_ensemble()` dan las distribuciones agregadas. Esto integra exactamente lo que el borrador pedía como brecha ("Gallagher bajo escenarios alternativos... posible si se integra plan_electoral_metrics con el pipeline de ensemble").
- **✓ Implementado — `margen_ultimo_escano(votos_district, magnitud)`** (`chiledist/electoral/district_malapportionment.py:112`): votos entre el último electo y el primer no electo, por circunscripción.
- **✓ Implementado — `umbral_efectivo(magnitud)`** (`chiledist/electoral/district_malapportionment.py:83`): `1/(M+1)` por circunscripción.
- **✓ Implementado — `seat_bonus(vote_shares, seat_shares)`** (`chiledist/electoral/proportionality.py:125`): diferencia entre cuota de escaños y cuota de votos. La firma final difiere levemente de la propuesta en el borrador (`seat_bonus(resultados_por_pacto)`) pero es funcionalmente equivalente.

**Lo que ya es suficiente para H4:**

Con D'Hondt binivel, el módulo de ensemble electoral, `margen_ultimo_escano`, `umbral_efectivo` y `seat_bonus`, no queda ninguna brecha de infraestructura identificada para H4.

**Investigación futura (genuinamente fuera de alcance, no una brecha de P0/P1):**

Candidatos individuales, independientes, candidaturas fuera de pacto: estos casos existen en el sistema real pero su implementación requiere un modelo de datos más complejo (candidato → partido → pacto, con casos bordes). No es necesario para responder H4 en su versión principal. Ver P2 más abajo.

**Componentes que no aportan a H4:**

- `split_metrics.py`: no relevante para conversión votos→escaños.
- Diagnósticos MCMC: no tienen relación con el sistema electoral.
- `autocorrelacion.py`: no aporta a H4.

---

### H5 — ¿Son robustas las conclusiones frente a cambios metodológicos?

**Pregunta operativa:** si cambio la fuente de población, la política de islas o el sampler, ¿cambia el ranking de escenarios?

**Lo que ya funciona:**

- Los cuatro modos de `pop_source` (viviendas, manzana, censo2024, padron) están implementados en `ScenarioConfig` y en `redistritaje.py`.
- Las tres políticas de islas (nearest, threshold, none) están implementadas en `build_graph()` y en `ScenarioConfig`.
- El bridge SMC (`generate_redist_script`, `load_redist_results`) permite comparar con un sampler independiente.
- Los tres escenarios permiten comparar efectos de `decision_unit` y `preserve_mode`.
- **✓ Implementado — `compare_sensitivity(ensembles, metric_cols)`** (`chiledist/scenario_comparison/sensitivity.py:213`): tabla de comparación por pares entre variantes metodológicas (KS test, diferencia de medianas, tamaño de efecto) — exactamente el framework de sensibilidad que el borrador marcaba como ausente.
- **✓ Implementado — `ranking_concordance(scores_a, scores_b)`** (`chiledist/scenario_comparison/sensitivity.py:317`): Kendall τ + Spearman ρ + lista de pares discordantes entre rankings bajo distintas condiciones metodológicas.
- **✓ Implementado (adicional, no contemplado en el borrador) — consistencia de `n_distritos` entre entrypoints**: `redistritaje.py`, `compare_scenarios.py`, `pareto_sweep.py`, `run_chains.py` y `smc_pipeline.py` resuelven `n_districts` con la misma precedencia (`--n-distritos` explícito > `scenario.n_districts`), eliminando un default=8 silencioso que antes podía introducir inconsistencia metodológica no intencional entre corridas. Esto es directamente relevante para H5: una diferencia de `n_districts` entre corridas comparadas dejaría de ser un artefacto de configuración oculto.
- **✓ Implementado (adicional) — preflight de factibilidad poblacional**: `chiledist.check_population_feasibility()` (`chiledist/feasibility.py`) determina, antes de intentar `recursive_tree_part`, si la tolerancia poblacional solicitada es matemáticamente alcanzable dada la indivisibilidad de las unidades de decisión. Cuando no lo es, `scripts/redistritaje.py` retorna `status: "infeasible_population"` con `reason` y diagnóstico completo, en vez de agotar reintentos silenciosamente. Esto es distinto de `status: "sin_particion"` (agotamiento de la búsqueda de inicialización, `reason: "initialization_search_exhausted"` — no es una prueba de inviabilidad). Relevante para H5 porque separa "el escenario es matemáticamente imposible" de "el sampler falló por razones de implementación", dos conclusiones muy distintas sobre robustez.
- **✓ Implementado (adicional) — completitud de la comparación**: `scripts/compare_scenarios.py` ahora detecta cuando un escenario de la comparación (por ejemplo el baseline `legal_comunas`) no produjo un ensemble válido, lo mantiene visible con su status/reason (`escenarios_overview.csv`), lo excluye del scoring, y marca la comparación global como `comparison_status: "INCOMPLETE"` / `ranking_scope: "partial"` en vez de reportar un ranking parcial como si fuera completo. Ver `chiledist/scenario_comparison/compare.py::build_scenario_overview`, `assess_comparison_completeness`.

**Lo que ya es suficiente para H5:**

Con `compare_sensitivity`, `ranking_concordance`, la resolución consistente de `n_distritos`, el preflight de factibilidad y el marcado de comparaciones incompletas, la infraestructura de robustez metodológica de H5 está sustancialmente más completa que en el borrador original. No se identifica una brecha de P0/P1 pendiente.

**Componentes que no aportan a H5:**

- `viz.py` (funciones de visualización exploratorias): no son parte del análisis de robustez.
- `autocorrelacion.py`: no aporta a la sensibilidad metodológica de los ensembles.

---

## 2. Matriz pregunta → capacidad

| Pregunta | Capacidad requerida | Estado | Brecha | Prioridad |
|----------|--------------------|----|--------|-----------|
| **H1** Costo de indivisibilidad | Tres escenarios (legal/apc_free/apc_soft) | ✅ Completo | — | — |
| **H1** | Métricas de splits: count, severity, small_fragments | ✅ Completo | — | — |
| **H1** | `pop_afectada_pct` (% pop en comunas divididas) | ✅ Completo | — | — |
| **H1** | Split metrics por plan en `ensemble_stats.csv` | ✅ Completo | — | — |
| **H1** | Barrido de `split_penalty` para trazar curva de costo | ✅ Completo | — | — |
| **H1** | Tasa de intercambio Δbalance/Δsplits como función nombrada | ⚠️ Parcial | Cálculo derivado trivial de `compare_ensembles()`, sin envolver en función | P1 |
| **H2** Frontera de Pareto | `pareto_frontier_nd()` | ✅ Completo | — | — |
| **H2** | `plot_tradeoff_frontier()` | ✅ Completo | — | — |
| **H2** | Barrido de `split_penalty` para trazar frontera continua | ✅ Completo | — | — |
| **H2** | Posicionamiento del mapa vigente en el espacio Pareto | ✅ Completo | — | — |
| **H2** | Caracterización de la forma de la frontera (codo) | ✅ Completo | — | — |
| **H2** | Bandas de confianza en la frontera | ✅ Completo | — | — |
| **H3** Malapportionment | `assign_seat_magnitudes()` (Hamilton acotado) | ✅ Completo | — | — |
| **H3** | `MAGNITUDES_LEGALES_LEY20840` | ✅ Completo | — | — |
| **H3** | `personas_por_escano(pop_by_district, magnitudes)` | ✅ Completo | — | — |
| **H3** | `peso_relativo_del_voto(pop_by_district, magnitudes)` | ✅ Completo | — | — |
| **H3** | Comparación magnitudes vigentes vs actualizadas (Censo 2024) | ✅ Completo | — | — |
| **H3** | Índice de Gini de representación | ✅ Completo | — | — |
| **H4** Geografía → votos → escaños | D'Hondt de un nivel | ✅ Completo | — | — |
| **H4** | `aggregate_votes()`, `run_electoral_plan()` | ✅ Completo | — | — |
| **H4** | Índices de proporcionalidad (Gallagher, LH, Rae, ENP) | ✅ Completo | — | — |
| **H4** | **D'Hondt binivel** (pactos → partidos) | ✅ Completo | — | — |
| **H4** | Módulo de ensemble electoral (Gallagher/seat bonus distribucional) | ✅ Completo | — | — |
| **H4** | `margen_ultimo_escano(votos_distrito, magnitud)` | ✅ Completo | — | — |
| **H4** | `umbral_efectivo(magnitud)` | ✅ Completo | — | — |
| **H4** | `seat_bonus(vote_shares, seat_shares)` | ✅ Completo | — | — |
| **H5** Robustez metodológica | Múltiples `pop_source` | ✅ Completo | — | — |
| **H5** | Múltiples `island_policy` | ✅ Completo | — | — |
| **H5** | Bridge SMC (ReCom vs SMC) | ✅ Completo | — | — |
| **H5** | Framework de análisis de sensibilidad (`compare_sensitivity`) | ✅ Completo | — | — |
| **H5** | Comparación de rankings entre variantes (`ranking_concordance`, Kendall τ) | ✅ Completo | — | — |
| **H5** | Consistencia de `n_distritos` entre entrypoints | ✅ Completo | — | — |
| **H5** | Preflight de factibilidad poblacional (`infeasible_population` vs `sin_particion`) | ✅ Completo | — | — |
| **H5** | Detección de comparaciones incompletas (`comparison_status`) | ✅ Completo | — | — |

---

## 3. Ajustes a ChileDist para H1

### Estado: resuelto casi por completo

Las dos métricas imprescindibles que este borrador pedía originalmente ya están implementadas:

- **`pop_afectada_pct(assignment, gdf, unit_col, id_col, pop_col)`** (`chiledist/split_metrics.py:260`) — fracción de la población total que reside en comunas partidas. Distinción respecto a `share_comunas_partidas` (nº comunas partidas / total comunas, ya existía antes): `pop_afectada_pct` pondera por población, no por conteo de comunas, que es el número interpretable en discusión legislativa.
- **`n_comunas_partidas`, `split_severity`, `pop_afectada_pct` por plan en `ensemble_stats.csv`** — `scripts/redistritaje.py` ya llama a `cd.plan_split_metrics()` por plan y persiste estas columnas.

### Único ítem pendiente (P1, no P0)

**Tasa de intercambio explícita como función reutilizable.** Sigue sin existir una función nombrada que calcule:

```
costo_restriccion = (median_max_dev_legal - median_max_dev_apc_free) / median_max_dev_apc_free
```

Es un cálculo derivado de `compare_ensembles()` de una sola línea; su ausencia es una conveniencia faltante, no una brecha de infraestructura. Implementarla como `chiledist.scenario_comparison.costo_restriccion(df_comp, baseline, target)` sería el ajuste mínimo restante para H1.

---

## 4. Ajustes a ChileDist para H2

### Estado: resuelto por completo

Las cuatro capacidades analíticas que este borrador pedía ya están implementadas:

- **Barrido de `split_penalty`** → `chiledist/pareto_sweep/frontier.py::sweep_split_penalty`, `build_tradeoff_frontier`, orquestado por `scripts/pareto_sweep.py`.
- **Posicionamiento del mapa vigente** → `chiledist/scenario_comparison/sensitivity.py::position_plan_vigente`.
- **Forma de la frontera** → `chiledist/pareto_sweep/frontier.py::detect_knee_point`.
- **Bandas de confianza** → `build_tradeoff_frontier(..., bootstrap=True)` calcula `bootstrap_bands` por punto.

No queda ningún ajuste pendiente identificado para H2.

---

## 5. Ajustes a ChileDist para H3

### Estado: resuelto por completo

- **`personas_por_escano(pop_by_district, magnitudes)`** → `chiledist/electoral/district_malapportionment.py:16`.
- **`peso_relativo_del_voto(pop_by_district, magnitudes)`** → `chiledist/electoral/district_malapportionment.py:43`.
- **Comparación contrafactual de magnitudes** → `chiledist/electoral/magnitudes.py::comparar_magnitudes`, alimentable con población real (Censo 2024) y con el mapa vigente real (`datos/asignacion_vigente.json`, ver README § "Datos externos").
- **Índice de Gini de representación** → `chiledist/malapportionment/indices.py::gini_personas_por_escano`, más un módulo `chiledist.malapportionment` completo (Samuels-Snyder, Loosemore-Hanby aplicado a escaños, comparación internacional).

**Distinción conceptual que sigue siendo relevante señalar** (no una brecha): `population_balance()` mide equidad interna de un *plan de redistritaje* (distinto de malapportionment del *mapa vigente*, que mide `personas_por_escano`). Ambos conceptos tienen soporte hoy, pero conviene no confundirlos al interpretar resultados.

No queda ningún ajuste pendiente identificado para H3.

---

## 6. Ajustes a ChileDist para H4

### Estado: resuelto por completo

**D'Hondt binivel (pactos → partidos)** — antes la brecha más crítica del módulo electoral — está implementado en `chiledist/electoral/dhondt.py::dhondt_binivel` / `run_electoral_plan_binivel`: D'Hondt entre pactos sobre votos totales de lista, luego asignación intra-pacto por mayor votación individual. `chiledist/electoral_ensemble/core.py::run_electoral_ensemble` lo integra sobre ensembles completos cuando se provee `pacto_map`.

**`margen_ultimo_escano(votos_district, magnitud)`** → `chiledist/electoral/district_malapportionment.py:112`.

**`umbral_efectivo(magnitud)`** → `chiledist/electoral/district_malapportionment.py:83`, fórmula `1/(M+1)`.

**`seat_bonus(vote_shares, seat_shares)`** → `chiledist/electoral/proportionality.py:125`.

### Investigación futura (genuinamente fuera de alcance)

Candidatos individuales, independientes, candidaturas fuera de pacto: existen en el sistema real pero requieren un modelo de datos más complejo (candidato → partido → pacto, con casos borde). No es necesario para responder H4 en su versión principal — ver P2 en la sección 9.

---

## 7. Ajustes a ChileDist para H5

### Estado: resuelto por completo, más capacidades no contempladas en el borrador original

**Comparación de distribuciones entre variantes metodológicas** → `chiledist/scenario_comparison/sensitivity.py::compare_sensitivity(ensembles, metric_cols)`: KS test, p-value y diferencia de medianas por métrica, entre pares de ensembles.

**Concordancia de ranking entre variantes** → `chiledist/scenario_comparison/sensitivity.py::ranking_concordance(scores_a, scores_b)`: Kendall τ, Spearman ρ, pares discordantes.

**Matriz de variantes a comparar** (viviendas vs personas, CUT vs APC, ReCom vs SMC, políticas de islas, `pop_tolerance`) — sigue siendo un buen checklist operativo para diseñar los experimentos de H5; la maquinaria para ejecutar cada comparación ya existe (arriba), lo que faltaba era el diseño experimental explícito, no infraestructura.

**Capacidades adicionales no contempladas en el borrador original, también relevantes para H5:**

- Consistencia de `n_distritos` (`--n-distritos` explícito > `scenario.n_districts`) en los cinco entrypoints (`redistritaje.py`, `compare_scenarios.py`, `pareto_sweep.py`, `run_chains.py`, `smc_pipeline.py`) — elimina una fuente de inconsistencia metodológica silenciosa entre corridas comparadas.
- Preflight de factibilidad poblacional (`chiledist/feasibility.py::check_population_feasibility`) — separa inviabilidad matemática probada (`status: "infeasible_population"`) de fallo de búsqueda de inicialización (`status: "sin_particion"`), evidencia directamente relevante para argumentar robustez o sus límites.
- Marcado de comparaciones incompletas (`chiledist/scenario_comparison/compare.py::assess_comparison_completeness`) — evita reportar un ranking parcial (ej. sin el baseline `legal_comunas`) como si fuera una comparación H1 completa.

No queda ningún ajuste de infraestructura pendiente identificado para H5.

---

## 8. Discusión legislativa

Si un comité del Congreso quisiera usar ChileDist para estudiar una eventual reforma, los indicadores que la librería debe producir son los siguientes. Los organizo por lo que un asesor técnico necesitaría para responder preguntas concretas de parlamentarios.

**Sobre igualdad del voto**

- *Personas por escaño por circunscripción* con datos del Censo 2024. Tabla de 28 filas. **✓ Computable** con `personas_por_escano()` (`chiledist/electoral/district_malapportionment.py:16`), usando `datos/asignacion_vigente.json` como mapa comuna→distrito y Censo 2024 como fuente de población.
- *Peso relativo del voto por circunscripción*: razón respecto a la media nacional. Si supera 2.0 o cae bajo 0.5, el argumento legislativo es inmediato. **✓ Computable** con `peso_relativo_del_voto()`.
- *Cambio en magnitudes requeridas con Censo 2024*: tabla de 28 distritos mostrando escaños actuales vs escaños bajo metodología actualizada. **✓ Computable** con `comparar_magnitudes()` (`chiledist/electoral/magnitudes.py:87`).
- *Número de distritos que cambiarían de magnitud* con una actualización basada en Censo 2024 — derivable directamente de la salida de `comparar_magnitudes()`.

**Sobre comunas partidas**

- *Fracción de la población en comunas partidas* bajo cada escenario. **✓ Computable** con `pop_afectada_pct()`, con la interpretación correcta (ponderada por población, no por conteo de comunas).
- *Lista de comunas más afectadas* con número de fragmentos y población involucrada. Disponible vía `split_unit_summary()`.
- *Mapa vigente de 28 distritos: cuántas comunas comparten más de un distrito*. Ya no requiere codificar el mapa vigente manualmente para cada análisis: `datos/asignacion_vigente.json` es exactamente ese `assignment` (346 comunas → 28 distritos), listo para pasar a `count_split_units()` u otras funciones de `split_metrics.py`.

**Sobre proporcionalidad**

- *Índice de Gallagher por elección bajo el mapa vigente* con datos reales SERVEL. **✓ Computable**: D'Hondt binivel (`dhondt_binivel`) + `datos/asignacion_vigente.json` + datos SERVEL vía `scripts/electoral_analysis.py --assignment-path --servel-path`.
- *Gallagher bajo escenarios alternativos*: distribución del ensemble de Gallagher por escenario. **✓ Computable** vía `chiledist.electoral_ensemble.run_electoral_ensemble()` + `ensemble_gallagher()`.
- *Umbral efectivo por circunscripción*: qué porcentaje de votos necesita un partido para ganar escaño en cada distrito. **✓ Computable** con `umbral_efectivo(magnitud)`.

**Sobre estabilidad electoral**

- *Margen del último escaño* por circunscripción. **✓ Computable** con `margen_ultimo_escano()`.
- *Varianza de escaños por pacto* entre planes del ensemble. **✓ Computable** vía `ensemble_seat_bonus()` (distribución por partido/pacto sobre el ensemble).

---

## 9. Priorización

### Resuelto desde el borrador original

Los ocho ítems P0 y cinco de los seis ítems P1 originales de este documento ya están implementados (ver secciones 1–8 arriba para la referencia exacta de cada uno): `pop_afectada_pct`, `personas_por_escano`, `peso_relativo_del_voto`, comparación de magnitudes vigentes vs Censo 2024, D'Hondt binivel, `margen_ultimo_escano`, posicionamiento del mapa vigente en espacio Pareto, split metrics por plan en `ensemble_stats.csv`, barrido de `split_penalty`, `umbral_efectivo`, `seat_bonus`, `compare_sensitivity`, concordancia de ranking (Kendall τ), Índice de Gini de representación. También se resolvió el P2 de bandas de confianza en la frontera de Pareto (`bootstrap_bands`).

### P0/P1 — Pendiente

| Capacidad | H que soporta | Impacto científico | Impacto legislativo | Dificultad |
|-----------|-------------|---------------------|---------------------|------------|
| Tasa de intercambio Δbalance/Δsplits como función nombrada | H1, H2 | Medio: cálculo derivado ya posible manualmente con `compare_ensembles()` | Alto: "cada comuna que preservamos cuesta X% de desbalance" | Baja (derivado) |

### P2 — Investigación futura (sin cambios respecto al borrador original)

| Capacidad | H que soporta | Justificación | Dificultad |
|-----------|-------------|---------------|------------|
| D'Hondt con candidatos individuales y listas abiertas | H4 | Necesario para análisis de candidatos específicos; fuera del alcance actual | Alta |
| Índice de malapportionment de Samuels-Snyder a nivel subnacional | H3 | Requiere datos a nivel más granular que lo disponible | Media |
| Autocorrelación espacial de resultados del ensemble (Moran sobre plans) | — | No responde directamente ninguna de H1–H5 | Media |

---

## Componentes actuales descartados para H1–H5

Los siguientes módulos y funciones no contribuyen a responder H1–H5 y consumen tiempo de mantenimiento. Nota: `autocorrelacion.py` y `export_imc_bundle.py` son scripts en `scripts/` (CLI operativo), no módulos de la librería `chiledist/`; se listan igual porque compiten por tiempo de mantenimiento del proyecto en su conjunto.

| Componente | Razón del descarte |
|------------|-------------------|
| `scripts/autocorrelacion.py` (Moran, LISA, G*) | Mide clustering espacial de viviendas en el mapa de entrada. Ninguna de H1–H5 pregunta sobre clustering espacial. Es análisis exploratorio de datos, no de planes. |
| `scripts/export_imc_bundle.py` | Formato para herramienta interactiva externa. No produce ningún indicador analítico para H1–H5. |
| `chiledist/equivalence.py` (tabla USA↔Chile, `print_equivalence`, `describe_hierarchy`) | Referencia conceptual. No tiene uso en ningún pipeline analítico de H1–H5. |
| `chiledist/viz.py` (mayoría de funciones) | Útil para comunicación; no para producir resultados científicos. `plot_tradeoff_frontier` y `plot_boxplots_comparativos` (usadas en H1–H2) viven en `chiledist/scenario_comparison/plots.py`, no en `viz.py` — corrección respecto al borrador original, que las atribuía a `viz.py`. El resto de `viz.py` no aporta. |
| Diagnósticos MCMC (`plot_acf`, `plot_gelman_rubin_evolution`, `plot_trace`) | Solo relevantes para H5 de forma periférica. El R-hat verifica convergencia de la cadena, no la validez de las conclusiones sustantivas. No son análisis científicos sobre H1–H5. |
| `graph_stats()`, `to_edgelist()`, `subgraph_region()` | Utilidades de inspección del grafo. No producen resultados para ninguna hipótesis. |

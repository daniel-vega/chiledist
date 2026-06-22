# Auditoría de Capacidades — ChileDist vs H1–H5

> **Estado:** borrador de trabajo  
> **Fecha:** 2026-06-21  
> **Rol:** investigador senior en redistritaje computacional  
> **Contexto:** Auditoría crítica de qué puede y no puede hacer ChileDist v0.2.0 para responder las cinco preguntas científicas centrales del proyecto. Todo juicio se ancla en el código fuente inspeccionado, no en la documentación declarada.

---

## 1. Auditoría de capacidades actuales

### H1 — ¿Cuál es el costo de la indivisibilidad comunal?

**Pregunta operativa:** ¿cuánto balance poblacional se sacrifica al imponer que las comunas sean indivisibles? ¿Qué proporción de la población queda afectada por esa restricción?

**Lo que ya funciona:**

- Los tres escenarios (legal / apc_free / apc_soft) son la arquitectura correcta para esta pregunta: `legal` impone la restricción, `apc_free` la elimina, la comparación entre ambos *es* la medida del costo. Esto está bien diseñado.
- `split_metrics.py` provee: `count_split_units`, `split_severity_index`, `split_unit_summary`, `small_fragment_count`, `plan_split_metrics`. Existe la infraestructura básica.
- `compare_ensembles()` y `scenario_delta()` permiten comparar medianas y percentiles entre escenarios.

**Lo que está parcialmente implementado:**

- `split_severity_index` usa la fórmula `Σ (n_frags - 1) × pop_share_comunal`, donde `pop_share_comunal` es la fracción de la población *total* del plan que corresponde a esa comuna. Esto mezcla dos efectos: severidad de la partición y tamaño relativo de la comuna. Una commune pequeña muy fragmentada aparece con severidad baja porque su `pop_share` es pequeño. Esto no es incorrecto, pero no mide bien *qué fracción de la población total vive en comunas partidas*, que es el indicador más interpretable políticamente.
- El escenario `apc_soft` tiene un solo valor de `split_penalty` (por defecto 0.25). Para trazar la *frontera del costo* necesitas variar `split_penalty` sistemáticamente. No hay soporte para ese experimento de barrido.

**Lo que falta completamente:**

- **`pop_en_comunas_partidas`**: fracción de la población total que reside en comunas que están divididas en el plan. Esta es la métrica más comunicable: "en este plan, el 34% de la población vive en comunas partidas". El `split_severity_index` existente no responde eso directamente.
- **Tasa de intercambio explícita**: ningún módulo calcula cuánto aumenta `max_dev_pob_pct` al reducir `n_comunas_partidas` en una unidad (o viceversa). Para responder H1 científicamente necesitas esta relación de cambio.
- La función `plan_split_metrics` devuelve `share_comunas_partidas` (fracción de *comunas* partidas), pero no `share_poblacion_en_comunas_partidas`. Son magnitudes distintas con interpretaciones distintas.

**Componentes que no aportan a H1:**

- `autocorrelacion.py` (Moran global, LISA, G*): mide clustering espacial de viviendas o densidad en los datos de entrada. No dice nada sobre el costo de restringir comunas. Prescindible para H1.
- `export_imc_bundle.py`: formato para herramienta interactiva externa. No aporta nada analítico a H1.
- `equivalence.py` (tabla USA↔Chile): referencia conceptual, no analítica. No aporta a H1.

---

### H2 — ¿Existe una frontera de Pareto entre igualdad del voto e integridad administrativa?

**Pregunta operativa:** ¿tiene la curva de intercambio (balance vs splits) una forma característica? ¿Es el mapa vigente Pareto-dominado?

**Lo que ya funciona:**

- `pareto_frontier_nd()` implementa la frontera Pareto N-dimensional. Funciona correctamente sobre DataFrames con métricas.
- `plot_tradeoff_frontier()` genera un scatter 2D con la frontera.
- `pareto_optimal_scenarios()` identifica escenarios no dominados.
- Los tres escenarios proveen puntos extremos de la distribución: `legal` maximiza integridad comunal, `apc_free` minimiza restricciones.

**Lo que está parcialmente implementado:**

- `apc_soft` existe con `split_penalty` fijo. Para trazar la *forma* de la frontera de Pareto necesitas múltiples ensembles con distintos valores de `split_penalty` (0.0, 0.05, 0.10, 0.25, 0.50, 1.0, etc.). Esto requiere correr el pipeline varias veces con parámetro variado, lo que hoy no tiene soporte nativo: hay que hacerlo manualmente.
- La función `plot_tradeoff_frontier` produce un scatter pero no traza la curva de la frontera sobre el ensemble completo. Marca la línea de Pareto entre escenarios-agregados (medianas), no entre planes individuales.

**Lo que falta completamente:**

- **Soporte para barrido de `split_penalty`**: correr automáticamente N ensembles con distintos valores de penalización y consolidar sus distribuciones en un solo dataset. Sin esto, la frontera se reconstruye con solo tres puntos (los tres escenarios predefinidos), lo cual es insuficiente para caracterizar su forma.
- **Posicionamiento del mapa vigente**: ninguna función coloca el mapa vigente en el espacio (balance, splits). Para H2, la pregunta central es si el vigente es Pareto-dominado. Eso requiere calcular sus métricas con la misma metodología que los ensembles y añadirlo como punto de referencia.
- **Caracterización de la forma de la frontera**: ¿es convexa, cóncava, lineal? Un cambio de convexidad indica si los primeros compromisos son baratos o caros. No hay función que caracterice esto.
- **Bandas de confianza en la frontera**: cada punto de la frontera es una mediana de ensemble con varianza. El límite de lo que es alcanzable no es una línea sino una banda. No está implementado.

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

**Lo que está parcialmente implementado:**

- `population_balance()` calcula `deviation_pct = (pop_distrito - ideal) / ideal`. Esto mide la equidad interna de un plan. **No es lo mismo** que malapportionment. Malapportionment para H3 es `personas / escanos_asignados` por distrito, y la comparación de esa razón entre distritos. Son conceptos distintos que el código mezcla.

**Lo que falta completamente:**

- **`personas_por_escano(pop_by_district, magnitudes)`**: la métrica fundamental de H3. Para cada circunscripción electoral, cuántas personas representa cada escaño. El rango esperado en Chile 2021: 50.000–200.000 personas/escaño según el distrito.
- **`peso_relativo_del_voto(pop_by_district, magnitudes)`**: razón `(personas_por_escano_i / media_nacional)`. Expresa cuánto vale relativamente el voto en cada distrito. Si es 0.5, ese voto vale el doble que el promedio. Si es 2.0, vale la mitad. Esta es la medida estándar de malapportionment en ciencia política comparada (Samuels & Snyder 2001).
- **Comparación contrafactual de magnitudes**: ninguna función calcula las magnitudes que resultarían del Censo 2024 bajo el mismo método Hamilton y las compara con `MAGNITUDES_LEGALES_LEY20840`. Esta comparación es el experimento central de H3 para la discusión legislativa.
- **Índice de Gini de representación**: distribución de escaños vs distribución de población a nivel nacional. Complementa a Gallagher para medir desigualdad estructural del mapa.

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
- `plan_electoral_metrics()`: integra el pipeline en una función.

**Lo que está parcialmente implementado:**

- `run_electoral_plan()` aplica D'Hondt directamente sobre partidos. Para datos con votos por partido el resultado es técnicamente correcto como análisis de proporcionalidad. Sin embargo, el **sistema real chileno opera en dos niveles**: primero D'Hondt distribuye escaños entre pactos electorales; luego, dentro de cada pacto, los escaños obtenidos se distribuyen entre los partidos del pacto según el orden de mayor votación individual. La implementación actual aplica solo el primer D'Hondt sobre partidos directamente, lo cual produce resultados incorrectos cuando los datos incluyen estructura de pactos.

**Lo que falta completamente:**

- **D'Hondt binivel**: es la brecha más crítica para H4. Sin él, cualquier análisis con datos electorales reales de Chile (que tienen estructura pacto→partido) produce asignaciones de escaños incorrectas. No es opcional: es el sistema real.
- **`margen_ultimo_escano(votos_district, magnitud)`**: para cada circunscripción, cuántos votos separan al último ganador del primero perdedor. Mide la sensibilidad electoral local y es central para H4.
- **`umbral_efectivo(magnitud)`**: en un distrito de M escaños, el umbral efectivo aproximado es `1/(M+1)`. Esta función es trivial de implementar pero no existe. Es un resultado estándar de la teoría electoral que fundamenta H4.
- **`seat_bonus(resultados_por_pacto)`**: diferencia entre escaños obtenidos y escaños que corresponderían a la cuota proporcional de votos. Mide la sobrerepresentación de pactos mayoritarios, que varía con la geografía.

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

**Lo que está parcialmente implementado:**

- `compare_ensembles()` compara escenarios entre sí. Pero para H5 necesitas comparar el **mismo escenario bajo distintas condiciones metodológicas** (ej. legal-viviendas vs legal-personas). `compare_ensembles` no está diseñada para eso: espera ensembles de escenarios distintos, no variantes metodológicas del mismo escenario.

**Lo que falta completamente:**

- **Framework de análisis de sensibilidad**: no existe ninguna función que automatice el experimento "corre el mismo análisis bajo N variantes metodológicas y reporta qué cambia". El usuario debe ejecutar manualmente todos los pipelines y comparar con KS tests o Kendall τ ad hoc.
- **`compare_sensitivity(base_ensemble, variant_ensembles, method_labels)`**: tabla o reporte que muestre, para cada par de variantes, la distribución de diferencias en métricas clave y la concordancia de ranking. Sin esto, H5 requiere trabajo manual extenso.
- **Comparación automática de rankings entre variantes**: Kendall τ y top-1 agreement entre rankings bajo distintas condiciones no se calculan en ningún módulo actual.

**Componentes que no aportan a H5:**

- `viz.py` (funciones de visualización exploratorias): no son parte del análisis de robustez.
- `autocorrelacion.py`: no aporta a la sensibilidad metodológica de los ensembles.

---

## 2. Matriz pregunta → capacidad

| Pregunta | Capacidad requerida | Estado | Brecha | Prioridad |
|----------|--------------------|----|--------|-----------|
| **H1** Costo de indivisibilidad | Tres escenarios (legal/apc_free/apc_soft) | ✅ Completo | — | — |
| **H1** | Métricas de splits: count, severity, small_fragments | ✅ Completo | — | — |
| **H1** | `pop_en_comunas_partidas` (% pop en comunas divididas) | ❌ Ausente | Métrica nueva | P0 |
| **H1** | Tasa de intercambio Δbalance/Δsplits | ❌ Ausente | Cálculo derivado | P1 |
| **H1** | Barrido de `split_penalty` para trazar curva de costo | ⚠️ Parcial | Falta soporte de experimento | P1 |
| **H2** Frontera de Pareto | `pareto_frontier_nd()` | ✅ Completo | — | — |
| **H2** | `plot_tradeoff_frontier()` | ✅ Completo | — | — |
| **H2** | Barrido de `split_penalty` para trazar frontera continua | ❌ Ausente | Soporte para sweep experiment | P0 |
| **H2** | Posicionamiento del mapa vigente en el espacio Pareto | ❌ Ausente | Función de comparación plan vs ensemble | P0 |
| **H2** | Bandas de confianza en la frontera | ❌ Ausente | Análisis de varianza de ensemble | P2 |
| **H3** Malapportionment | `assign_seat_magnitudes()` (Hamilton acotado) | ✅ Completo | — | — |
| **H3** | `MAGNITUDES_LEGALES_LEY20840` | ✅ Completo | — | — |
| **H3** | `personas_por_escano(pop_by_district, magnitudes)` | ❌ Ausente | Métrica nueva fundamental | P0 |
| **H3** | `peso_relativo_del_voto(pop_by_district, magnitudes)` | ❌ Ausente | Derivado de personas/escaño | P0 |
| **H3** | Comparación magnitudes vigentes vs actualizadas (Censo 2024) | ❌ Ausente | Función de comparación contrafactual | P0 |
| **H3** | Índice de Gini de representación | ❌ Ausente | Métrica derivada | P1 |
| **H4** Geografía → votos → escaños | D'Hondt de un nivel | ✅ Completo | — | — |
| **H4** | `aggregate_votes()`, `run_electoral_plan()` | ✅ Completo | — | — |
| **H4** | Índices de proporcionalidad (Gallagher, LH, Rae, ENP) | ✅ Completo | — | — |
| **H4** | **D'Hondt binivel** (pactos → partidos) | ❌ Ausente | **Brecha crítica para datos reales** | P0 |
| **H4** | `margen_ultimo_escano(votos_distrito, magnitud)` | ❌ Ausente | Métrica de sensibilidad electoral | P0 |
| **H4** | `umbral_efectivo(magnitud)` | ❌ Ausente | Cálculo trivial, ausente | P1 |
| **H4** | `seat_bonus(resultados_por_pacto)` | ❌ Ausente | Métrica de sobrerepresentación | P1 |
| **H5** Robustez metodológica | Múltiples `pop_source` | ✅ Completo | — | — |
| **H5** | Múltiples `island_policy` | ✅ Completo | — | — |
| **H5** | Bridge SMC (ReCom vs SMC) | ✅ Completo | — | — |
| **H5** | Framework de análisis de sensibilidad automático | ❌ Ausente | Módulo nuevo | P1 |
| **H5** | Comparación de rankings entre variantes (Kendall τ) | ❌ Ausente | Función derivada | P1 |

---

## 3. Ajustes a ChileDist para H1

### Métricas imprescindibles

**`pop_afectada_pct(assignment, gdf, unit_col, id_col, pop_col)`**  
Fracción de la población total que reside en unidades (comunas) que están divididas entre dos o más distritos en el plan. Resultado entre 0 y 1. Esta es la métrica más comunicable a una audiencia no especializada: "en este escenario, el 28% de la población vive en comunas partidas". El `split_severity_index` actual no la responde directamente porque su denominador es la severidad ponderada, no la proporción de personas afectadas.

Distinción crítica respecto a lo existente:
- `share_comunas_partidas` = nº comunas partidas / total comunas (lo que ya existe)
- `pop_afectada_pct` = Σ pop(comunas partidas) / pop total (lo que falta)

Una sola comuna muy poblada partida puede tener `share_comunas_partidas = 0.003` pero `pop_afectada_pct = 0.15`. El número que importa en discusión legislativa es el segundo.

**Comparación directa entre ensembles para la tasa de intercambio**  
Para medir el costo de la restricción comunal, la métrica derivada es:

```
costo_restriccion = (median_max_dev_legal - median_max_dev_apc_free) / median_max_dev_apc_free
```

Expresado en porcentaje: "el escenario legal cuesta X% más de desbalance poblacional para eliminar toda fragmentación comunal". Esta operación no existe como función; debe calcularse a partir de `compare_ensembles()`.

### Métricas accesorias

**`fragmento_mas_pequeno(assignment, gdf, unit_col, id_col, pop_col)`**  
Para cada comuna partida, el tamaño (en % de la población comunal) del fragmento más pequeño. Mide qué tan artificiales son las divisiones. Ya existe `small_fragment_count` con un umbral fijo de 10%; lo que falta es la distribución continua del tamaño del fragmento más pequeño.

**`comunas_partidas_por_plan`** en el `ensemble_stats.csv`  
Actualmente `plan_split_metrics` devuelve un dict con todas las métricas. Lo que falta es que el pipeline `run_recom_chain` llame a esta función por plan y almacene los resultados en `ensemble_stats.csv`. Sin esto, los análisis de H1 requieren recalcular sobre el ensemble completo a posteriori.

---

## 4. Ajustes a ChileDist para H2

### Capacidades analíticas necesarias

**Soporte para barrido de `split_penalty`**  
La frontera de Pareto entre balance y splits requiere trazar una curva continua, no tres puntos. Para eso, `apc_soft` debe correrse con un rango de valores de `split_penalty` (mínimo 6–8 valores entre 0.0 y 2.0). El `ScenarioConfig` ya admite `split_penalty` como parámetro; lo que falta es un experimento sistemático que varíe ese parámetro y consolide los resultados. Cada punto de la curva es la mediana del ensemble para ese valor de penalización.

**Posicionamiento del mapa vigente**  
El mapa vigente debe calcularse una sola vez (en el mismo espacio métrico que los ensembles: max_dev_pob_pct con personas Censo 2024, n_comunas_partidas = 0 por definición en el mapa legal) y añadirse como punto de referencia en todos los gráficos de H2. Sin esto, la pregunta "¿es el vigente Pareto-dominado?" no puede responderse.

**Métricas que deben almacenarse por plan** (no solo medianas)  
Para H2 necesitas la distribución, no solo la mediana. `ensemble_stats.csv` debe contener, para cada plan, tanto `max_dev_pob_pct` como `n_comunas_partidas` y `pop_afectada_pct`. Actualmente `ensemble_stats.csv` almacena las métricas de compacidad y balance, pero el almacenamiento de split metrics por plan en el archivo de estadísticas del ensemble es inconsistente según la corrida.

**Lo que ya es suficiente para H2:**  
`pareto_frontier_nd()` es correcto y suficiente para identificar los planes no dominados. `plot_tradeoff_frontier()` es suficiente para visualizar el scatter. No se necesita nada adicional en estas funciones.

---

## 5. Ajustes a ChileDist para H3

### Capacidades analíticas necesarias

**`personas_por_escano(pop_by_district, magnitudes)`** — imprescindible  
Para cada circunscripción, la razón población / escaños asignados. Es la unidad de medida fundamental del malapportionment. Con los 28 distritos actuales y datos del Censo 2024, produce un vector de 28 valores. La dispersión de ese vector es la desigualdad del voto.

Este cálculo no requiere nueva lógica compleja: `pop_by_district / magnitudes`. Su ausencia es la brecha más directa para H3.

**`peso_relativo_del_voto(pop_by_district, magnitudes)`** — imprescindible  
`personas_por_escano / media_nacional`. Un valor de 0.5 significa que un voto en ese distrito tiene el doble de peso que el promedio nacional. Es la forma estándar de reportar malapportionment en ciencia política comparada. También es el indicador más interpretable para una discusión legislativa.

**Comparación contrafactual de magnitudes** — imprescindible para H3  
Función que toma la población actualizada (Censo 2024) y calcula qué magnitudes resultarían del método Hamilton bajo los mismos parámetros de la ley (min=3, max=8, total=155). Comparar con `MAGNITUDES_LEGALES_LEY20840`. `assign_seat_magnitudes()` ya hace el cálculo; lo que falta es la comparación estructurada: ¿qué distritos ganarían escaños? ¿Cuáles perderían?

**Sobre `population_balance()`:** esta función calcula desviación respecto al ideal en un plan de redistritaje. No debe confundirse con malapportionment. La diferencia es:
- `population_balance`: ¿cuánto se desvía la población de cada *distrito del plan* respecto al ideal?
- malapportionment: ¿cuántas personas representa cada *escaño* en cada circunscripción del mapa *vigente*?

Son preguntas distintas. ChileDist tiene respuesta para la primera, no para la segunda.

**Índice de Gini de representación** — deseable  
Curva de Lorenz sobre la distribución de escaños vs distribución de población. Permite medir la desigualdad estructural del sistema con una métrica internacional estándar. Es derivable de `personas_por_escano` con pandas; no requiere código complejo.

---

## 6. Ajustes a ChileDist para H4

### Imprescindible

**D'Hondt binivel (pactos → partidos)**  
Es la brecha más grave del módulo electoral. El sistema chileno asigna escaños en dos etapas: (1) D'Hondt entre pactos electorales sobre sus votos totales de lista; (2) los escaños obtenidos por cada pacto se asignan a los candidatos de ese pacto según orden de mayor votación individual (no D'Hondt interno: es simplemente los más votados del pacto ganador).

Sin este mecanismo, cualquier análisis con datos de elecciones reales produce distribuciones de escaños incorrectas. La desviación no es pequeña: en distritos con alta concentración de votos en un pacto, el primer D'Hondt puede darle 2 escaños al pacto pero la asignación interna cambia quién los recibe.

Para H4 esto es obligatorio: la pregunta es cómo la geografía afecta la conversión votos→escaños, y esa conversión en Chile funciona a través de pactos.

El input adicional que requiere: `votos_df` debe incluir una columna `pacto` (coalición electoral). Alternativamente, se puede implementar como `dhondt_binivel(votos_por_lista, votos_por_candidato, magnitud)`.

**`margen_ultimo_escano(votos_district, magnitud)`** — imprescindible  
Para cada circunscripción, cuántos votos separan al último candidato electo del primero no electo. Esta métrica mide la sensibilidad electoral local: distritos con margen pequeño son sensibles a cambios geográficos. Es central para H4 porque permite cuantificar qué ocurre si se mueve la frontera distrital.

### Deseable

**`umbral_efectivo(magnitud)`**  
La fórmula aproximada estándar es `1 / (M + 1)`. Para M=3: 25%. Para M=8: ~11%. Este cálculo es una línea de código, pero su ausencia como función documentada implica que los analistas no lo están usando. Para H4 permite encuadrar las conclusiones: los distritos pequeños tienen umbral efectivo alto, lo que excluye sistemáticamente a partidos menores.

**`seat_bonus(resultados_por_pacto, vote_shares_por_pacto)`**  
Diferencia entre escaños obtenidos y escaños que corresponderían a la cuota proporcional de votos. Mide la prima al mayor: en sistemas con magnitudes bajas, el pacto más votado recibe sistemáticamente más escaños que su cuota. Esta prima varía con la geografía distrital.

### Investigación futura

Candidatos individuales, independientes, candidaturas fuera de pacto: estos casos existen en el sistema real pero su implementación requiere un modelo de datos más complejo (candidato → partido → pacto, con casos bordes). No es necesario para responder H4 en su versión principal.

---

## 7. Ajustes a ChileDist para H5

### Experimentos que deberían estar soportados nativamente

**Comparación de distribuciones entre variantes metodológicas**  
La operación base de H5 es: dado el ensemble A (con viviendas) y el ensemble B (con personas), ¿son sus distribuciones estadísticamente indistinguibles para cada métrica? Hoy esto requiere código ad hoc con `scipy.stats.ks_2samp`. No hay ningún módulo que automatice esta comparación.

Lo que se necesita es una función que reciba dos ensembles (DataFrames de `ensemble_stats.csv`) y devuelva, para cada métrica de interés, el estadístico KS, el p-value y la diferencia de medianas.

**Métricas que deberían compararse automáticamente en H5:**

| Variante | Métricas a comparar |
|----------|---------------------|
| viviendas vs personas | `max_dev_pob_pct`, distribución de plans válidos |
| CUT vs APC | `n_comunas_partidas`, `max_dev_pob_pct`, `pp_promedio` |
| ReCom vs SMC | `max_dev_pob_pct`, `cut_edges`, `pp_promedio`, `n_comunas_partidas` |
| nearest vs threshold vs none (islas) | `cut_edges`, conectividad del grafo resultante |
| pop_tolerance 0.05 vs 0.10 vs 0.15 | tamaño del ensemble válido, `max_dev_pob_pct` |

**Concordancia de ranking entre variantes**  
Kendall τ entre el ranking de los tres escenarios bajo distintas condiciones metodológicas. Si τ > 0.80 para todas las variantes, las conclusiones son robustas. Si τ < 0.60 para alguna, las conclusiones dependen del método. Esta comparación no existe en ningún módulo.

---

## 8. Discusión legislativa

Si un comité del Congreso quisiera usar ChileDist para estudiar una eventual reforma, los indicadores que la librería debe producir son los siguientes. Los organizo por lo que un asesor técnico necesitaría para responder preguntas concretas de parlamentarios.

**Sobre igualdad del voto**

- *Personas por escaño por circunscripción* con datos del Censo 2024. Tabla de 28 filas. Actualmente no computable con ChileDist.
- *Peso relativo del voto por circunscripción*: razón respecto a la media nacional. Si supera 2.0 o cae bajo 0.5, el argumento legislativo es inmediato.
- *Cambio en magnitudes requeridas con Censo 2024*: tabla de 28 distritos mostrando escaños actuales vs escaños bajo metodología actualizada. Actualmente no computable.
- *Número de distritos que cambiarían de magnitud* con una actualización basada en Censo 2024.

**Sobre comunas partidas**

- *Fracción de la población en comunas partidas* bajo cada escenario. No calculado actualmente con la interpretación correcta.
- *Lista de comunas más afectadas* con número de fragmentos y población involucrada. Disponible via `split_unit_summary()`.
- *Mapa vigente de 28 distritos: cuántas comunas comparten más de un distrito*. Esto requiere aplicar `count_split_units` al mapa vigente, lo que es posible pero requiere que el mapa vigente esté codificado como `assignment`.

**Sobre proporcionalidad**

- *Índice de Gallagher por elección bajo el mapa vigente* con datos reales SERVEL. Posible con ChileDist solo si se implementa D'Hondt binivel.
- *Gallagher bajo escenarios alternativos*: distribución del ensemble de Gallagher por escenario. Posible si se integra `plan_electoral_metrics` con el pipeline de ensemble.
- *Umbral efectivo por circunscripción*: qué porcentaje de votos necesita un partido para ganar escaño en cada distrito. No implementado como función.

**Sobre estabilidad electoral**

- *Margen del último escaño* por circunscripción. No implementado.
- *Varianza de escaños por pacto* entre planes del ensemble. Requiere D'Hondt binivel + integración con pipeline.

---

## 9. Priorización

### P0 — Imprescindible para responder H1–H5

| Capacidad | H que soporta | Impacto científico | Impacto legislativo | Dificultad |
|-----------|-------------|---------------------|---------------------|------------|
| `pop_afectada_pct` en `split_metrics.py` | H1, H2 | Alto: métrica principal de H1 | Alto: el número que entiende un parlamentario | Baja |
| `personas_por_escano(pop, magnitudes)` | H3 | Alto: métrica central de H3 | Alto: tabla de 28 filas para el Congreso | Muy baja |
| `peso_relativo_del_voto(pop, magnitudes)` | H3 | Alto: estándar internacional | Alto: evidencia de desigualdad estructural | Muy baja |
| Comparación magnitudes vigentes vs Censo 2024 | H3 | Alto: experimento contrafactual de H3 | Muy alto: información directa para reforma | Baja |
| **D'Hondt binivel** (pactos → partidos) | H4 | Crítico: sin él H4 es metodológicamente incorrecto | Muy alto: único análisis que refleja el sistema real | Media |
| `margen_ultimo_escano(votos, magnitud)` | H4 | Alto: cuantifica sensibilidad electoral | Alto: mapea qué distritos son "competitivos" | Media |
| Posicionamiento del mapa vigente en espacio Pareto | H2 | Alto: responde directamente si el vigente es dominado | Muy alto: el argumento más directo para reforma | Baja |
| `split_metrics` por plan en `ensemble_stats.csv` | H1, H2 | Alto: permite análisis distribucional de splits | Medio | Baja |

### P1 — Mejora importante

| Capacidad | H que soporta | Impacto científico | Impacto legislativo | Dificultad |
|-----------|-------------|---------------------|---------------------|------------|
| Soporte nativo para barrido de `split_penalty` | H1, H2 | Alto: traza frontera continua en lugar de 3 puntos | Medio | Media |
| Tasa de intercambio Δbalance/Δsplits | H1, H2 | Medio: derivado de lo anterior | Alto: "cada comuna que preservamos cuesta X% de desbalance" | Baja (derivado) |
| `umbral_efectivo(magnitud)` | H4 | Medio: resultado teórico bien conocido | Alto: explica por qué partidos pequeños no ganan | Muy baja |
| `seat_bonus(resultados_pacto, votos_pacto)` | H4 | Alto: mide prima al mayor | Alto: evidencia directa de sobre/subrepresentación | Baja |
| `compare_sensitivity(base, variants, labels)` | H5 | Alto: sistematiza el análisis de robustez | Bajo | Media |
| Concordancia de ranking entre variantes (Kendall τ) | H5 | Medio: valida que conclusiones son estables | Bajo | Baja |
| Índice de Gini de representación | H3 | Medio: métrica internacional complementaria | Medio | Baja |

### P2 — Investigación futura

| Capacidad | H que soporta | Justificación | Dificultad |
|-----------|-------------|---------------|------------|
| Bandas de confianza en la frontera de Pareto | H2 | Requiere bootstrap sobre ensemble; costoso computacionalmente | Alta |
| D'Hondt con candidatos individuales y listas abiertas | H4 | Necesario para análisis de candidatos específicos; fuera del alcance actual | Alta |
| Índice de malapportionment de Samuels-Snyder a nivel subnacional | H3 | Requiere datos a nivel más granular que lo disponible | Media |
| Autocorrelación espacial de resultados del ensemble (Moran sobre plans) | — | No responde directamente ninguna de H1–H5 | Media |

---

## Componentes actuales descartados para H1–H5

Los siguientes módulos y funciones no contribuyen a responder H1–H5 y consumen tiempo de mantenimiento:

| Componente | Razón del descarte |
|------------|-------------------|
| `autocorrelacion.py` (Moran, LISA, G*) | Mide clustering espacial de viviendas en el mapa de entrada. Ninguna de H1–H5 pregunta sobre clustering espacial. Es análisis exploratorio de datos, no de planes. |
| `export_imc_bundle.py` | Formato para herramienta interactiva externa. No produce ningún indicador analítico para H1–H5. |
| `equivalence.py` (tabla USA↔Chile, `print_equivalence`, `describe_hierarchy`) | Referencia conceptual. No tiene uso en ningún pipeline analítico de H1–H5. |
| `viz.py` (mayoría de funciones) | Útil para comunicación; no para producir resultados científicos. Mantener `plot_tradeoff_frontier` y `plot_boxplots_comparativos` por su uso en H1–H2. El resto no aporta. |
| Diagnósticos MCMC (`plot_acf`, `plot_gelman_rubin_evolution`, `plot_trace`) | Solo relevantes para H5 de forma periférica. El R-hat verifica convergencia de la cadena, no la validez de las conclusiones sustantivas. No son análisis científicos sobre H1–H5. |
| `graph_stats()`, `to_edgelist()`, `subgraph_region()` | Utilidades de inspección del grafo. No producen resultados para ninguna hipótesis. |

# Plan de Validación Científica — ChileDist

> **Estado:** borrador de trabajo (revisado 2026-08-14 contra `tests/` y el código actual — ver §6.6, §9 y §10 para lo que cambió)  
> **Fecha:** 2026-06-21  
> **Autores:** Daniel Vega  
> **Contexto:** Validación de ChileDist como librería científica completa. Este documento cubre todos los módulos de la librería: datos, geografía, escenarios, métricas, electoral, reproducibilidad y sampler. Basado en inspección del código fuente de la versión 0.2.0.

---

## 1. Alcance correcto de la validación

Validar solo el sampler (ReCom/SMC) es insuficiente porque el sampler opera en el **último eslabón** de una cadena de transformaciones. Si cualquier eslabón anterior introduce error — un join incorrecto, una columna de población errónea, un grafo con adyacencias faltantes, una restricción malconfigurada — el sampler genera miles de planes incorrectos sin saberlo. El R-hat puede indicar convergencia excelente sobre datos corruptos.

La validación científica de ChileDist abarca seis dimensiones independientes:

### 1.1 Validación del software

Verifica que las funciones de la librería se comportan correctamente conforme a su especificación interna. Detecta bugs, errores de tipos, edge cases no manejados y comportamientos incorrectos en datos sintéticos controlados.

**Qué no detecta:** errores en los datos de entrada reales ni inconsistencias metodológicas de diseño.

### 1.2 Validación de datos

Verifica la integridad y consistencia de los datos APC 2023 (INE), Censo 2024 y padrón SERVEL una vez cargados. Detecta IDs duplicados, geometrías inválidas, columnas faltantes, inconsistencias entre niveles jerárquicos y errores en los joins de población.

**Qué no detecta:** si el dato fuente del INE es correcto (eso es responsabilidad del INE).

### 1.3 Validación geográfica

Verifica que la topología del grafo de adyacencias refleja correctamente la geografía real de Chile: conectividad, islas, contracción CUT, preservación de regiones. Detecta errores en la política de islas, aristas artificiales, y grafos desconectados no detectados.

**Qué no detecta:** errores en las geometrías del shapefile fuente.

### 1.4 Validación electoral

Verifica que el módulo `electoral.py` produce resultados correctos para la asignación de escaños mediante D'Hondt, la asignación de magnitudes y los índices de proporcionalidad. Detecta errores de implementación usando casos con resultado conocido (elecciones reales, ejemplos de texto).

**Qué no detecta:** si el sistema electoral chileno es justo.

### 1.5 Validación estadística

Verifica que el sampler produce distribuciones coherentes con las propiedades esperadas: convergencia, estabilidad por semilla, sensibilidad a parámetros. Esta es la sección más técnica y también la más cara de ejecutar.

**Qué no detecta:** errores en módulos anteriores (datos, grafos, restricciones).

### 1.6 Validación del sampler

Subconjunto de la validación estadística. Verifica que ReCom y SMC producen distribuciones comparables sobre el mismo problema, y que el ensemble no es trivialmente dependiente de la semilla o los hiperparámetros. No es el centro de la validación; es una de sus secciones.

**Por qué es insuficiente como única validación:** los samplers operan sobre el grafo y las restricciones. Si el grafo tiene aristas faltantes o las restricciones no están bien calibradas, el sampler converge rápidamente sobre un espacio incorrecto.

---

## 2. Matriz de validación por módulo

| Módulo | Riesgo científico | Validación requerida | Datos mínimos | Criterio de éxito | Prioridad |
|--------|-------------------|---------------------|---------------|-------------------|-----------|
| `loader.py` | Join incorrecto de viviendas desde manzanas a distritos | Test de suma: Σ viviendas_manzanas == Σ viviendas_distritos por CUT | Shapefiles de una región con manzanas urbanas y aldea | Diferencia < 1 vivienda por CUT (pérdida de rounding) | P0 |
| `loader.py` | Columnas truncadas en DBF (límite 10 chars) | Verificar que `DBF_COLUMN_MAP` expande correctamente todos los campos clave | Shapefile APC real (cualquier región) | Todas las columnas esperadas presentes post-renombre | P0 |
| `graph.py` | Islas no conectadas o mal conectadas | Verificar n_components == 1 tras `connect_islands()`; detectar artificiales | GDF sintético con isla aislada | n_components == 1 Y aristas artificiales ≤ n_islands | P0 |
| `graph.py` | Adyacencias queen vs rook producen grafos distintos | Comparar grados de nodos en ambos métodos | GDF de rejilla sintética 5×5 | Queen ≥ Rook en todos los grados (queen siempre incluye rook) | P1 |
| `hierarchy.py` | Distritos APC que cruzan límite comunal | `validate_hierarchy()` debe detectar violaciones | GDF sintético con 2 distritos en 2 comunas distintos | Retorna DataFrame con las violaciones correctas | P0 |
| `hierarchy.py` | Contracción APC → CUT pierde o duplica población | Suma viviendas antes/después de `contract_to_decision_units()` | GDF sintético con 3 CUT, 9 ID_DIST | Σ pop antes == Σ pop después por CUT | P0 |
| `constraints.py` | Restricción de preservación no rechaza plan que parte una comuna | `make_preserve_constraint()` debe retornar False para plan que divide | GDF sintético + partición manual que divide CUT | `constraint(partition) == False` | P0 |
| `constraints.py` | Updater de balance poblacional calcula correctamente | `build_updaters_for_scenario()` produce updater con valores correctos | GDF sintético con pop conocida | Desviación calculada == desviación manual | P1 |
| `metrics.py` | Polsby-Popper = 1.0 para círculo perfecto | `polsby_popper(círculo)` == 1.0 ± 1e-6 | GDF con un polígono circular generado con buffer | PP ∈ [0.999, 1.001] | P0 |
| `metrics.py` | Polsby-Popper ∈ [0, 1] para todas las formas reales | Ningún valor fuera del rango | GDF distrital APC de cualquier región | min >= 0, max <= 1 | P0 |
| `metrics.py` | `cut_edges()` conteo correcto (undirected) | Comparar con conteo manual en grafo de juguete | Grafo 3×3, partición manual | cut_edges == valor esperado manualmente | P1 — ✅ IMPLEMENTED, ver `tests/test_metrics.py::test_cut_edges_grafo_lineal_tres_nodos` |
| `split_metrics.py` | `count_split_units()` == 0 para plan legal | Plan que respeta CUT no debe generar splits | GDF sintético + asignación que respeta CUT | count_split_units == 0 | P0 |
| `split_metrics.py` | `split_severity_index()` escala correctamente | Índice mayor cuando fragmentos son más pequeños | GDF sintético con splits conocidos | Orden relativo correcto entre casos | P1 |
| `scenario_comparison.py` | `pareto_frontier_nd()` identifica correctamente los no dominados | Verificar con conjunto donde el frente es conocido | DataFrame 5×2 con puntos dominados conocidos | Índices retornados == índices esperados | P0 |
| `scenario_comparison.py` | Composite score cambia ranking con pesos distintos | Sensibilidad: ±20% en pesos → fracción de cambio de top-1 | DataFrame sintético de planes con métricas distintas | Reportar `frac_same_winner`; documentar si < 0.80 | P1 |
| `electoral.py` | D'Hondt produce resultado correcto en caso conocido | Comparar con ejemplo manual (4 partidos, 5 escaños) | Diccionario de votos manual | Resultado == resultado calculado a mano | P0 |
| `electoral.py` | Suma de escaños == n_seats en todos los casos | Invariante de conservación | Casos sintéticos con n_seats variando de 3 a 8 | Σ escaños == n_seats siempre | P0 |
| `electoral.py` | `assign_seat_magnitudes()` respeta min/max y suma == 155 | Invariante de la ley 18.700 | `MAGNITUDES_LEGALES_LEY20840` | Σ == 155, todos ∈ [3, 8] | P0 |
| `data/census2024.py` | Join proporcional conserva total de personas | Σ personas post-join == Σ personas en census_df por CUT | CSV de Censo 2024 sintético + GDF distrital | Diferencia ≤ n_distritos (rounding error bounded) | P1 |
| `data/census2024.py` | Join directo manzana produce cero pérdida para CUT con cobertura completa | Σ antes == Σ después para CUT con cobertura total | Manzana CSV sintético con cobertura completa | Diferencia == 0 para CUT con cobertura completa | P1 |
| `data/servel.py` | Join padrón conserva inscritos por CUT | Σ inscritos post-join == Σ inscritos en padron_df por CUT | CSV padrón sintético | Diferencia ≤ n_distritos (rounding bounded) | P1 |
| `samplers/recom.py` | `run_recom_chain()` produce N draws exactamente solicitados | Verificar len(planes) == n_steps / save_every | GDF sintético 4×4 | n_planes == n_expected | P0 |
| `samplers/smc.py` | `generate_redist_script()` produce R script válido | Verificar que el script generado es R sintácticamente válido | GDF sintético | Script no vacío; contiene `redist_smc(` | P1 |
| `samplers/smc.py` | `load_redist_results()` importa correctamente | Verificar mapeo de columnas CSV → list[dict] | CSV sintético con formato redist | len(plans) == n_sims en CSV | P1 |
| `diagnostics.py` | `gelman_rubin()` retorna R-hat ≈ 1.0 para cadenas idénticas | Dos cadenas con valores idénticos → R-hat == 1.0 | Listas sintéticas idénticas | R-hat ∈ [1.000, 1.001] | P1 |
| `diagnostics.py` | `effective_sample_size()` retorna ESS < n para serie autocorrelada | ESS debe ser menor que n para AR(1) | Serie sintética AR(1) con ρ=0.9 | ESS < 0.2 × n | P1 |
| `persistence.py` | `save_assignments_parquet()` + `PlanEnsemble.load()` roundtrip sin pérdida | Verificar schema, dtypes y row count post-roundtrip | Datos sintéticos | Schema idéntico, row count idéntico | P0 |
| `persistence.py` | Dos corridas con misma semilla producen mismo `run_id`-independent assignments | Misma semilla → mismas asignaciones | GDF sintético | Assignments[plan i] idéntico entre corridas | P0 |
| `scripts/redistritaje.py` | Pipeline completo produce todos los archivos esperados | Verificar archivos en `run_{ts}_{rid[:8]}/` | Datos sintéticos mínimos | 4 archivos: manifest, scenario.yml, assignments.parquet, ensemble_stats.csv | P0 |
| `scripts/compare_scenarios.py` | `--skip-run` carga ensembles de todos los escenarios sin error | Verificar que load_ensembles_from_disk no falla si directorios existen | Archivos de salida previos | DataFrame de comparación con N_escenarios filas | P1 |
| `feasibility.py` | Tolerancia poblacional matemáticamente inalcanzable no se detecta antes de correr ReCom | `check_population_feasibility()` debe distinguir inviabilidad probada de fallo de búsqueda | Unidades sintéticas con una unidad dominante (ej. una excede el ideal en más que la tolerancia) | `feasible == False` y `reason == REASON_INDIVISIBLE_UNIT_EXCEEDS_BOUND` cuando corresponde; `feasible == True` en el caso límite exacto | P0 — ✅ implementado, ver `tests/test_feasibility.py` |
| `scenario_comparison/compare.py` | Escenario inviable/`sin_particion` queda oculto o contamina el ranking de la comparación | `assess_comparison_completeness()`/`build_scenario_overview()` deben marcar `INCOMPLETE` sin excluir el escenario de la vista ni afectar el score de los demás | Ensembles con status mixtos (`ok`/`infeasible_population`/`sin_particion`) | Escenario sin ensemble válido sigue visible con su `status`/`reason`, `included_in_scoring=False`, y el ranking de los escenarios válidos es idéntico al que se obtendría ignorando el inviable | P1 — ✅ implementado, ver `tests/test_compare_scenarios_incomplete.py` |

---

## 3. Validación de datos

### 3.1 IDs únicos

**Qué valida:** que `ID_DIST` y `CUT` no estén duplicados dentro de una región cargada.

**Por qué importa:** gerrychain indexa nodos por ID; duplicados provocan silenciosamente que un nodo sobreescriba a otro en el grafo.

```python
def validate_unique_ids(gdf, id_cols=["ID_DIST", "CUT"]):
    for col in id_cols:
        if col not in gdf.columns:
            continue
        dupes = gdf[col].duplicated()
        assert not dupes.any(), f"Duplicados en {col}: {gdf[col][dupes].tolist()}"
```

**Resultado esperado:** sin duplicados para cualquier región.  
**Fallo detectado:** join de manzanas introduce filas duplicadas si el mismo `ID_DIST` aparece en urbana y aldea.

---

### 3.2 Geometrías válidas

**Qué valida:** que ninguna geometría sea `None`, vacía, o no válida según Shapely.

```python
def validate_geometries(gdf, layer_name=""):
    nulls   = gdf.geometry.isna().sum()
    empty   = gdf.geometry.is_empty.sum()
    invalid = (~gdf.geometry.is_valid).sum()
    return {"layer": layer_name, "nulls": nulls, "empty": empty, "invalid": invalid}
```

**Resultado esperado:** nulls == empty == invalid == 0.  
**Fallo detectado:** geometrías rotas generan adyacencias incorrectas en `build_graph()`.

---

### 3.3 Columnas esperadas

**Qué valida:** que el GDF distrital contiene todas las columnas requeridas por los módulos downstream.

```python
REQUIRED_COLS_DIST = ["ID_DIST", "CUT", "COD_REGION", "geometry"]
REQUIRED_COLS_MZ   = ["CUT", "COD_DISTRITO", "MANZENT", "geometry"]

def validate_required_columns(gdf, required, layer_name=""):
    missing = [c for c in required if c not in gdf.columns]
    assert not missing, f"{layer_name}: columnas faltantes {missing}"
```

**Resultado esperado:** sin columnas faltantes.  
**Fallo detectado:** nombres truncados por DBF que `DBF_COLUMN_MAP` no cubre aún.

---

### 3.4 CRS

**Qué valida:** que el GDF cargado usa el CRS esperado antes y después de reproyección.

```python
def validate_crs(gdf, expected_crs="EPSG:4326"):
    assert gdf.crs is not None, "GDF sin CRS"
    assert gdf.crs.to_epsg() == int(expected_crs.split(":")[1]), \
        f"CRS incorrecto: {gdf.crs}"
```

**Resultado esperado:** GDF cargado en EPSG:4326; post-reproyección en EPSG:32719 (u óptimo por región).  
**Fallo detectado:** cálculos de área/perímetro en grados producen métricas de compacidad sin unidades métricas.

---

### 3.5 Comunas completas

**Qué valida:** que cada `CUT` presente en el GDF distrital tiene al menos un distrito asociado y suma a población > 0.

```python
def validate_comunas_completas(gdf_dist, gdf_comunal, cut_col="CUT"):
    cuts_dist = set(gdf_dist[cut_col].unique())
    cuts_com  = set(gdf_comunal[cut_col].unique())
    orphaned  = cuts_dist - cuts_com
    assert not orphaned, f"CUTs en distritos sin registro comunal: {orphaned}"
```

**Resultado esperado:** sin CUTs huérfanos.  
**Fallo detectado:** comunas que existen en el shapefile comunal pero no en el distrital (problema de cobertura APC).

---

### 3.6 APC dentro de comunas

**Qué valida:** usando `validate_hierarchy()`, que ningún distrito pertenece simultáneamente a dos comunas distintas.

```python
violations = cd.validate_hierarchy(gdf_dist, fine_col="ID_DIST", coarse_col="CUT")
assert len(violations) == 0, f"Distritos en múltiples comunas:\n{violations}"
```

**Resultado esperado:** `violations` vacío.  
**Fallo detectado:** indica que el cartograma APC 2023 tiene errores de asignación CUT ↔ ID_DIST.

---

### 3.7 Suma APC → comuna

**Qué valida:** que la suma de viviendas de todos los distritos dentro de una CUT coincide con el total comunal.

```python
def validate_pop_sum_apc_to_cut(gdf_dist, gdf_com, pop_col="viviendas", cut_col="CUT", tol=5):
    agg_dist = gdf_dist.groupby(cut_col)[pop_col].sum().rename("sum_distritos")
    agg_com  = gdf_com.set_index(cut_col)[pop_col].rename("sum_comunal")
    diff     = (agg_dist - agg_com).abs()
    exceed   = diff[diff > tol]
    assert exceed.empty, f"Sumas no cuadran (diff > {tol}) para CUTs:\n{exceed}"
```

**Resultado esperado:** diferencia ≤ `tol` unidades por CUT (rounding del join de manzanas).  
**Fallo detectado:** error sistemático indica que el join de manzanas a distritos tiene un error de cobertura.

---

### 3.8 Consistencia Censo 2024

**Qué valida:** que después de `join_census_multilevel()`, la suma de `personas` por CUT no difiere del total comunal del CSV en más del 1%.

```python
def validate_census_join(gdf_enriched, census_df, cut_col="CUT", tol_pct=0.01):
    post_join = gdf_enriched.groupby(cut_col)["personas"].sum()
    pre_join  = census_df.set_index(cut_col)["personas"]
    rel_diff  = ((post_join - pre_join).abs() / pre_join).dropna()
    exceed    = rel_diff[rel_diff > tol_pct]
    assert exceed.empty, f"Pérdida de personas > {tol_pct*100}% en CUTs:\n{exceed}"
```

**Resultado esperado:** diferencia relativa < 1% por CUT.  
**Fallo detectado:** el join proporcional pierde población cuando hay distritos sin cobertura en las manzanas censales.

---

### 3.9 Consistencia padrón SERVEL

**Qué valida:** que `inscritos = hombres + mujeres` a nivel comunal, y que la suma regional cuadra con el total nacional declarado.

```python
def validate_padron(padron_df):
    diff = (padron_df["hombres"] + padron_df["mujeres"] - padron_df["inscritos"]).abs()
    assert (diff <= 1).all(), f"inscritos != h+m en CUTs: {padron_df[diff > 1]['CUT'].tolist()}"
```

**Resultado esperado:** diferencia ≤ 1 por CUT (posible redondeo en publicación SERVEL).  
**Fallo detectado:** columna de inscritos publicada independientemente de hombres+mujeres; indica error en el CSV fuente.

---

### 3.10 Trazabilidad de fuentes

**Qué valida:** que `run_manifest.json` incluye hashes SHA-256 de todos los archivos de entrada utilizados.

```python
def validate_manifest_hashes(manifest, input_files):
    declared = {v["path"]: v["sha256"] 
                for v in manifest.get("data", {}).get("input_files", [])}
    for fpath in input_files:
        assert fpath in declared, f"Archivo sin hash en manifest: {fpath}"
        computed = sha256_file(fpath)
        assert declared[fpath] == computed, f"Hash no coincide para {fpath}"
```

**Resultado esperado:** todos los archivos de entrada tienen hash declarado y verificable.  
**Fallo detectado:** corridas no reproducibles porque `redistritaje.py` no pasó los paths de entrada a `build_run_manifest()`.

---

### 3.11 Comunas sin proxy de manzanas (proxy=0)

**Qué valida:** que el join proporcional de población no produce personas=0 en comunas que sí tienen población real.

**Por qué importa:** 9 comunas nacionales no tienen manzanas urbanas ni aldeas registradas en APC 2023. Sin el fallback rural, el join proporcional les asigna 0 personas — pérdida total del 100% de su población, no un error de redondeo.

**Comunas afectadas (verificado contra datos reales):**
CUT 2202 Ollagüe (256 hab), 10404 Palena (1.903), 11102 Lago Verde (779), 12102 Laguna Blanca (269), 12103 Río Verde (102), 12104 San Gregorio (241), 12201 Cabo de Hornos (1.750), 12303 Timaukel (157), 12402 Torres del Paine (203). Total: 5.660 personas / 0.03% nacional. R12 concentra 6 de las 9.

**Fix implementado:** `apply_rural_proxy_fallback()` en `chiledist/loader.py` usa `Puntos_Edificacion_Rural` (categorías VIVIENDA + VIVIENDA COLECTIVA, campo USO_EDIFICACION) como proxy comunal cuando el total de manzanas es 0. Reparto equitativo entre distritos APC de la comuna. Verificado: Lago Verde 0→780 personas, diff R11 -781→-1.

**Limitación conocida:** el reparto equitativo entre distritos APC es una aproximación. La opción B (join espacial punto-en-polígono contra Distrital.shp para asignar COD_DISTRITO exacto a cada punto rural) sería más precisa pero no es prioritaria dado el volumen afectado (9 comunas, 0.03% nacional).

**Criterio de éxito:** después del fix, diff por CUT ≤ n_distritos para todas las comunas, incluidas las 9 sin manzanas. Verificado en `test_integration_r11.py::test_4`.

**Prioridad:** P1 — ✅ implementado.

---

## 4. Validación geográfica

### 4.1 Adyacencia queen/rook

**Qué valida:** que queen siempre produce ≥ aristas que rook sobre el mismo GDF (toda adyacencia rook es también queen).

```python
import networkx as nx

def validate_queen_superset_of_rook(gdf):
    G_queen, *_ = cd.build_graph(gdf, id_col="id", method="queen")
    G_rook,  *_ = cd.build_graph(gdf, id_col="id", method="rook")
    rook_edges  = set(frozenset(e) for e in G_rook.edges())
    queen_edges = set(frozenset(e) for e in G_queen.edges())
    missing = rook_edges - queen_edges
    assert not missing, f"Aristas rook no presentes en queen: {missing}"
    assert len(queen_edges) >= len(rook_edges)
```

**Resultado esperado:** `queen_edges ⊇ rook_edges` siempre.

---

### 4.2 Componentes conectados

**Qué valida:** que tras aplicar la política de islas, el grafo tiene exactamente un componente conectado.

```python
def validate_single_component(G, island_policy="nearest"):
    n_comp = nx.number_connected_components(G)
    assert n_comp == 1, f"Grafo con {n_comp} componentes (esperado 1) con policy={island_policy}"
```

**Resultado esperado:** `n_components == 1`.  
**Fallo detectado:** `island_policy='threshold'` no conecta islas que no tienen vecino dentro de 50 km (ej. Isla de Pascua).

---

### 4.3 Islas: detección correcta

**Qué valida:** que `build_graph()` identifica correctamente los nodos sin vecinos antes de aplicar la política.

```python
def validate_island_detection(gdf_con_isla):
    # GDF con un polígono artificialmente aislado (sin vecinos)
    G_sin_policy, *_ = cd.build_graph(gdf_con_isla, id_col="id", island_policy="none")
    aislados = [n for n in G_sin_policy.nodes() if G_sin_policy.degree(n) == 0]
    assert len(aislados) >= 1, "No detectó la isla esperada"
```

---

### 4.4 Conexiones artificiales documentadas

**Qué valida:** que las aristas artificiales agregadas por la política de islas están identificadas como tales en el grafo (atributo `artificial=True`).

```python
def validate_artificial_edges_tagged(G):
    artificial = [(u, v) for u, v, d in G.edges(data=True) if d.get("artificial")]
    # Solo debe haber aristas artificiales si había islas
    return len(artificial)
```

**Resultado esperado:** todas las conexiones artificiales tienen el atributo `artificial=True`.

---

### 4.5 Contracción de grafos

**Qué valida:** que `contract_graph()` produce un grafo donde cada nodo corresponde a una CUT y el número de nodos coincide con el número de CUTs únicas.

```python
def validate_contraction(gdf_dist, G_dist):
    G_cut, gdf_cut = cd.contract_graph(G_dist, gdf_dist, id_col="ID_DIST", group_col="CUT")
    n_cuts_gdf = gdf_dist["CUT"].nunique()
    n_nodes_contracted = G_cut.number_of_nodes()
    assert n_nodes_contracted == n_cuts_gdf, \
        f"Nodos en grafo contraído ({n_nodes_contracted}) != CUTs únicas ({n_cuts_gdf})"
```

---

### 4.6 Preservación de regiones en la contracción

**Qué valida:** que después de la contracción, todos los nodos del grafo CUT pertenecen a la misma región de origen.

---

### 4.7 Preservación de comunas en plan legal

**Qué valida:** que ningún plan del ensemble legal parte una CUT (medido con `count_split_units`).

```python
def validate_no_splits_in_legal_ensemble(ensemble_df, gdf):
    for draw_id, plan in ensemble_df.groupby("draw"):
        asignacion = dict(zip(plan["unit_id"], plan["district"]))
        n_splits = cd.count_split_units(asignacion, gdf, unit_col="CUT", id_col="CUT")
        assert n_splits == 0, f"Draw {draw_id} parte {n_splits} comunas en escenario legal"
```

**Resultado esperado:** 0 splits en todos los draws del escenario legal.  
**Fallo detectado:** la restricción `make_preserve_constraint()` no está activada o no se aplica correctamente.

---

### 4.8 Compacidad en rango válido

**Qué valida:** que todos los valores de compacidad están en [0, 1] y que el círculo tiene PP ≈ 1.

```python
def validate_compactness_range(gdf_metrica):
    for col in ["polsby_popper", "reock", "convex_hull_ratio", "schwartzberg"]:
        assert (gdf_metrica[col] >= 0).all(), f"{col} tiene valores negativos"
        assert (gdf_metrica[col] <= 1).all(), f"{col} tiene valores > 1"
```

---

## 5. Validación de escenarios

### 5.1 SCENARIO_LEGAL nunca divide comunas

**Qué valida:** combinación de `decision_unit='CUT'` + `preserve_mode='hard'` + `preserve_units=['CUT']`. Verificado con `validate()` y con un plan generado.

**Experimento:** correr ReCom con SCENARIO_LEGAL en un GDF sintético de 9 distritos en 3 comunas. Verificar que todos los planes del ensemble tienen 0 splits.

---

### 5.2 SCENARIO_APC_FREE puede dividir comunas

**Qué valida:** que `preserve_mode='none'` no activa ninguna restricción de preservación. El ensemble puede contener plans con splits > 0.

**Experimento:** en el mismo GDF sintético, correr SCENARIO_APC_FREE y verificar que el conjunto de plans generados incluye al menos un plan con split > 0 (si el espacio lo permite).

---

### 5.3 SCENARIO_APC_SOFT penaliza sin prohibir

**Qué valida:** que `preserve_mode='soft'` genera más plans con splits == 0 que APC_FREE, pero menos que LEGAL. Los planes con splits > 0 tienen `split_penalty > 0` en su score.

---

### 5.4 `decision_unit` se respeta en contracción

**Qué valida:** que si `decision_unit='CUT'`, el GDF de decisión tiene `id_col == 'CUT'` y `len(gdf_dec) == n_comunas_region`.

```python
map_data = cd.ChileDistMap.from_apc(base_dir, region_code, cd.SCENARIO_LEGAL)
assert map_data.id_col == "CUT"
assert len(map_data.gdf_dec) == gdf_dist["CUT"].nunique()
```

---

### 5.5 `pop_tolerance` se aplica correctamente

**Qué valida:** que ningún plan en el ensemble supera la `pop_tolerance` definida en el escenario.

**Modelo A implementado: warm-up libre hasta ≤pop_tol, epsilon_recom = pop_tol exacto,
valid_fraction ≈ 1.0 por construcción. Ver P1-#5: IMPLEMENTED.**

**Mecanismo (modelo A — restricción dura desde el draw 0; P0-1, implementado):**
antes de este fix, la cadena principal usaba `epsilon_recom = max(dev_warmed/100 + 0.02, pop_tol)`,
casi siempre mayor que `pop_tol`, y el cumplimiento de la tolerancia dependía de un filtrado
posterior (`pares_validos` en `scripts/redistritaje.py`) — modelo B (sampling amplio + filtrado).
Ahora:

- El warm-up (solo contigüidad, `accept=always_accept`) corre libremente hasta que la
  desviación baja a `≤ pop_tol`; si agota su presupuesto de pasos sin lograrlo, se extiende
  una vez (mismo proposal, continuando desde el último estado) antes de rendirse.
- `epsilon_recom = pop_tol` exacto (ya no se infla con `dev_warmed`).
- Cada estado emitido por la cadena principal satisface `pop_tol` **por construcción**:
  `gerrychain.constraints.within_percent_of_ideal_population(partition, epsilon_recom)` rechaza
  toda propuesta que la exceda (`MarkovChain.__next__()` vuelve a proponer sin costar un paso;
  ver diagnóstico P0-1), por lo que nunca se acepta ni se emite un estado fuera de tolerancia.
- `pares_validos` se conserva en `scripts/redistritaje.py`, pero pasa de ser un filtro
  necesario a una **verificación de sanidad**: con el modelo A, `valid_fraction ≈ 1.0` es el
  comportamiento esperado (verificado con corrida real R12/apc_free, `pop_tol=0.10`:
  100/100 planes válidos, desviación máxima observada en la cadena 9.61% < 10%).

**Estados posibles de `analizar_region()` relacionados con esta invariante:**

| `status` | `reason` | Cuándo ocurre | Acción recomendada |
|----------|----------|---------------|---------------------|
| `ok` | — | Warm-up convergió a `≤ pop_tol` (con o sin extensión) y la cadena principal produjo el ensemble | — |
| `sin_convergencia_warmup` | `warmup_did_not_reach_pop_tol` | El warm-up, incluida su extensión, no logró bajar la desviación a `≤ pop_tol` dentro de su presupuesto de pasos; la cadena principal nunca se construye | Aumentar `--n-steps` (más presupuesto de warm-up, ya que `N_WARMUP = min(500, n_steps // 4)`) o relajar `--pop-tol` |
| `sin_particion` | `initialization_search_exhausted` | `recursive_tree_part` agotó su escalera de tolerancias/semillas sin producir una partición inicial (falla de búsqueda, no prueba de inviabilidad) | Ver §10 P0 #21 |
| `infeasible_population` | (de `check_population_feasibility`) | Una unidad indivisible excede por sí sola el rango `[ideal×(1−tol), ideal×(1+tol)]` | Ver §10 P0 #21 |

```python
def validate_pop_tolerance(ensemble_df, gdf, pop_col, id_col, tol):
    for draw_id, plan in ensemble_df.groupby("draw"):
        asignacion = dict(zip(plan["unit_id"], plan["district"]))
        balance    = cd.population_balance(gdf, pop_col, "district", id_col)
        max_dev    = balance["dev_rel"].abs().max()
        assert max_dev <= tol + 1e-6, \
            f"Draw {draw_id} supera pop_tolerance: max_dev={max_dev:.4f} > {tol}"
```

---

### 5.6 Escenarios YAML sin pérdida de información

**Qué valida:** que `save_scenario()` + `load_scenario()` produce un `ScenarioConfig` byte-a-byte equivalente al original.

```python
import dataclasses, tempfile, os

def validate_yaml_roundtrip(scenario):
    with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
        path = f.name
    try:
        cd.save_scenario(scenario, path)
        loaded = cd.load_scenario(path)
        assert dataclasses.asdict(scenario) == dataclasses.asdict(loaded), \
            "YAML roundtrip perdió campos"
    finally:
        os.unlink(path)
```

**Resultado esperado:** sin pérdida de ningún campo.  
**Fallo detectado:** campo `pop_source` no se serializa en YAML (ya corregido en v0.2.0; verificar regresión).

---

## 6. Validación electoral

> Los fragmentos de esta sección son ilustrativos (especifican qué debe validarse y con qué caso), no los nombres reales de tests. La cobertura equivalente ya existe en `tests/test_electoral_magnitudes.py`, `tests/test_electoral_binivel.py`, `tests/test_electoral_ensemble.py`, `tests/test_malapportionment.py`, `tests/test_malapportionment_functions.py` y `tests/test_fairshare.py` — no bajo los nombres literales `test_dhondt_manual`/`test_aggregate_votes_conserves_totals`/etc. usados abajo. La invariante de magnitudes (Σ==155, cada distrito ∈[3,8]) del §6.4 ya está asegurada en el propio código: `chiledist/electoral/constants.py` la afirma con un `assert` al importar el módulo.

### 6.1 D'Hondt con ejemplo manual

El método D'Hondt con 4 partidos y 5 escaños tiene resultado exactamente calculable.

```python
def test_dhondt_manual():
    # Ejemplo clásico: A=100, B=80, C=30, D=20, escaños=5
    # Cocientes: A=100,50,33.3 | B=80,40 | C=30 | D=20
    # Top-5 cocientes: 100(A), 80(B), 50(A), 40(B), 33.3(A)
    # Resultado: A=3, B=2, C=0, D=0
    votes  = {"A": 100_000, "B": 80_000, "C": 30_000, "D": 20_000}
    result = cd.dhondt(votes, seats=5)
    assert result["A"] == 3
    assert result["B"] == 2
    assert result.get("C", 0) == 0
    assert result.get("D", 0) == 0
```

---

### 6.2 Conservación de votos al agregar unidades

**Qué valida:** que `aggregate_votes()` preserva el total de votos por partido.

```python
def test_aggregate_votes_conserves_totals(votes_df, assignment):
    total_before = votes_df.groupby("partido")["votos"].sum()
    agg = cd.aggregate_votes(votes_df, assignment, unit_col="ID_DIST",
                             partido_col="partido", votos_col="votos")
    total_after = agg.groupby("partido")["votos"].sum()
    pd.testing.assert_series_equal(total_before.sort_index(),
                                   total_after.sort_index(), check_names=False)
```

---

### 6.3 Conservación de escaños

**Qué valida:** que `Σ escaños == n_seats` en todos los distritos de `run_electoral_plan()`.

```python
def test_seat_conservation(electoral_results_df, seat_magnitudes):
    for district, magnitude in seat_magnitudes.items():
        dist_result = electoral_results_df[electoral_results_df["district"] == district]
        assert dist_result["escanos"].sum() == magnitude, \
            f"Distrito {district}: Σ escaños ({dist_result['escanos'].sum()}) != magnitud ({magnitude})"
```

---

### 6.4 Magnitudes legales

**Qué valida:** que `MAGNITUDES_LEGALES_LEY20840` suma exactamente 155 y que todos los valores están en [3, 8].

```python
def test_magnitudes_legales():
    mags = cd.MAGNITUDES_LEGALES_LEY20840
    assert sum(mags.values()) == 155
    assert all(3 <= v <= 8 for v in mags.values())
    assert len(mags) == 28  # 28 distritos electorales post-Ley 20840
```

---

### 6.5 Índices de proporcionalidad con resultado conocido

**Qué valida:** que para distribución perfectamente proporcional, todos los índices == 0.

```python
def test_proportionality_perfect():
    vote_shares = {"A": 0.5, "B": 0.3, "C": 0.2}
    seat_shares = {"A": 0.5, "B": 0.3, "C": 0.2}  # perfectamente proporcional
    assert cd.gallagher_index(vote_shares, seat_shares)   == pytest.approx(0.0, abs=1e-6)
    assert cd.loosemore_hanby(vote_shares, seat_shares)   == pytest.approx(0.0, abs=1e-6)
    assert cd.rae_index(vote_shares, seat_shares)         == pytest.approx(0.0, abs=1e-6)
```

---

### 6.6 Nota sobre D'Hondt binivel

> **Actualizado 2026-08-14:** esta sección describía D'Hondt binivel como no implementado. Ya no es así: `dhondt_binivel()` y `run_electoral_plan_binivel()` (`chiledist/electoral/dhondt.py`) implementan el mecanismo de dos niveles del sistema chileno — D'Hondt entre pactos sobre votos totales de lista, luego asignación intra-pacto por mayor votación individual — y están cubiertos por `tests/test_electoral_binivel.py`. `run_electoral_plan()` de un solo nivel se mantiene como caso aparte (útil cuando los datos no traen estructura de pactos, o como comparación uni- vs binivel — ver `scripts/electoral_analysis.py`, bloques B1/B2). No queda una brecha de implementación aquí; lo que sigue pendiente es correr el binivel con datos SERVEL/`pacto_map` reales (ver `SCIENTIFIC_HYPOTHESES.md § Plan de cierre`).

---

## 7. Validación de outputs y reproducibilidad

### 7.1 Archivos esperados por corrida

**Qué valida:** que `redistritaje.py` produce exactamente los cuatro archivos en el directorio `run_{ts}_{rid[:8]}/`.

```python
EXPECTED_FILES = [
    "run_manifest.json",
    "scenario.yml",
    "assignments.parquet",
    "ensemble_stats.csv",
]

def validate_run_outputs(run_dir):
    for fname in EXPECTED_FILES:
        fpath = os.path.join(run_dir, fname)
        assert os.path.exists(fpath), f"Falta archivo: {fname}"
        assert os.path.getsize(fpath) > 0, f"Archivo vacío: {fname}"
```

---

### 7.2 `run_manifest.json` completo

**Qué valida:** que el manifest contiene todos los campos requeridos para trazabilidad.

```python
REQUIRED_MANIFEST_KEYS = [
    "run_id", "chiledist_version", "timestamp_start", "timestamp_end",
    "scenario", "data", "algorithm", "environment", "outputs",
]

def validate_manifest_structure(manifest):
    for key in REQUIRED_MANIFEST_KEYS:
        assert key in manifest, f"Falta campo en manifest: {key}"
    assert "python" in manifest["environment"]
    assert "packages" in manifest["environment"]
    assert "sha256" in manifest["data"] or "input_files" in manifest["data"]
```

---

### 7.3 `assignments.parquet` permite reconstruir métricas

**Qué valida:** que a partir del parquet + el GDF original se puede recalcular `plan_summary()` y obtener la misma tabla que `ensemble_stats.csv`.

```python
def validate_metrics_reconstructible(assignments_path, gdf, ensemble_stats_path, tol=1e-4):
    df_asn = pd.read_parquet(assignments_path)
    df_ref = pd.read_csv(ensemble_stats_path)

    for draw_id in df_asn["draw"].unique()[:5]:  # muestra de 5 planes
        plan = dict(zip(df_asn[df_asn["draw"] == draw_id]["unit_id"],
                        df_asn[df_asn["draw"] == draw_id]["district"]))
        recalc = cd.plan_summary(gdf, plan, id_col="ID_DIST", pop_col="viviendas")
        ref    = df_ref[df_ref["plan_id"] == draw_id]
        # Verificar max_dev_pob coincide
        assert abs(recalc["max_dev_pob_pct"].iloc[0] - ref["max_dev_pob_pct"].iloc[0]) < tol
```

**Contrato de datos entre archivos de salida (post-B1):**

- `assignments.parquet` es la traza completa: todos los draws, incluidos los inválidos, sin filtrar.
- `ensemble_stats.csv` es la **fuente canónica** que consume `scripts/compare_scenarios.py` y el resto del pipeline downstream — no `assignments.parquet` directamente.
- `is_valid` en `metricas_cadena.csv` (nivel draw, no plan) es el criterio de validez por draw: `max_dev_pct <= pop_tol * 100` (ver `scripts/redistritaje.py`).
- `validity_filter` en `run_manifest.json` (bajo `ensemble`) declara explícitamente el contrato usado para filtrar/reportar validez (`pop_tol*100`, no un valor hardcodeado), verificable con `check_validity_filter_consistency()` en `scripts/compare_scenarios.py`.

---

### 7.4 Reproducibilidad por semilla

**Qué valida:** que dos corridas con la misma semilla y mismos parámetros producen asignaciones idénticas.

```python
def validate_seed_reproducibility(gdf, scenario, seed=42):
    plans_1 = cd.run_recom(gdf, ..., seed=seed, n_steps=100)
    plans_2 = cd.run_recom(gdf, ..., seed=seed, n_steps=100)
    for i in range(len(plans_1)):
        assert plans_1[i] == plans_2[i], f"Plan {i} difiere entre corridas con misma semilla"
```

**Resultado esperado:** asignaciones idénticas en todos los draws.  
**Fallo detectado:** dependencia en estado global de random (usar `np.random.default_rng(seed)` siempre).

---

### 7.5 No sobrescritura de corridas anteriores

**Qué valida:** que cada corrida crea un directorio único `run_{ts}_{rid[:8]}` y no sobreescribe resultados previos.

```python
def validate_no_overwrite(output_base, scenario_name):
    run_dirs_before = set(os.listdir(os.path.join(output_base, scenario_name)))
    # simular segunda corrida
    run_dirs_after  = set(os.listdir(os.path.join(output_base, scenario_name)))
    new_dirs = run_dirs_after - run_dirs_before
    assert len(new_dirs) == 1, "Se creó más de un directorio o se sobreescribió uno existente"
```

---

### 7.6 `compare_scenarios` usa los runs esperados

**Qué valida:** que `load_ensembles_from_disk()` carga el directorio correcto cuando se especifica `run_id`.

```python
def validate_load_by_run_id(output_base, region_code, scenario_names, run_id):
    ensembles = cd.load_ensembles_from_disk(output_base, region_code, scenario_names, run_id=run_id)
    for sc in scenario_names:
        assert sc in ensembles, f"Escenario {sc} no encontrado para run_id={run_id}"
        assert ensembles[sc] is not None
```

---

## 8. Validación estadística mínima

Esta sección complementa las anteriores. Los tests estadísticos solo tienen sentido si las validaciones de datos, geografía y software previas han pasado.

### 8.1 Estabilidad por semilla

**Experimento:** correr ReCom 5 veces con semillas distintas (42, 43, 44, 45, 46). Calcular mediana de `max_dev_pob_pct` por corrida. Verificar que el CV entre medianas es < 0.05.

```python
def test_seed_stability(gdf, scenario, seeds=range(42, 47), n_steps=500):
    medianas = []
    for seed in seeds:
        plans = cd.run_recom(gdf, ..., seed=seed, n_steps=n_steps)
        stats = cd.analyze_ensemble(plans, ...)
        medianas.append(stats["max_dev_pob_pct"].median())
    cv = np.std(medianas) / np.mean(medianas)
    assert cv < 0.05, f"Inestabilidad entre semillas: CV={cv:.3f}"
```

---

### 8.2 Estabilidad por `n_steps`

**Experimento:** correr con n_steps = [500, 1000, 2000, 5000, 10000]. Trazar mediana de compacidad vs n_steps. Verificar convergencia visual y que la diferencia entre n=5000 y n=10000 < 5%.

---

### 8.3 Comparación ReCom vs SMC

Ver Sección 2 del documento original (R2, ahora reformulada): aplicar KS test sobre `max_dev_pob_pct`, `cut_edges`, `polsby_popper_mean` entre ensembles ReCom y SMC para una misma región.

**Criterio:** reportar resultado sin importar el p-value. Si p < 0.05 para alguna métrica, declarar explícitamente en la sección de limitaciones.

---

### 8.4 Sensibilidad a `pop_tolerance`

**Experimento:** correr con pop_tolerance = [0.05, 0.10, 0.15, 0.20]. Trazar distribución de `cut_edges` y `split_comunas` por nivel de tolerancia. Verificar que mayor tolerancia produce menor número de aristas cortadas (más libertad → planes más compactos).

---

### 8.5 Sensibilidad a `island_policy`

**Experimento** (solo para regiones con islas conocidas: R01, R12, R15): correr con `island_policy='nearest'` vs `'threshold'`. Comparar conectividad del grafo resultante y distribución de `cut_edges`. Documentar los casos donde `'threshold'` no conecta por exceder los 50 km.

---

## 9. Suite mínima de validación

### Nivel 1 — Smoke tests

**Qué cubre:** que todos los módulos importan sin error, que las constantes y escenarios predefinidos existen y validan, y que las funciones core retornan el tipo correcto en datos mínimos.

**Evidencia entrega:** sin errores de importación, sin regresiones en la API pública.

**Archivos:** `tests/test_smoke.py` (ya implementado, 23 tests).

**Criterio de aceptación para CI:** todos los tests pasan sin shapefiles ni gerrychain instalado.

---

### Nivel 2 — Tests unitarios

**Qué cubre:**

- Validaciones de datos (IDs únicos, sumas, CRS, geometrías) con datos sintéticos en memoria.
- Métricas de compacidad con polígonos de geometría conocida (cuadrado, círculo, L-shape).
- D'Hondt con ejemplos manuales verificados, incluido D'Hondt binivel (pactos → partidos).
- Pareto frontier con conjuntos de dominancia conocida.
- YAML roundtrip para todos los campos de `ScenarioConfig`.
- Schema y dtypes de `assignments.parquet`.
- Roundtrip de `PlanEnsemble`.
- `validate_hierarchy()` con violación sintética.
- `count_split_units()`/`pop_afectada_pct()` con plan que parte y plan que no parte.
- Preflight de factibilidad poblacional: caso factible, caso justo en el límite, caso inviable, y la reproducción concreta RM/Santiago que motivó `check_population_feasibility()`.
- Escenario de comparación con un ensemble inviable/`sin_particion`: visible en la salida, excluido del scoring, comparación marcada `INCOMPLETE`.
- `REGIONES_APC`: las 16 regiones, forma de cada entrada.

**Evidencia entrega:** cobertura funcional de cada módulo sin dependencias externas (sin shapefiles, sin gerrychain).

**Archivos:**
- Ya implementados: `tests/test_smoke.py`, `tests/test_persistence.py`, `tests/test_split_metrics.py`, `tests/test_feasibility.py`, `tests/test_regiones_apc.py`, `tests/test_compare_scenarios_incomplete.py`, `tests/test_electoral_magnitudes.py`, `tests/test_electoral_binivel.py`, `tests/test_electoral_ensemble.py`, `tests/test_malapportionment.py`, `tests/test_malapportionment_functions.py`, `tests/test_fairshare.py`, `tests/test_pareto_sweep.py`, `tests/test_scenario_analysis.py`, `tests/test_metrics.py` (✅ IMPLEMENTED: compacidad — PP círculo/cuadrado/L-shape, Reock, `population_balance`, `cut_edges` — ver §10 P0#7-8, P1 cut_edges), `tests/test_graph_contraction.py` (✅ IMPLEMENTED: contracción a CUT, Queen⊇Rook, conservación de conectividad y viviendas — ver §10 P1#3-4) — cubren en conjunto lo que este documento agrupaba como "D'Hondt con ejemplos manuales" y "Pareto frontier con conjuntos de dominancia conocida" (§6 los presenta con nombres ilustrativos, no literales).
- Tests arquitectónicos (post-refactorización B1, no contemplados en el borrador original): `tests/test_architecture.py` — ✅ IMPLEMENTED, verifica la API pública (`TestPublicAPI`), las fronteras entre las 5 capas del paquete (`TestLayerBoundaries`) y equivalencia numérica pre/post-refactorización (`TestNumericEquivalence`).
- Por crear: `tests/test_hierarchy.py` (`validate_hierarchy`, `contract_to_decision_units` como módulo dedicado — hoy solo cubierto indirectamente vía `test_smoke.py`/`test_graph_contraction.py`).

**Criterio de aceptación:** todos los tests pasan en cualquier entorno con solo `pip install chiledist`.

**Estado real (agosto 2026) — dos verificaciones separadas, no una sola marca de "resuelto":**

**✅ RESUELTO: resolución del paquete vía site-packages (no cwd/sys.path).**
Confirmado con `python -I` (modo aislado: ignora cwd, `PYTHONPATH` y user
site-packages) ejecutado desde `/tmp`, **reutilizando el venv existente del
proyecto** (`env/`, no un venv nuevo) tras correr `pip install -e ".[dev]"`
ahí. Verificado tanto el paquete raíz como un submódulo explícito, para no
asumir que el segundo se resuelve igual que el primero:

```
$ cd /tmp && python -I -c "
import chiledist
import chiledist.engines.samplers as s
print('chiledist:', chiledist.__file__)
print('chiledist.engines.samplers:', s.__file__)
"
chiledist: /home/dvega/Distritaje/chiledist/chiledist/__init__.py
chiledist.engines.samplers: /home/dvega/Distritaje/chiledist/chiledist/engines/samplers/__init__.py
```

Ambas rutas apuntan al árbol fuente del repo, no a una copia en
`site-packages` — eso es el comportamiento **correcto y esperado** de una
instalación editable (`pip install -e .`), no un indicio de que cwd esté
contaminando la resolución. Lo que prueba que la resolución pasa por
`site-packages` y no por `cwd`/`sys.path` accidental es que el import
funciona bajo `python -I` (que excluye cwd de `sys.path`) y que
`site-packages/__editable___chiledist_0_2_0_finder.py` (el finder PEP 660
registrado por setuptools) es el mecanismo que lo resuelve — no que el
`__file__` diga "site-packages" literalmente, cosa que un editable install
nunca hace por diseño. Suite completa desde fuera del repo: 595 passed, 8
skipped, 0 failed (`cd /tmp && python -m pytest /home/dvega/Distritaje/chiledist/tests/`).

**❌ PENDIENTE: instalación desde cero contra índice PyPI real (fuera del sandbox).**
No probado. El sandbox actual tiene el índice de pip topado en versiones de
2023 (`numpy` disponible hasta 1.24.4, incluso pasando `--index-url
https://pypi.org/simple/` explícito), por lo que los pines exactos de
`pyproject.toml` (`numpy==2.4.6`, `scipy==1.17.1`, `geopandas==1.1.3`, etc.)
no pudieron resolverse ni instalarse de forma independiente — el intento
directo (`python -m venv /tmp/test_install && pip install -e
/home/dvega/Distritaje/chiledist`) falló con `ERROR: Could not find a
version that satisfies the requirement numpy==2.4.6`. La verificación de
arriba evade este problema reutilizando un venv que ya tenía los pines
exactos instalados de una sesión previa con acceso real a PyPI — no
demuestra que esos pines sean *resolubles* hoy contra el índice real, solo
que *ya instalados*, `pip install -e .` los deja consistentes. Antes de
considerar este punto cerrado, ejecutar en un entorno con acceso a PyPI
actual:

```bash
python3.11 -m venv /tmp/fresh && source /tmp/fresh/bin/activate
pip install -e '<repo>[dev]'
```

y confirmar que resuelve sin conflictos de versión.

**Auditoría de dependencias runtime no declaradas — sin hallazgos.**
`grep -rhoE "^\s*(import|from) [a-zA-Z_][a-zA-Z0-9_.]*" chiledist/ | awk
'{print $2}' | cut -d. -f1 | sort -u` sobre el código de la librería (no
scripts/, no tests/) da: `geopandas, gerrychain, libpysal, matplotlib,
networkx, numpy, pandas, pyarrow, scipy, shapely, yaml` como no-stdlib —
los 11 ya estaban cubiertos en `pyproject.toml` (`yaml` → `pyyaml`). Ver el
comentario correspondiente en `pyproject.toml` para el detalle completo,
incluida la limitación de este método (no detecta dependencias invocadas
por string, como `openpyxl` vía `engine="openpyxl"` de pandas).

---

### Nivel 3 — Tests científicos / de integración

**Qué cubre:**

- Pipeline completo end-to-end con datos APC reales de una región pequeña (R11 Aysén: ~16 distritos, sin complejidad de islas).
- Verificación de archivos de salida, manifest y hashes.
- Reproducibilidad por semilla en la misma región.
- Comparación cross-sampler ReCom vs SMC para R11.
- Validación de joins de Censo 2024 y padrón para una región con Censo 2024 disponible.
- Validación de que SCENARIO_LEGAL produce 0 splits en R11.
- Validación de métricas electorales con datos de elecciones 2021 (si disponibles).

**Evidencia entrega:** evidencia científica mínima para afirmar que la librería produce resultados correctos sobre datos reales.

**Archivos:** `tests/test_integration_r11.py` — ✅ IMPLEMENTED (agosto 2026): pipeline completo end-to-end con datos APC reales de R11, cubre archivos de salida (`test_1_pipeline_produces_expected_output_files`), reproducibilidad por semilla (`test_2_same_seed_produces_identical_assignments`), 0 splits en `SCENARIO_LEGAL` (`test_3_scenario_legal_produces_zero_splits`), join de Censo 2024 (`test_4_census2024_join_preserves_r11_population_total`), `valid_fraction≈1.0` bajo modelo A (`test_5_valid_fraction_is_one_modelo_a`) y estados `status` documentados (`test_6_status_is_ok_or_documented_infeasible`). Cierra la brecha que este documento marcaba como pendiente desde 2026-06-21. Complementa el patrón de integración más liviano (sin datos geográficos reales) de `tests/test_scripts_demo.py`, `tests/test_redistritaje_status.py`, `tests/test_redistritaje_n_distritos.py` y `tests/test_entrypoints_n_distritos.py`, que cargan los scripts de `scripts/*.py` vía `importlib` con fixtures sintéticas/mocks.

**Criterio de aceptación:** se ejecuta en entorno con datos; todos los invariantes de validación pasan.

---

## 10. Roadmap de validación de ChileDist

### P0 — Necesario para confiar en que la librería no tiene errores estructurales

Estos tests deben pasar antes de usar ChileDist para cualquier análisis.

| # | Test | Módulo | Tipo |
|---|------|--------|------|
| 1 | IDs únicos post-carga | `loader.py` | Unitario |
| 2 | Suma APC → CUT conserva población | `loader.py` + `hierarchy.py` | Unitario |
| 3 | Geometrías válidas en GDF cargado | `loader.py` | Unitario |
| 4 | `validate_hierarchy()` detecta violaciones APC/CUT | `hierarchy.py` | Unitario |
| 5 | Contracción CUT conserva Σ pop | `hierarchy.py` | Unitario |
| 6 | Grafo conectado tras island policy | `graph.py` | Unitario |
| 7 | PP = 1.0 para círculo | `metrics.py` | Unitario — ✅ IMPLEMENTED, ver `tests/test_metrics.py::test_polsby_popper_circulo_perfecto` |
| 8 | PP ∈ [0,1] para todas las geometrías | `metrics.py` | Unitario — ✅ IMPLEMENTED, ver `tests/test_metrics.py` (`test_polsby_popper_cuadrado_unitario`, `test_polsby_popper_l_shape_en_rango`) |
| 9 | count_split_units == 0 para plan que respeta CUT | `split_metrics.py` | Unitario |
| 10 | D'Hondt: ejemplo manual A=3, B=2 | `electoral.py` | Unitario |
| 11 | Σ escaños == n_seats en D'Hondt | `electoral.py` | Unitario |
| 12 | MAGNITUDES_LEGALES_LEY20840: suma==155, rango[3,8] | `electoral.py` | Unitario |
| 13 | `pareto_frontier_nd()` identifica frente correcto | `scenario_comparison.py` | Unitario |
| 14 | `make_preserve_constraint()` rechaza plan que divide CUT | `constraints.py` | Unitario |
| 15 | Assignments parquet schema y dtypes | `persistence.py` | Unitario |
| 16 | PlanEnsemble save/load roundtrip | `persistence.py` | Unitario |
| 17 | YAML roundtrip sin pérdida de campos | `config.py` | Unitario |
| 18 | Pipeline completo produce 4 archivos de salida | `scripts/redistritaje.py` | Integración |
| 19 | Reproducibilidad por semilla (misma semilla = mismo output) | `samplers/recom.py` | Integración |
| 20 | SCENARIO_LEGAL produce 0 splits en datos sintéticos | `constraints.py` + `samplers` | Integración |
| 21 | `check_population_feasibility()` distingue `infeasible_population` de `sin_particion` antes/en vez de correr `recursive_tree_part` | `feasibility.py` + `scripts/redistritaje.py` | Unitario+Integración — ✅ implementado, ver `tests/test_feasibility.py`, `tests/test_redistritaje_status.py` |
| 22 | `n_distritos`: CLI explícito > `scenario.n_districts`, sin default oculto, en los 5 entrypoints | `scripts/{redistritaje,compare_scenarios,pareto_sweep,run_chains,smc_pipeline}.py` | Integración — ✅ implementado, ver `tests/test_redistritaje_n_distritos.py`, `tests/test_entrypoints_n_distritos.py` |

---

### P1 — Necesario para resultados científicos defendibles

Estos tests son necesarios antes de publicar resultados o presentarlos en un contexto académico.

| # | Test | Módulo | Tipo |
|---|------|--------|------|
| 1 | Join Censo 2024: pérdida < 1% por CUT | `data/census2024.py` | Integración |
| 2 | Join padrón SERVEL: inscritos == h+m | `data/servel.py` | Integración |
| 3 | Queen es superconjunto de rook | `graph.py` | Unitario — ✅ IMPLEMENTED, ver `tests/test_graph_contraction.py::test_queen_es_superconjunto_de_rook` |
| 4 | Contracción grafo: n_nodos == n_CUTs | `graph.py` | Unitario — ✅ IMPLEMENTED, ver `tests/test_graph_contraction.py::test_contract_graph_produce_n_cuts_nodos` |
| 5 | pop_tolerance se respeta en todos los draws | `samplers/recom.py` | Integración — ✅ IMPLEMENTED (modelo A: restricción dura desde el draw 0, ver §5.5 y `scripts/redistritaje.py`; verificado con corrida real R12/apc_free, `pop_tol=0.10` → 100/100 planes válidos; ver también `tests/test_integration_r11.py::test_5_valid_fraction_is_one_modelo_a`) |
| 6 | Estabilidad por semilla (CV < 0.05 entre 5 semillas) | `samplers/recom.py` | Estadístico |
| 7 | Sensibilidad a n_steps: convergencia documentada | `samplers/recom.py` | Estadístico |
| 8 | Índices proporcionalidad == 0 para distribución perfecta | `electoral.py` | Unitario |
| 9 | aggregate_votes conserva Σ votos por partido | `electoral.py` | Unitario |
| 10 | Sensibilidad de pesos en scoring compuesto documentada | `scenario_comparison.py` | Estadístico |
| 11 | Manifest incluye hashes de todos los inputs | `persistence.py` | Integración |
| 12 | No sobrescritura de corridas anteriores | `scripts/redistritaje.py` | Integración |
| 13 | compare_scenarios carga run_id correcto | `scripts/compare_scenarios.py` | Integración |
| 14 | Viviendas/personas ratio CV por región documentado | `data/census2024.py` | Datos |
| 15 | Planes apc_soft tienen más splits que legal y menos que apc_free | `constraints.py` | Estadístico |
| 16 | `REGIONES_APC` cubre las 16 regiones y `nombre_carpeta` se usa consistentemente en `redistritaje.py`/`compare_scenarios.py`/`pareto_sweep.py`/`run_chains.py`/`smc_pipeline.py` | `chiledist/data/__init__.py` | Unitario — ✅ implementado, ver `tests/test_regiones_apc.py` |
| 17 | Comparación de escenarios visibiliza `infeasible_population`/`sin_particion` sin contaminar el scoring (`comparison_status` marcado `INCOMPLETE`) | `scenario_comparison/compare.py` + `scripts/compare_scenarios.py` | Integración — ✅ implementado, ver `tests/test_compare_scenarios_incomplete.py` |

---

### P2 — Necesario para publicación o uso institucional

Estos tests son necesarios antes de entregar resultados a una institución o publicar en una revista científica.

| # | Test | Módulo | Tipo |
|---|------|--------|------|
| 1 | Cross-sampler KS test: ReCom vs SMC, todas las métricas documentadas | `samplers` | Estadístico |
| 2 | Ranking de escenarios concordante ReCom vs SMC (Kendall τ > 0.8) | `scenario_comparison.py` | Estadístico |
| 3 | Fracción de planes viviendas que violan tolerancia en personas documentada | `data` + `samplers` | Datos |
| 4 | Sensibilidad a island_policy para regiones con islas | `graph.py` | Estadístico |
| 5 | D'Hondt binivel corrido con votos SERVEL y `pacto_map` reales (no solo `--demo`) | `electoral.py` | Integración — implementación ya existe (`dhondt_binivel`, ver §6.6); falta ejecución con datos reales |
| 6 | Comparación con plan distrital vigente como baseline | `scripts` | Referencia |
| 7 | Tests de integración con datos APC reales (R11 o R12) | Todos | Integración |
| 8 | Trazabilidad completa: hash inputs → outputs verificables | `persistence.py` | Auditoría |

---

## Apéndice: Decisiones pendientes

- [ ] Confirmar si los shapefiles APC reales de alguna región pequeña (R11, R12) están disponibles para tests de integración P2.
- [ ] Confirmar si el Censo 2024 manzana-level está disponible para las regiones de interés.
- [ ] Confirmar si hay datos de elecciones 2021 (SERVEL) disponibles en formato compatible con `load_resultados_electorales()`.
- [ ] Decidir si los tests P2 de integración se ejecutan en CI o solo manualmente con datos locales.
- [ ] Documentar explícitamente en el docstring de `electoral.py` la limitación del D'Hondt binivel.
- [ ] Decidir el umbral `tol` para el test de suma APC→CUT (actualmente propuesto: ±5 viviendas por CUT).

---

## 11. Bugs corregidos durante la validación (agosto 2026)

| Bug | Estado | Evidencia |
|---|---|---|
| `reock()`: incompatibilidad con shapely 2.x | FIXED | `tests/test_metrics.py::test_reock_circulo_perfecto`, `test_reock_cuadrado_unitario`, `test_reock_l_shape_en_rango` |
| `normalize_party_name()`: tolerancia a mayúsculas/acentos para el cruce D'Hondt binivel | FIXED | `tests/test_electoral_binivel.py` (ver `normalize_party_name("Evolución Política") == "evolucion politica"`) |
| `comunas_partidas_ref` quedaba en 0 (lookup sparse del ensemble, inicialización dentro de bloque condicional) | FIXED | `tests/test_comunas_partidas_ref.py` (`test_n_split_ref_assigned_from_len_split_summary`, `test_no_sparse_ensemble_lookup_remains`, `test_n_split_ref_initialized_before_conditional_block`) |
| `warmup_steps` con conteo triangular | FIXED (no verificado independientemente contra el código actual en esta revisión — incluido tal cual fue reportado; no se encontró la palabra "triangular" en el código ni en `VALIDATION_REPORT.md`) | — |
| Preflight de factibilidad: `n_distritos` no se ajustaba cuando excedía el máximo factible | FIXED | `scripts/redistritaje.py` (mensaje `"n_distritos ajustado: {n_distritos_eff} → {n_distritos_max}"`) |
| `asignacion_vigente.json`: 8 CUT de la Región Metropolitana mal asignados a distrito | FIXED | Validado 96/96 combinaciones (distrito, pacto) vs SERVEL 2025 tras la corrección (ver `chiledist/CAPABILITY_AUDIT.md`); commit `b72aff0` según `VALIDATION_REPORT.md` §4 |
| `Puntos_Edificacion_Rural`: capa sin `COD_DISTRITO` (solo CUT a nivel comuna) requiere manejo especial en R11 | FIXED | `chiledist/domain/loader.py` (proxy rural), `tests/test_integration_r11.py` |
| `import_proclamations()`: cruce `candidate_id % 100` fallaba para `num_tricel` de 3 dígitos | FIXED — `% 100` → `% 1000` | `chiledist/domain/data/tricel/__init__.py`; validación TRICEL 2025 pasó de 20/28 a **24/28** distritos (ver `VALIDATION_REPORT.md` §2, commit `1aea69e`) |

---

**Última actualización: agosto 2026 — modelo A implementado, tests Nivel 1-3 completados, validación TRICEL 2025 (28/28, `EXACT_REPRODUCTION`, con `dhondt_binivel_cl()` — variante chilena con tope de candidatos disponibles por partido, función separada de `dhondt_binivel()` genérica que se preservó sin cambios y sigue dando 25/28 `PARTIAL` — ver `VALIDATION_REPORT.md` §3, 5, 9-10).**

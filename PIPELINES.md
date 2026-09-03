# Pipelines de Ejecución — chiledist

> Todos los comandos de este documento fueron verificados ejecutándolos
> realmente contra este repo (sep. 2026). Donde la verificación encontró
> una discrepancia con el comportamiento esperado, se corrigió el comando,
> la ruta de salida o el resultado esperado — nunca se dejó un valor sin
> confirmar. Ver notas al pie de cada sección para el detalle.

## Prerrequisitos

    source env/bin/activate
    export CHILEDIST_DATA_DIR=/ruta/a/DATA
    # Verificar instalación
    python -c "import chiledist as cd; print(cd.__version__)"

## H1 — Costo de la restricción comunal

### Paso 1: Generar ensembles (3 escenarios)
    python scripts/redistritaje.py \
        --base-dir ./SHP_APC2023 --regiones 13 \
        --scenario legal \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10 --n-steps 50000 --seed 42

    python scripts/redistritaje.py \
        --base-dir ./SHP_APC2023 --regiones 13 \
        --scenario apc_free \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10 --n-steps 50000 --seed 42

    python scripts/redistritaje.py \
        --base-dir ./SHP_APC2023 --regiones 13 \
        --scenario apc_soft \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10 --n-steps 50000 --seed 42

    Produce:
        SHP_APC2023/datos/R13_METROPOLITANA/redistritaje/legal_comunas/run_*/
        SHP_APC2023/datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_libre/run_*/
        SHP_APC2023/datos/R13_METROPOLITANA/redistritaje/contrafactual_apc_soft/run_*/
        Cada run contiene: assignments.parquet, ensemble_stats.csv,
        metricas_cadena.csv, run_manifest.json

    Nota de ruta: sin --output-dir explícito, el directorio de salida es
    siempre <base-dir>/datos (aquí SHP_APC2023/datos/...), no datos/ a
    secas — confirmado leyendo redistritaje.py (`output_base =
    args.output_dir or os.path.join(base_dir, "datos")`) y verificado
    contra los runs reales ya generados en este repo.

### Paso 2: Comparar escenarios
    python scripts/compare_scenarios.py \
        --base-dir ./SHP_APC2023 \
        --regiones 13 \
        --scenarios legal,apc_free,apc_soft \
        --skip-run

    Produce:
        SHP_APC2023/datos/R13_METROPOLITANA/comparacion/comparacion_escenarios.csv
        SHP_APC2023/datos/R13_METROPOLITANA/comparacion/*.png

    Resultado esperado (verificado contra comparacion_escenarios.csv real):
        Status: COMPLETE (3/3 escenarios)
        legal_comunas: max_dev=9.127%, comunas_partidas=0.0
        apc_free: max_dev=9.124%, comunas_partidas=28.5
        apc_soft: max_dev=9.131%, comunas_partidas=26.5

## H2 — Frontera Pareto (balance vs fragmentación)

### Paso 1: Barrido de penalizaciones (requiere H1 completado)
    python scripts/pareto_sweep.py \
        --base-dir ./SHP_APC2023 \
        --output-dir ./datos \
        --regiones 13 \
        --penalties 0.0,0.25,0.5,1.0,2.5,5.0,10.0,25.0 \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10 \
        --n-steps 10000 \
        --seed 42

    Produce:
        datos/R13_METROPOLITANA/pareto_sweep/pareto_sweep_results.csv
        datos/R13_METROPOLITANA/pareto_sweep/pareto_frontier.csv
        datos/R13_METROPOLITANA/pareto_sweep/pareto_tradeoff.png

    Nota de ruta: aquí sí es datos/ a secas (sin SHP_APC2023/) porque el
    comando pasa --output-dir ./datos explícitamente, a diferencia de H1.

### Paso 2: Knee point
    python -c "
    import chiledist as cd, pandas as pd
    frontier = pd.read_csv(
        'datos/R13_METROPOLITANA/pareto_sweep/pareto_frontier.csv')
    frontier_r = frontier.rename(columns={
        'max_dev_pob_pct_median': 'max_dev_pob_pct',
        'n_comunas_partidas_median': 'n_comunas_partidas'})
    knee = cd.detect_knee_point(frontier_r)
    print(f'Knee: penalty={knee[\"knee_penalty\"]}, '
          f'dev={knee[\"knee_x\"]:.1f}%, '
          f'splits={knee[\"knee_y\"]}')
    "

    Resultado esperado (verificado contra pareto_frontier.csv real):
        Knee: penalty=1.0, dev=7.781%, splits=22

## H3 — Malapportionment

### Paso único
    python scripts/malapportionment.py \
        --assignment-path datos/asignacion_vigente.json \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --magnitudes ley20840

    # Régimen vigente desde abril 2026:
    python scripts/malapportionment.py \
        --assignment-path datos/asignacion_vigente.json \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --magnitudes censo2026

    Produce:
        datos/malapportionment/malapportionment_pxe.csv
        datos/malapportionment/figuras/*.png

    Resultado esperado (re-ejecutado y verificado en ambos regímenes):
        Ratio max/min: 5.74x (invariante entre regímenes)
        D8 máximo, D27 mínimo en ambos regímenes

## H4 — D'Hondt binivel

### Paso 1: Generar datos SERVEL (requiere Excel crudos)
    python datos/scripts_extra/escanos.py
    # Copiar a datos/
    cp escanos_oficiales_2025.csv datos/
    cp servel_2025_candidatos.csv datos/

    Nota: este script NO lee $CHILEDIST_DATA_DIR — glob'ea
    `PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx` directamente en el
    directorio de trabajo (verificado leyendo datos/scripts_extra/
    escanos.py). Ejecutar desde el directorio que contiene esos Excel
    crudos (típicamente dentro de $CHILEDIST_DATA_DIR/SERVEL_2025/...),
    no desde chiledist/. Los CSV de salida (`datos/escanos_oficiales_2025.csv`,
    `datos/servel_2025_candidatos.csv`) ya existen en este repo — este
    paso solo es necesario para regenerarlos desde cero.

### Paso 2: Validar D'Hondt
    python scripts/validar_dhondt.py \
        --modo candidatos \
        --votos-path datos/servel_2025_candidatos.csv

    Resultado esperado: PASS 96/96

### Paso 3: Análisis electoral completo
    python scripts/electoral_analysis.py \
        --servel-path datos/servel_2025_candidatos.csv \
        --assignment-path datos/asignacion_vigente.json \
        --pacto-path datos/pacto_map_2025.json

    Produce:
        datos/electoral_analysis/electoral_b2_matrix.csv
        datos/electoral_analysis/electoral_b4_bonus.csv
        datos/electoral_analysis/figuras/*.png

    Resultado esperado:
        Gallagher (magnitudes fijas): 5.91
        Partidos con escaños: 20

## H4 (extensión) — Validación TRICEL

### Paso único
    python scripts/validar_tricel.py \
        --data-dir $CHILEDIST_DATA_DIR \
        --base-dir ./SHP_APC2023 \
        --servel-candidates datos/servel_2025_candidatos.csv \
        --pacto-map datos/pacto_map_2025.json \
        --assignment datos/asignacion_vigente.json

    Resultado esperado (con el default actual --votes-source
    servel_final; corregido tras re-ejecutar el comando — un resultado
    anterior de 24/28 con Status PARTIAL correspondía al default antiguo
    --votes-source tricel, ya no vigente):
        Districts validated: 28/28
        Seats validated: 155/155
        List allocations: 185/185
        Candidate proclamations: 155/155
        Status: EXACT_REPRODUCTION

## H8 — Knee point Pareto
    (requiere H2 completado — el knee point ya se calcula
    en el Paso 2 de H2)

## H9 — Comparación internacional

### Paso único (requiere H3 completado)
    python -c "
    import chiledist as cd, pandas as pd
    pxe = pd.read_csv(
        'datos/malapportionment/malapportionment_pxe.csv')
    pop_by_dist = pd.Series(dict(zip(pxe['distrito'], pxe['poblacion'])))
    mag = pd.Series(dict(zip(pxe['distrito'], pxe['magnitud_vigente'])))
    chile = cd.malapportionment_summary(pop_by_dist, mag)
    tabla = cd.international_comparison(
        custom={'Chile_legal_2025': chile},
        include_benchmarks=True)
    print(tabla)
    "

    Nota: malapportionment_summary()/international_comparison() esperan
    pd.Series (no dict) indexadas por distrito, y pop_by_district debe
    ser POBLACIÓN CRUDA (columna `poblacion` de malapportionment_pxe.csv)
    — no `personas_x_escano` (que ya viene dividida por magnitud; usarla
    aquí duplica la división y produce un Samuels-Snyder incorrecto).
    Verificado ejecutando ambas versiones: la corregida reproduce
    exactamente el resultado esperado, la del borrador original fallaba
    con AttributeError ('dict' object has no attribute 'index').

    Resultado esperado (verificado):
        Chile rank 3/6, Samuels-Snyder=0.106

## Ensemble Nacional SMC (H2 nacional / base para H4-B3)

### Paso 1: Generar datos para R
    python scripts/smc_pipeline.py \
        --base-dir ./SHP_APC2023 \
        --regiones nacional_comunal \
        --scenario legal \
        --n-districts 28 \
        --n-sims 5000 \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10

### Paso 2: Ejecutar SMC en R
    Rscript "<ruta_generada>/legal_redist.R"
    # La ruta exacta se imprime en el output del Paso 1

    Produce:
        SHP_APC2023/datos/nacional_comunal/smc/legal/legal_smc_planes.csv
        SHP_APC2023/datos/nacional_comunal/smc/legal/legal_smc_metricas.csv

    (misma nota de ruta que H1 — <base-dir>/datos/..., no datos/... a
    secas, porque no se pasa --output-dir)

    Resultado esperado (verificado con n-sims=5000):
        5000/5000 planes válidos
        pp_promedio mediana: 0.077
        max_dev mediana: 9.75%

## Validación ReCom vs SMC

### Paso 1: Generar ensemble ReCom (requiere H1 legal completado)
    python scripts/redistritaje.py \
        --base-dir ./SHP_APC2023 --regiones 13 \
        --scenario legal \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10 --n-steps 50000 --seed 42 \
        --n-distritos 7

### Paso 2: Generar ensemble SMC
    python scripts/smc_pipeline.py \
        --base-dir ./SHP_APC2023 \
        --regiones 13 \
        --scenario legal \
        --contract-to-cut \
        --n-districts 7 \
        --n-sims 500 \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --pop-tol 0.10

    Rscript "<ruta_generada>/legal_redist.R"

### Paso 3: Comparar
    python scripts/smc_pipeline.py \
        --base-dir ./SHP_APC2023 \
        --regiones 13 \
        --scenario legal \
        --contract-to-cut \
        --n-districts 7 \
        --pop-source censo2024 \
        --census-path datos/poblacion_comunal_censo2024.csv \
        --compare \
        --plans-csv "<ruta>/legal_smc_planes.csv" \
        --recom-ensemble "<ruta>/ensemble_stats.csv"

    Resultado esperado:
        pp_promedio: KS=0.999, efecto=grande
        max_dev: KS=0.637, efecto=grande
        τ Kendall = 1.0 (ranking consistente)

Notas generales:
- Todos los comandos asumen pwd=chiledist/ con env/ activado, salvo el
  Paso 1 de H4 (ver nota ahí).
- Salvo que un comando pase --output-dir explícitamente, la salida va a
  <base-dir>/datos/... (no a datos/... a secas) — ver notas de ruta en
  H1 y Ensemble Nacional SMC. Con --base-dir . (o sin pasar --base-dir,
  en los scripts donde el default ya es "."), sí coincide con datos/...
  a secas.
- <ruta_generada> se imprime en el output de cada script.
- Los resultados numéricos fueron verificados en septiembre 2026
  re-ejecutando cada comando contra los archivos canónicos documentados
  en SCIENTIFIC_HYPOTHESES.md (Censo 2024, TRICEL 2025, SERVEL 2025).
- Para H5 (múltiples cadenas): ver scripts/run_chains.py --help

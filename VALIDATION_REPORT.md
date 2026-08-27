# Reporte de validación: D'Hondt binivel vs proclamaciones oficiales TRICEL 2025

Estado de `scripts/validar_tricel.py` — compara los escaños que
`chiledist.engines.allocation.dhondt.dhondt_binivel()` calcula a partir
de los votos SERVEL contra los que el Tribunal Calificador de
Elecciones proclamó oficialmente para Diputados 2025 (16 nov. 2025),
sobre los 28 distritos reales.

**Estado actual: `PARTIAL`, no `EXACT_REPRODUCTION`.** Este documento
explica por qué, qué se corrigió para llegar hasta acá, y qué falta.

## 0. Estado canónico (fuente de verdad)

**96/96 y 24/28 son dos validaciones distintas contra fuentes distintas — nunca combinar en una sola cifra.**

```json
{
  "SERVEL_INTERNAL_CONSISTENCY": {"result": "96/96", "status": "PASS", "source": "validar_dhondt.py vs SERVEL 2025"},
  "TRICEL_OFFICIAL_REPRODUCTION": {"result": "24/28 distritos", "status": "PARTIAL", "detail": "141/155 escaños, 181/185 asignaciones de lista, 141/155 candidatos", "source": "validar_tricel.py vs TRICEL 2025", "unresolved": ["D3", "D5", "D8", "D19"]},
  "EXACT_REPRODUCTION": false
}
```

| Validación | Resultado | Estado | Contra qué | Script |
|---|---|---|---|---|
| `SERVEL_INTERNAL_CONSISTENCY` | 96/96 combinaciones (distrito, pacto) | PASS | Resultado oficial **SERVEL** 2025 (no TRICEL) | `scripts/validar_dhondt.py` |
| `TRICEL_OFFICIAL_REPRODUCTION` | 24/28 distritos (141/155 escaños, 181/185 asignaciones de lista, 141/155 candidatos) | PARTIAL | Proclamaciones oficiales **TRICEL** 2025 | `scripts/validar_tricel.py` |

Cualquier documento que cite "validado 96/96" debe decir explícitamente **vs SERVEL 2025**, no vs TRICEL — ver §2-3 más abajo para el detalle de por qué estas dos cifras no son intercambiables.

---

## 1. Output completo de la última corrida

```
======================================================================
  Validación TRICEL: D'Hondt binivel chiledist vs proclamaciones oficiales
======================================================================
  Cargando candidatos SERVEL desde datos/servel_2025_candidatos.csv ...
  1378 candidatos, 28 distritos.
  Importando proclamaciones TRICEL desde /home/dvega/Distritaje/DATA/TRICEL_2025 ...
  Cargando 'comunal' (16 archivo(s))...
  → 345 registros.
  ⚠ comunas sin CUT mapeado: ['ANTARTICA']
  28 distritos leídos, 155 candidatos cruzados con SERVEL, 0 sin cruce.
  Importando votación mesa a mesa TRICEL desde /home/dvega/Distritaje/DATA/TRICEL_2025 ...
  1096 registros (distrito, candidato) de votación TRICEL.

Election: Diputados 2025
Districts validated: 24/28
Seats validated: 141/155
List allocations: 181/185
Candidate proclamations: 141/155
Ties requiring legal resolution: 0
Votes with SERVEL fallback: 283/1096
Source hashes:
  SERVEL: 1c3fd5dab12d8716c6854ba3da14a7d3bcc13038c18b388fae2c33239226d2f0
  TRICEL: 359c13cee96490b5ed6dba559694d7f27d7ed6083395af24bf8ced555ffffc91
Status: PARTIAL

Distritos no validados (4):
  D3: 2 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: JAIME ARAYA GUERRERO, MARCELA HERNANDO PEREZ
  D5: 3 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: CAROLINA TELLO ROJAS, NATHALIE CASTILLO ROJAS, BERNARDO SALINAS MAYA
  D8: 12 discrepancias (candidate_mismatch + list_allocation_mismatch)
    Proclamados pero no calculados: GUSTAVO GATICA VILLARROEL, MARCOS BARRAZA GOMEZ, TATIANA URRUTIA HERRERA, CRISTIAN CONTRERAS RADOVIC, MARIO OLAVARRIA RODRIGUEZ, AGUSTIN ROMERO LEIVA, ENRIQUE BASSALETTI RIESS, PIER KARLEZI HAZLEBY
  D19: 1 discrepancias (candidate_mismatch)
    Proclamados pero no calculados: FRANCISCO CRISOSTOMO LLANOS

Para investigar discrepancias: usar --verbose para ver detalle completo
```

---

## 2. Historial de progreso

| Etapa | Districts validated | Ties | Causa de la mejora |
|---|---|---|---|
| Baseline (solo votos SERVEL preliminares, sin `votes_tricel`) | 10/28 | 0 | — punto de partida, tras corregir el `KeyError` de `_read_electos_sheet()` (ver §4) |
| `votes_tricel` recién conectado a `validate_election()` | **0/28** | **123** | Candidatos sin match TRICEL↔SERVEL por nombre quedaban en `votes=0` → empates espurios (0==0) dentro del mismo partido |
| Fallback a votos SERVEL agregado (`_apply_votes_source`) | 0/28 (sin cambio) | 123 (sin cambio) | El fallback en sí funcionaba correctamente (verificado en aislado), pero operaba sobre datos ya corruptos aguas arriba — no se movió nada |
| `_cargar_candidates_servel()` agrega por candidato | **20/28** | **0** | Causa real de los "empates": `servel_2025_candidatos.csv` trae una fila por (candidato × CUT) — hasta 26 filas por candidato — y se pasaban sin sumar; el ranking intra-partido comparaba fragmentos de votos por comuna, no el total real |
| `candidate_id % 100` → `% 1000` en `import_proclamations()` | **24/28** | 0 | 12 candidatos electos con `num_tricel` de 3 dígitos (≥100, distritos con 100+ candidatos registrados) nunca cruzaban con SERVEL — `candidates_matched` 143→155, `candidates_unmatched` 12→0 |

La lección estructural: **la mejora de 0/28 a 20/28 no vino de tocar
la lógica de votos TRICEL ni el fallback** (ambos ya estaban correctos
en ese punto) — vino de un bug completamente distinto y más simple
(agregación de filas) que estaba corrompiendo el input antes de que
`validate_election()` viera los datos. Confirmar cada fix con un test
aislado (no solo con la corrida completa) fue lo que permitió
distinguir "el fallback funciona" de "el resultado global mejora".

---

## 3. Causas documentadas de las 4 discrepancias restantes

Los 4 distritos no validados muestran **exclusivamente discrepancias
"proclamados pero no calculados"** (falsos negativos: TRICEL proclama
a alguien que el D'Hondt calculado no elige) — ya no hay ningún
"calculado pero no proclamado" (falso positivo) en ningún distrito, a
diferencia de etapas anteriores.

- **Distrito 8 (12 discrepancias, incluye `list_allocation_mismatch`
  — el único de los 4 con error a nivel de pacto, no solo de
  candidato)**: causa confirmada. La fuente `servel_2025_candidatos.csv`
  y el Excel crudo `PRELIMINARES_DIPUTADOS_DISTRITO_8.xlsx` (verificados
  por separado, mismo resultado) solo capturan **38.8%** del total de
  votos que TRICEL certifica para ese distrito (777,192 de 2,002,540)
  — muy por debajo del resto de los distritos revisados (77-86%). Con
  menos de la mitad de las mesas reflejadas, tanto el reparto por
  pacto como el ranking intra-partido quedan mal calculados.
- **Distrito 3, 5 y 19 (1-3 discrepancias cada uno, todas
  `candidate_mismatch`)**: candidatos individuales en el margen —no
  todo el bloque de escaños del distrito. Distrito 3 y 5 tienen
  cobertura SERVEL de 78.0% y 77.2% respectivamente (verificado);
  Distrito 19 no se verificó específicamente en esta sesión. La
  hipótesis consistente con la evidencia: el déficit SERVEL (~15-23%
  en los distritos medidos) no es perfectamente uniforme candidato a
  candidato dentro de un mismo partido, así que en carreras
  ajustadas puede alterar quién queda dentro de los N electos de su
  partido sin cambiar cuántos escaños gana el partido en total — por
  eso no aparecen `list_allocation_mismatch` en estos tres distritos.

**Mecanismo común a los 4**: `servel_2025_candidatos.csv` es un conteo
*preliminar* (noche de elección) que en los distritos revisados cubre
77-86% del escrutinio final que certifica TRICEL — Distrito 8 es un
outlier severo con 38.8%. No es un bug de este código: se confirmó
que el CSV coincide exactamente con su Excel SERVEL crudo fuente
(mismos totales al voto), así que la brecha está en la fuente misma,
no en el procesamiento.

---

## 4. Bugs corregidos durante el proceso

| # | Bug | Commit | Alcance |
|---|---|---|---|
| 1 | `asignacion_vigente.json`: 8 CUT de la Región Metropolitana mal asignados a distrito | `b72aff0` | **Anterior a esta sesión** — corregido por el usuario antes de que empezara el trabajo de TRICEL/validation documentado acá. Se menciona por completitud del historial, no lo hice yo en las tareas de esta sesión. |
| 2 | `_read_electos_sheet()`: rename por nombre exacto solo capturaba la etiqueta `"TOTALES"` de la columna de votos en la hoja ELECTOS; 17 de 28 distritos reales usan `"VOTOS"` o `"VOCALES"` (Distrito-10, error tipográfico del archivo oficial) → `KeyError` | `7c66ce4` | `chiledist/domain/data/tricel/__init__.py` |
| 3 | `_list_tricel_files()`/detección de fila de totales en MESA A MESA: exigía NaN en 15 columnas de identificación de mesa; en Distrito-15/16 las columnas de mesa (`Tipo de mesa`/`Mesa`/`Fusionadas`/`Local`/`Dirección del local`) no están en NaN en esa fila → 0 filas matcheadas → `ValueError` | `3436f98` | `chiledist/domain/data/tricel/__init__.py` — acotado a las columnas geográficas (`_MESA_GEO_COLS`), más `_safe_int()` para Nulos/Blancos NaN en Distrito-08 |
| 4 | `_cargar_candidates_servel()` (script): no agregaba las filas por (candidato × CUT) del CSV — 13,410 filas sin sumar en vez de 1,096 candidatos únicos, corrompiendo el ranking intra-partido | `7b7e61c` | `scripts/validar_tricel.py` |
| 5 | `import_proclamations()`: cruce `num_tricel == candidate_id % 100` fallaba en silencio para `num_tricel` de 3 dígitos (candidatos numerados ≥100 dentro de su distrito) — el sufijo real de `candidate_id` es de 3 dígitos, no 2 | `1aea69e` | `chiledist/domain/data/tricel/__init__.py` |

Además, `_apply_votes_source()` (`chiledist/validation/__init__.py`,
commit `939ef9e`) agregó un fallback a votos SERVEL para candidatos sin
match TRICEL — necesario y correcto, pero **no** fue la causa de
ninguna de las mejoras de cobertura documentadas en §2 (ver esa
sección: el salto real vino del bug #4).

---

## 5. Camino hacia `EXACT_REPRODUCTION`

Dos vías, no mutuamente excluyentes:

1. **Conseguir una fuente SERVEL con 100% de las mesas escrutadas**
   (el resultado final de SERVEL, no el "preliminares" de noche de
   elección) — resolvería directamente Distrito 8 (38.8% de
   cobertura) y probablemente los casos marginales de Distrito 3/5/19.
2. **Usar `import_votes()` (TRICEL mesa a mesa) como fuente primaria
   del D'Hondt**, en vez del diseño actual donde SERVEL es la fuente
   primaria y TRICEL solo sobrescribe a los candidatos con match
   (283/1096 candidatos hoy dependen del fallback a SERVEL). Esto
   eliminaría por completo la dependencia de la cobertura SERVEL,
   pero requiere extender el cruce candidato↔`num_tricel` que hoy
   `import_proclamations()` solo hace para los electos de ELECTOS, a
   *todos* los candidatos del roster (`CANDIDATOS`) — no implementado.

---

## 6. Comando de reproducción

```bash
export CHILEDIST_DATA_DIR=/home/dvega/Distritaje/DATA

python scripts/validar_tricel.py \
    --data-dir "$CHILEDIST_DATA_DIR" \
    --servel-candidates datos/servel_2025_candidatos.csv \
    --pacto-map datos/pacto_map_2025.json \
    --assignment datos/asignacion_vigente.json
    # --base-dir por defecto: ./SHP_APC2023 (correr desde la raíz de chiledist/)
```

Requiere (no distribuido en el repo, ver `.env.example`):
`$CHILEDIST_DATA_DIR/SERVEL_2025/PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx`,
`$CHILEDIST_DATA_DIR/TRICEL_2025/Distrito-*.xlsx`, y `SHP_APC2023_R*/`
en el directorio pasado a `--base-dir`.

---

## 7. SHA256 de las fuentes usadas (última corrida)

| Fuente | SHA256 |
|---|---|
| SERVEL (`datos/servel_2025_candidatos.csv`) | `1c3fd5dab12d8716c6854ba3da14a7d3bcc13038c18b388fae2c33239226d2f0` |
| TRICEL (hash combinado de los 28 `Distrito-XX.xlsx`, ver `_combined_hash()` en `scripts/validar_tricel.py`) | `359c13cee96490b5ed6dba559694d7f27d7ed6083395af24bf8ced555ffffc91` |

#!/usr/bin/env bash
# =============================================================================
# setup_env.sh
# Crea el entorno virtual de chiledist e instala todas las dependencias.
#
# Uso:
#   bash setup_env.sh              # entorno en ./env
#   bash setup_env.sh mi_entorno   # entorno en ./mi_entorno
#
# Requiere: Python >= 3.11
# =============================================================================

set -e

ENV_NAME="${1:-env}"
PYTHON_MIN="3.11"

# ── Colores ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
warning() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error()   { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ── Verificar Python ──────────────────────────────────────────────────────────
info "Verificando Python..."

PYTHON_CMD=""
for cmd in python3.11 python3.12 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        VERSION=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        MAJOR=$(echo "$VERSION" | cut -d. -f1)
        MINOR=$(echo "$VERSION" | cut -d. -f2)
        if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            info "  Usando $cmd ($VERSION)"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    error "No se encontró Python >= ${PYTHON_MIN}. Instala con:
  Ubuntu/Debian: sudo apt install python3.11 python3.11-venv
  macOS:         brew install python@3.11
  Windows:       winget install Python.Python.3.11"
fi

# ── Crear entorno virtual ─────────────────────────────────────────────────────
if [ -d "$ENV_NAME" ]; then
    warning "El entorno '$ENV_NAME' ya existe."
    read -p "  ¿Recrear desde cero? [s/N] " -n 1 -r REPLY
    echo
    if [[ $REPLY =~ ^[Ss]$ ]]; then
        info "Eliminando entorno existente..."
        rm -rf "$ENV_NAME"
    else
        info "Usando entorno existente. Solo se actualizarán las dependencias."
    fi
fi

if [ ! -d "$ENV_NAME" ]; then
    info "Creando entorno virtual en ./$ENV_NAME ..."
    "$PYTHON_CMD" -m venv "$ENV_NAME"
fi

# ── Activar entorno ───────────────────────────────────────────────────────────
if [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "win32" ]]; then
    ACTIVATE="$ENV_NAME/Scripts/activate"
else
    ACTIVATE="$ENV_NAME/bin/activate"
fi

# shellcheck disable=SC1090
source "$ACTIVATE"
info "Entorno activado: $VIRTUAL_ENV"

# ── Actualizar pip ────────────────────────────────────────────────────────────
info "Actualizando pip..."
pip install --upgrade pip --quiet

# ── Instalar dependencias en orden correcto ───────────────────────────────────
info "Instalando dependencias..."

# 1. Dependencias base (numpy/shapely primero para evitar conflictos)
info "  [1/6] Base científica..."
pip install "numpy==2.4.6" "scipy==1.17.1" "pandas==3.0.3" --quiet

# 2. Geoespacial (fiona antes de geopandas)
info "  [2/6] Geoespacial..."
pip install "shapely==2.1.2" "pyproj==3.7.2" "fiona==1.10.1" --quiet
pip install "pyogrio==0.12.1" "geopandas==1.1.3" --quiet

# 3. Grafos y visualización
info "  [3/6] Grafos y visualización..."
pip install "networkx==3.6.1" "matplotlib==3.11.0" --quiet

# 4. Análisis espacial
info "  [4/6] Análisis espacial..."
pip install "libpysal==4.14.1" "esda==2.6.0" --quiet

# 5. Persistencia (parquet)
info "  [5/7] Pyarrow (parquet)..."
pip install "pyarrow>=14.0.0" --quiet

# 6. Machine learning (dependencia de gerrychain)
info "  [6/7] Scikit-learn..."
pip install "scikit-learn==1.9.0" --quiet

# 7. Redistritaje
info "  [7/7] Gerrychain..."
pip install "gerrychain==0.3.2" --quiet

# ── Instalar chiledist en modo editable ───────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/setup.py" ]; then
    info "Instalando chiledist en modo editable..."
    pip install -e "$SCRIPT_DIR" --quiet
fi

# ── Verificar instalación ─────────────────────────────────────────────────────
info "Verificando instalación..."

python - << 'PYCHECK'
import sys
issues = []

checks = [
    ("geopandas",         "geopandas"),
    ("numpy",             "numpy"),
    ("pandas",            "pandas"),
    ("scipy",             "scipy"),
    ("networkx",          "networkx"),
    ("matplotlib",        "matplotlib"),
    ("libpysal",          "libpysal"),
    ("esda",              "esda"),
    ("shapely",           "shapely"),
    ("pyarrow",           "pyarrow"),
    ("gerrychain",        "gerrychain"),
    ("chiledist",         "chiledist"),
    ("chiledist.samplers","chiledist.samplers"),
]

print()
for name, module in checks:
    try:
        m = __import__(module)
        version = getattr(m, "__version__", "?")
        print(f"  ✓  {name:<22} {version}")
    except ImportError as e:
        print(f"  ✗  {name:<22} NO INSTALADO ({e})")
        issues.append(name)

print()
if issues:
    print(f"ADVERTENCIA: paquetes con problemas: {issues}")
    sys.exit(1)
else:
    print("Todos los paquetes instalados correctamente.")

# Verificar funcionalidades clave de chiledist
import chiledist as cd
try:
    crs = cd.get_optimal_crs.__module__   # smoke test — función debe existir
    print(f"  ✓  cd.get_optimal_crs       disponible (equivalence)")
except AttributeError:
    print("  ✗  cd.get_optimal_crs       NO encontrado")
    sys.exit(1)

try:
    _ = cd.ScoringConfig.default()
    print(f"  ✓  cd.ScoringConfig         disponible (scenario_comparison)")
except AttributeError:
    print("  ✗  cd.ScoringConfig         NO encontrado")
    sys.exit(1)
PYCHECK

# ── Verificar R (opcional, solo para flujo SMC) ───────────────────────────────
if command -v Rscript &>/dev/null; then
    R_VER=$(Rscript -e "cat(R.version\$major, R.version\$minor, sep='.')" 2>/dev/null || echo "?")
    info "R disponible: $R_VER (recomendado para samplers.smc)"
else
    warning "Rscript no encontrado en PATH."
    warning "  El flujo SMC (samplers.smc) requiere R con el paquete 'redist'."
    warning "  Para instalar R: https://cran.r-project.org/"
    warning "  Los flujos ReCom y de análisis funcionan sin R."
fi

# ── Instrucciones finales ─────────────────────────────────────────────────────
echo ""
info "=============================================="
info " Entorno listo: ./$ENV_NAME"
info "=============================================="
echo ""
echo "  Para activar el entorno:"
if [[ "$OSTYPE" == "msys"* ]] || [[ "$OSTYPE" == "win32" ]]; then
    echo "    $ENV_NAME\\Scripts\\activate"
else
    echo "    source $ENV_NAME/bin/activate"
fi
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  FLUJO DE TRABAJO CHILEDIST"
echo "════════════════════════════════════════════════════════════════"
echo ""
echo "  ── 1. SETUP ─────────────────────────────────────────────────"
echo "  # Inicializa matrices, grafos y figuras nacionales"
echo "  python scripts/setup.py --base-dir ./SHP_APC2023"
echo ""
echo "  # Sin figuras (más rápido)"
echo "  python scripts/setup.py --base-dir ./SHP_APC2023 --skip-viz"
echo ""
echo "  ── 2. REDISTRITAJE ──────────────────────────────────────────"
echo "  # Escenarios disponibles: legal | apc_free | apc_soft"
echo ""
echo "  # Modo legal — comunas indivisibles (Ley 18.700)"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario legal"
echo ""
echo "  # APC libre — máxima compacidad posible"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario apc_free"
echo ""
echo "  # APC con penalización de splits"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario apc_soft"
echo ""
echo "  # Con población del Censo 2024 — join exacto por distrito (recomendado)"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario legal \\"
echo "      --pop-source manzana --census-path datos/Base_manzana_entidad_CPV24.csv"
echo ""
echo "  # Con padrón electoral SERVEL"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario legal \\"
echo "      --pop-source padron --padron-path datos/padron_2024.csv"
echo ""
echo "  # Escenario personalizado desde YAML"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario-file scenarios/mi_escenario.yml"
echo ""
echo "  # Todas las regiones"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones todas --scenario legal"
echo ""
echo "  # Parámetros personalizados"
echo "  python scripts/redistritaje.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --scenario apc_free \\"
echo "      --n-distritos 8 --pop-tol 0.15 --n-steps 10000 --seed 42"
echo ""
echo "  ── 3. COMPARACIÓN DE ESCENARIOS ─────────────────────────────"
echo "  # Corre los 3 escenarios sobre la misma región y compara"
echo "  python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 13"
echo ""
echo "  # Varias regiones"
echo "  python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 --regiones 5,13"
echo ""
echo "  # Solo comparar resultados ya existentes (sin re-ejecutar)"
echo "  python scripts/compare_scenarios.py --base-dir ./SHP_APC2023 \\"
echo "      --regiones 13 --skip-run"
echo ""
echo "  ── 4. AUTOCORRELACIÓN ESPACIAL ──────────────────────────────"
echo "  # Región específica: Moran, LISA, G*, correlograma"
echo "  python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones 13"
echo ""
echo "  # Todas las regiones por separado"
echo "  python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones todas"
echo ""
echo "  # Chile completo a nivel APC ~2.768 nodos"
echo "  python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional"
echo ""
echo "  # Chile completo a nivel comunal ~345 nodos"
echo "  python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional_comunal"
echo ""
echo "  # Variables y parámetros personalizados"
echo "  python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones nacional \\"
echo "      --variables viviendas,densidad_viv_km2,polsby_popper \\"
echo "      --max-order 7 --permutaciones 999"
echo ""
echo "  ── 5. ANÁLISIS H2: PARETO (split_penalty sweep) ────────────"
echo "  # Barrido de split_penalty → frontera Pareto compacidad vs comunas partidas"
echo "  python scripts/pareto_sweep.py --base-dir ./SHP_APC2023 --regiones 13"
echo ""
echo "  ── 6. ANÁLISIS H3: MALAPPORTIONMENT ────────────────────────"
echo "  # Desviación de magnitudes vigentes (Ley 20.840) vs ideal proporcional"
echo "  python scripts/malapportionment.py --base-dir ./SHP_APC2023"
echo ""
echo "  ── 7. ANÁLISIS H4: ELECTORAL (D'Hondt binivel) ─────────────"
echo "  # D'Hondt sobre ensemble; requiere CSV de resultados electorales"
echo "  python scripts/electoral_analysis.py --base-dir ./SHP_APC2023 --regiones 13 \\"
echo "      --votes-path datos/resultados_2021.csv"
echo ""
echo "  ── 8. ANÁLISIS H5: MULTI-CADENAS (convergencia) ────────────"
echo "  # 4 cadenas ReCom independientes + R-hat, ESS, mezcla"
echo "  python scripts/run_chains.py --base-dir ./SHP_APC2023 --regiones 13 \\"
echo "      --scenario apc_soft --n-chains 4 --sensitivity"
echo ""
echo "  ── 9. ANÁLISIS H5: PIPELINE SMC (R/redist) ─────────────────"
echo "  # Paso 1: generar script R y GeoPackage"
echo "  python scripts/smc_pipeline.py --base-dir ./SHP_APC2023 --regiones 13 \\"
echo "      --n-sims 500"
echo "  # Luego ejecutar en R: Rscript datos/R13_.../smc/run_redist.R"
echo "  # Paso 2 (post-R): comparar SMC vs ReCom (ver --compare en script)"
echo ""
echo "  ── 10. BUNDLE IMC PLAN LAB ──────────────────────────────────"
echo "  # Bundle distrital nacional (todas las regiones)"
echo "  python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level distrital"
echo ""
echo "  # Bundle comunal nacional"
echo "  python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 --level comunal"
echo ""
echo "  # Bundle solo para una región"
echo "  python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \\"
echo "      --level distrital --regiones 13"
echo ""
echo "  # Sin cálculo de compacidad (más rápido)"
echo "  python scripts/export_imc_bundle.py --base-dir ./SHP_APC2023 \\"
echo "      --level comunal --no-compacidad"
echo ""
echo "════════════════════════════════════════════════════════════════"
echo "  SALIDAS"
echo "════════════════════════════════════════════════════════════════"
echo "  datos/nacional/matrices/                        → matrices sparse, índices"
echo "  datos/nacional/figuras/                         → mapas y grafos nacionales"
echo "  datos/R13_*/redistritaje/legal_comunas/         → planes ReCom escenario legal"
echo "  datos/R13_*/redistritaje/contrafactual_apc_libre/ → planes ReCom APC libre"
echo "  datos/R13_*/redistritaje/contrafactual_apc_soft/  → planes ReCom APC soft"
echo "  datos/R13_*/comparacion/                        → tabla, tradeoff plots, boxplots"
echo "  datos/R13_*/pareto/                             → sweep Pareto H2"
echo "  datos/R13_*/chains/                             → multi-cadenas H5"
echo "  datos/R13_*/smc/                                → pipeline SMC H5"
echo "  datos/R13_*/autocorrelacion/                    → Moran, LISA, G*, correlograma"
echo "  datos/nacional/redistritaje_apc/                → redistritaje nacional APC"
echo "  datos/nacional/redistritaje_comunal/            → redistritaje nacional comunal"
echo "  datos/nacional/autocorrelacion/                 → autocorr nacional APC"
echo "  datos/nacional/autocorrelacion_comunal/         → autocorr nacional comunal"
echo "  datos/nacional/malapportionment/                → malapportionment H3"
echo "  imc_bundle_distrital_nacional/                  → bundle GeoJSON/JSON"
echo ""

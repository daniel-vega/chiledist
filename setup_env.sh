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
pip install "libpysal==4.14.1" "esda" --quiet

# 5. Machine learning (dependencia de gerrychain)
info "  [5/6] Scikit-learn..."
pip install "scikit-learn==1.9.0" --quiet

# 6. Redistritaje
info "  [6/6] Gerrychain..."
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
    ("geopandas",   "geopandas"),
    ("numpy",       "numpy"),
    ("pandas",      "pandas"),
    ("scipy",       "scipy"),
    ("networkx",    "networkx"),
    ("matplotlib",  "matplotlib"),
    ("libpysal",    "libpysal"),
    ("esda",        "esda"),
    ("shapely",     "shapely"),
    ("gerrychain",  "gerrychain"),
    ("chiledist",   "chiledist"),
]

print()
for name, module in checks:
    try:
        m = __import__(module)
        version = getattr(m, "__version__", "?")
        print(f"  ✓  {name:<15} {version}")
    except ImportError as e:
        print(f"  ✗  {name:<15} NO INSTALADO ({e})")
        issues.append(name)

print()
if issues:
    print(f"ADVERTENCIA: paquetes con problemas: {issues}")
    sys.exit(1)
else:
    print("Todos los paquetes instalados correctamente.")
PYCHECK

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
echo "  Flujo de trabajo:"
echo "    python scripts/setup.py --base-dir ./SHP_APC2023"
echo "    python scripts/redistritaje.py   --base-dir ./SHP_APC2023 --regiones 13"
echo "    python scripts/autocorrelacion.py --base-dir ./SHP_APC2023 --regiones 13"
echo ""

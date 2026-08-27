"""
domain.data._paths
====================
Resolución de rutas a fuentes de datos externas crudas (Excel SERVEL/TRICEL)
que no se distribuyen en el repositorio — capa 0 (Domain).

Convención: ``CHILEDIST_DATA_DIR`` (variable de entorno) apunta a un
directorio raíz con dos subcarpetas:

    <CHILEDIST_DATA_DIR>/SERVEL_2025/   PRELIMINARES_DIPUTADOS_DISTRITO_*.xlsx
    <CHILEDIST_DATA_DIR>/TRICEL_2025/   DISTRITO-*.xlsx

Si la variable no está definida, se usa ``DEFAULT_DATA_DIR``
("datos/fuentes", relativo al directorio de trabajo actual). Ver
.env.example en la raíz del repositorio.
"""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_DATA_DIR = Path("datos/fuentes")


def _data_root() -> Path:
    return Path(os.environ.get("CHILEDIST_DATA_DIR", str(DEFAULT_DATA_DIR)))


def get_servel_dir() -> Path:
    """Directorio con los Excel crudos de SERVEL (PRELIMINARES_DIPUTADOS_*)."""
    return _data_root() / "SERVEL_2025"


def get_tricel_dir() -> Path:
    """Directorio con los Excel crudos de TRICEL (DISTRITO-*.xlsx)."""
    return _data_root() / "TRICEL_2025"

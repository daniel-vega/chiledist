"""
domain.data.servel.provenance
================================
Metadatos de procedencia de un archivo fuente SERVEL/TRICEL — de dónde
vino, cuándo, con qué hash, y con qué versión del parser se procesó.

Separado de servel/__init__.py::import_candidates()'s `provenance` dict
(que describe *qué transformaciones* se aplicaron a los datos — filas
administrativas eliminadas, aliases usados, etc.) — ProvenanceRecord
describe *el archivo en sí*, uno por archivo fuente procesado.
"""

from __future__ import annotations

import dataclasses
import hashlib
from datetime import datetime, timezone
from pathlib import Path


#: Versión semver del parser de servel/__init__.py. Incrementar cuando
#: cambie la lógica de RAW→NORMALIZED→CANONICAL (no cuando solo cambien
#: los datos de entrada).
PARSER_VERSION = "1.0.0"


@dataclasses.dataclass(frozen=True)
class ProvenanceRecord:
    """Procedencia de un único archivo fuente."""
    authority: str        # "SERVEL" | "TRICEL"
    source_path: str      # ruta original al archivo
    original_filename: str
    retrieved_at: str     # ISO 8601
    sha256: str            # hash del archivo fuente
    parser_version: str     # semver del módulo parser
    election_id: str         # ej. "CL-2025-DIP"


def compute_provenance(
    source_path: "str | Path",
    election_id: str,
    authority: str = "SERVEL",
) -> ProvenanceRecord:
    """
    Calcula el registro de procedencia de un archivo fuente.

    `retrieved_at` usa la fecha de modificación del archivo (mtime), no
    `datetime.now()`: es la única marca temporal disponible sin metadata
    externa de descarga, y a diferencia de "ahora" es determinista — la
    misma llamada sobre el mismo archivo produce siempre el mismo
    ProvenanceRecord, lo que hace reproducibles los tests y cualquier
    comparación de provenance entre corridas.

    Parameters
    ----------
    source_path : str | Path
        Ruta al archivo fuente (ej. un .xlsx de SERVEL).
    election_id : str
        ej. "CL-2025-DIP".
    authority : str
        "SERVEL" | "TRICEL" (default: "SERVEL").

    Returns
    -------
    ProvenanceRecord

    Raises
    ------
    FileNotFoundError
        Si source_path no existe.
    """
    path = Path(source_path)
    if not path.exists():
        raise FileNotFoundError(f"Archivo fuente no encontrado: {path}")

    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha256.update(chunk)

    retrieved_at = datetime.fromtimestamp(
        path.stat().st_mtime, tz=timezone.utc
    ).isoformat()

    return ProvenanceRecord(
        authority=authority,
        source_path=str(path),
        original_filename=path.name,
        retrieved_at=retrieved_at,
        sha256=sha256.hexdigest(),
        parser_version=PARSER_VERSION,
        election_id=election_id,
    )

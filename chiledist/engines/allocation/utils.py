"""
engines.allocation.utils
==========================
Utilidad técnica de normalización de texto — capa 2 (Engines).

No codifica ninguna regla legal (a diferencia de
``rules.electoral_rules``): solo tolera variaciones de formato
(mayúsculas, tildes) entre fuentes de datos al hacer lookups por nombre
de partido/pacto.
"""

from __future__ import annotations

import unicodedata


def normalize_party_name(s: str) -> str:
    """
    Normaliza un nombre de partido o pacto para comparación tolerante a
    mayúsculas/minúsculas y tildes.

    Los datos reales de SERVEL suelen venir en MAYÚSCULAS SIN TILDES
    ("EVOLUCION POLITICA"), mientras que un `pacto_map` curado a mano
    (ej. datos/pacto_map_2025.json) suele usar formato título con tildes
    ("Evolución Política"). Un lookup case/tilde-sensible entre ambas
    fuentes falla en silencio — ver `dhondt_binivel()`, que usa esta
    función para que el resultado no dependa de qué formato use cada lado.

    Parameters
    ----------
    s : str
        Nombre de partido o pacto en cualquier capitalización/acentuación.

    Returns
    -------
    str
        Nombre normalizado: minúsculas, sin tildes/caracteres no ASCII,
        sin espacios al inicio/final.

    Examples
    --------
    >>> normalize_party_name("Evolución Política")
    'evolucion politica'
    >>> normalize_party_name("EVOLUCION POLITICA")
    'evolucion politica'
    """
    s = s.lower()
    s = unicodedata.normalize("NFKD", s)
    s = s.encode("ascii", "ignore").decode("ascii")
    return s.strip()

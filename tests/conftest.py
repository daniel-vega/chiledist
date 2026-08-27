"""
tests/conftest.py
===================
Fixtures compartidos entre archivos de test.
"""

import sys
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def mock_gerrychain(monkeypatch):
    """
    Simula gerrychain ausente/mockeado para un solo test.

    monkeypatch.setitem revierte sys.modules["gerrychain"] a su valor
    original (o lo elimina si no existía) automáticamente al terminar el
    test que pidió este fixture — a diferencia de una asignación directa
    a sys.modules a nivel de módulo, que persiste para el resto de la
    sesión de pytest y contamina cualquier test posterior que importe
    gerrychain de verdad (ver Etapa 3, BUG 1).
    """
    mock = MagicMock()
    monkeypatch.setitem(sys.modules, "gerrychain", mock)
    return mock

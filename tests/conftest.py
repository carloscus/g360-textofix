"""Fixtures globales para los tests del corrector."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# El engine vive en src/core/engine.py; pytest corre desde tests/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


@pytest.fixture(autouse=True)
def _vaciar_cache():
    """El cache de engine vive a nivel de modulo (sobrevive entre tests);
    vaciarlo antes/despues evita contaminacion entre suites."""
    from core.engine import cache_vaciar

    cache_vaciar()
    yield
    cache_vaciar()

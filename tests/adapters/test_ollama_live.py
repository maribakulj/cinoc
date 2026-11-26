"""D17/D18 contre un **vrai** serveur Ollama — opt-in (``CINOC_LIVE_OLLAMA``).

``CINOC_LIVE_OLLAMA=http://127.0.0.1:11434 pytest tests/adapters/test_ollama_live.py``
: les modèles installés sont listés avec leur digest, et le digest que trace
l'adaptateur est celui du serveur. La couverture déterministe vit dans
``tests/app/test_models.py`` et ``tests/adapters/test_ollama_digest.py``.
"""

from __future__ import annotations

import os

import pytest

from cinoc.adapters.llm.ollama import OllamaAdapter
from cinoc.app.models import available_models

pytestmark = [pytest.mark.live, pytest.mark.network]


def test_installed_models_and_their_digest() -> None:
    host = os.environ.get("CINOC_LIVE_OLLAMA")
    if not host:
        pytest.skip("CINOC_LIVE_OLLAMA non défini (serveur Ollama local opt-in).")
    listing = available_models("ollama", {"host": host})
    assert listing.unavailable is None and listing.models
    first = listing.models[0]
    assert first.digest is not None and len(first.digest) == 64
    traced = OllamaAdapter(label="o", model=first.name, host=host).system_binaries()
    assert traced == {f"ollama:{first.name}": first.digest}

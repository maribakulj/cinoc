"""Garde-fou : le **mode public** (verrou *fail-closed*) est **opt-in, jamais forcé**.

Décision opérateur : une instance — y compris un HuggingFace Space — exécute ses
moteurs (cloud compris) avec la clé de son opérateur **sans blocage par défaut**.
Le verrou (masquage cloud, refus des imports distants, plugins tiers désactivés)
ne s'active que sur demande explicite, ``CINOC_PUBLIC_MODE=true``.

Ce test verrouille les trois propriétés : le choix explicite prime ; l'env
``true`` active le verrou ; **un Space n'est PAS auto-verrouillé** (le défaut,
sans env, reste ouvert).
"""

from __future__ import annotations

import pytest

from cinoc.interfaces.web.app import resolve_public_mode


def test_explicit_choice_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_PUBLIC_MODE", "true")
    assert resolve_public_mode(False) is False
    monkeypatch.setenv("CINOC_PUBLIC_MODE", "false")
    assert resolve_public_mode(True) is True


def test_env_true_opts_into_the_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_PUBLIC_MODE", "true")
    assert resolve_public_mode(None) is True


def test_space_is_not_auto_locked(monkeypatch: pytest.MonkeyPatch) -> None:
    # Un Space (``SPACE_ID`` présent) **sans** ``CINOC_PUBLIC_MODE`` reste ouvert :
    # plus de verrou imposé qui renverrait 403 sur Mistral/OpenAI. L'opérateur
    # maîtrise sa clé (l'ajoute, l'utilise, la retire). Verrou = opt-in seulement.
    monkeypatch.setenv("SPACE_ID", "user/space")
    monkeypatch.delenv("CINOC_PUBLIC_MODE", raising=False)
    assert resolve_public_mode(None) is False

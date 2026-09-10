"""Résolution **zéro-config** du compte HF des datasets curés (``/library``).

Sur un Space, l'``owner`` du ``SPACE_ID`` suffit (aucun jeton, aucun réseau) ;
en local, un jeton HF résout le handle via ``whoami`` ; ``CINOC_HF_AUTHOR`` reste
l'override explicite. Aucun signal → ``None`` (l'import manuel reste offert).
"""

from __future__ import annotations

import pytest

from cinoc.app import corpus_import
from cinoc.app.corpus_import import resolve_curated_author

_ENVS = (
    "CINOC_HF_AUTHOR",
    "HF_TOKEN",
    "HUGGINGFACE_TOKEN",
    "HUGGING_FACE_HUB_TOKEN",
    "SPACE_ID",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env in _ENVS:
        monkeypatch.delenv(env, raising=False)
    # whoami ne doit jamais toucher le réseau dans ces tests.
    monkeypatch.setattr(corpus_import, "whoami", lambda token: "from-token")


def test_explicit_env_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CINOC_HF_AUTHOR", "explicit")
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.setenv("SPACE_ID", "owner/space")
    assert resolve_curated_author() == "explicit"


def test_token_resolves_handle_via_whoami(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HF_TOKEN", "hf_x")
    monkeypatch.setenv("SPACE_ID", "owner/space")  # le jeton prime sur le Space
    assert resolve_curated_author() == "from-token"


def test_space_owner_is_derived_without_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SPACE_ID", "ma-ri/cinoc")
    assert resolve_curated_author() == "ma-ri"


def test_token_present_but_whoami_fails_falls_back_to_space(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(corpus_import, "whoami", lambda token: None)
    monkeypatch.setenv("HF_TOKEN", "hf_bad")
    monkeypatch.setenv("SPACE_ID", "ma-ri/cinoc")
    assert resolve_curated_author() == "ma-ri"


def test_no_signal_is_none() -> None:
    assert resolve_curated_author() is None

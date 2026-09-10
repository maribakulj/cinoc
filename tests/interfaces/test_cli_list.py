"""``cinoc list`` : lire l'état de son installation sans ouvrir un navigateur.

Ce qui est vérifié est le **transport** — que chaque sujet aille chercher la
sonde de la couche ``app`` et la rende lisiblement. Les sondes elles-mêmes ont
leurs tests ailleurs (``tests/app/test_engines.py``…) : les rejouer ici
mesurerait deux fois la même chose.

Le point qui mérite un test à lui seul : un moteur indisponible doit dire
**pourquoi**. C'est le seul écart qui compte entre « la liste est courte » et
« il te manque un extra ».
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.engines import EngineStatus
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces.cli import main


def test_engines_name_what_is_missing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """La cause d'indisponibilité est la moitié utile de la liste."""
    monkeypatch.setattr(
        "cinoc.interfaces._list_command.engine_statuses",
        lambda: (
            EngineStatus(
                kind="tesseract",
                label="Tesseract",
                available=False,
                detail="binaire tesseract absent du PATH",
            ),
            EngineStatus(
                kind="precomputed", label="Pré-calculé", available=True, detail=""
            ),
        ),
    )
    assert main(["list", "engines"]) == 0
    sortie = capsys.readouterr().out
    assert "binaire tesseract absent du PATH" in sortie
    # Disponible et indisponible se distinguent d'un coup d'œil.
    assert "✓ precomputed" in sortie
    assert "· tesseract" in sortie


def test_engines_covers_the_three_categories(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Moteurs, segmenteurs et briques de post-traitement : la page web montre
    les trois catégories, la commande aussi — sinon la parité serait de façade."""
    assert main(["list", "engines"]) == 0
    sortie = capsys.readouterr().out
    assert "Moteurs" in sortie
    assert "Segmenteurs" in sortie
    # Les briques de post-traitement sont une catégorie à part — ni des moteurs
    # de transcription, ni des segmenteurs.
    assert "ner" in sortie
    assert "saknussemm" in sortie


def test_models_of_one_provider(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "models", "anthropic"]) == 0
    sortie = capsys.readouterr().out
    assert "claude" in sortie
    assert "[vision]" in sortie


def test_models_without_a_provider_lists_them_all(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["list", "models"]) == 0
    sortie = capsys.readouterr().out
    for provider in ("openai", "anthropic", "mistral", "ollama"):
        assert provider in sortie


def test_a_provider_without_a_catalogue_says_so(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``ollama`` n'a pas de catalogue canonique — le dire vaut mieux qu'un vide
    qui se lirait « ce fournisseur ne marche pas »."""
    assert main(["list", "models", "ollama"]) == 0
    assert "aucun modèle canonique" in capsys.readouterr().out


def test_profiles_are_listed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "profiles"]) == 0
    sortie = capsys.readouterr().out
    for profil in ("heritage", "hipe", "dehyphenated"):
        assert profil in sortie


def test_a_preview_shows_the_before_and_the_after(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Un profil se juge sur un texte, pas sur son nom."""
    assert (
        main(["list", "profiles", "--preview", "Il eſtoit", "--profile", "heritage"])
        == 0
    )
    sortie = capsys.readouterr().out
    assert "avant" in sortie and "après" in sortie
    assert "estoit" in sortie  # le ſ long est retombé sur un s


def test_a_custom_config_is_applied_without_being_stored(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Même contrat que l'aperçu web : appliqué à la volée, jamais persisté."""
    config = tmp_path / "norme.yaml"
    config.write_text("name: essai\ncaseless: true\n", encoding="utf-8")
    code = main(["list", "profiles", "--preview", "ABC", "--config", str(config)])
    assert code == 0
    assert "abc" in capsys.readouterr().out


def test_a_preview_without_a_profile_refuses_to_guess(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """« Normaliser par défaut » ne veut rien dire : mieux vaut le dire."""
    assert main(["list", "profiles", "--preview", "ABC"]) == 1
    assert "--profile" in capsys.readouterr().err


def test_an_unknown_profile_fails_loudly(capsys: pytest.CaptureFixture[str]) -> None:
    """Anti-défaut-muet : un profil inconnu ne doit pas retomber sur un autre."""
    assert (
        main(["list", "profiles", "--preview", "ABC", "--profile", "inexistant"]) == 1
    )
    assert capsys.readouterr().err.strip()


def test_curated_prompts_are_listed(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "prompts"]) == 0
    sortie = capsys.readouterr().out
    assert "correction_" in sortie
    assert "prompt_name" in sortie  # on dit où le poser


def test_the_topics_are_declared() -> None:
    args = build_parser().parse_args(["list", "models", "openai"])
    assert (args.command, args.topic, args.provider) == ("list", "models", "openai")

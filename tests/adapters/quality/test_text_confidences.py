"""``LanguageConfidenceScorer`` : une confiance par mot, sans moteur d'OCR.

Le banc mesure la calibration — ECE, MCE, courbe de fiabilité — et cet appareil
ne s'allume que si un pipeline émet des ``CONFIDENCES``. Deux moteurs seulement
en émettent. Pour l'OCR Mistral, un VLM zero-shot ou un texte corrigé, la
section restait vide faute de donnée, pas faute de sujet.

Le test le plus important de ce fichier est celui du **sens**. Le scoreur rend
un besoin de correction (haut = suspect) ; une confiance est son contraire. Se
tromper d'inversion ne casse rien : ça produit une courbe de fiabilité
parfaitement retournée, qui *ressemble* à un résultat.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from cinoc.adapters.quality.text_confidences import (
    LanguageConfidenceScorer,
    confidence_from,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_needs_torch = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None
    or importlib.util.find_spec("transformers") is None,
    reason="extra [qe] absent — le vrai modèle n'est pas chargeable.",
)


# --------------------------------------------------------------------------- #
# Le sens de l'inversion — pur, donc vérifiable sans modèle
# --------------------------------------------------------------------------- #


def test_a_suspicious_word_gets_a_low_confidence() -> None:
    """**Le test qui compte.** Inverser le sens ne casserait rien : ça
    retournerait la courbe de fiabilité, ce qui se lit comme un résultat."""
    assert confidence_from(0.9) == pytest.approx(0.1)
    assert confidence_from(0.1) == pytest.approx(0.9)


@pytest.mark.parametrize("note", [-0.2, 0.0, 0.5, 1.0, 1.3])
def test_the_confidence_always_fits_the_domain_type(note: float) -> None:
    """``ConfidenceToken`` refuse tout ce qui sort de ``[0, 1]``, et une note
    calibrée peut frôler les bornes : borner ici évite de faire échouer une page
    entière pour un mot extrême."""
    valeur = confidence_from(note)
    assert 0.0 <= valeur <= 1.0
    ConfidenceToken(text="mot", confidence=valeur)  # ne doit pas lever


def test_an_invalid_label_is_refused() -> None:
    with pytest.raises(AdapterStepError, match="label"):
        LanguageConfidenceScorer(label="pas/valide")


def test_it_declares_the_right_contract() -> None:
    module = LanguageConfidenceScorer(label="qe")
    assert module.input_types == frozenset({ArtifactType.RAW_TEXT})
    assert module.output_types == frozenset({ArtifactType.CONFIDENCES})


def test_registered_under_its_own_kind() -> None:
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build("text_confidences:qe", {"label": "qe"})
    assert module.output_types == frozenset({ArtifactType.CONFIDENCES})


# --------------------------------------------------------------------------- #
# Le parcours complet, avec un scoreur postiche : on vérifie le **câblage**
# --------------------------------------------------------------------------- #


class _ScoreurPostiche:
    """Rend une surprise croissante par mot. Aucun modèle, aucun poids."""

    def word_surprisals(self, texte: str) -> list[tuple[str, float]]:
        mots = [m for m in texte.split() if any(c.isalnum() for c in m)]
        return [(mot, 2.0 * index) for index, mot in enumerate(mots)]


def _run(tmp_path: Path, texte: str, monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    monkeypatch.setattr(
        LanguageConfidenceScorer, "_scorer", lambda self: _ScoreurPostiche()
    )
    src = tmp_path / "texte.txt"
    src.write_text(texte, encoding="utf-8")
    out = LanguageConfidenceScorer(label="qe").execute(
        {
            ArtifactType.RAW_TEXT: Artifact(
                id="t",
                document_id="d",
                type=ArtifactType.RAW_TEXT,
                uri=str(src),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1.0",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    uri = out.artifacts[ArtifactType.CONFIDENCES].uri
    assert uri is not None
    return json.loads(Path(uri).read_text(encoding="utf-8"))


def test_the_sidecar_has_one_entry_per_word(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jetons = _run(tmp_path, "le cheval court\ndans le pré", monkeypatch)
    assert [j["text"] for j in jetons] == [
        "le", "cheval", "court", "dans", "le", "pré"
    ]


def test_the_confidence_decreases_as_surprise_grows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le postiche rend une surprise croissante : les confiances doivent
    décroître. C'est l'inversion vérifiée **de bout en bout**, pas seulement
    sur la fonction pure."""
    jetons = _run(tmp_path, "un deux trois quatre", monkeypatch)
    valeurs = [j["confidence"] for j in jetons]
    assert valeurs == sorted(valeurs, reverse=True)


def test_lines_are_scored_separately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ligne par ligne, et pas page entière : la surprise d'un mot doit se
    mesurer dans **son** contexte. Coller la page ferait juger le début d'un
    paragraphe par la fin du précédent — ici, le postiche repart de zéro à
    chaque ligne, donc le premier mot de la seconde retrouve la confiance
    maximale."""
    jetons = _run(tmp_path, "alpha beta\ngamma delta", monkeypatch)
    assert jetons[0]["confidence"] == jetons[2]["confidence"]


def test_blank_lines_produce_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _run(tmp_path, "\n\n   \n", monkeypatch) == []


def test_a_missing_text_is_named(tmp_path: Path) -> None:
    module = LanguageConfidenceScorer(label="qe")
    with pytest.raises(AdapterStepError, match="sans URI"):
        module.execute(
            {},
            {},
            RunContext(
                document_id="d",
                code_version="1.0",
                pipeline_name="p",
                workspace_uri=str(tmp_path),
            ),
            RunControl(),
        )


# --------------------------------------------------------------------------- #
# Le vrai modèle — opt-in
# --------------------------------------------------------------------------- #


@_needs_torch
@pytest.mark.slow
def test_a_mangled_word_is_the_least_confident(tmp_path: Path) -> None:
    """Contrôle de sensibilité avec le vrai modèle : le mot abîmé doit être
    celui dont on est le moins sûr."""
    src = tmp_path / "t.txt"
    src.write_text("le cheval c0urt dans le pré", encoding="utf-8")
    tokens = LanguageConfidenceScorer(label="qe").score(
        src.read_text(encoding="utf-8"), RunControl()
    )
    pire = min(tokens, key=lambda t: t.confidence)
    assert pire.text == "c0urt", (
        f"le mot le moins sûr devrait être 'c0urt', pas {pire.text!r}."
    )

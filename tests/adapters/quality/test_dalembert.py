"""``DalembertQEScorer`` : noter le besoin de correction sans punir l'époque.

Le piège que ce scoreur devait éviter est nommé dans ``saknussemm`` lui-même : un
modèle contemporain juge improbable une orthographe d'Ancien Régime, donc
signale comme « à corriger » une transcription parfaitement fidèle. La parade
est la **copie dé-glyphée** — on neutralise la typographie, jamais la langue.

Deux niveaux de test, et la séparation est délibérée :

* les fonctions **pures** (dé-glyphage, sigmoïde de Platt) sont vérifiées sans
  modèle : elles portent la décision de conception, et elles doivent être
  vérifiables dans un gate qui ne télécharge pas 500 Mo de poids ;
* le comportement du **vrai modèle** est un test ``slow``, opt-in.
"""

from __future__ import annotations

import importlib.util

import pytest

from cinoc.adapters.quality.dalembert import (
    GLYPHS,
    PLATT_MIDPOINT,
    PLATT_SCALE,
    DalembertQEScorer,
    deglyph,
    platt,
)

_needs_torch = pytest.mark.skipif(
    importlib.util.find_spec("torch") is None
    or importlib.util.find_spec("transformers") is None,
    reason="extra [qe] absent — le vrai modèle n'est pas chargeable.",
)


# --------------------------------------------------------------------------- #
# Le dé-glyphage : typographie neutralisée, langue intacte
# --------------------------------------------------------------------------- #


def test_typography_is_normalised() -> None:
    assert deglyph("qu'il eſt bon d'auoir ﬁni") == "qu'il est bon d'auoir fini"


def test_period_language_survives_untouched() -> None:
    """**Le test central du module.**

    ``auoir``, ``estoit``, ``cultiuent`` sont des formes d'époque *correctes*.
    Les normaliser ferait mesurer au scoreur l'écart au français contemporain,
    c'est-à-dire exactement ce qu'il ne doit pas mesurer : le corpus de
    référence en est plein, et un scoreur qui les signale note la vérité
    terrain comme fautive.
    """
    for forme in ("auoir", "estoit", "cultiuent", "meurs", "vn"):
        assert deglyph(forme) == forme


def test_the_map_carries_no_letter_substitution() -> None:
    """Le pendant mécanique : aucune entrée ``u`` → ``v`` ne peut s'y glisser.

    Une seule ligne de plus dans la table suffirait à transformer le
    dé-glyphage en modernisation, et le test ci-dessus ne le verrait que pour
    les cinq formes qu'il cite.
    """
    for ancien in GLYPHS:
        assert not ancien.isascii(), (
            f"{ancien!r} est un caractère ASCII : le remplacer est une "
            "normalisation de langue, pas de typographie."
        )


# --------------------------------------------------------------------------- #
# La calibration de Platt — de la donnée mesurée, pas un réglage
# --------------------------------------------------------------------------- #


def test_platt_is_monotone_and_bounded() -> None:
    valeurs = [platt(s) for s in (0.0, 5.0, 10.0, 15.0, 40.0)]
    assert valeurs == sorted(valeurs), "plus de surprise doit noter plus haut."
    assert all(0.0 <= v <= 1.0 for v in valeurs)


def test_the_midpoint_is_the_half() -> None:
    """Le point de bascule mesuré : à la surprise médiane, la note vaut 0,5."""
    assert platt(PLATT_MIDPOINT) == pytest.approx(0.5)


def test_the_calibration_constants_are_the_measured_ones() -> None:
    """Verrou sur de la **donnée**, pas sur du code.

    Ces deux nombres viennent de ``qe-report-max.json`` (réducteur ``max``,
    AUC ligne 0,766). Les changer sans re-mesurer rendrait les notes de deux
    runs incomparables, en silence — un test qui l'annonce vaut mieux qu'un
    commentaire.
    """
    assert (PLATT_MIDPOINT, PLATT_SCALE) == (10.9436, 6.7179)


# --------------------------------------------------------------------------- #
# Le vrai modèle — opt-in
# --------------------------------------------------------------------------- #


@_needs_torch
@pytest.mark.slow
def test_a_damaged_line_scores_above_its_faithful_twin() -> None:
    """**Contrôle de sensibilité.** Sans lui, une note constante passerait.

    Chaque paire ne diffère que par des confusions d'OCR (``o``/``0``,
    ``u``/``n``, ``l``/``1``) : ni la langue ni la longueur ne changent, donc
    l'écart mesuré ne peut venir que de ce que le scoreur est censé voir.
    """
    scorer = DalembertQEScorer()
    paires = [
        (
            "On a beaucoup parlé depuis quelque temps",
            "On a beauc0up parlé depuis quelqne temps",
        ),
        (
            "de l'entente de l'Autriche et de la Russie",
            "de l'enteute de l'Antriche et de la Rnssie",
        ),
    ]
    for fidele, abimee in paires:
        assert scorer.needs_correction(abimee) > scorer.needs_correction(fidele), (
            f"« {abimee} » devrait être notée au-dessus de « {fidele} »."
        )


@_needs_torch
@pytest.mark.slow
def test_a_line_without_words_scores_zero() -> None:
    """Une ligne de ponctuation n'a rien à corriger : le routeur doit pouvoir
    la sauter au lieu de payer un appel pour un tiret."""
    scorer = DalembertQEScorer()
    assert scorer.needs_correction("— . ;") == 0.0
    assert scorer.needs_correction("   ") == 0.0


@_needs_torch
@pytest.mark.slow
def test_the_score_says_which_word_triggered_it() -> None:
    """Une note seule ne s'audite pas : le mot fautif doit être nommable."""
    scorer = DalembertQEScorer()
    mots = scorer.word_surprisals("le cheval c0urt dans le pré")
    assert mots, "la ligne porte des mots."
    pire = max(mots, key=lambda paire: paire[1])[0]
    assert pire == "c0urt", (
        f"le mot le plus surprenant devrait être 'c0urt', pas {pire!r}."
    )

"""Parité de la **convention** du CER, cas par cas, contre jiwer et dinglehopper.

Critère de sortie de P5e 7 (D-285). Une ligne par cas : la référence,
la sortie, puis le CER que donne chaque convention. Ce sont les cas où les
outils **divergent** — Unicode, bords, blancs, invisibles, saut de ligne — et
la table dit pourquoi, au lieu de laisser croire que « CER » veut dire une
seule chose.

Colonnes :

- ``texte`` — vue par défaut de Cinoc (``flat_text`` : NFC, invisibles
  retirés, tout blanc réduit à une espace, bords retirés) ;
- ``lignes`` — seconde vue par défaut, « texte (lignes) »
  (``keep_line_breaks`` : la même, sauts de ligne comptés) ;
- ``brut`` — ``normalization_profile: null``, aucune préparation ;
- ``jiwer`` — ``jiwer.cer`` 4.0.0 au défaut (``cer_default`` = ``Strip`` seul :
  bords retirés, rien d'autre ; points de code). Recalculé ici quand jiwer
  est installé (dépendance *dev*) ;
- ``dingle`` — dinglehopper 0.11.0 sur deux fichiers texte
  (``plain_extract`` + ``character_error_rate``) : chaque ligne ``strip``-ée
  puis ``normalize_sbb`` (NFC, ligatures dépliées, ``’`` → ``'``, ``—`` → ``–``,
  ``⸗`` → ``-``…), lignes jointes par ``\\n`` **compté**, distance sur les
  **graphèmes** (uniseg). Valeurs figées ici, **recalculées** par le dernier
  test dans le job CI ``oracle`` (extra ``oracle`` + dinglehopper
  ``--no-deps``, D-290) ; sautées ailleurs.

Lecture des écarts :

- ``nfc_nfd`` : jiwer compte la marque combinante (2 points de code contre 1) ;
  dinglehopper et Cinoc normalisent en NFC.
- ``bords`` : seul ``brut`` compte les espaces de bord (l'ancien défaut ``nfc``
  aussi, D-285).
- ``nbsp``, ``tabulation`` : un blanc qui n'est pas une espace compte chez jiwer
  et dinglehopper ; Cinoc l'écrase (``\\s`` Unicode).
- ``tiret_conditionnel``, ``espace_zero`` : invisibles (catégorie ``Cf``)
  retirés par Cinoc, comptés par les deux autres.
- ``saut_vs_espace`` : **le cas du pilote** (D-281 D8). Le saut de ligne compte
  chez jiwer et dinglehopper, et sous ``lignes`` ; pas sous ``texte``.
- ``espaces_multiples`` : jiwer et dinglehopper les comptent un par un
  (ocreval les écrase, selon sa source ``text.c``) ; Cinoc les écrase.
- ``apostrophe`` : seul dinglehopper unifie ``’`` et ``'`` ; Cinoc les garde
  distincts par défaut (équivalence de contenu = convention du corpus, D-285).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.text import cer
from cinoc.evaluation.representations import prepare_text
from cinoc.formats.text import DEFAULT_PROFILE

_NFD = "cafe\u0301"

#: (cas, référence, sortie,
#:  texte, lignes, brut, jiwer, dingle)
_CASES: tuple[tuple[str, str, str, float, float, float, float, float], ...] = (
    ("erreur_simple", "le chat noir", "le chien noir",
     3 / 12, 3 / 12, 3 / 12, 3 / 12, 3 / 12),
    ("nfc_nfd", "un café noir", f"un {_NFD} noir",
     0.0, 0.0, 2 / 12, 2 / 12, 0.0),
    ("bords", "le chat noir", "  le chat noir  ",
     0.0, 0.0, 4 / 12, 0.0, 0.0),
    ("nbsp", "le\u00a0chat noir", "le chat noir",
     0.0, 0.0, 1 / 12, 1 / 12, 1 / 12),
    ("tiret_conditionnel", "le chat noir", "le cha\u00adt noir",
     0.0, 0.0, 1 / 12, 1 / 12, 1 / 12),
    ("espace_zero", "le chat noir", "le\u200b chat noir",
     0.0, 0.0, 1 / 12, 1 / 12, 1 / 12),
    ("saut_vs_espace", "le chat\nnoir dort", "le chat noir dort",
     0.0, 1 / 17, 1 / 17, 1 / 17, 1 / 17),
    ("espaces_multiples", "le chat noir", "le  chat   noir",
     0.0, 0.0, 3 / 12, 3 / 12, 3 / 12),
    ("tabulation", "le chat noir", "le\tchat noir",
     0.0, 0.0, 1 / 12, 1 / 12, 1 / 12),
    ("apostrophe", "l’homme dort", "l'homme dort",
     1 / 12, 1 / 12, 1 / 12, 1 / 12, 0.0),
)  # fmt: skip

_IDS = [case[0] for case in _CASES]


def _cinoc(profile: str | None, reference: str, hypothesis: str) -> float:
    view = EvaluationView(
        name="v",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        normalization_profile=profile,
    )
    observation = cer.fn(
        DocContext(
            document_id="d",
            reference=prepare_text(reference, view),
            hypothesis=prepare_text(hypothesis, view),
        )
    )
    assert observation is not None
    return observation.value


def test_the_default_view_is_the_flat_profile() -> None:
    view = EvaluationView(name="v", candidate_types=frozenset({ArtifactType.RAW_TEXT}))
    assert view.normalization_profile == DEFAULT_PROFILE.name == "flat_text"
    assert DEFAULT_PROFILE.unicode_form == "NFC" and DEFAULT_PROFILE.strip_invisible
    assert DEFAULT_PROFILE.whitespace == "flat" and not DEFAULT_PROFILE.diplomatic_table


@pytest.mark.parametrize(
    ("ref", "hyp", "texte", "lignes", "brut"),
    [case[1:6] for case in _CASES],
    ids=_IDS,
)
def test_cinoc_conventions(
    ref: str, hyp: str, texte: float, lignes: float, brut: float
) -> None:
    assert _cinoc(DEFAULT_PROFILE.name, ref, hyp) == pytest.approx(texte)
    assert _cinoc("keep_line_breaks", ref, hyp) == pytest.approx(lignes)
    assert _cinoc(None, ref, hyp) == pytest.approx(brut)


@pytest.mark.parametrize(
    ("ref", "hyp", "expected"), [(c[1], c[2], c[6]) for c in _CASES], ids=_IDS
)
def test_jiwer_column(ref: str, hyp: str, expected: float) -> None:
    jiwer = pytest.importorskip("jiwer")
    assert jiwer.cer(ref, hyp) == pytest.approx(expected)


@pytest.mark.oracle
@pytest.mark.parametrize(
    ("name", "ref", "hyp", "expected"),
    [(c[0], c[1], c[2], c[7]) for c in _CASES],
    ids=_IDS,
)
def test_dinglehopper_column(
    tmp_path: Path, name: str, ref: str, hyp: str, expected: float
) -> None:
    """Recalcul vivant, seulement si dinglehopper est installé : job CI
    ``oracle`` (D-290), sauté ailleurs."""
    ocr_files = pytest.importorskip("dinglehopper.ocr_files")
    rates = pytest.importorskip("dinglehopper.character_error_rate")
    gt = tmp_path / f"{name}.gt.txt"
    ocr = tmp_path / f"{name}.ocr.txt"
    gt.write_text(ref, encoding="utf-8")
    ocr.write_text(hyp, encoding="utf-8")
    value = rates.character_error_rate(
        ocr_files.plain_extract(str(gt), encoding="utf-8"),
        ocr_files.plain_extract(str(ocr), encoding="utf-8"),
    )
    assert value == pytest.approx(expected)

"""Parité CER/WER/MER vs jiwer (oracle, dépendance *dev*). Skippé si jiwer absent.

Entrées propres (espaces simples, sans bord) → alignement non ambigu, donc MER
comparable. Les valeurs exactes (y compris cas dégénérés) sont, elles, vérifiées
sans jiwer dans ``test_metrics_text``.
"""

from __future__ import annotations

import pytest

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.text import cer, mer, wer

jiwer = pytest.importorskip("jiwer")

_PAIRS = [
    ("le chat noir", "le chien noir"),
    ("Icy commence le prologue", "Icy commence le prologve"),
    ("maistre Jehan Froissart", "maistre Jehan Froiart"),
    ("hello world here", "world here"),
    ("transcription test case", "transcryption test case"),
]


def _ctx(reference: str, hypothesis: str) -> DocContext:
    return DocContext(document_id="d", reference=reference, hypothesis=hypothesis)


@pytest.mark.parametrize(("ref", "hyp"), _PAIRS)
def test_cer_matches_jiwer(ref: str, hyp: str) -> None:
    assert cer.fn(_ctx(ref, hyp)).value == pytest.approx(jiwer.cer(ref, hyp))


@pytest.mark.parametrize(("ref", "hyp"), _PAIRS)
def test_wer_matches_jiwer(ref: str, hyp: str) -> None:
    assert wer.fn(_ctx(ref, hyp)).value == pytest.approx(jiwer.wer(ref, hyp))


@pytest.mark.parametrize(("ref", "hyp"), _PAIRS)
def test_mer_matches_jiwer(ref: str, hyp: str) -> None:
    assert mer.fn(_ctx(ref, hyp)).value == pytest.approx(jiwer.mer(ref, hyp))


def test_la_distance_tient_sur_une_page_entiere() -> None:
    """Une page de presse complète doit se mesurer, pas faire attendre la nuit.

    La matrice à deux lignes est O(n×m) *itérations Python* : sur une ligne c'est
    instantané, sur 25 000 caractères c'est 750 millions de tours, plus de deux
    minutes par appel et par métrique. Un banc de 48 documents n'aboutissait pas.

    Ce test ne chronomètre rien — un temps d'exécution n'est pas une propriété
    stable. Il vérifie l'exactitude **sur une taille que l'ancienne version
    n'atteignait pas** : si quelqu'un revenait à la matrice, la suite le dirait
    en s'arrêtant de rendre la main.
    """
    from cinoc.evaluation.metrics.text import _edit_distance

    base = "l'aviateur Marsot, chevalier de la Légion d'honneur. " * 500
    assert len(base) > 25_000
    assert _edit_distance(base, base) == 0
    # trois insertions au milieu, et rien d'autre
    milieu = len(base) // 2
    modifie = base[:milieu] + "xyz" + base[milieu:]
    assert _edit_distance(base, modifie) == 3
    # une suppression en tête, une substitution en queue
    autre = base[1:-1] + "Z"
    assert _edit_distance(base, autre) == 2

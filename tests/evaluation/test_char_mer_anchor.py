"""Ancrage char-MER — primitive d'alignement unique (Phase 1 → fusionnée Phase 3.1).

Le Match Error Rate caractère vivait à DEUX endroits (``metrics/conformity.cmer``
et ``correction._cmer``). La Phase 3.1 les a fusionnés dans une seule primitive,
``evaluation._alignment.char_mer``. Ce fichier fige (1) les valeurs canoniques de
``char_mer`` sur des cas dérivés à la main, et (2) que ``conformity.cmer`` **délègue**
bien à cette primitive — toute ré-introduction d'un calcul jumeau divergent casse.

Convention (SPEC_HIPE §4.1) : ``value = (S+D+I) / (len(ref) + I)`` sur les
comptes **canoniques** (P1) ; dénominateur ``H+S+D+I`` = ``n_réf + I`` de la
statistique ; deux textes vides → ``0.0`` pour la primitive (analyse de
correction), scalaire indéfini pour la métrique (K1, dénominateur nul).
"""

from __future__ import annotations

import pytest

from cinoc.evaluation._alignment import char_mer
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.conformity import cmer

#: (référence, hypothèse, value attendue, dénominateur attendu, edits attendus).
#: Valeurs dérivées à la main depuis l'alignement caractère.
_CASES = [
    ("abc", "abc", 0.0, 3, 0),  # identiques
    ("abc", "abxc", 0.25, 4, 1),  # 1 insertion
    ("abc", "", 1.0, 3, 3),  # 3 suppressions
    ("ab", "abcd", 0.5, 4, 2),  # 2 insertions
    ("abc", "abd", 1 / 3, 3, 1),  # 1 substitution
    ("", "", 0.0, 0, 0),  # deux vides
]


@pytest.mark.parametrize(("ref", "hyp", "value", "denom", "edits"), _CASES)
def test_char_mer_pinned(
    ref: str, hyp: str, value: float, denom: int, edits: int
) -> None:
    got_value, got_edits, got_denom = char_mer(ref, hyp)
    assert got_value == pytest.approx(value)
    assert got_edits == edits
    assert got_denom == denom


@pytest.mark.parametrize(("ref", "hyp", "value", "denom", "edits"), _CASES)
def test_conformity_cmer_delegates_to_char_mer(
    ref: str, hyp: str, value: float, denom: int, edits: int
) -> None:
    """La métrique de socle ``cmer`` produit exactement ``char_mer`` (valeur +
    dénominateur), sauf deux textes vides : indéfini pour la métrique."""
    observation = cmer.fn(DocContext(document_id="d", reference=ref, hypothesis=hyp))
    assert observation is not None
    primitive_value, primitive_edits, primitive_denom = char_mer(ref, hyp)
    stat = observation.stat
    assert (stat.edits, stat.reference_length + stat.insertions) == (
        primitive_edits,
        primitive_denom,
    )
    if primitive_denom == 0:
        assert observation.value is None
        return
    assert observation.value == pytest.approx(primitive_value)
    # et ces valeurs sont bien les valeurs canoniques figées
    assert observation.value == pytest.approx(value)
    assert stat.reference_length + stat.insertions == denom

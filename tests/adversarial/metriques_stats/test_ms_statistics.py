"""Affirmation 3 — statistiques : échec non aléatoire et classement.

Importé de la contre-expertise (``metriques_stats/test_ms_statistics.py``,
commit ``04a1c17b``) : seul le test que ``CONTRATS.md`` § 4.1 range en tranche
1b, reformulé selon A6 et B7. Les autres (C05, C06, C09) relèvent de la tranche
I et seront importés à son ouverture.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.adversarial._contrat import (
    comparaison,
    couverture,
    paire,
    support_global,
    support_micro,
)
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    aggregate,
    letters,
    substitute,
    view,
)


def _failure_bench(tmp_path: Path) -> Bench:
    """7 pages faciles (100 car.) : A 5 erreurs, B 4 ; 1 page difficile (1 000 car.) : A
    échoue, B 500 erreurs."""
    bench = Bench(tmp_path)
    for i in range(7):
        ref = letters(100, seed=i)
        bench.document(f"e{i}", ref)
        bench.output("A", f"e{i}", substitute(ref, 5))
        bench.output("B", f"e{i}", substitute(ref, 4))
    hard = letters(1000, seed=50)
    bench.document("hard", hard)
    bench.fail("A", "hard")
    bench.output("B", "hard", substitute(hard, 500))
    return bench


@pytest.mark.discutable("C07-politique-echec-classement")
@pytest.mark.tranche("1b")
def test_echec_non_aleatoire__classement_sur_documents_communs(tmp_path: Path) -> None:
    """A échoue sur la page difficile (politique par défaut), B est meilleur sur
    chaque page commune. Reformulé (A6, B7) : l'agrégat conditionnel de A
    (0,05 sur 7/8) reste publié, avec sa couverture ; mais A et B ne
    s'ordonnent que sur leur support apparié, où B (28/700 = 0,040) passe devant
    A (35/700 = 0,050), et le tri multi-pipelines se fait sur le support
    global — jamais sur les agrégats conditionnels."""
    result = _failure_bench(tmp_path).run(view(["cer"]))
    cer_a = aggregate(result, "A", "cer")
    assert (cer_a.support, cer_a.expected) == (7, 8)  # l'échec est bien affiché
    assert (support_micro(cer_a), couverture(cer_a)) == (7, {"step_failed": 1})
    communs = tuple(f"e{i}" for i in range(7))
    payload = comparaison(result, "v", "cer")
    ab = paire(payload, "A", "B")
    assert tuple(ab.micro_documents) == communs
    assert dict(ab.micro) == pytest.approx({"A": 0.05, "B": 0.04})
    family = support_global(payload)
    assert tuple(family.micro_documents) == communs
    assert tuple(family.ranking) == ("B", "A")

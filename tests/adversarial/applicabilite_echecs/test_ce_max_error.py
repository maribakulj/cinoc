"""Affirmation 2 (suite) — la règle ``max_error`` (``runner._score_failed``) :
``worst = 0.0 if higher_is_better else 1.0``. Elle ne peut pas être déduite de
``higher_is_better`` seul.

Importé de la contre-expertise (``applicabilite_echecs/test_ce_max_error.py``,
commit ``04a1c17b``) : les trois tests que ``CONTRATS.md`` § 4.1 range en
tranche 1b. Les deux discutables (C08) sont reformulés selon § 2.1 e :
``max_error`` est retiré, aucune imputation par défaut, et la sensibilité
``empty_page`` note l'échec comme une hypothèse vide, sous ce nom.

Références indépendantes : distance d'édition écrite à la main ; la valeur
que la **métrique elle-même** donne à une page rendue vide (pipeline ``vide``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.extension import AdapterStepError
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import couverture, politique_empty_page, support_micro

from ._kit import (
    Behaviour,
    TextBrick,
    aggregate,
    corpus,
    execute,
    levenshtein,
    per_document,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)

pytestmark = pytest.mark.tranche("1b")

REF = "Le chat 1789 dort sur le tapis"
GARBAGE = " ".join(["zq"] * 30)  # sortie hallucinée, trois fois plus longue que la page


def _behaviour(outputs: dict[str, str | None]) -> Behaviour:
    """``None`` = la brique lève l'erreur typée d'un moteur en panne."""

    def run(document_id: str) -> str | AdapterStepError:
        text = outputs[document_id]
        return AdapterStepError("moteur en panne") if text is None else text

    return run


def _three_engines(
    tmp_path: Path, metrics: tuple[str, ...], **evaluation: object
) -> RunResult:
    """``panne`` échoue sur ``b`` ; ``vide`` y rend une page vide ; ``bavard`` y
    hallucine. Sur ``a`` et ``c`` les trois sont parfaits."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    bricks = (
        TextBrick("ce_panne", _behaviour({"a": REF, "b": None, "c": REF})),
        TextBrick("ce_vide", _behaviour({"a": REF, "b": "", "c": REF})),
        TextBrick("ce_bavard", _behaviour({"a": REF, "b": GARBAGE, "c": REF})),
    )
    return execute(
        spec(
            corpus(tmp_path, {"a": REF, "b": REF, "c": REF}),
            [
                pipeline("panne", step("ocr", "ce_panne")),
                pipeline("vide", step("ocr", "ce_vide")),
                pipeline("bavard", step("ocr", "ce_bavard")),
            ],
            [text_view(metrics=metrics)],
            **evaluation,
        ),
        registry_with(*bricks),
    )


@pytest.mark.discutable("C08-imputation-echec-max-error")
def test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse(tmp_path: Path) -> None:
    """Reformulé (§ 2.1 e, A7) : par défaut, l'échec de ``panne`` sur ``b``
    n'est pas noté (aucune imputation : couverture 2/3, motif
    ``step_failed``). Sous la sensibilité ``empty_page``, il vaut exactement
    ce que la métrique donne à une hypothèse vide (CER 1,0, le pipeline
    ``vide``), et le résultat porte ce nom ; ``max_error`` n'existe plus."""
    result = _three_engines(tmp_path / "defaut", ("cer",))
    bavard = levenshtein(REF, GARBAGE) / len(REF)
    assert per_document(result, "bavard", "b").value == pytest.approx(bavard)
    assert per_document(result, "panne", "b").value is None
    agg = aggregate(result, "panne")
    assert (support_micro(agg), agg.expected) == (2, 3)
    assert couverture(agg) == {"step_failed": 1}
    sensible = _three_engines(
        tmp_path / "sensible", ("cer",), failure_policy=politique_empty_page()
    )
    assert per_document(sensible, "panne", "b").value == pytest.approx(1.0)
    assert per_document(sensible, "vide", "b").value == pytest.approx(1.0)
    assert str(sensible.manifest.failure_policy) == "empty_page"


@pytest.mark.parametrize(
    "metric",
    [
        pytest.param(
            "ins_rate", marks=pytest.mark.discutable("C08-imputation-echec-max-error")
        )
    ],
)
def test_max_error__echec_note_comme_une_page_vide(tmp_path: Path, metric: str) -> None:
    """Reformulé (§ 2.1 e) : par défaut l'échec n'est pas noté ; sous
    ``empty_page``, sa valeur est celle que la métrique donne à la page vide du
    pipeline ``vide`` sur le même document — pour ``ins_rate``, 0,0 (une page
    vide n'insère rien), et non le « 1 » de ``max_error``."""
    result = _three_engines(tmp_path / "defaut", (metric,))
    assert per_document(result, "panne", "b", metric).value is None
    sensible = _three_engines(
        tmp_path / "sensible", (metric,), failure_policy=politique_empty_page()
    )
    failed = per_document(sensible, "panne", "b", metric)
    empty = per_document(sensible, "vide", "b", metric)
    assert (failed.value, empty.value) == (0.0, 0.0)
    assert str(sensible.manifest.failure_policy) == "empty_page"


@pytest.mark.valide
def test_max_error__un_echec_compte_comme_note_deplace_lagregat(tmp_path: Path) -> None:
    """``bow_precision`` pèse par la taille de l'**hypothèse** : l'échec noté 0
    a un poids nul. S'il est compté dans « n notés » (3/3), l'agrégat doit en
    porter la trace ; il vaut pourtant exactement celui des deux pages réussies."""
    result = _three_engines(tmp_path, ("bow_precision",), failure_policy="max_error")
    agg = aggregate(result, "panne", "bow_precision")
    failed = per_document(result, "panne", "b", "bow_precision")
    assert not (agg.support == 3 and agg.value == 1.0), (
        f"échec noté {failed.value} (poids {failed.support}) ; agrégat "
        f"{agg.value} sur {agg.support}/{agg.expected} — identique sans l'échec"
    )

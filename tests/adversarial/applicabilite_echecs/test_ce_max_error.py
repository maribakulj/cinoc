"""Affirmation 2 (suite) — la règle ``max_error`` (``runner._score_failed``) :
``worst = 0.0 if higher_is_better else 1.0``. Elle ne peut pas être déduite de
``higher_is_better`` seul.

Références indépendantes : distance d'édition écrite à la main ; la valeur
que la **métrique elle-même** donne à une page rendue vide (ce que la
documentation de ``EvaluationSpec`` promet : « comme une page rendue vide »).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.extension import AdapterStepError

from ._kit import (
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

REF = "Le chat 1789 dort sur le tapis"
GARBAGE = " ".join(["zq"] * 30)  # sortie hallucinée, trois fois plus longue que la page


def _behaviour(outputs: dict[str, str | None]):  # type: ignore[no-untyped-def]
    """``None`` = la brique lève l'erreur typée d'un moteur en panne."""

    def run(document_id: str) -> str | AdapterStepError:
        text = outputs[document_id]
        return AdapterStepError("moteur en panne") if text is None else text

    return run


def _three_engines(tmp_path: Path, metrics: tuple[str, ...]):  # type: ignore[no-untyped-def]
    """``panne`` échoue sur ``b`` ; ``vide`` y rend une page vide ; ``bavard`` y
    hallucine. Sur ``a`` et ``c`` les trois sont parfaits."""
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
            failure_policy="max_error",
        ),
        registry_with(*bricks),
    )


def test_max_error__un_echec_ne_note_jamais_mieux_quune_reponse(tmp_path: Path) -> None:
    """CER non borné : le moteur qui répond n'importe quoi sur ``b`` obtient un
    CER > 1 (calculé à la main) ; « erreur maximale » doit noter l'échec au moins
    aussi mal, sinon échouer rapporte plus que répondre."""
    result = _three_engines(tmp_path, ("cer",))
    bavard = levenshtein(REF, GARBAGE) / len(REF)
    assert per_document(result, "bavard", "b").value == pytest.approx(bavard)
    panne = per_document(result, "panne", "b").value
    assert panne is not None and panne >= bavard, (
        f"CER échec = {panne}, CER réponse hallucinée = {bavard:.3f} ; agrégats "
        f"panne={aggregate(result, 'panne').value:.3f}, "
        f"bavard={aggregate(result, 'bavard').value:.3f}"
    )


@pytest.mark.parametrize(
    "metric",
    [
        "cer",
        "wer",
        "mer",
        "cmer",
        "del_rate",
        "ins_rate",
        "char_accuracy",
        "word_accuracy",
        "bow_recall",
        "bow_f1",
        "searchability",
        "numseq_value",
    ],
)
def test_max_error__echec_note_comme_une_page_vide(tmp_path: Path, metric: str) -> None:
    """La spec promet qu'un échec sous ``max_error`` est noté « comme une page
    rendue vide » : sa valeur et son poids doivent être ceux que la métrique
    donne à la page vide du pipeline ``vide`` sur le même document."""
    result = _three_engines(tmp_path, (metric,))
    failed = per_document(result, "panne", "b", metric)
    empty = per_document(result, "vide", "b", metric)
    assert (failed.value, failed.support) == (empty.value, empty.support), (
        f"{metric} : échec = {failed.value} (poids {failed.support}), "
        f"page vide = {empty.value} (poids {empty.support})"
    )


def test_max_error__un_echec_compte_comme_note_deplace_lagregat(tmp_path: Path) -> None:
    """``bow_precision`` pèse par la taille de l'**hypothèse** : l'échec noté 0
    a un poids nul. S'il est compté dans « n notés » (3/3), l'agrégat doit en
    porter la trace ; il vaut pourtant exactement celui des deux pages réussies."""
    result = _three_engines(tmp_path, ("bow_precision",))
    agg = aggregate(result, "panne", "bow_precision")
    failed = per_document(result, "panne", "b", "bow_precision")
    assert not (agg.support == 3 and agg.value == 1.0), (
        f"échec noté {failed.value} (poids {failed.support}) ; agrégat "
        f"{agg.value} sur {agg.support}/{agg.expected} — identique sans l'échec"
    )

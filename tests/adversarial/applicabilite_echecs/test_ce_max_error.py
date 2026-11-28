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
from tests.adversarial._contrat import (
    agregat_operationnel,
    couverture,
    politique_empty_page,
    support_micro,
)

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
    """Reformulé (§ 2.1 e, f, A7 ; ``max_error`` est retiré). Intention conservée :
    un échec **compté comme noté** (sous ``empty_page``, une sortie vide) ne doit
    pas laisser l'agrégat identique à celui des pages réussies sans que rien ne le
    dise. Ce qui change, calculé à la main sur ``panne`` (a et c parfaits, b en
    échec, référence de 7 mots) :

    - **ce qui est noté** : l'échec n'est plus noté 0 mais comme une hypothèse
      vide (tp 0, fp 0, fn 7), non plus par ``max_error`` ;
    - ``bow_precision`` (dénominateur : l'hypothèse) **ne bouge pas**, par
      construction : une sortie vide n'ajoute ni vrai ni faux positif, Σtp/Σ|hyp|
      reste 14/14 = 1,0. Le document est désormais compté (support 3/3, scalaire
      indéfini ``zero_denominator``), et sa trace est dans la statistique (fn = 7),
      non dans la précision : l'ancien attendu « l'agrégat de précision doit
      changer » n'est plus vrai du côté précision ;
    - ``bow_recall`` (dénominateur : la référence) **bouge** : de 14/14 = 1,0 (a et
      c seuls, par défaut) à 14/21 = 2/3 sous ``empty_page`` ; ``bow_f1`` suit :
      2·14/(2·14 + 0 + 7) = 0,8 ;
    - par défaut, aucune imputation : précision et rappel valent 1,0 sur 2 notés
      sur 3 attendus, et la couverture dit ``step_failed`` : 1.
    """
    metrics = ("bow_precision", "bow_recall", "bow_f1")
    sensible = _three_engines(
        tmp_path / "sensible", metrics, failure_policy=politique_empty_page()
    )
    precision = aggregate(sensible, "panne", "bow_precision")
    rappel = aggregate(sensible, "panne", "bow_recall")
    f1 = aggregate(sensible, "panne", "bow_f1")
    assert rappel.value == pytest.approx(14 / 21), (
        f"un échec noté comme sortie vide doit déplacer le rappel : {rappel.value}"
    )
    assert f1.value == pytest.approx(0.8)
    assert precision.value == pytest.approx(1.0), "précision : sortie vide"
    assert (support_micro(precision), precision.expected) == (3, 3)
    assert (support_micro(rappel), rappel.expected) == (3, 3)
    # Par défaut : aucune imputation (agrégat conditionnel) ; la qualité
    # opérationnelle, publiée à côté, note l'échec comme une sortie vide.
    defaut = _three_engines(tmp_path / "defaut", metrics)
    for metric in metrics:
        agg = aggregate(defaut, "panne", metric)
        assert agg.value == pytest.approx(1.0), metric
        assert (support_micro(agg), agg.expected) == (2, 3), metric
        assert couverture(agg) == {"step_failed": 1}, metric
    assert agregat_operationnel(defaut, "panne", "bow_recall").value == pytest.approx(
        14 / 21
    )
    assert agregat_operationnel(defaut, "panne", "bow_precision").value == (
        pytest.approx(1.0)
    )

"""Affirmation 6 — échecs partiels : OCR réussi **et facturé**, puis correction
LLM défaillante, dans un même pipeline.

La panne est simulée par une brique tierce (``Module`` Protocol, branchée par
``discover_plugins``) qui lève l'erreur typée du produit
(``AdapterStepError(billed=…)``) ; l'orchestrateur n'est pas touché.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.extension import AdapterStepError, Artifact
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import INITIAL_STEP_ID
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.pipeline.types import DocumentExecution

from ._kit import (
    T,
    TextBrick,
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

REF = "abcdefghijklmnopqrst"
OCR_TEXT = {"a": "abcdefghijklmnopqrsX", "b": "aXcdefghijklmnopqrsX"}
OCR_USAGE = ResourceUsage(tokens_in=500, tokens_out=200, billed_pages=1)
LLM_USAGE = ResourceUsage(tokens_in=300, tokens_out=100)
LLM_REFUSED = ResourceUsage(tokens_in=300)


def _bricks(fail_once: bool = False) -> tuple[TextBrick, TextBrick]:
    """OCR facturé (jetons + une page) ; correcteur qui échoue sur ``b`` — à
    chaque appel, ou seulement au premier (panne transitoire)."""
    ocr = TextBrick("ce_ocr", lambda d: OCR_TEXT[d], usage=OCR_USAGE)
    seen: list[str] = []

    def correct(document_id: str) -> str | AdapterStepError:
        seen.append(document_id)
        if document_id == "b" and (not fail_once or seen.count("b") == 1):
            return AdapterStepError("réponse refusée par le fournisseur", billed=LLM_REFUSED)
        return REF

    llm = TextBrick(
        "ce_llm", correct, in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT, usage=LLM_USAGE
    )
    return ocr, llm


def _spec(tmp_path: Path, *, analyses: tuple[str, ...] | None = None):  # type: ignore[no-untyped-def]
    views = [
        text_view("final", candidates=(T.RAW_TEXT, T.CORRECTED_TEXT)),
        text_view("ocr_seul", candidates=(T.RAW_TEXT,), target_step="ocr"),
    ]
    return spec(
        corpus(tmp_path / "corpus", {"a": REF, "b": REF}),
        [
            pipeline(
                "ocr_llm",
                step("ocr", "ce_ocr"),
                step("llm", "ce_llm", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT),
            )
        ],
        views,
        analyses=analyses,
    )


@pytest.fixture
def corpus_dir(tmp_path: Path) -> Path:
    (tmp_path / "corpus").mkdir()
    return tmp_path


def test_echec_partiel__le_type_interdit_bien_les_artefacts_dune_unite_failed() -> None:
    """Constat sur le type : ``DocumentExecution`` refuse une unité ``failed``
    qui porte des artefacts (vert = l'affirmation du mainteneur est exacte)."""
    image = Artifact(id="b:init:image", document_id="b", type=T.IMAGE, uri="b.png")
    with pytest.raises(CinocError, match="n'a pas d'artefact"):
        DocumentExecution(
            by_step={INITIAL_STEP_ID: {T.IMAGE: image}},
            outcome="failed",
            reason="engine",
        )


def test_echec_partiel__lamont_reussi_reste_observable(corpus_dir: Path) -> None:
    """Après l'échec de la correction sur ``b``, la vue ``target_step: ocr`` doit
    noter le texte OCR qui a été produit (et payé) : CER = d(REF, OCR)/|REF|."""
    ocr, llm = _bricks()
    result = execute(_spec(corpus_dir), registry_with(ocr, llm))
    assert ocr.calls == ["a", "b"]  # l'OCR a bien produit b
    attendu = levenshtein(REF, OCR_TEXT["b"]) / len(REF)
    obtenu = per_document(result, "ocr_llm", "b", view="ocr_seul").value
    assert obtenu == pytest.approx(attendu), (
        f"CER OCR de b = {obtenu} (attendu {attendu}) : la sortie amont est jetée"
    )


def test_echec_partiel__le_cout_amont_reste_compte_a_lunite(corpus_dir: Path) -> None:
    """L'unité ``b`` a payé l'OCR (500/200 jetons, 1 page) puis le refus LLM
    (300 jetons) : sa ligne d'``usage`` doit porter les deux."""
    ocr, llm = _bricks()
    result = execute(_spec(corpus_dir), registry_with(ocr, llm))
    unit = next(u for u in result.usage if u.document_id == "b")
    assert unit.outcome == "failed"
    assert (unit.usage.tokens_in, unit.usage.tokens_out, unit.usage.billed_pages) == (
        800,
        200,
        1,
    ), f"usage de l'unité en échec : {unit.usage}"


def test_echec_partiel__le_bilan_economique_compte_lamont_paye(corpus_dir: Path) -> None:
    """Bilan du run : ``a`` = 800 jetons d'entrée, ``b`` = 500 (OCR) + 300 (refus)
    = 800 ; total 1600 (les pages ne sont comptées qu'à un moteur tarifé à la
    page : la brique de test ne l'est pas, on ne regarde que les jetons)."""
    ocr, llm = _bricks()
    result = execute(_spec(corpus_dir, analyses=("economics",)), registry_with(ocr, llm))
    (row,) = [
        r
        for a in result.analyses
        if isinstance(a.payload, EconomicsPayload) and a.view == "final"
        for r in a.payload.pipelines
    ]
    assert row.tokens_in == 1600, f"bilan : tokens_in={row.tokens_in}"


def test_echec_partiel__pipeline_tout_en_echec_garde_sa_facture(corpus_dir: Path) -> None:
    """Si la correction échoue sur **toutes** les pages, ce que le pipeline a fait
    facturer ne disparaît pas du bilan économique."""
    ocr = TextBrick("ce_ocr", lambda d: OCR_TEXT[d], usage=OCR_USAGE)
    llm = TextBrick(
        "ce_llm",
        lambda d: AdapterStepError("quota dépassé", billed=LLM_REFUSED),
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    result = execute(_spec(corpus_dir, analyses=("economics",)), registry_with(ocr, llm))
    rows = [
        r
        for a in result.analyses
        if isinstance(a.payload, EconomicsPayload) and a.view == "final"
        for r in a.payload.pipelines
    ]
    billed = sum(u.usage.tokens_in or 0 for u in result.usage)
    assert [r.pipeline for r in rows] == ["ocr_llm"], (
        f"aucune ligne au bilan alors que les unités portent {billed} jetons facturés"
    )


def test_echec_partiel__la_reprise_ne_repaie_pas_lamont(corpus_dir: Path) -> None:
    """Panne transitoire du correcteur sur ``b`` ; on relance avec la même
    archive (``--resume-dir``). Seule l'étape aval doit être rejouée : l'OCR de
    ``b``, déjà produit et facturé, ne doit pas être rappelé."""
    ocr, llm = _bricks(fail_once=True)
    registry = registry_with(ocr, llm)
    archive = corpus_dir / "archive"
    first = execute(_spec(corpus_dir), registry, resume_dir=archive)
    assert {u.document_id: u.outcome for u in first.usage} == {"a": "ok", "b": "failed"}
    second = execute(_spec(corpus_dir), registry, resume_dir=archive)
    assert {u.document_id: u.outcome for u in second.usage} == {"a": "ok", "b": "ok"}
    assert ocr.calls.count("a") == 1  # l'unité réussie, elle, est bien reprise
    assert ocr.calls.count("b") == 1, (
        f"OCR de b exécuté {ocr.calls.count('b')} fois : l'amont est repayé"
    )

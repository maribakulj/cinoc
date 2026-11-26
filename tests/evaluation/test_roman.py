"""Numéraux romains : parseur, 5 statuts de restitution, collecteur, R1/R2.

Valeurs dérivées à la main (règles romaines publiées). Vérifie aussi que le
romain n'est compté **qu'**en philologie (R1) et que ``min_length=2`` filtre
les lettres isolées (R2).
"""

from __future__ import annotations

import itertools
from datetime import UTC, datetime
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import RomanNumeralsPayload, StructuredDataPayload
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.roman import (
    RomanNumeralsCollector,
    classify,
    detect_roman_numerals,
    roman_to_int,
)
from cinoc.evaluation.runner import evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def test_roman_to_int_valid_forms() -> None:
    assert roman_to_int("XIV") == 14
    assert roman_to_int("iv") == 4  # casse tolérée
    assert roman_to_int("IIII") == 4  # forme médiévale relâchée acceptée
    assert roman_to_int("viij") == 8  # j médiéval final (viii)
    # MCCLXXXIJ → MCCLXXXII = 1000+200+50+30+2 (le « ij » final note « ii »).
    assert roman_to_int("MCCLXXXIJ") == 1282


def test_roman_to_int_rejects_implausible() -> None:
    assert roman_to_int("IL") is None  # paire soustractive illégale
    assert roman_to_int("IIIII") is None  # répétition absurde
    assert roman_to_int("VV") is None
    assert roman_to_int("") is None
    assert roman_to_int("bonjour") is None


#: Les 3 999 formes canoniques (1 → 3 999), écrites ici par la règle des
#: chiffres — milliers, centaines, dizaines, unités — sans passer par le module.
_CHIFFRES = (
    ("", "M", "MM", "MMM"),
    ("", "C", "CC", "CCC", "CD", "D", "DC", "DCC", "DCCC", "CM"),
    ("", "X", "XX", "XXX", "XL", "L", "LX", "LXX", "LXXX", "XC"),
    ("", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX"),
)


def _canonique(n: int) -> str:
    return "".join(
        chiffres[(n // puissance) % 10]
        for chiffres, puissance in zip(_CHIFFRES, (1000, 100, 10, 1), strict=True)
    )


def test_every_canonical_form_reads_its_value() -> None:
    for n in range(1, 4000):
        assert roman_to_int(_canonique(n)) == n


def test_malformed_numerals_are_refused() -> None:
    """Défaut 11 de l'audit D-264 : ``IIV``, ``IXI``, ``VIV``, ``XIIX`` étaient
    acceptés — chaque paire soustractive était légale prise seule, mais aucune
    écriture romaine, ni canonique ni médiévale, ne les produit."""
    for forme in (
        "IIV", "IXI", "VIV", "XIIX", "IIX", "XXC", "IVI", "IXX", "XCX", "CMC",
        "VIX", "LXL", "DCD", "IVIV", "XLX", "MMMMM", "DD", "LL",
    ):
        assert roman_to_int(forme) is None, forme


def test_only_canonical_and_medieval_additive_forms_pass() -> None:
    """Toute chaîne de ``IVXLCDM`` (jusqu'à 5 lettres, 19 607 chaînes) acceptée
    est soit canonique, soit la forme additive médiévale d'un chiffre (``IIII``,
    ``VIIII``, ``XXXX``, ``LXXXX``, ``CCCC``, ``DCCCC``, ``MMMM``) — et vaut
    alors ce que vaut sa forme canonique."""
    canoniques = {_canonique(n): n for n in range(1, 4000)}
    # Le chiffre 9 additif d'abord : ``VIIII`` contient ``IIII``.
    additives = {"VIIII": "IX", "IIII": "IV", "LXXXX": "XC", "XXXX": "XL",
                 "DCCCC": "CM", "CCCC": "CD"}
    for longueur in range(1, 6):
        for lettres in itertools.product("IVXLCDM", repeat=longueur):
            forme = "".join(lettres)
            valeur = roman_to_int(forme)
            if valeur is None:
                continue
            canonique = forme
            for additive, soustractive in additives.items():
                canonique = canonique.replace(additive, soustractive)
            if canonique.startswith("MMMM"):
                assert valeur == 4000 + canoniques.get(canonique[4:], 0), forme
                continue
            assert canoniques.get(canonique) == valeur, forme


def test_medieval_additive_forms_are_kept() -> None:
    """D-121 : l'additif médiéval n'est pas une faute (``xiiij`` = 14)."""
    assert roman_to_int("xiiij") == 14
    assert roman_to_int("VIIII") == 9
    assert roman_to_int("MCCCCLXXXXVIIII") == 1499
    assert roman_to_int("MMMM") == 4000


def test_detect_min_length_two_filters_singletons() -> None:
    """R2 : « I » isolé (pronom) n'est pas retenu, « XIV » oui."""
    found = detect_roman_numerals("I saw XIV ships", min_length=2)
    assert [(form, value) for _i, form, value in found] == [("XIV", 14)]


def test_classify_five_statuses() -> None:
    assert classify("XIV", 14, "Louis XIV règne") == "strict_preserved"
    assert classify("xiv", 14, "chapitre XIV") == "case_changed"
    assert classify("viij", 8, "numéro viii") == "j_dropped"
    assert classify("IV", 4, "tome 4 relié") == "converted_to_arabic"
    assert classify("XII", 12, "texte sans rien") == "lost"


def test_collector_aggregates_statuses() -> None:
    collector = RomanNumeralsCollector()
    collector.observe("eng", "Louis XIV", "Louis XIV")  # strict
    collector.observe("eng", "tome IV", "tome 4")  # converted
    collector.observe("eng", "roi XII", "roi malade")  # lost (XII)
    analysis = collector.build("text")
    assert analysis is not None
    assert isinstance(analysis.payload, RomanNumeralsPayload)
    (row,) = analysis.payload.pipelines
    assert row.n_total == 3
    assert row.strict_preserved == 1
    assert row.converted_to_arabic == 1
    assert row.lost == 1
    assert row.lost_samples == ("XII",)


def test_collector_silent_without_numerals() -> None:
    collector = RomanNumeralsCollector()
    collector.observe("eng", "texte moderne", "texte moderne")
    assert collector.build("text") is None


def _run(tmp_path: Path, gt_text: str, hyp_text: str) -> object:
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text(gt_text, encoding="utf-8")
    hyp = tmp_path / "doc1.hyp.txt"
    hyp.write_text(hyp_text, encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    outputs = {
        "eng": {
            "doc1": {
                "ocr": {
                    ArtifactType.RAW_TEXT: Artifact(
                        id="doc1:raw",
                        document_id="doc1",
                        type=ArtifactType.RAW_TEXT,
                        uri=str(hyp),
                    )
                }
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    view = EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    manifest = RunManifest(
        run_id="r",
        corpus_name="c",
        n_documents=1,
        pipeline_specs=(
            PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
    )
    return evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,), analyses="toutes"),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=manifest,
    )


def test_through_evaluate_run_and_r1_single_count(tmp_path: Path) -> None:
    """« Louis XIV » → compté en romain, **pas** en données structurées (R1)."""
    result = _run(tmp_path, "Louis XIV", "Louis 14")
    roman = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, RomanNumeralsPayload)
    ]
    structured = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, StructuredDataPayload)
    ]
    assert len(roman) == 1
    assert structured == []  # pas de double comptage du romain
    (row,) = roman[0].pipelines
    assert row.n_total == 1
    assert row.converted_to_arabic == 1

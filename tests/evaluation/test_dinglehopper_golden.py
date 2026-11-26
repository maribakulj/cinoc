"""Golden **dinglehopper** sur le mini-corpus de référence ``bnl_mini``.

Critère de sortie de P5e 10 (D-290). Pour chacun des 150 couples (30 pages ×
5 moteurs), le CER et le WER de Cinoc — vue ``texte (lignes)``, le chiffre
comparable d'après D-285 — sont rapprochés de ceux de dinglehopper 0.11.0
(``plain_extract`` des deux fichiers, puis ``character_error_rate`` /
``word_error_rate``) par une **chaîne d'écarts** : chaque maillon retire *une*
différence de convention, et le dernier tombe exactement sur dinglehopper.
Un écart n'est donc pas « une tolérance » : il est nommé, mesuré, et sa somme
explique tout.

Chaîne du CER (:data:`CER_STAGES`), chaque maillon cumulant les précédents :

1. ``cinoc`` — la vue ``texte (lignes)`` (``keep_line_breaks``) : NFC,
   invisibles retirés, blancs d'une ligne écrasés en une espace, lignes vides
   de tête et de fin retirées ; points de code.
2. ``blancs`` — les lignes à la manière de dinglehopper : chacune ``strip``-ée,
   rien d'autre. **30 couples bougent** : les espaces multiples à l'intérieur
   d'une ligne, que dinglehopper compte un par un et que Cinoc écrase.
3. ``invisibles`` — les invisibles (``Cf``/``Cc``) gardés, comme dinglehopper.
   **0 couple** sur ``bnl_mini`` (aucun dans ces textes ; le cas construit est
   à ``test_normalization_parity``).
4. ``sbb`` — ``normalize_sbb`` de dinglehopper, ligne par ligne (NFC,
   ligatures dépliées, ``’`` → ``'``, ``—`` → ``–``, ``⸗`` → ``-``…).
   **87 couples bougent** — surtout l'apostrophe (303 remplacements dans les
   180 fichiers : la GT BNL écrit ``’``, Tesseract lit souvent ``'``), puis
   ``⸗`` (31), ``—`` (14) et ``==`` (6). Cinoc ne les unifie pas (D-285 :
   équivalence de contenu = convention du corpus).
5. ``graphemes`` — distance sur les **graphèmes** (``uniseg``) au lieu des
   points de code. **0 couple** sur ``bnl_mini`` (aucune suite combinante
   après NFC) ; = dinglehopper, **150/150**.

Chaîne du WER (:data:`WER_STAGES`) — le découpage aux blancs de Cinoc ignore
déjà les espaces multiples, d'où pas de maillon ``blancs`` :

1. ``cinoc`` — ``split()`` sur la vue ``texte (lignes)`` (même valeur sous
   ``texte`` : les blancs ne comptent pas au mot) ;
2. ``invisibles`` — NFC seul ; **0 couple** ;
3. ``sbb`` — ``normalize_sbb`` ; **74 couples bougent** (``l’entente`` contre
   ``l'entente``, un mot faux de moins) ;
4. ``uax29`` — les mots de dinglehopper : segmentation Unicode UAX #29
   (``uniseg.wordbreak``), mots faits de seule ponctuation écartés — « Russie; »
   fait **un** mot chez Cinoc, **un mot et rien** chez dinglehopper ; **122
   couples bougent** ; = dinglehopper, **150/150**.

Le CER de Cinoc vaut celui de dinglehopper sur **49** couples sans aucun pont.

Ce qui tourne où :

- **partout** (suite ordinaire) : le côté Cinoc de la chaîne est recalculé et
  comparé au golden — si le calcul de Cinoc change, ce test le dit et le golden
  se régénère (avec l'oracle) au lieu de dériver ; le golden est cohérent (son
  dernier maillon vaut sa colonne dinglehopper) et ses écarts sont ceux que ce
  docstring documente ;
- **job CI ``oracle``** (marqueur ``oracle``, extra ``oracle`` +
  dinglehopper ``--no-deps``) : dinglehopper est **exécuté**, et ses chiffres
  comme les maillons qui l'utilisent doivent égaler le golden.

Régénérer (dans un environnement d'oracle, cf. ``README.md`` §Development) ::

    python tests/evaluation/test_dinglehopper_golden.py
"""

from __future__ import annotations

import json
import unicodedata
from collections.abc import Callable, Sequence
from importlib import metadata
from pathlib import Path
from typing import Any

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.text import _edit_distance, _error_rate, cer, wer
from cinoc.evaluation.representations import prepare_text
from cinoc.formats.text.normalization import NormalizationProfile

_ROOT = Path(__file__).resolve().parents[2]
_CORPUS = _ROOT / "tests" / "fixtures" / "reference_corpus" / "bnl_mini"
_GOLDEN = _ROOT / "tests" / "fixtures" / "dinglehopper_golden" / "bnl_mini.json"

CER_STAGES = ("cinoc", "blancs", "invisibles", "sbb", "graphemes")
WER_STAGES = ("cinoc", "invisibles", "sbb", "uax29")
#: Maillons qui n'appellent pas dinglehopper : recalculés dans la suite ordinaire.
_CINOC_SIDE = {"cer": CER_STAGES[:3], "wer": WER_STAGES[:2]}

#: Couples que chaque maillon fait bouger (documentés au docstring).
DOCUMENTED_GAPS = {
    "cer": {"blancs": 30, "invisibles": 0, "sbb": 87, "graphemes": 0},
    "wer": {"invisibles": 0, "sbb": 74, "uax29": 122},
}
#: Couples où le CER de Cinoc vaut déjà celui de dinglehopper, sans pont.
DOCUMENTED_EXACT_CER = 49

_LINES_VIEW = EvaluationView(
    name="texte (lignes)",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    normalization_profile="keep_line_breaks",
)
#: NFC + invisibles retirés, blancs intacts : Cinoc sans son traitement des blancs.
_NFC_CLEAN = NormalizationProfile(name="nfc_sans_blancs", whitespace="none")


def _lines(raw: str) -> list[str]:
    """Les lignes de ``raw`` comme ``readlines()`` les rend, fin de ligne ôtée."""
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return lines[:-1] if raw.endswith(("\n", "\r")) else lines


def _dh_layout(raw: str) -> str:
    """Le texte tel que ``plain_extract`` l'assemble : chaque ligne ``strip``-ée,
    lignes jointes par ``\\n`` (avant ``normalize_sbb``)."""
    return "\n".join(line.strip() for line in _lines(raw))


def _ratio(reference: Sequence[str], hypothesis: Sequence[str]) -> float:
    return _error_rate(_edit_distance(reference, hypothesis), len(reference))


def _metric(fn: Callable[[DocContext], Any], reference: str, hypothesis: str) -> float:
    observation = fn(
        DocContext(
            document_id="d",
            reference=prepare_text(reference, _LINES_VIEW),
            hypothesis=prepare_text(hypothesis, _LINES_VIEW),
        )
    )
    return float(observation.value)


def cinoc_side(reference: str, hypothesis: str) -> dict[str, dict[str, float]]:
    """Maillons sans dinglehopper : Cinoc, puis ses blancs et ses invisibles ôtés."""
    ref, hyp = _dh_layout(reference), _dh_layout(hypothesis)
    nfc_ref = unicodedata.normalize("NFC", ref)
    nfc_hyp = unicodedata.normalize("NFC", hyp)
    return {
        "cer": {
            "cinoc": _metric(cer.fn, reference, hypothesis),
            "blancs": _ratio(_NFC_CLEAN.normalize(ref), _NFC_CLEAN.normalize(hyp)),
            "invisibles": _ratio(nfc_ref, nfc_hyp),
        },
        "wer": {
            "cinoc": _metric(wer.fn, reference, hypothesis),
            "invisibles": _ratio(nfc_ref.split(), nfc_hyp.split()),
        },
    }


def oracle_side(reference: str, hypothesis: str) -> dict[str, dict[str, float]]:
    """Maillons qui empruntent à dinglehopper (``normalize_sbb``, graphèmes, mots)."""
    from dinglehopper.extracted_text import normalize_sbb
    from dinglehopper.word_error_rate import words_normalized
    from uniseg.graphemecluster import grapheme_clusters

    ref = "\n".join(normalize_sbb(line.strip()) for line in _lines(reference))
    hyp = "\n".join(normalize_sbb(line.strip()) for line in _lines(hypothesis))
    return {
        "cer": {
            "sbb": _ratio(ref, hyp),
            "graphemes": _ratio(
                list(grapheme_clusters(ref)), list(grapheme_clusters(hyp))
            ),
        },
        "wer": {
            "sbb": _ratio(ref.split(), hyp.split()),
            "uax29": _ratio(list(words_normalized(ref)), list(words_normalized(hyp))),
        },
    }


def dinglehopper_scores(gt: Path, ocr: Path) -> dict[str, float]:
    """CER et WER de dinglehopper, exécuté comme sa CLI le fait sur deux .txt."""
    from dinglehopper.character_error_rate import character_error_rate
    from dinglehopper.ocr_files import plain_extract
    from dinglehopper.word_error_rate import word_error_rate

    reference = plain_extract(str(gt), encoding="utf-8")
    compared = plain_extract(str(ocr), encoding="utf-8")
    return {
        "cer": float(character_error_rate(reference, compared)),
        "wer": float(word_error_rate(reference, compared)),
    }


def _couples() -> list[tuple[str, str]]:
    return [
        (gt.name.removesuffix(".gt.txt"), ocr.name.split(".")[1])
        for gt in sorted(_CORPUS.glob("*.gt.txt"))
        for ocr in sorted(_CORPUS.glob(f"{gt.name.removesuffix('.gt.txt')}.*.txt"))
        if ocr.name != gt.name
    ]


def _texts(page: str, engine: str) -> tuple[str, str]:
    return (
        (_CORPUS / f"{page}.gt.txt").read_text(encoding="utf-8"),
        (_CORPUS / f"{page}.{engine}.txt").read_text(encoding="utf-8"),
    )


def _golden() -> dict[str, Any]:
    data: dict[str, Any] = json.loads(_GOLDEN.read_text(encoding="utf-8"))
    return data


def _golden_pairs() -> dict[tuple[str, str], dict[str, Any]]:
    return {(p["page"], p["engine"]): p for p in _golden()["pairs"]}


_COUPLES = _couples()
_IDS = [f"{page}-{engine}" for page, engine in _COUPLES]


def test_the_golden_covers_the_reference_corpus() -> None:
    assert len(_COUPLES) == 150
    assert sorted(_golden_pairs()) == sorted(_COUPLES)


@pytest.mark.parametrize(("page", "engine"), _COUPLES, ids=_IDS)
def test_cinoc_side_of_the_chain_is_the_golden(page: str, engine: str) -> None:
    """Le calcul de Cinoc n'a pas bougé depuis le golden (sinon : régénérer)."""
    expected = _golden_pairs()[(page, engine)]
    current = cinoc_side(*_texts(page, engine))
    for metric, stages in _CINOC_SIDE.items():
        for stage in stages:
            assert current[metric][stage] == pytest.approx(
                expected[metric][stage], rel=1e-12, abs=1e-15
            ), (metric, stage)


def test_the_chain_ends_on_dinglehopper() -> None:
    """Dernier maillon = dinglehopper sur chaque couple : rien d'inexpliqué."""
    for pair in _golden()["pairs"]:
        assert pair["cer"]["graphemes"] == pair["dinglehopper"]["cer"], pair["page"]
        assert pair["wer"]["uax29"] == pair["dinglehopper"]["wer"], pair["page"]


def test_each_gap_moves_the_documented_number_of_pairs() -> None:
    pairs = _golden()["pairs"]
    for metric, stages in (("cer", CER_STAGES), ("wer", WER_STAGES)):
        moved = {
            after: sum(p[metric][before] != p[metric][after] for p in pairs)
            for before, after in zip(stages, stages[1:], strict=False)
        }
        assert moved == DOCUMENTED_GAPS[metric], metric
    exact = sum(p["cer"]["cinoc"] == p["dinglehopper"]["cer"] for p in pairs)
    assert exact == DOCUMENTED_EXACT_CER


@pytest.mark.oracle
def test_the_golden_was_computed_by_the_installed_oracle() -> None:
    pytest.importorskip("dinglehopper")
    assert _golden()["oracle"] == {
        "dinglehopper": metadata.version("dinglehopper"),
        "uniseg": metadata.version("uniseg"),
    }


@pytest.mark.oracle
@pytest.mark.parametrize(("page", "engine"), _COUPLES, ids=_IDS)
def test_dinglehopper_executed_matches_the_golden(page: str, engine: str) -> None:
    pytest.importorskip("dinglehopper")
    expected = _golden_pairs()[(page, engine)]
    assert dinglehopper_scores(
        _CORPUS / f"{page}.gt.txt", _CORPUS / f"{page}.{engine}.txt"
    ) == pytest.approx(expected["dinglehopper"], rel=1e-12)
    bridged = oracle_side(*_texts(page, engine))
    for metric, stages in bridged.items():
        for stage, value in stages.items():
            assert value == pytest.approx(expected[metric][stage], rel=1e-12)


def _generate() -> dict[str, Any]:
    pairs = []
    for page, engine in _COUPLES:
        reference, hypothesis = _texts(page, engine)
        cinoc_values, oracle_values = (
            cinoc_side(reference, hypothesis),
            oracle_side(reference, hypothesis),
        )
        pairs.append(
            {
                "page": page,
                "engine": engine,
                "cer": {
                    stage: {**cinoc_values["cer"], **oracle_values["cer"]}[stage]
                    for stage in CER_STAGES
                },
                "wer": {
                    stage: {**cinoc_values["wer"], **oracle_values["wer"]}[stage]
                    for stage in WER_STAGES
                },
                "dinglehopper": dinglehopper_scores(
                    _CORPUS / f"{page}.gt.txt", _CORPUS / f"{page}.{engine}.txt"
                ),
            }
        )
    return {
        "oracle": {
            "dinglehopper": metadata.version("dinglehopper"),
            "uniseg": metadata.version("uniseg"),
        },
        "corpus": "tests/fixtures/reference_corpus/bnl_mini",
        "view": "texte (lignes)",
        "cer_stages": list(CER_STAGES),
        "wer_stages": list(WER_STAGES),
        "pairs": pairs,
    }


if __name__ == "__main__":
    golden = _generate()
    pairs = golden.pop("pairs")
    head = json.dumps(golden, ensure_ascii=False, indent=1)[:-2]
    body = ",\n  ".join(json.dumps(pair, ensure_ascii=False) for pair in pairs)
    _GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    _GOLDEN.write_text(f'{head},\n "pairs": [\n  {body}\n ]\n}}\n', encoding="utf-8")
    print(f"golden écrit : {_GOLDEN.relative_to(_ROOT)}")

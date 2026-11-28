"""Golden de conformité HIPE : nos scores vs le scorer officiel, à 1e-9.

Protocole (SPEC_HIPE §11) — **fixture vendorée**, pas d'exécution du scorer en
CI ordinaire :

1. Sur un poste **Python ≥ 3.12** : ``pip install "hipe-ocrepair-scorer==0.9.9"`` ;
2. lancer ``tests/fixtures/hipe_golden/generate.py`` : il score un **corpus
   synthétique contrôlé** (le scorer officiel ne distribue pas de corpus
   d'exemple — l'oracle reste le vrai scorer v0.9.9, seules les entrées sont
   curées) et (ré)écrit ``input.jsonl`` (enregistrements §4.8, texte brut) +
   ``expected.json`` (``{"system": {"cmer_micro": …, "cmer_macro": …}}`` ;
   ``mainscore`` = micro/macro globaux, CI bootstrap ignorées) ;
3. ce test recalcule alors les scores **par notre chemin** (profil ``hipe`` +
   ``cmer`` + conventions micro/macro §4.1) et exige l'égalité à 1e-9 — il prouve
   donc que notre profil ``hipe`` reproduit le ``norm()`` du scorer. Il tourne sur
   **n'importe quel** Python (il recalcule, il n'exécute pas le scorer).

Si la fixture est absente, le test **skip avec message** (jamais un faux vert
silencieux). La parité locale de la *formule* tourne en plus à chaque CI via
``jiwer`` (``test_metrics_conformity``).
"""

from __future__ import annotations

import json
from pathlib import Path
from statistics import fmean

import pytest

from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.conformity import cmer
from cinoc.formats.text import get_builtin_profile

_FIXTURES = Path(__file__).parent.parent / "fixtures" / "hipe_golden"
_TOLERANCE = 1e-9

pytestmark = pytest.mark.skipif(
    not (_FIXTURES / "input.jsonl").is_file()
    or not (_FIXTURES / "expected.json").is_file(),
    reason=(
        "fixture golden HIPE non vendorée (générer input.jsonl + expected.json "
        "avec le scorer officiel sur Python ≥ 3.12 — voir docstring)"
    ),
)


def test_cmer_matches_official_scorer_at_1e9() -> None:
    profile = get_builtin_profile("hipe")
    expected = json.loads((_FIXTURES / "expected.json").read_text("utf-8"))
    observations = []
    for line in (_FIXTURES / "input.jsonl").read_text("utf-8").splitlines():
        record = json.loads(line)
        reference = profile.normalize(record["ground_truth"]["transcription_unit"])
        hypothesis = profile.normalize(
            record["ocr_postcorrection_output"]["transcription_unit"]
        )
        observations.append(
            cmer.fn(
                DocContext(
                    document_id=record["document_metadata"]["document_id"],
                    reference=reference,
                    hypothesis=hypothesis,
                )
            )
        )
    # Micro = somme des comptes puis ratio (§4.1) : la finalisation de la
    # statistique cumulée, comme l'agrégat du runner (K1).
    micro = sum(o.stat.edits for o in observations) / sum(
        o.stat.reference_length + o.stat.insertions for o in observations
    )
    macro = fmean(o.value for o in observations if o.value is not None)
    scores = expected["system"]
    assert micro == pytest.approx(scores["cmer_micro"], abs=_TOLERANCE)
    assert macro == pytest.approx(scores["cmer_macro"], abs=_TOLERANCE)

"""Les statistiques suffisantes survivent à la sérialisation (tranche 1a, D-313).

La statistique n'est utile que si elle est **archivée** : un micro se
recalcule, une re-notation se compare, une analyse se refait depuis les comptes
du ``RunResult`` écrit — pas depuis la mémoire du processus qui l'a produit.
Deux preuves : l'aller-retour ``model_dump_json`` → ``model_validate_json`` sur
toutes les familles (``Fraction`` de la calibration comprise), et la relecture
du fichier qu'écrit ``cinoc run --json``.
"""

from __future__ import annotations

import json
import shutil
from fractions import Fraction
from pathlib import Path

from cinoc.app.results import load_run_result
from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.analysis import CalibrationPayload
from cinoc.evaluation.result import RunResult
from cinoc.evaluation.statistics import (
    EditCounts,
    ErrorCounts,
    MatchCounts,
    Proportion,
    combine,
)
from cinoc.interfaces.cli import main
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    entities_json,
    view,
)

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _text_run(tmp_path: Path) -> RunResult:
    tmp_path.mkdir(parents=True, exist_ok=True)
    bench = Bench(tmp_path)
    bench.document("a", "abcdefghij")
    bench.document("blank", "")
    bench.output(
        "p",
        "a",
        "abcdefgxij",
        extra={
            ArtifactType.CONFIDENCES: json.dumps(
                [{"text": "abcdefgxij", "confidence": 0.3170000000000001}]
            )
        },
    )
    bench.output("p", "blank", "inventé de toutes pièces")
    return bench.run(
        view(["cer", "char_accuracy", "bow_f1", "mufi_err"])
    )


def test_every_family_round_trips_through_json(tmp_path: Path) -> None:
    text = _text_run(tmp_path / "texte")
    entities = Bench(tmp_path / "ent", gt_type=ArtifactType.ENTITIES)
    (tmp_path / "ent").mkdir()
    entities.document("d", entities_json("Jean à Paris", [("PER", 0, 4)]))
    entities.output("p", "d", entities_json("Jean à Paris", [("LOC", 7, 12)]))
    ner = entities.run(view(["ner_f1"], ArtifactType.ENTITIES))
    for result in (text, ner):
        again = RunResult.model_validate_json(result.model_dump_json())
        assert again == result
        families = {
            type(score.stat)
            for entry in again.documents
            for score in entry.scores
            if score.stat is not None
        }
        assert families <= {EditCounts, ErrorCounts, MatchCounts, Proportion}
    families = {
        type(s.stat) for e in text.documents for s in e.scores if s.stat is not None
    }
    assert families == {EditCounts, ErrorCounts, MatchCounts, Proportion}
    (cal,) = [
        a.payload
        for a in RunResult.model_validate_json(text.model_dump_json()).analyses
        if isinstance(a.payload, CalibrationPayload)
    ]
    (bin_,) = cal.pipelines[0].bins
    # La somme exacte est relue exacte : le binaire IEEE de 0,317…, pas 0,317.
    assert bin_.confidence_sum == Fraction(0.3170000000000001)
    assert isinstance(bin_.confidence_sum, Fraction)


def test_a_blank_page_keeps_its_counts_and_reason_in_the_json(tmp_path: Path) -> None:
    raw = json.loads(_text_run(tmp_path).model_dump_json())
    (blank,) = [
        s
        for d in raw["documents"]
        if d["document_id"] == "blank"
        for s in d["scores"]
        if s["metric"] == "cer"
    ]
    assert blank["value"] is None and blank["scalar_reason"] == "zero_denominator"
    assert blank["stat"] == {
        "family": "edit_counts",
        "substitutions": 0,
        "deletions": 0,
        "insertions": 24,
        "reference_length": 0,
    }
    (accuracy,) = [
        s for p in raw["pipelines"] for s in p["conditional_aggregate"]
        if s["metric"] == "char_accuracy"
    ]
    assert accuracy["stat"] == {
        "family": "error_counts", "errors": 25, "reference_length": 10,
    }
    assert accuracy["value"] == 0.0 and accuracy["untruncated_error_rate"] == 2.5


def test_the_file_written_by_cinoc_run_carries_the_statistics(tmp_path: Path) -> None:
    shutil.copytree(EXAMPLES, tmp_path / "examples")
    out = tmp_path / "run.json"
    assert main([
        "run", str(tmp_path / "examples" / "config.yaml"),
        "-o", str(tmp_path / "r.html"), "--json", str(out),
    ]) == 0
    result = load_run_result(out)
    assert result.schema_version == 7
    checked = 0
    for entry in result.pipelines:
        for aggregate in result.principal_aggregate(entry):
            stats = [
                score.stat
                for doc in result.documents
                if (doc.pipeline, doc.view) == (entry.pipeline, entry.view)
                for score in doc.scores
                if score.metric == aggregate.metric and score.stat is not None
            ]
            # L'agrégat relu est la somme exacte des statistiques relues.
            assert aggregate.stat == combine(stats)
            checked += aggregate.stat is not None
    assert checked > 0

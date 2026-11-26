"""Export JSONL HIPE : format §4.8, sémantique R-1.8, un fichier par pipeline."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from cinoc.app.hipe_export import hipe_jsonl_sink, write_hipe_jsonl
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef


def _artifact(doc: str, kind: ArtifactType, uri: Path) -> Artifact:
    return Artifact(
        id=f"{doc}:{kind.value}", document_id=doc, type=kind, uri=str(uri)
    )


def _corpus(tmp_path: Path) -> CorpusSpec:
    gt = tmp_path / "doc1.gt.txt"
    gt.write_text("vérité terrain", encoding="utf-8")
    gt2 = tmp_path / "doc2.gt.txt"
    gt2.write_text("autre page", encoding="utf-8")
    return CorpusSpec(
        name="corpus-test",
        documents=(
            DocumentRef(
                id="doc1",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
            DocumentRef(
                id="doc2",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt2)),
                ),
            ),
            DocumentRef(id="doc3"),  # sans GT texte → sauté avec warning
        ),
    )


def test_single_pipeline_records(tmp_path: Path, caplog) -> None:
    raw = tmp_path / "doc1.raw.txt"
    raw.write_text("verite terain", encoding="utf-8")
    corrected = tmp_path / "doc1.cor.txt"
    corrected.write_text("vérité terrain", encoding="utf-8")
    outputs = {
        "chain": {
            "doc1": {
                "ocr": {
                    ArtifactType.RAW_TEXT: _artifact(
                        "doc1", ArtifactType.RAW_TEXT, raw
                    )
                },
                "llm": {
                    ArtifactType.CORRECTED_TEXT: _artifact(
                        "doc1", ArtifactType.CORRECTED_TEXT, corrected
                    )
                },
            }
            # doc2 : aucune sortie → R-1.8 (chaîne vide + warning).
        }
    }
    target = tmp_path / "out.jsonl"
    with caplog.at_level(logging.WARNING):
        written = write_hipe_jsonl(target, _corpus(tmp_path), outputs)
    assert written == [target]
    lines = [json.loads(line) for line in target.read_text("utf-8").splitlines()]
    assert len(lines) == 2  # doc3 sans GT est sauté
    assert lines[0] == {
        "document_metadata": {
            "document_id": "doc1",
            "primary_dataset_name": "corpus-test",
        },
        "ground_truth": {"transcription_unit": "vérité terrain"},
        "ocr_hypothesis": {"transcription_unit": "verite terain"},
        "ocr_postcorrection_output": {"transcription_unit": "vérité terrain"},
    }
    # R-1.8 : sortie absente = chaîne vide (erreur maximale), jamais une exclusion.
    assert lines[1]["document_metadata"]["document_id"] == "doc2"
    assert lines[1]["ocr_hypothesis"]["transcription_unit"] == ""
    assert lines[1]["ocr_postcorrection_output"]["transcription_unit"] == ""
    assert "scorée vide" in caplog.text and "doc3" in caplog.text


def test_mono_stage_uses_raw_as_system_output(tmp_path: Path) -> None:
    raw = tmp_path / "doc1.raw.txt"
    raw.write_text("sortie ocr", encoding="utf-8")
    outputs = {
        "ocr": {
            "doc1": {"ocr": {
                ArtifactType.RAW_TEXT: _artifact("doc1", ArtifactType.RAW_TEXT, raw)
            }}
        }
    }
    target = tmp_path / "out.jsonl"
    write_hipe_jsonl(target, _corpus(tmp_path), outputs)
    first = json.loads(target.read_text("utf-8").splitlines()[0])
    assert first["ocr_hypothesis"] == first["ocr_postcorrection_output"]


def test_two_pipelines_two_files(tmp_path: Path) -> None:
    raw = tmp_path / "doc1.raw.txt"
    raw.write_text("a", encoding="utf-8")
    artifact = {
        "doc1": {
            "ocr": {
                ArtifactType.RAW_TEXT: _artifact("doc1", ArtifactType.RAW_TEXT, raw)
            }
        }
    }
    outputs = {"ocr": artifact, "ocr+llm": artifact}
    target = tmp_path / "out.jsonl"
    written = write_hipe_jsonl(target, _corpus(tmp_path), outputs)
    assert [p.name for p in written] == ["out-ocr.jsonl", "out-ocr_llm.jsonl"]


def test_sink_writes_on_invocation(tmp_path: Path) -> None:
    raw = tmp_path / "doc1.raw.txt"
    raw.write_text("a", encoding="utf-8")
    corpus = _corpus(tmp_path)
    target = tmp_path / "out.jsonl"
    sink = hipe_jsonl_sink(target, corpus)
    sink(
        {
            "ocr": {
                "doc1": {
                    "ocr": {
                        ArtifactType.RAW_TEXT: _artifact(
                            "doc1", ArtifactType.RAW_TEXT, raw
                        )
                    }
                }
            }
        },
        manifest=None,  # le sink n'utilise pas le manifeste
    )
    assert target.exists()

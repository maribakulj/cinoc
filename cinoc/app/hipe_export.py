"""Export **JSONL HIPE-OCRepair** d'un run (couche 6 — SPEC_HIPE §7.4).

Le format d'entrée du scorer/leaderboard porte les **textes** (GT, OCR brut,
sortie corrigée — §4.8), pas les scores : l'export a donc besoin du corpus et
des ``pipeline_outputs``, que seule l'app détient. Il se branche sur le seam
``artifact_sink`` de l'orchestrateur (les URI des artefacts sont encore
lisibles), sans second chemin d'exécution.

Un fichier par pipeline (le format = une sortie système par enregistrement) :
``out.jsonl`` pour un run mono-pipeline, ``out-<pipeline>.jsonl`` sinon.
Sémantique des sorties manquantes (R-1.8, alignée scorer §4.6) : sortie absente
→ chaîne vide (erreur maximale) + warning — jamais d'exclusion silencieuse.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from cinoc.app.orchestrator import ArtifactSink, PipelineOutputs
from cinoc.domain.artifacts import ArtifactType, latest_by_type
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.representations import load_representation

logger = logging.getLogger(__name__)


def _slug(name: str) -> str:
    return re.sub(r"[^\w.-]+", "_", name)


def _text_of(
    outputs: PipelineOutputs, pipeline: str, document_id: str, kind: ArtifactType
) -> str | None:
    by_step = outputs.get(pipeline, {}).get(document_id, {})
    artifact = latest_by_type(by_step).get(kind)
    if artifact is None or artifact.uri is None:
        return None
    return str(load_representation(artifact.uri, kind))


def write_hipe_jsonl(
    path: Path, corpus: CorpusSpec, outputs: PipelineOutputs
) -> list[Path]:
    """Écrit les enregistrements HIPE (§4.8) ; renvoie les fichiers produits.

    GT = la vérité-terrain ``RAW_TEXT`` du document (sans GT texte → document
    sauté avec warning : le scorer ne peut rien en faire). ``ocr_hypothesis`` =
    l'étage brut ; ``ocr_postcorrection_output`` = l'étage corrigé, ou le brut
    pour un pipeline mono-étage (la sortie système est alors l'OCR lui-même).
    """
    written: list[Path] = []
    pipelines = list(outputs)
    for pipeline in pipelines:
        target = (
            path
            if len(pipelines) == 1
            else path.with_name(f"{path.stem}-{_slug(pipeline)}{path.suffix}")
        )
        lines: list[str] = []
        for document in corpus.documents:
            gt_ref = document.gt_for(ArtifactType.RAW_TEXT)
            if gt_ref is None:
                logger.warning(
                    "[hipe_export] %s : pas de GT texte — document sauté.",
                    document.id,
                )
                continue
            ground_truth = str(load_representation(gt_ref.uri, ArtifactType.RAW_TEXT))
            raw = _text_of(outputs, pipeline, document.id, ArtifactType.RAW_TEXT)
            corrected = _text_of(
                outputs, pipeline, document.id, ArtifactType.CORRECTED_TEXT
            )
            if raw is None:
                # R-1.8 : sortie manquante = chaîne vide (erreur maximale).
                logger.warning(
                    "[hipe_export] %s · %s : sortie absente — scorée vide (R-1.8).",
                    pipeline,
                    document.id,
                )
                raw = ""
            system = corrected if corrected is not None else raw
            lines.append(
                json.dumps(
                    {
                        "document_metadata": {
                            "document_id": document.id,
                            "primary_dataset_name": corpus.name,
                        },
                        "ground_truth": {"transcription_unit": ground_truth},
                        "ocr_hypothesis": {"transcription_unit": raw},
                        "ocr_postcorrection_output": {"transcription_unit": system},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(target)
        logger.info("[hipe_export] %d enregistrements → %s", len(lines), target)
    return written


def hipe_jsonl_sink(path: Path, corpus: CorpusSpec) -> ArtifactSink:
    """Sink d'orchestrateur : écrit le JSONL avant le nettoyage du workspace."""

    def sink(outputs: PipelineOutputs, manifest: RunManifest) -> None:
        write_hipe_jsonl(path, corpus, outputs)

    return sink


__all__ = ["hipe_jsonl_sink", "write_hipe_jsonl"]

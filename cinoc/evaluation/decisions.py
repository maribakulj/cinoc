"""Bilan des **décisions** d'un correcteur : ce qu'il a refusé, et pourquoi.

Un texte corrigé ne dit pas si une ligne est intacte parce qu'une garde l'a
protégée ou parce que rien n'a été proposé. Les deux rendent le même artefact,
et un correcteur **prudent** y ressemble trait pour trait à un correcteur
**inerte**.

Cette lecture n'existe donc pas pour flatter un correcteur mais pour rendre les
deux distinguables — c'est ce que le CER seul ne peut pas faire. La campagne du
2026-08-21 l'a montré chiffres en main : sur le même corpus, un modèle qui
gagnait *plus* de CER qu'un autre **abîmait quatre fois plus de lignes**.

Lecture seule : aucun recalcul, aucun jugement. La **classe** de chaque ligne
(corrigée, à revoir, abstention, refus technique, repli) est **déclarée** par
l'adaptateur dans le sidecar (``line_class`` et son ``class_code``) ; cette
couche la lit et la compte, elle ne la reconstruit jamais d'après les textes
(D6, § 2.1 f). Le rapport lit ce que l'adaptateur a écrit.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import cast, get_args

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.evaluation.analysis import (
    Analysis,
    DecisionReasonCount,
    DecisionReviewReason,
    DecisionSample,
    DecisionsPayload,
    LineClass,
    PipelineDecisions,
)

logger = logging.getLogger(__name__)

#: Lignes montrées en exemple par pipeline (cf. ``analysis._MAX_DECISION_SAMPLES``).
_MAX_SAMPLES = 40
#: Extrait d'une ligne montrée (cf. ``analysis._MAX_LINE_CHARS``).
_MAX_CHARS = 300

_Outputs = Mapping[str, Mapping[str, Mapping[ArtifactType, Artifact]]]


def _lines_of(artifact: Artifact) -> list[dict[str, object]]:
    if artifact.uri is None:
        return []
    try:
        data = json.loads(Path(artifact.uri).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # Un sidecar illisible n'est pas une raison d'abattre un run entier :
        # il prive d'une lecture, il ne fausse aucun score.
        return []
    lines = data.get("lines") if isinstance(data, dict) else None
    return [ligne for ligne in lines or [] if isinstance(ligne, dict)]


def _texte(valeur: object) -> str:
    return str(valeur or "")[:_MAX_CHARS]


def _review_reasons(ligne: dict[str, object]) -> tuple[DecisionReviewReason, ...]:
    reasons = ligne.get("review_reasons")
    if not isinstance(reasons, list):
        return ()
    return tuple(
        DecisionReviewReason(
            code=reason["code"][:128],
            detail=_texte(reason["detail"]) if reason.get("detail") else None,
        )
        for reason in reasons
        if isinstance(reason, dict)
        and isinstance(reason.get("code"), str)
        and reason["code"]
    )


_CLASSES: frozenset[str] = frozenset(get_args(LineClass))


def _pipeline_decisions(
    pipeline: str, by_document: Mapping[str, Mapping[ArtifactType, Artifact]]
) -> PipelineDecisions | None:
    counts: Counter[str] = Counter()
    refused: Counter[str] = Counter()
    fallback: Counter[str] = Counter()
    reviews: Counter[str] = Counter()
    echantillons: list[DecisionSample] = []
    vu = False

    for document_id in sorted(by_document):
        artifact = by_document[document_id].get(ArtifactType.DECISIONS)
        if artifact is None:
            continue
        vu = True
        for ligne in _lines_of(artifact):
            classe = ligne.get("line_class")
            if classe not in _CLASSES:
                # Une ligne dont l'adaptateur ne déclare pas la classe n'est pas
                # rangée au hasard : elle n'est pas comptée.
                logger.warning(
                    "[decisions] dégradé : ligne %s/%s sans classe déclarée",
                    ligne.get("page_id"),
                    ligne.get("line_id"),
                )
                continue
            line_class = cast(LineClass, classe)
            code = ligne.get("class_code")
            counts[line_class] += 1
            if line_class == "refused":
                refused[str(code or "sans_motif")] += 1
            elif line_class == "fallback":
                fallback[str(code or "sans_motif")] += 1
            review_reasons = _review_reasons(ligne)
            if line_class == "review_required":
                reviews.update({r.code for r in review_reasons} or {"sans_motif"})
            if line_class != "abstained" and len(echantillons) < _MAX_SAMPLES:
                echantillons.append(
                    DecisionSample(
                        document_id=str(ligne.get("document_id") or document_id),
                        page_id=str(ligne.get("page_id") or "?"),
                        line_id=str(ligne.get("line_id") or "?"),
                        line_class=line_class,
                        source_text=_texte(ligne.get("source_text")),
                        final_text=_texte(ligne.get("final_text")),
                        reason_code=str(ligne["reason_code"])
                        if ligne.get("reason_code")
                        else None,
                        reason_detail=(
                            _texte(ligne.get("reason_detail"))
                            if ligne.get("reason_detail")
                            else None
                        ),
                        review_reasons=review_reasons,
                    )
                )
    if not vu:
        return None
    return PipelineDecisions(
        pipeline=pipeline,
        n_lines=sum(counts.values()),
        corrected=counts["corrected"],
        review_required=counts["review_required"],
        abstained=counts["abstained"],
        refused=tuple(
            DecisionReasonCount(code=code, n=n) for code, n in sorted(refused.items())
        ),
        fallback=tuple(
            DecisionReasonCount(code=code, n=n) for code, n in sorted(fallback.items())
        ),
        review_reasons=tuple(
            DecisionReasonCount(code=code, n=n) for code, n in sorted(reviews.items())
        ),
        samples=tuple(echantillons),
    )


def decisions_analysis(view: str, outputs: _Outputs) -> Analysis | None:
    """Payload ``decisions`` de la vue, ou ``None`` si aucun correcteur n'en
    produit. **Absence ≠ section vide** : sans décisions, pas de section."""
    rows = [
        row
        for pipeline in sorted(outputs)
        if (row := _pipeline_decisions(pipeline, outputs[pipeline])) is not None
    ]
    if not rows:
        return None
    return Analysis(
        scope="corpus",
        view=view,
        payload=DecisionsPayload(pipelines=tuple(rows)),
    )


__all__ = ["decisions_analysis"]

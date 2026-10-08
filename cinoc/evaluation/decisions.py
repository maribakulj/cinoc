"""Bilan des **décisions** d'un correcteur : ce qu'il a refusé, et pourquoi.

Un texte corrigé ne dit pas si une ligne est intacte parce qu'une garde l'a
protégée ou parce que rien n'a été proposé. Les deux rendent le même artefact,
et un correcteur **prudent** y ressemble trait pour trait à un correcteur
**inerte**.

Cette lecture n'existe donc pas pour flatter un correcteur mais pour rendre les
deux distinguables — c'est ce que le CER seul ne peut pas faire. La campagne du
2026-08-21 l'a montré chiffres en main : sur le même corpus, un modèle qui
gagnait *plus* de CER qu'un autre **abîmait quatre fois plus de lignes**.

Lecture seule : aucun recalcul, aucun verdict. Le rapport lit ce que
l'adaptateur a écrit.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from pathlib import Path

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.evaluation.analysis import (
    Analysis,
    DecisionReasonCount,
    DecisionReviewReason,
    DecisionSample,
    DecisionsPayload,
    PipelineDecisions,
)

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


def _pipeline_decisions(
    pipeline: str, by_document: Mapping[str, Mapping[ArtifactType, Artifact]]
) -> PipelineDecisions | None:
    total = changed = refused = untouched = review_required = 0
    motifs: Counter[str] = Counter()
    reviews: Counter[str] = Counter()
    echantillons: list[DecisionSample] = []
    vu = False

    for document_id in sorted(by_document):
        artifact = by_document[document_id].get(ArtifactType.DECISIONS)
        if artifact is None:
            continue
        vu = True
        for ligne in _lines_of(artifact):
            total += 1
            source = str(ligne.get("source_text") or "")
            final = str(ligne.get("final_text") or "")
            propose = ligne.get("proposed_text")
            code = ligne.get("reason_code")
            review = ligne.get("status") == "review_required"
            review_reasons = _review_reasons(ligne)
            if review:
                review_required += 1
                reviews.update({r.code for r in review_reasons} or {"sans_motif"})
            if final != source:
                changed += 1
            elif code or (propose is not None and str(propose) != source):
                # Une proposition existait et la ligne n'a pas bougé : c'est un
                # refus, pas une absence de proposition.
                refused += 1
                motifs[str(code or "sans_motif")] += 1
            else:
                untouched += 1
            if final != source or code or review:
                if len(echantillons) < _MAX_SAMPLES:
                    echantillons.append(
                        DecisionSample(
                            document_id=str(ligne.get("document_id") or document_id),
                            page_id=str(ligne.get("page_id") or "?"),
                            line_id=str(ligne.get("line_id") or "?"),
                            status=str(ligne.get("status") or "?"),
                            source_text=_texte(source),
                            final_text=_texte(final),
                            reason_code=str(code) if code else None,
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
        n_lines=total,
        changed=changed,
        refused=refused,
        untouched=untouched,
        review_required=review_required,
        reasons=tuple(
            DecisionReasonCount(code=code, n=n) for code, n in sorted(motifs.items())
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

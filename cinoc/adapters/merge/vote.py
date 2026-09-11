"""``TextVoteMerger`` — plusieurs lectures d'une page, une seule sortie.

Le banc savait comparer des moteurs ; il ne savait pas en **combiner**. Le pool
d'artefacts étant indexé par type, deux OCR dans un même pipeline s'écrasaient
l'un l'autre, et aucun vote n'était exprimable. C'est le manque qu'OCR-D comble
avec ``cor-asv-ann-align``, qui accepte N groupes de fichiers pour fusionner
plusieurs sorties.

Ce que la fusion peut, et ce qu'elle ne peut pas : elle rattrape les erreurs
qu'**un** moteur commet là où les autres ont juste ; elle est impuissante quand
tous se trompent pareil — ce qui arrive sur une écriture qu'aucun n'a apprise.
Savoir dans lequel des deux cas on se trouve est précisément le travail du banc,
et c'est pourquoi la fusion se **mesure** plutôt qu'elle ne se suppose.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.adapters.merge._vote import vote_tokens
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.formats.text.plain import read_plaintext
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"


class TextVoteMerger:
    """Vote majoritaire par jeton entre N transcriptions d'un même document.

    ``kind`` choisit le type fusionné : ``raw_text`` pour des sorties d'OCR,
    ``corrected_text`` pour des sorties de correcteurs. Le type d'entrée et celui
    de sortie sont **le même** — fusionner ne change pas la nature de ce qu'on
    tient, seulement le nombre d'avis qui l'ont produit.
    """

    def __init__(self, *, label: str, kind: str = "raw_text") -> None:
        try:
            self._kind = ArtifactType(kind)
        except ValueError as exc:
            raise AdapterStepError(
                f"vote : type {kind!r} inconnu (attendu un ArtifactType)."
            ) from exc
        if self._kind not in {ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}:
            raise AdapterStepError(
                f"vote : {kind!r} n'est pas du texte — le vote par jeton ne "
                "s'applique qu'à des transcriptions."
            )
        self._label = label

    @property
    def name(self) -> str:
        return f"vote:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({self._kind})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({self._kind})

    def execute_merge(
        self,
        sources: Mapping[str, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat MergingModule
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        if len(sources) < 2:
            raise AdapterStepError(
                f"{self.name} : {len(sources)} source(s) — fusionner un seul avis "
                "ne fusionne rien."
            )
        from pathlib import Path  # noqa: PLC0415

        lectures: dict[str, str] = {}
        for nom, artefact in sources.items():
            if artefact.uri is None:
                raise AdapterStepError(
                    f"{self.name} : la source {nom!r} n'a pas d'URI."
                )
            lectures[nom] = read_plaintext(Path(artefact.uri).read_bytes())

        fusionne = vote_tokens(lectures)
        octets = fusionne.encode("utf-8")
        if context.workspace_uri is None:
            raise AdapterStepError(
                f"{self.name} : workspace requis (RunContext.workspace_uri)."
            )
        cible = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "txt"
        )
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(octets)
        return StepOutput(
            artifacts={
                self._kind: Artifact(
                    id=f"{context.document_id}:{self._label}:{self._kind.value}",
                    document_id=context.document_id,
                    type=self._kind,
                    uri=str(cible),
                    content_hash=compute_content_hash(octets),
                    produced_by_step=self._label,
                )
            }
        )


__all__ = ["TextVoteMerger"]

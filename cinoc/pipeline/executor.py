"""``PipelineExecutor`` — exécute une ``PipelineSpec`` sur un document.

Mono-document, séquentiel : résout les entrées de chaque étape (DAG via
``inputs_from``, sinon dernière version par type), appelle ``Module.execute``,
puis **estampille la provenance** (``code_version`` + ``parameters_hash``) et le
``produced_by_step`` sur chaque artefact produit — le module n'a pas à connaître
ces concerns. L'annulation coopérative est vérifiée avant chaque étape.

Une étape ``fanout=True`` (reconnaissance par région) exécute son module **une
fois par région** du ``LAYOUT`` d'entrée et réassemble un ``LAYOUT`` rempli
(délégué à ``execute_region_fanout``) ; l'estampillage de provenance reste
identique. L'orchestration multi-documents (threads, timeout, backpressure) vit
dans l'orchestrateur (couche 6) ; l'exécuteur reste **mono-document** — il est
sans état mutable partagé, donc sûr à appeler depuis plusieurs threads.
"""

from __future__ import annotations

import json
import time
from collections.abc import Mapping

from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.provenance import ProvenanceRecord
from cinoc.domain.usage import ResourceUsage
from cinoc.pipeline.fanout import RegionCropper, execute_region_fanout
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import DocumentExecution, RunContext, StepOutput


class PipelineStepError(CinocError):
    """Une étape n'a pas pu s'exécuter (module, entrée ou sortie manquante)."""


def _parameters_hash(params: Mapping[str, object]) -> str:
    payload = json.dumps(params, sort_keys=True, ensure_ascii=False)
    return compute_content_hash(payload.encode("utf-8"))


class PipelineExecutor:
    """Exécute les pipelines déclaratives sur des artefacts initiaux."""

    def __init__(self, code_version: str) -> None:
        if not code_version:
            raise CinocError("PipelineExecutor : code_version vide.")
        self._code_version = code_version

    def execute_document(
        self,
        spec: PipelineSpec,
        modules: Mapping[str, Module],
        initial_inputs: Mapping[ArtifactType, Artifact],
        *,
        document_id: str,
        deadline: Deadline | None = None,
        control: RunControl | None = None,
        workspace_uri: str | None = None,
        cropper: RegionCropper | None = None,
    ) -> DocumentExecution:
        """Exécute ``spec`` ; renvoie artefacts (dernier par type) + ``usage``.

        ``cropper`` (couche 5, injecté par l'app) active le découpage réel des
        blocs dans les étapes ``fanout`` (pipeline hybride seg→OCR par bloc).
        La **durée** de chaque étape est mesurée ici (horloge monotone, source
        unique) puis fusionnée avec les jetons remontés par les modules.
        """
        ctrl = control if control is not None else RunControl()
        dl = deadline if deadline is not None else Deadline.infinite()
        pool: dict[ArtifactType, Artifact] = dict(initial_inputs)
        by_step: dict[str, dict[ArtifactType, Artifact]] = {}
        usage = ResourceUsage()

        for step in spec.steps:
            ctrl.raise_if_cancelled()
            module = modules.get(step.adapter_name)
            if module is None:
                raise PipelineStepError(
                    f"étape {step.id!r} : module {step.adapter_name!r} "
                    "absent du registre."
                )
            inputs = (
                {}
                if step.merge_from
                else self._resolve_inputs(step, pool, by_step)
            )
            context = RunContext(
                document_id=document_id,
                code_version=self._code_version,
                pipeline_name=spec.name,
                deadline=dl,
                workspace_uri=workspace_uri,
            )
            started = time.monotonic()
            if step.merge_from:
                output = self._run_merge(step, module, by_step, context, ctrl)
            elif step.fanout:
                output = self._run_fanout(step, module, inputs, context, ctrl, cropper)
            else:
                output = module.execute(inputs, dict(step.params), context, ctrl)
            step_usage = ResourceUsage(
                duration_seconds=time.monotonic() - started
            ).merged_with(output.usage)
            usage = usage.merged_with(step_usage)
            stamped = self._stamp(output.artifacts, step)
            self._check_outputs(step, stamped)
            by_step[step.id] = stamped
            pool.update(stamped)
        return DocumentExecution(artifacts=pool, usage=usage)

    def _run_merge(
        self,
        step: PipelineStep,
        module: object,
        by_step: Mapping[str, dict[ArtifactType, Artifact]],
        context: RunContext,
        ctrl: RunControl,
    ) -> StepOutput:
        """Réunit les sorties de plusieurs étapes en une seule.

        Le pool est indexé par type : deux sorties du même type s'y écrasent, et
        ``inputs_from`` ne nomme qu'une source par type. Les avis sont donc pris
        dans ``by_step``, qui les garde **tous** — la donnée existait déjà, seule
        la façon de la demander manquait.
        """
        if not hasattr(module, "execute_merge"):
            raise PipelineStepError(
                f"étape {step.id!r} : {step.adapter_name!r} n'est pas une brique "
                "de fusion (pas d'``execute_merge``). Une étape déclarant "
                "``merge_from`` exige un module qui sache réunir plusieurs avis."
            )
        (attendu,) = tuple(step.input_types)
        sources: dict[str, Artifact] = {}
        for source in step.merge_from:
            produits = by_step.get(source)
            if produits is None:
                raise PipelineStepError(
                    f"étape {step.id!r} : source {source!r} inconnue — une "
                    "fusion ne peut nommer qu'une étape déjà exécutée."
                )
            artefact = produits.get(attendu)
            if artefact is None:
                raise PipelineStepError(
                    f"étape {step.id!r} : la source {source!r} ne produit pas "
                    f"de {attendu.value!r}."
                )
            sources[source] = artefact
        return module.execute_merge(  # type: ignore[attr-defined,no-any-return]
            sources, dict(step.params), context, ctrl
        )

    def _run_fanout(
        self,
        step: PipelineStep,
        module: Module,
        inputs: Mapping[ArtifactType, Artifact],
        context: RunContext,
        control: RunControl,
        cropper: RegionCropper | None,
    ) -> StepOutput:
        layout = inputs.get(ArtifactType.LAYOUT)
        image = inputs.get(ArtifactType.IMAGE)
        if layout is None or image is None:
            raise PipelineStepError(
                f"étape {step.id!r} (fanout) : entrées LAYOUT et IMAGE requises."
            )
        return execute_region_fanout(
            layout_artifact=layout,
            page_image=image,
            recognizer=module,
            context=context,
            control=control,
            params=dict(step.params),
            # ``crop`` déclaré par l'étape : OCR réel par bloc → découpe ; sinon
            # (``precomputed``) image page entière + ``region_id``, aucun pixel lu.
            cropper=cropper if step.crop else None,
        )

    def _resolve_inputs(
        self,
        step: PipelineStep,
        pool: Mapping[ArtifactType, Artifact],
        by_step: Mapping[str, dict[ArtifactType, Artifact]],
    ) -> dict[ArtifactType, Artifact]:
        resolved: dict[ArtifactType, Artifact] = {}
        for t in step.input_types:
            src = step.inputs_from.get(t)
            if src is None or src == INITIAL_STEP_ID:
                art = pool.get(t)
            else:
                art = by_step.get(src, {}).get(t)
            if art is None:
                raise PipelineStepError(
                    f"étape {step.id!r} : entrée {t.value!r} introuvable."
                )
            resolved[t] = art
        return resolved

    def _stamp(
        self, outputs: Mapping[ArtifactType, Artifact], step: PipelineStep
    ) -> dict[ArtifactType, Artifact]:
        # Déterminisme : l'identité d'un artefact = content_hash + (code_version,
        # parameters_hash). Le timestamp wall-clock de ProvenanceRecord est de la
        # métadonnée, EXCLUE de l'identité (cf. ProvenanceRecord.is_compatible_with)
        # et jamais rendue dans RunResult/HTML. Un cache futur comparerait donc via
        # is_compatible_with, pas via model_dump_json. (Journal D-012.)
        provenance = ProvenanceRecord(
            code_version=self._code_version,
            parameters_hash=_parameters_hash(dict(step.params)),
        )
        return {
            t: art.model_copy(
                update={"produced_by_step": step.id, "provenance": provenance}
            )
            for t, art in outputs.items()
        }

    def _check_outputs(
        self, step: PipelineStep, outputs: Mapping[ArtifactType, Artifact]
    ) -> None:
        for t in step.output_types:
            if t not in outputs:
                raise PipelineStepError(
                    f"étape {step.id!r} : sortie déclarée {t.value!r} "
                    "non produite."
                )


__all__ = ["PipelineExecutor", "PipelineStepError"]

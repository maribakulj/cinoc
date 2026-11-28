"""``PipelineExecutor`` — exécute une ``PipelineSpec`` sur un document.

Mono-document, séquentiel : résout les entrées de chaque étape (DAG via
``inputs_from``, sinon dernière version par type), appelle ``Module.execute``,
puis **estampille la provenance** (``code_version``, ``parameters_hash`` = empreinte
de l'étape, modèles servis) et le ``produced_by_step`` sur chaque artefact
produit — le module n'a pas à connaître ces concerns. L'annulation coopérative
est vérifiée avant chaque étape.

Une étape ``fanout=True`` (reconnaissance par région) exécute son module **une
fois par région** du ``LAYOUT`` d'entrée et réassemble un ``LAYOUT`` rempli
(délégué à ``execute_region_fanout``) ; l'estampillage de provenance reste
identique. L'orchestration multi-documents (threads, timeout, backpressure) vit
dans l'orchestrateur (couche 6) ; l'exécuteur reste **mono-document** — il est
sans état mutable partagé, donc sûr à appeler depuis plusieurs threads.
"""

from __future__ import annotations

import time
from collections.abc import Mapping

from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    latest_by_type,
)
from cinoc.domain.deadline import Deadline
from cinoc.domain.errors import AdapterStepError, CinocError, DeadlineExceeded
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.provenance import ProvenanceRecord
from cinoc.domain.usage import FailureReason, LineOutcomes, ResourceUsage, StepIssue
from cinoc.pipeline.fanout import RegionCropper, execute_region_fanout
from cinoc.pipeline.fingerprint import ModuleIdentity, step_fingerprint
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import DocumentExecution, RunContext, StepOutput


class PipelineStepError(CinocError):
    """Une étape n'a pas pu s'exécuter (module, entrée ou sortie manquante)."""


#: Erreurs qui font échouer **une** unité sans arrêter le run. L'annulation
#: (``RunCancelledError``) n'en est pas : elle arrête tout.
UNIT_FAILURES: tuple[type[CinocError], ...] = (AdapterStepError, PipelineStepError)


def failure_reason(exc: CinocError) -> FailureReason:
    """Motif codé d'un échec d'unité, lu sur la **classe** de l'erreur.

    ``DeadlineExceeded`` avant ``AdapterStepError`` (elle en hérite) : une unité
    arrêtée à expiration — du run ou du délai propre de l'étape — n'est pas un
    moteur en panne (pilote D-281, D3). ``PipelineStepError`` =
    l'exécuteur n'a pas pu câbler l'étape (entrée introuvable, sortie déclarée
    non produite, brique inadaptée) : le pipeline ne s'applique pas tel que
    déclaré à ce document.
    """
    if isinstance(exc, DeadlineExceeded):
        return "cancelled"
    if isinstance(exc, PipelineStepError):
        return "unsupported"
    return "engine"


class PipelineExecutor:
    """Exécute les pipelines déclaratives sur des artefacts initiaux.

    ``identities`` : l'identité de chaque module (``adapter_name`` →
    :class:`ModuleIdentity`), calculée **une fois** par l'appelant — la même qui
    sert la clé de reprise et le manifeste. Un module absent de la table (appel
    direct, tests) n'est identifié que par sa ``version`` : l'exécuteur ne voit
    pas les kwargs saisis.
    """

    def __init__(
        self,
        code_version: str,
        identities: Mapping[str, ModuleIdentity] | None = None,
    ) -> None:
        if not code_version:
            raise CinocError("PipelineExecutor : code_version vide.")
        self._code_version = code_version
        self._identities = dict(identities or {})

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
        """Exécute ``spec`` ; renvoie les sorties et la consommation **par étape**.

        ``cropper`` (couche 5, injecté par l'app) active le découpage réel des
        blocs dans les étapes ``fanout`` (pipeline hybride seg→OCR par bloc).
        La **durée** de chaque étape est mesurée ici (horloge monotone, source
        unique) puis fusionnée avec les jetons remontés par les modules.

        ``by_step`` est la seule structure tenue : les entrées initiales y
        figurent sous ``INITIAL_STEP_ID``, et le pool (« dernière version par
        type ») s'en déduit à la demande (``latest_by_type``).
        """
        ctrl = control if control is not None else RunControl()
        dl = deadline if deadline is not None else Deadline.infinite()
        by_step: dict[str, dict[ArtifactType, Artifact]] = {
            INITIAL_STEP_ID: dict(initial_inputs)
        }
        step_usage: dict[str, ResourceUsage] = {}
        # Une coupure par étape qui en déclare une : l'unité garde ses sorties
        # (elles seront notées) et son issue dit laquelle est coupée.
        truncations: list[str] = []
        # Les étapes qui déclarent leur sortie incomplète (``StepOutput.partial``)
        # et les issues de lignes qu'elles comptent : déclarées par l'étape,
        # portées ici, jamais reconstruites en aval.
        partials: list[str] = []
        step_issues: dict[str, StepIssue] = {}
        line_outcomes: LineOutcomes | None = None

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
                else self._resolve_inputs(step, by_step)
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
            step_usage[step.id] = ResourceUsage(
                duration_seconds=time.monotonic() - started
            ).merged_with(output.usage)
            stamped = self._stamp(output, step, module)
            self._check_outputs(step, stamped)
            by_step[step.id] = stamped
            if output.truncation is not None:
                truncations.append(f"étape {step.id!r} : {output.truncation}")
                step_issues[step.id] = "truncated"
            if output.partial is not None:
                partials.append(f"étape {step.id!r} : {output.partial}")
                step_issues[step.id] = "partial"
            if output.line_outcomes is not None:
                line_outcomes = output.line_outcomes.merged_with(line_outcomes)
        return DocumentExecution(
            by_step=by_step,
            step_usage=step_usage,
            outcome=(
                "partial" if partials else "truncated" if truncations else "ok"
            ),
            message="; ".join([*partials, *truncations]) or None,
            line_outcomes=line_outcomes,
            step_issues=step_issues,
        )

    def _run_merge(
        self,
        step: PipelineStep,
        module: object,
        by_step: Mapping[str, dict[ArtifactType, Artifact]],
        context: RunContext,
        ctrl: RunControl,
    ) -> StepOutput:
        """Réunit les sorties de plusieurs étapes en une seule.

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
        by_step: Mapping[str, dict[ArtifactType, Artifact]],
    ) -> dict[ArtifactType, Artifact]:
        # ``INITIAL_STEP_ID`` lit le pool (dernière version du type), comme
        # avant : une recette qui prétraite l'image puis nomme ``__initial__``
        # pour l'OCR reçoit l'image prétraitée. Le changer changerait des sorties.
        pool = latest_by_type(by_step)
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

    def identity_of(self, step: PipelineStep, module: Module) -> ModuleIdentity:
        """L'identité du module de ``step`` (table de l'appelant, sinon sa version)."""
        identity = self._identities.get(step.adapter_name)
        return identity if identity is not None else ModuleIdentity(module.version)

    def _stamp(
        self, output: StepOutput, step: PipelineStep, module: Module
    ) -> dict[ArtifactType, Artifact]:
        # Déterminisme : l'identité d'un artefact = content_hash + (code_version,
        # parameters_hash). Le timestamp wall-clock de ProvenanceRecord est de la
        # métadonnée, EXCLUE de l'identité (cf. ProvenanceRecord.is_compatible_with)
        # et jamais rendue dans RunResult/HTML. (Journal D-012.) ``parameters_hash``
        # est l'empreinte de l'étape — celle dont dérive la clé de reprise.
        provenance = ProvenanceRecord(
            code_version=self._code_version,
            parameters_hash=step_fingerprint(step, self.identity_of(step, module)),
            served_models=tuple(sorted(set(output.served_models))),
        )
        return {
            t: art.model_copy(
                update={"produced_by_step": step.id, "provenance": provenance}
            )
            for t, art in output.artifacts.items()
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


__all__ = ["UNIT_FAILURES", "PipelineExecutor", "PipelineStepError", "failure_reason"]

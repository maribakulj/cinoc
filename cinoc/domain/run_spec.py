"""``RunSpec`` — description déclarative complète d'un run.

Compose les types déclaratifs du domaine (corpus + pipelines + vues) en **une**
entrée auto-suffisante : un run est entièrement décrit par son ``RunSpec`` (+ le
``code_version``). **Pas de ``StepSpec`` distinct** — ``PipelineStep`` (déjà en
domain) est l'étape déclarative ; en introduire un second serait une 2ᵉ
représentation de pipeline (la dette qu'on abandonne, cf. journal D-010).

``adapter_kwargs`` (``adapter_name → kwargs de construction``) alimente la
factory de modules **et** le ``RunManifest`` (reproductibilité).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep


class RunSpec(BaseModel):
    """Ce qu'il faut exécuter : corpus, pipelines candidats, vues d'évaluation."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    corpus: CorpusSpec
    pipelines: tuple[PipelineSpec, ...] = Field(min_length=1)
    evaluation: EvaluationSpec
    adapter_kwargs: dict[str, dict[str, str | int | float | bool]] = Field(
        default_factory=dict
    )
    run_id: str | None = Field(default=None, max_length=256)
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_steps_declare_outputs(self) -> RunSpec:
        """Une étape **déclare** ses types de sortie.

        Une étape sans ``output_types`` n'est vue d'aucune vue : son pipeline
        sort de toutes les évaluations sans qu'aucune erreur ne le dise
        (« jamais un défaut muet », F8). Refusée au chargement, par son nom.
        """
        for pipeline in self.pipelines:
            for step in pipeline.steps:
                if not step.output_types:
                    raise CinocError(
                        f"pipeline {pipeline.name!r} : l'étape {step.id!r} ne "
                        "déclare aucun type de sortie ('output_types' vide) — "
                        "sans eux, aucune vue ne peut la voir."
                    )
        return self

    @model_validator(mode="after")
    def _check_view_targets(self) -> RunSpec:
        """Chaque vue désigne, dans chaque pipeline, **une** sortie à noter.

        Une cible d'étape (``target_step``) inconnue d'un pipeline est refusée
        ici, au chargement, plutôt que de rendre une vue vide après un run payé.
        Une étape visée — nommée, ou à défaut la plus aval qui produit un type
        candidat — qui **déclare** plusieurs types candidats de la vue est
        ambiguë : aucune précédence implicite ne tranche plus entre eux.
        """
        for view in self.evaluation.views:
            for pipeline in self.pipelines:
                step = _scored_step(view, pipeline)
                if step is None:
                    continue
                candidats = sorted(
                    t.value for t in step.output_types if t in view.candidate_types
                )
                if len(candidats) > 1:
                    raise CinocError(
                        f"vue {view.name!r} : l'étape {step.id!r} du pipeline "
                        f"{pipeline.name!r} produit plusieurs types candidats "
                        f"({', '.join(candidats)}) — restreignez "
                        "'candidate_types' à celui qui doit être noté."
                    )
        return self


def _scored_step(view: EvaluationView, pipeline: PipelineSpec) -> PipelineStep | None:
    """L'étape dont ``view`` note la sortie dans ``pipeline`` (déclarations seules)."""
    if view.target_step is not None:
        step = pipeline.step_by_id(view.target_step)
        if step is None:
            raise CinocError(
                f"vue {view.name!r} : cible d'étape {view.target_step!r} inconnue "
                f"du pipeline {pipeline.name!r} (étapes : "
                f"{', '.join(s.id for s in pipeline.steps) or 'aucune'})."
            )
        return step
    for step in reversed(pipeline.steps):
        if any(t in view.candidate_types for t in step.output_types):
            return step
    return None


__all__ = ["RunSpec"]

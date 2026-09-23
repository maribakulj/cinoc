"""Cohérence d'une spec **avant** de l'exécuter (couche 6).

Une spec peut être *valide* — types compatibles, briques connues — et pourtant
décrire un montage qui ne fera pas ce qu'on croit. Ce module vérifie ce qui ne
se lit que sur **plusieurs étapes à la fois**, et qu'aucune brique isolée ne
peut donc contrôler.

Le cas qui l'a motivé, mesuré sur la campagne BNL : une table
``psm_by_class="plain text:6,title:6"`` posée sur un reconnaisseur par région,
alors que le segmenteur en amont posait d'autres étiquettes. **Rien ne
matchait**, chaque région retombait sur le réglage par défaut, et le run
s'exécutait sans un mot — le défaut n'apparaissait que dans un CER légèrement
dégradé, indiscernable d'un moteur médiocre.

Placé en ``app`` et non dans l'exécuteur : c'est une règle de **planification**,
elle doit valoir pour la CLI (``cinoc run --check``) comme pour le lanceur web,
sans que la couche 4 ait à connaître le paramètre d'un adapter particulier.
"""

from __future__ import annotations

from collections.abc import Mapping

from cinoc.domain.errors import CinocError
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.protocols import ParamValue


class SpecCoherenceError(CinocError):
    """La spec décrit un montage qui ne ferait pas ce qu'il annonce."""


def _source_layout(pipeline: PipelineSpec, step: PipelineStep) -> PipelineStep | None:
    """L'étape qui fournit le ``LAYOUT`` d'une étape par région."""
    from cinoc.domain.artifacts import ArtifactType  # noqa: PLC0415

    origine = (step.inputs_from or {}).get(ArtifactType.LAYOUT)
    if origine is None:
        return None
    return pipeline.step_by_id(str(origine))


def check_region_class_settings(spec: RunSpec) -> None:
    """Une table « classe → réglage » doit parler la langue de son segmenteur.

    Refuse une intersection **vide** entre les classes réglées et celles que le
    segmenteur amont sait poser. Une intersection partielle passe : régler deux
    classes sur dix est un choix légitime ; n'en régler aucune ne l'est pas,
    c'est une table écrite pour un autre modèle.
    """
    from cinoc.adapters.ocr.tesseract import parse_psm_by_class  # noqa: PLC0415

    for pipeline in spec.pipelines:
        for step in pipeline.steps:
            if not step.fanout:
                continue
            table = str(
                (spec.adapter_kwargs.get(step.adapter_name) or {}).get(
                    "psm_by_class", ""
                )
            )
            if not table:
                continue
            reglees = set(parse_psm_by_class(table))
            source = _source_layout(pipeline, step)
            if source is None:
                continue
            connues = declared_labels(
                source.adapter_name,
                spec.adapter_kwargs.get(source.adapter_name) or {},
            )
            if connues is None:
                continue
            if not connues:
                raise SpecCoherenceError(
                    f"étape {step.id!r} : une table 'psm_by_class' est posée, "
                    f"mais le segmenteur {source.adapter_name!r} ne pose aucune "
                    "classe sémantique — il n'y a rien à régler par classe."
                )
            if not reglees & connues:
                raise SpecCoherenceError(
                    f"étape {step.id!r} : 'psm_by_class' règle "
                    f"{sorted(reglees)}, mais le segmenteur "
                    f"{source.adapter_name!r} pose {sorted(connues)}. Aucune "
                    "classe en commun : la table serait ignorée en silence et "
                    "chaque région retomberait sur le réglage par défaut."
                )


def declared_labels(
    kind: str, kwargs: Mapping[str, ParamValue]
) -> frozenset[str] | None:
    """Vocabulaire d'étiquettes d'une brique, ``None`` si elle n'en déclare pas.

    Lu sur la **classe**, pas sur l'instance : un vocabulaire est une propriété
    du modèle, pas de son réglage, et le lire sans construire évite de charger
    des poids pour valider une spec.
    """
    from cinoc.app.modules.registry import (  # noqa: PLC0415
        ModuleRegistry,
        register_default_modules,
    )

    registre = ModuleRegistry()
    register_default_modules(registre)
    try:
        module = registre.build(kind, kwargs)
    except CinocError:
        return None
    labels = getattr(type(module), "LABELS", None)
    return frozenset(labels) if labels is not None else None


def check(spec: RunSpec) -> None:
    """Tous les contrôles de cohérence. Lève au **premier** manquement."""
    check_region_class_settings(spec)


__all__ = [
    "SpecCoherenceError",
    "check",
    "check_region_class_settings",
    "declared_labels",
]

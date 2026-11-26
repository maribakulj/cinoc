"""Identité des modules d'un run et son ``RunManifest`` (couche 6).

Une seule lecture de « ce qui produit les sorties », faite **une fois** au début
du run et servie à trois consommateurs qui doivent dire la même chose :

- l'**exécuteur**, qui en tire l'empreinte de chaque étape (``parameters_hash``
  de la provenance) ;
- le **cache de reprise**, dont la clé d'unité dérive de ces empreintes ;
- le **manifeste**, qui écrit les mêmes réglages, versions et binaires.

Avant, trois lectures divergeaient : la clé hachait la saisie et la version du
paquet, la provenance les seuls ``params`` de l'étape, le manifeste la saisie
complétée des réglages d'inférence et des binaires sondés **à la fin** du run.

Les valeurs **secrètes** n'entrent ni dans l'identité ni au manifeste : le
manifeste voyage (JSON, rapport), et l'empreinte nomme un dossier d'archive.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping
from datetime import datetime

from cinoc.app.modules.params import operational_names, secret_names
from cinoc.app.versioning import dependencies_lock
from cinoc.domain.artifacts import StepArtifacts
from cinoc.domain.run import RunManifest
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.fingerprint import ModuleIdentity
from cinoc.pipeline.params import declared_params
from cinoc.pipeline.protocols import Module

#: Réglages qui portent une **valeur secrète** (jeton d'un endpoint privé…). Le
#: module la reçoit pour s'authentifier ; le manifeste, lui, voyage — dans le
#: JSON ``RunResult``, dans la section « composition » du rapport, chez qui on
#: partage le rapport. Il garde donc le **fait** qu'un secret a été fourni,
#: jamais sa valeur. Un seul point de passage : tout ce qui sort d'un run sort
#: du manifeste.
#:
#: Une brique **déclare** ses secrets (``Param.secret``, ``pipeline.params``) ;
#: cette liste de noms reste le filet d'une brique qui ne déclare rien (un
#: module tiers écrit avant la déclaration) : un ``token`` y est masqué même
#: sans qu'on le sache secret.
SECRET_KWARGS = frozenset({"token", "api_key", "key", "secret", "password"})
SECRET_PLACEHOLDER = "<secret>"


def sans_secrets(
    kwargs: Mapping[str, object], declared: frozenset[str] = frozenset()
) -> dict[str, object]:
    """Les kwargs saisis, valeurs secrètes (par nom, ou ``declared``)
    remplacées par ``<secret>``."""
    secrets = SECRET_KWARGS | declared
    return {k: SECRET_PLACEHOLDER if k in secrets else v for k, v in kwargs.items()}


def secret_values(
    adapter_kwargs: Mapping[str, Mapping[str, object]],
    modules: Mapping[str, Module] | None = None,
) -> tuple[str, ...]:
    """Valeurs secrètes du run — à caviarder dans tout message d'échec : celles
    des noms de ``SECRET_KWARGS`` et celles que chaque module déclare secrètes."""
    values: set[str] = set()
    for name, kwargs in adapter_kwargs.items():
        module = (modules or {}).get(name)
        secrets = SECRET_KWARGS | secret_names(
            declared_params(module) if module is not None else None
        )
        values.update(str(v) for k, v in kwargs.items() if k in secrets and str(v))
    # Le plus long d'abord : un secret qui en contient un autre reste masqué.
    return tuple(sorted(values, key=lambda v: (-len(v), v)))


def _hook(module: Module, name: str) -> dict[str, object]:
    """Un hook de provenance **optionnel**, détecté par duck-typing.

    Hors du ``Module`` Protocol : le contrat d'exécution reste unique, et un
    module qui n'a rien à déclarer n'a rien à implémenter. Le hook est
    best-effort côté module (binaire absent → ``{}``).
    """
    probe = getattr(module, name, None)
    return dict(probe()) if callable(probe) else {}


def module_identities(
    spec: RunSpec,
    modules: Mapping[str, Module],
    *,
    recorded_binaries: Mapping[str, Mapping[str, str]] | None = None,
) -> dict[str, ModuleIdentity]:
    """L'identité de chaque module construit pour ``spec``.

    ``settings`` = la saisie (sans secret) complétée de ``effective_settings()``
    — ce que le module applique vraiment : défauts, prompt, modèle demandé,
    endpoint lu dans l'environnement. Les réglages saisis que la brique déclare
    d'**exploitation** (``affects_output=False``) vont à ``operational`` : au
    manifeste, hors de l'empreinte. ``binaries`` = ``system_binaries()``,
    sondés ici, **avant** la première page : ce sont eux qui entrent dans la clé.
    ``recorded_binaries`` (relecture hors ligne) les remplace par ceux de
    l'archive : rien ne s'exécute, la machine qui relit n'a rien à sonder.
    """
    identities: dict[str, ModuleIdentity] = {}
    for name in sorted(modules):
        module = modules[name]
        binaries: Mapping[str, object] = (
            _hook(module, "system_binaries")
            if recorded_binaries is None
            else recorded_binaries.get(name, {})
        )
        params = declared_params(module)
        saisis = sans_secrets(spec.adapter_kwargs.get(name, {}), secret_names(params))
        exploitation = operational_names(params)
        identities[name] = ModuleIdentity(
            version=module.version,
            settings={
                **{k: v for k, v in saisis.items() if k not in exploitation},
                **_hook(module, "effective_settings"),
            },
            binaries={str(k): str(v) for k, v in binaries.items()},
            operational={k: v for k, v in saisis.items() if k in exploitation},
        )
    return identities


def served_models(
    spec: RunSpec, outputs: Mapping[str, Mapping[str, StepArtifacts]]
) -> dict[str, tuple[str, ...]]:
    """``{adapter_name: modèles servis}``, lus dans la provenance des sorties.

    L'exécuteur estampille sur chaque artefact ce que le module a lu dans la
    réponse ; une unité rechargée de l'archive garde sa provenance, donc son
    modèle servi. Un module dont aucune réponse ne le dit n'a pas d'entrée.
    """
    found: dict[str, set[str]] = {}
    for pipeline in spec.pipelines:
        for by_step in outputs.get(pipeline.name, {}).values():
            for step in pipeline.steps:
                for artifact in by_step.get(step.id, {}).values():
                    if artifact.provenance and artifact.provenance.served_models:
                        found.setdefault(step.adapter_name, set()).update(
                            artifact.provenance.served_models
                        )
    return {name: tuple(sorted(models)) for name, models in sorted(found.items())}


def build_manifest(
    spec: RunSpec,
    identities: Mapping[str, ModuleIdentity],
    code_version: str,
    started_at: datetime,
    completed_at: datetime,
    *,
    served: Mapping[str, tuple[str, ...]],
    artifacts_dir: str | None = None,
) -> RunManifest:
    """Le manifeste : ce que les identités ont haché, plus l'environnement.

    ``adapter_kwargs`` = les réglages **effectifs** de l'identité (pas la seule
    saisie : la température d'un run ne doit pas dépendre du défaut de la
    version qui l'a produit), réglages d'exploitation compris (``self_hosted``,
    que l'économie lit) ; ``system_binaries_lock`` = les binaires de
    l'identité (ceux de la clé, pas un second sondage en fin de run).
    """
    names = sorted(identities)
    binaries: dict[str, str] = {}
    for name in names:
        binaries.update(identities[name].binaries)
    return RunManifest(
        run_id=spec.run_id or f"run-{started_at.strftime('%Y%m%dT%H%M%S')}",
        corpus_name=spec.corpus.name,
        n_documents=len(spec.corpus.documents),
        pipeline_specs=spec.pipelines,
        adapter_kwargs={
            name: {**identities[name].operational, **identities[name].settings}
            for name in names
        },
        module_versions={name: identities[name].version for name in names},
        system_binaries_lock=binaries,
        dependencies_lock=dependencies_lock(),
        unicode_version=unicodedata.unidata_version,
        served_models=dict(served),
        view_specs=spec.evaluation.views,
        failure_policy=spec.evaluation.failure_policy,
        code_version=code_version,
        started_at=started_at,
        completed_at=completed_at,
        metadata=spec.metadata,
        artifacts_dir=artifacts_dir,
    )


__all__ = [
    "SECRET_KWARGS",
    "SECRET_PLACEHOLDER",
    "build_manifest",
    "module_identities",
    "sans_secrets",
    "secret_values",
    "served_models",
]

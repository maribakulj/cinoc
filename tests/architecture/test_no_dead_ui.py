"""Garde-fou **anti-vide** : chaque option du composeur a un backend réel.

Le composeur (Banc d'essai) n'offre que des moteurs du **catalogue**
(``benchmark_engine_catalog``), regroupés par rôle. Ce test verrouille
mécaniquement qu'on **ne peut pas afficher une option sans backend** :

1. tout moteur offert est un **builder enregistré** (constructible au runtime) ;
2. tout moteur offert, **dans le mode de son rôle**, produit une spec sans
   ``RunPlanningError`` (une branche ``plan_benchmark_run`` réelle l'accepte).

Si un jour le catalogue et le planificateur/registre divergent (option ajoutée
côté UI sans branche serveur, ou inversement), ce test casse — pas l'UI en prod.
"""

from __future__ import annotations

import pytest

from cinoc.app.engines import engine_statuses
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.run_planning import (
    Competitor,
    RunPlanningError,
    benchmark_engine_catalog,
    plan_benchmark_run,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef


def _catalog() -> dict[str, list[dict[str, object]]]:
    # Sondes réelles : la *liste* des moteurs par rôle est déterministe (seule la
    # disponibilité varie selon l'environnement — ici on ne teste que la liste).
    return benchmark_engine_catalog(engine_statuses())


def _registry_kinds() -> set[str]:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return set(registry.kinds())


def _corpus() -> CorpusSpec:
    return CorpusSpec(name="t", documents=(DocumentRef(id="d", image_uri="d.png"),))


def test_catalog_engines_are_registered_builders() -> None:
    offered = {entry["kind"] for role in _catalog().values() for entry in role}
    missing = offered - _registry_kinds()
    assert not missing, f"moteurs offerts au composeur sans builder : {missing}"


def _competitor(role: str, kind: str) -> Competitor:
    if role == "ocr":
        return Competitor(engine=kind, model="m")
    if role == "llm":
        return Competitor(engine="tesseract", mode="text_only", llm=kind, model="m")
    return Competitor(
        engine="tesseract", mode="text_and_image", llm=kind, model="m"
    )  # vlm


def test_every_catalog_option_has_a_working_plan_branch() -> None:
    corpus = _corpus()
    for role, entries in _catalog().items():
        for entry in entries:
            comp = _competitor(role, str(entry["kind"]))
            # ne doit pas lever : l'option offerte est réellement planifiable.
            plan_benchmark_run((comp,), corpus, "r")


def test_vlm_engines_also_plan_zero_shot() -> None:
    corpus = _corpus()
    for entry in _catalog()["vlm"]:
        comp = Competitor(engine=str(entry["kind"]), mode="zero_shot", model="m")
        plan_benchmark_run((comp,), corpus, "r")


def test_non_offered_engine_is_refused() -> None:
    # Contre-épreuve : un moteur **hors catalogue** (precomputed = démo) ne se
    # planifie pas comme concurrent → le catalogue ne ment pas par omission.
    with pytest.raises(RunPlanningError):
        plan_benchmark_run((Competitor(engine="precomputed"),), _corpus(), "r")

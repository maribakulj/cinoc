"""Les specs de la campagne de référence (P5h) se chargent, et sa partie sans
clé **est** une partie de la spec complète.

La campagne s'exécute en deux temps : ce qui ne demande aucune clé (Tesseract,
le VLM local) tourne d'abord, archivé ; la spec complète, avec Mistral, relit
ensuite ces unités au lieu de les rejouer. Cela ne tient que si chaque pipeline
sans clé est, au caractère près, un pipeline de la spec complète, avec les mêmes
réglages de briques : la clé d'unité en dérive. Un écart silencieux ferait
rejouer — ou, hors ligne, refuser — la moitié de la campagne.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cinoc.domain.run_spec import RunSpec

CAMPAGNE = Path(__file__).resolve().parents[2] / "campaigns" / "2026-11-26-reference"


def _spec(nom: str) -> RunSpec:
    data = yaml.safe_load((CAMPAGNE / nom).read_text(encoding="utf-8"))
    return RunSpec.model_validate(data)


@pytest.mark.parametrize("corpus", ["bnl", "dresden"])
def test_the_keyless_part_is_a_part_of_the_full_campaign(corpus: str) -> None:
    complete = _spec(f"{corpus}.yaml")
    sans_cle = _spec(f"{corpus}-sans-cle.yaml")
    pipelines = {p.name: p for p in complete.pipelines}

    for pipeline in sans_cle.pipelines:
        assert pipelines[pipeline.name] == pipeline
        for step in pipeline.steps:
            assert complete.adapter_kwargs.get(step.adapter_name) == (
                sans_cle.adapter_kwargs.get(step.adapter_name)
            ), step.adapter_name
    assert sans_cle.corpus == complete.corpus
    assert sans_cle.evaluation == complete.evaluation
    # La partie sans clé n'appelle aucun service facturé.
    facturees = {"mistral", "mistral_ocr"}
    for pipeline in sans_cle.pipelines:
        for step in pipeline.steps:
            assert step.adapter_name.split(":", 1)[0] not in facturees
            kwargs = sans_cle.adapter_kwargs.get(step.adapter_name, {})
            assert kwargs.get("producer") not in {"mistral", "mistral_vision"}


@pytest.mark.parametrize(
    "nom", ["bnl", "dresden", "bnl-local", "bnl-local-saknussemm", "dresden-local"]
)
def test_every_view_scores_every_pipeline_of_the_campaign(nom: str) -> None:
    """La vue d'ablation ``lecture`` vise une étape que chaque chaîne nomme."""
    spec = _spec(f"{nom}.yaml")
    noms = {v.name for v in spec.evaluation.views}
    assert {"texte", "texte (lignes)", "lecture", "sans césure"} <= noms
    for pipeline in spec.pipelines:
        assert pipeline.step_by_id("lecture") is not None, pipeline.name


# --- La campagne locale (S31L, D-311) ---------------------------------------
#
# Sans clé Mistral, les expériences que S31 lui réservait tournent sur des
# modèles locaux (Ollama). Chaque spec locale **contient** la partie sans clé
# de S30, au caractère près — sinon l'archive de S30 ne serait pas relue — et
# chaque pipeline local a la forme d'un pipeline Mistral de la spec complète :
# seule la brique qui appelle le modèle change. La correction structurée,
# trop lente sur CPU pour le corpus entier, tourne sur un sous-ensemble fixé
# d'avance (rangs multiples de 8) : sa spec reprend tout ``bnl-local``.

_FACTUREES = {"mistral", "mistral_ocr"}
_LOCALES = [
    ("bnl", "bnl-local"),
    ("bnl", "bnl-local-saknussemm"),
    ("dresden", "dresden-local"),
]


def _forme(pipeline: object) -> list[tuple[object, ...]]:
    """Le câblage d'un pipeline, sans le nom des briques."""
    return [
        (s.id, s.kind, s.input_types, s.output_types, s.inputs_from, s.fanout, s.crop)
        for s in pipeline.steps  # type: ignore[attr-defined]
    ]


@pytest.mark.parametrize(("corpus", "nom"), _LOCALES)
def test_the_local_campaign_rereads_the_keyless_part(corpus: str, nom: str) -> None:
    locale = _spec(f"{nom}.yaml")
    sans_cle = _spec(f"{corpus}-sans-cle.yaml")
    pipelines = {p.name: p for p in locale.pipelines}

    for pipeline in sans_cle.pipelines:
        assert pipelines[pipeline.name] == pipeline
        for step in pipeline.steps:
            assert locale.adapter_kwargs.get(step.adapter_name) == (
                sans_cle.adapter_kwargs.get(step.adapter_name)
            ), step.adapter_name
    assert locale.evaluation == sans_cle.evaluation
    # Le corpus entier, ou un sous-ensemble de ses documents, tels quels.
    documents = list(sans_cle.corpus.documents)
    rangs = [documents.index(d) for d in locale.corpus.documents]
    assert rangs == sorted(rangs) and rangs
    assert locale.corpus.name == sans_cle.corpus.name


def test_the_structured_correction_subset_is_fixed_by_rank() -> None:
    """Rangs 0, 8, 16, 24, 32 de l'ordre des identifiants — la règle dite au
    README, pas un choix fait après coup ; et tout ``bnl-local`` y est repris."""
    complet = list(_spec("bnl-sans-cle.yaml").corpus.documents)
    sous = _spec("bnl-local-saknussemm.yaml")
    assert list(sous.corpus.documents) == complet[::8]
    pipelines = {p.name: p for p in sous.pipelines}
    base = _spec("bnl-local.yaml")
    for pipeline in base.pipelines:
        assert pipelines[pipeline.name] == pipeline
        for step in pipeline.steps:
            assert sous.adapter_kwargs.get(step.adapter_name) == (
                base.adapter_kwargs.get(step.adapter_name)
            )


@pytest.mark.parametrize(("corpus", "nom"), _LOCALES)
def test_each_local_pipeline_mirrors_a_mistral_one(corpus: str, nom: str) -> None:
    locale = _spec(f"{nom}.yaml")
    complete = _spec(f"{corpus}.yaml")
    sans_cle = {p.name for p in _spec(f"{corpus}-sans-cle.yaml").pipelines}
    mistral = [
        p for p in complete.pipelines
        if any(s.adapter_name.split(":", 1)[0] in _FACTUREES
               or complete.adapter_kwargs.get(s.adapter_name, {}).get("producer")
               == "mistral" for s in p.steps)
    ]
    ajoutes = [p for p in locale.pipelines if p.name not in sans_cle]
    assert ajoutes
    for pipeline in ajoutes:
        prefixe = pipeline.name.split(" · ", 1)[0]
        assert any(
            m.name.split(" · ", 1)[0] == prefixe and _forme(m) == _forme(pipeline)
            for m in mistral
        ), pipeline.name
        for step in pipeline.steps:
            nom_brique = step.adapter_name.split(":", 1)[0]
            assert nom_brique not in _FACTUREES, step.adapter_name
            kwargs = locale.adapter_kwargs.get(step.adapter_name, {})
            if nom_brique == "ollama":
                # Déterminisme demandé, pas supposé : écrit dans la spec.
                assert kwargs["temperature"] == 0 and kwargs["seed"] == 0
            if nom_brique in {"ollama", "saknussemm"} and "host" in kwargs:
                assert kwargs["host"].startswith("http://127.0.0.1:")
            assert kwargs.get("producer") not in {"mistral", "mistral_vision"}

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


@pytest.mark.parametrize("corpus", ["bnl", "dresden"])
def test_the_billed_part_completes_the_keyless_part(corpus: str) -> None:
    """S31 exécute la partie Mistral seule, cinq fois (``--repeat 5``), dans des
    répétitions semées de la partie sans clé : la spec complète, hors ligne, les
    relit toutes deux. La partie facturée est donc, elle aussi, une partie de la
    spec complète au caractère près — et les deux parties la recouvrent."""
    complete = _spec(f"{corpus}.yaml")
    sans_cle = _spec(f"{corpus}-sans-cle.yaml")
    facturee = _spec(f"{corpus}-mistral.yaml")
    pipelines = {p.name: p for p in complete.pipelines}

    for pipeline in facturee.pipelines:
        assert pipelines[pipeline.name] == pipeline
        for step in pipeline.steps:
            assert complete.adapter_kwargs.get(step.adapter_name) == (
                facturee.adapter_kwargs.get(step.adapter_name)
            ), step.adapter_name
    noms_sans_cle = [p.name for p in sans_cle.pipelines]
    noms_factures = [p.name for p in facturee.pipelines]
    assert not set(noms_sans_cle) & set(noms_factures)
    assert sorted(noms_sans_cle + noms_factures) == sorted(pipelines)
    assert facturee.corpus == complete.corpus
    assert facturee.evaluation == complete.evaluation


@pytest.mark.parametrize("corpus", ["bnl", "dresden"])
def test_every_view_scores_every_pipeline_of_the_campaign(corpus: str) -> None:
    """La vue d'ablation ``lecture`` vise une étape que chaque chaîne nomme."""
    spec = _spec(f"{corpus}.yaml")
    noms = {v.name for v in spec.evaluation.views}
    assert {"texte", "texte (lignes)", "lecture", "sans césure"} <= noms
    for pipeline in spec.pipelines:
        assert pipeline.step_by_id("lecture") is not None, pipeline.name

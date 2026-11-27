"""Contre-expertise, affirmation 10 — la campagne de référence (P5h) est-elle
une **ablation** (une seule variable changée par comparaison) ?

Lecture pure des specs publiées ``campaigns/2026-11-26-reference/*.yaml`` : on
réduit chaque étape à sa « brique » (famille d'adaptateur + réglages déclarés,
étiquette ôtée) et à son amont complet, puis on compare les paires que la
campagne présente comme des réponses à ses questions. Rouge = la paire change
plus d'une chose à la fois.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run_spec import RunSpec

CAMPAGNE = (
    Path(__file__).resolve().parents[3] / "campaigns" / "2026-11-26-reference"
)
CORPUS = ["bnl", "dresden"]


def _spec(corpus: str) -> RunSpec:
    data = yaml.safe_load((CAMPAGNE / f"{corpus}.yaml").read_text(encoding="utf-8"))
    return RunSpec.model_validate(data)


def _pipeline(spec: RunSpec, name: str) -> PipelineSpec:
    for pipeline in spec.pipelines:
        if pipeline.name == name:
            return pipeline
    raise AssertionError(f"pipeline absent : {name!r}")


def _brick(spec: RunSpec, adapter_name: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Famille d'adaptateur + réglages déclarés, sans l'étiquette (un nom)."""
    kwargs = {
        k: repr(v)
        for k, v in spec.adapter_kwargs.get(adapter_name, {}).items()
        if k != "label"
    }
    return adapter_name.split(":", 1)[0], tuple(sorted(kwargs.items()))


def _upstream(spec: RunSpec, pipeline: PipelineSpec, step_id: str) -> Any:
    """Forme canonique d'une étape **et de tout son amont** (sans les ids)."""
    if step_id == "__initial__":
        return "entrée initiale"
    step = pipeline.step_by_id(step_id)
    assert step is not None, (pipeline.name, step_id)
    return (
        step.kind,
        _brick(spec, step.adapter_name),
        tuple(sorted(step.params.items())),
        step.fanout,
        step.crop,
        tuple(
            sorted(
                (t.value, repr(_upstream(spec, pipeline, source)))
                for t, source in step.inputs_from.items()
            )
        ),
    )


def _model(spec: RunSpec, adapter_name: str) -> object:
    return spec.adapter_kwargs.get(adapter_name, {}).get("model")


# --------------------------------------------------------------------------
# Saknussemm contre correction LLM libre (la question centrale)
# --------------------------------------------------------------------------


@pytest.mark.parametrize("corpus", CORPUS)
def test_ablation_saknussemm__un_temoin_correction_libre_sur_la_meme_lecture(
    corpus: str,
) -> None:
    """Pour chaque correction structurée à modèle, il faut un pipeline jumeau :
    correction LLM libre, **même LLM**, sur **la même lecture** (même amont)."""
    spec = _spec(corpus)
    sans_temoin: list[str] = []
    for pipeline in spec.pipelines:
        for step in pipeline.steps:
            if step.kind != "structured_correction":
                continue
            if spec.adapter_kwargs.get(step.adapter_name, {}).get("producer") == "rules":
                continue
            lecture = _upstream(spec, pipeline, "lecture")
            modele = _model(spec, step.adapter_name)
            temoins = [
                other.name
                for other in spec.pipelines
                for s in other.steps
                if s.kind == "correction"
                and _model(spec, s.adapter_name) == modele
                and _upstream(spec, other, next(iter(s.inputs_from.values())))
                == lecture
            ]
            if not temoins:
                sans_temoin.append(pipeline.name)
    assert not sans_temoin, (
        "aucune correction LLM libre au même LLM sur la même lecture que : "
        f"{sans_temoin}"
    )


# --------------------------------------------------------------------------
# Les autres comparaisons de la campagne
# --------------------------------------------------------------------------


def test_ablation_selective__e4_ne_differe_de_e3_que_par_le_routage_qe() -> None:
    """E3 (saknussemm mistral) contre E4 (même chose + QE dalembert, seuil 0,5) :
    même amont, même producteur, même modèle ; seuls ``qe``/``qe_skip`` changent."""
    spec = _spec("bnl")
    e3 = _pipeline(spec, "E3 · segmentation → tesseract → saknussemm (mistral)")
    e4 = _pipeline(
        spec, "E4 · segmentation → tesseract → saknussemm sélectif (mistral, QE dalembert)"
    )
    assert [_upstream(spec, e3, s.id) for s in e3.steps[:-1]] == [
        _upstream(spec, e4, s.id) for s in e4.steps[:-1]
    ]
    k3 = dict(spec.adapter_kwargs[e3.steps[-1].adapter_name])
    k4 = dict(spec.adapter_kwargs[e4.steps[-1].adapter_name])
    differ = {k for k in k3.keys() | k4.keys() if k3.get(k) != k4.get(k)}
    assert differ == {"label", "qe", "qe_skip"}


@pytest.mark.parametrize("corpus", CORPUS)
@pytest.mark.parametrize(
    ("e0", "e2"),
    [
        ("E0 · tesseract", "E2 · tesseract → mistral"),
        ("E0 · mistral-ocr", "E2 · mistral-ocr → mistral"),
    ],
)
def test_ablation_post_correction__e2_est_e0_plus_une_seule_etape(
    corpus: str, e0: str, e2: str
) -> None:
    """E2 doit être E0 (même brique OCR, mêmes réglages) suivi d'une correction."""
    spec = _spec(corpus)
    p0, p2 = _pipeline(spec, e0), _pipeline(spec, e2)
    assert len(p2.steps) == len(p0.steps) + 1
    assert [_upstream(spec, p0, s.id) for s in p0.steps] == [
        _upstream(spec, p2, s.id) for s in p2.steps[:-1]
    ]


@pytest.mark.parametrize("corpus", CORPUS)
def test_ablation_correction_regles__e3_est_e1_plus_une_seule_etape(
    corpus: str,
) -> None:
    """E3 « règles » doit être E1 (segmentation → tesseract) plus une correction."""
    spec = _spec(corpus)
    p1 = _pipeline(spec, "E1 · segmentation → tesseract")
    p3 = _pipeline(spec, "E3 · segmentation → tesseract → saknussemm (règles)")
    assert [_upstream(spec, p1, s.id) for s in p1.steps] == [
        _upstream(spec, p3, s.id) for s in p3.steps[:-1]
    ]


@pytest.mark.parametrize("corpus", CORPUS)
def test_ablation_segmentation_ocr__meme_reglages_tesseract_page_et_region(
    corpus: str,
) -> None:
    """E0 contre E1 (Tesseract) : la brique de lecture doit avoir les mêmes
    réglages déclarés ; seule la segmentation (et le découpage) change."""
    spec = _spec(corpus)
    assert _brick(spec, "tesseract:lecture") == _brick(spec, "tesseract:reco")


@pytest.mark.parametrize("corpus", CORPUS)
def test_ablation_segmentation_vlm__meme_reglages_vlm_page_et_region(
    corpus: str,
) -> None:
    """« La segmentation aide-t-elle les VLM ? » : E1-VLM (``mistral:reco``) et
    E5 (``mistral:vlm``) doivent appeler le VLM avec les mêmes réglages."""
    spec = _spec(corpus)
    assert _brick(spec, "mistral:reco") == _brick(spec, "mistral:vlm")

"""Deux chaînes **de même nom**, composées différemment (S34b, n° 6 + 7).

Le testeur extérieur a lancé ``ocr_simple`` deux fois (``lang=eng``,
``lang=fra``) : le rapport disait ``ocr_simple · tesseract`` et ``… #2``, la
langue ne se lisait que dans « Composition des chaînes ». Puis ``cinoc
compare`` a apparié deux ``ocr_simple · tesseract`` de langues différentes et
présenté le delta comme une amélioration. Le nom ne change pas (il entre dans
la clé d'archive) : la différence se **dit**, là où on lit les noms.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import MetricScore, PipelineResult, RunResult
from cinoc.interfaces.cli import main
from cinoc.reports import default_report_renderer
from cinoc.reports.compare import render_comparison
from cinoc.reports.composition_diff import homonym_hints, paired_differences

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _corpus() -> CorpusSpec:
    return CorpusSpec.model_validate(
        {
            "name": "c",
            "documents": [
                {
                    "id": "p1",
                    "image_uri": "p1.png",
                    "ground_truths": [{"type": "raw_text", "uri": "p1.gt.txt"}],
                }
            ],
        }
    )


def _run(*langs: str, run_id: str = "r") -> RunResult:
    spec = plan_recipe_run(
        _corpus(),
        tuple(
            RecipeEntry(recipe="ocr_simple", params={"ocr": {"lang": lang}})
            for lang in langs
        ),
        run_id=run_id,
    )
    manifest = RunManifest(
        run_id=run_id,
        corpus_name="c",
        n_documents=1,
        code_version="1.0",
        started_at=FIXED,
        completed_at=FIXED,
        pipeline_specs=spec.pipelines,
        adapter_kwargs=spec.adapter_kwargs,
        module_versions={n: "1.0" for n in spec.adapter_kwargs},
    )
    return RunResult(
        manifest=manifest,
        pipelines=tuple(
            PipelineResult(
                pipeline=p.name,
                view="texte",
                conditional_aggregate=(
                    MetricScore(metric="cer", value=0.1, support=1),
                ),
            )
            for p in spec.pipelines
        ),
    )


def test_two_homonyms_in_one_run_say_what_sets_them_apart() -> None:
    run = _run("eng", "fra")
    noms = [p.name for p in run.manifest.pipeline_specs]
    assert noms == ["ocr_simple · tesseract", "ocr_simple · tesseract #2"]
    assert homonym_hints(run.manifest) == {
        "ocr_simple · tesseract": "ocr.lang=eng",
        "ocr_simple · tesseract #2": "ocr.lang=fra",
    }


def test_a_pipeline_without_homonym_gets_no_hint() -> None:
    assert homonym_hints(_run("eng").manifest) == {}


def test_the_report_shows_the_setting_next_to_the_name() -> None:
    html = default_report_renderer().render(_run("eng", "fra"))
    # Dans le classement (vue d'ensemble), pas seulement dans la composition.
    classement = html.split('aria-label="Composition', 1)[0]
    assert "ocr.lang=eng" in classement and "ocr.lang=fra" in classement


def test_paired_pipelines_with_different_settings_are_named() -> None:
    (paire,) = paired_differences(_run("fra").manifest, _run("eng").manifest)
    assert paire.pipeline == "ocr_simple · tesseract"
    (diff,) = paire.differences
    assert (diff.label(), diff.value_a, diff.value_b) == ("ocr.lang", "fra", "eng")


def test_identical_compositions_are_not_reported() -> None:
    assert paired_differences(_run("fra").manifest, _run("fra").manifest) == ()


def test_the_comparison_warns_in_both_languages() -> None:
    a, b = _run("fra", run_id="a"), _run("eng", run_id="b")
    fr = render_comparison(a, b)
    assert "ocr.lang" in fr and "fra → eng" in fr and "même composition" in fr
    en = render_comparison(a, b, lang="en")
    assert "ocr.lang" in en and "same composition" in en
    assert "même composition" not in render_comparison(a, a)


def test_cinoc_compare_warns_on_the_console(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(_run("fra", run_id="a").model_dump_json(), encoding="utf-8")
    b.write_text(_run("eng", run_id="b").model_dump_json(), encoding="utf-8")
    assert main(["compare", str(a), str(b), "-o", str(tmp_path / "d.html")]) == 0
    sortie = capsys.readouterr()
    assert "ocr_simple · tesseract" in sortie.err
    assert "ocr.lang : fra -> eng" in sortie.err

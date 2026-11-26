"""Section profil moteur : panneaux drill-in (KPIs + CER/document, révélés)."""

from __future__ import annotations

from datetime import UTC, datetime

from cinoc.domain.run import RunManifest
from cinoc.evaluation.analysis import (
    Analysis,
    CalibrationBin,
    CalibrationPayload,
    PipelineCalibration,
    PipelineTaxonomy,
    TaxonomyCount,
    TaxonomyPayload,
)
from cinoc.evaluation.result import (
    MetricScore,
    PipelineResult,
    RunDocumentResult,
    RunResult,
)
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.engine_profile import EngineProfileSection

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _doc(doc_id: str, pipeline: str, cer: float) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id,
        pipeline=pipeline,
        view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),),
    )


def _result() -> RunResult:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=2,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    pipelines = (
        PipelineResult(
            pipeline="tesseract", view="text",
            aggregate=(MetricScore(metric="cer", value=0.20, support=2),),
        ),
        PipelineResult(
            pipeline="pero", view="text",
            aggregate=(MetricScore(metric="cer", value=0.10, support=2),),
        ),
    )
    docs = (
        _doc("d1", "tesseract", 0.10), _doc("d2", "tesseract", 0.30),
        _doc("d1", "pero", 0.05), _doc("d2", "pero", 0.15),
    )
    return RunResult(manifest=manifest, pipelines=pipelines, documents=docs)


def test_one_hidden_panel_per_engine_with_anchor() -> None:
    html = EngineProfileSection().render(_result(), SectionContext())
    assert html is not None
    assert html.count('class="drill-panel eng-profile"') == 2  # un panneau/moteur
    assert 'id="engine-0"' in html and 'id="engine-1"' in html  # ancres drill-in
    assert html.count('hidden role="region"') == 2  # cachés par défaut (au clic)
    assert "← Tous les moteurs" in html  # fil d'Ariane vers la liste, par panneau


def test_panel_has_kpi_band_and_cer_chart() -> None:
    html = EngineProfileSection().render(_result(), SectionContext())
    assert html is not None
    assert 'class="kpi-band"' in html and 'class="kpi-v"' in html
    assert "20,0 %" in html  # CER agrégat de tesseract en KPI
    assert 'class="bars-svg"' in html  # graphe CER par document


def test_prev_next_links_cycle() -> None:
    html = EngineProfileSection().render(_result(), SectionContext())
    assert html is not None
    # panneau 0 → suivant #engine-1 ; précédent boucle sur #engine-1
    assert 'href="#engine-1"' in html and 'href="#engine-0"' in html


def test_profile_includes_calibration_and_composition_when_present() -> None:
    base = _result()
    calib = CalibrationPayload(
        n_bins=2,
        pipelines=(
            PipelineCalibration(
                pipeline="tesseract", step="ocr", n_tokens=10, ece=0.08, mce=0.2,
                bins=(
                    CalibrationBin(
                        lower=0.8, upper=1.0, mean_confidence=0.9,
                        accuracy=0.85, count=10,
                    ),
                ),
            ),
        ),
    )
    taxo = TaxonomyPayload(
        classes=("visual", "case"),
        pipelines=(
            PipelineTaxonomy(
                pipeline="tesseract", total_errors=4,
                counts=(
                    TaxonomyCount(label="visual", count=3),
                    TaxonomyCount(label="case", count=1),
                ),
            ),
        ),
    )
    result = base.model_copy(
        update={
            "analyses": (
                Analysis(scope="corpus", view="text", payload=calib),
                Analysis(scope="corpus", view="text", payload=taxo),
            )
        }
    )
    html = EngineProfileSection().render(result, SectionContext())
    assert html is not None
    assert 'class="calib-svg"' in html  # courbe de calibration du moteur
    assert 'class="comp-bar"' in html  # composition d'erreurs du moteur
    assert "8,0 %" in html  # ECE en KPI (réutilise les builders U2b/U2c)


def _doc_s(doc_id: str, pipeline: str, cer: float, stratum: str) -> RunDocumentResult:
    return RunDocumentResult(
        document_id=doc_id, pipeline=pipeline, view="text",
        scores=(MetricScore(metric="cer", value=cer, support=1),), stratum=stratum,
    )


def test_profile_shows_per_stratum_cer_when_multiple_strata() -> None:
    from cinoc.evaluation.result import RunResult as _RR

    base = _result()
    docs = (
        _doc_s("d1", "tesseract", 0.10, "presse"),
        _doc_s("d2", "tesseract", 0.40, "manuscrit"),
        _doc_s("d3", "tesseract", 0.20, "presse"),
    )
    result = _RR(manifest=base.manifest, pipelines=base.pipelines, documents=docs)
    html = EngineProfileSection().render(result, SectionContext())
    assert html is not None
    assert "Performance par strate" in html
    assert "presse" in html and "manuscrit" in html
    # macro-moyenne presse = (0.10+0.20)/2 = 15.0 % ; manuscrit = 40.0 %
    assert "15,0 %" in html and "40,0 %" in html
    # une seule strate → pas de bloc (jamais inventé)
    one = _RR(
        manifest=base.manifest, pipelines=base.pipelines,
        documents=(_doc_s("d1", "tesseract", 0.1, "presse"),),
    )
    assert "Performance par strate" not in (
        EngineProfileSection().render(one, SectionContext()) or ""
    )


def test_profile_config_details_from_manifest() -> None:
    from cinoc.domain.artifacts import ArtifactType
    from cinoc.domain.pipeline import PipelineSpec, PipelineStep

    base = _result()
    spec = PipelineSpec(
        name="tesseract",
        steps=(
            PipelineStep(
                id="ocr", kind="ocr", adapter_name="tesseract:fra",
                params={"psm": 6}, input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    manifest = base.manifest.model_copy(
        update={"pipeline_specs": (spec,), "module_versions": {"tesseract:fra": "5.3"}}
    )
    result = base.model_copy(update={"manifest": manifest})
    html = EngineProfileSection().render(result, SectionContext())
    assert html is not None
    assert "<details>" in html and "Configuration" in html  # disclosure natif
    assert "tesseract:fra" in html  # adapter
    assert "5.3" in html  # version déclarée (reproductibilité)
    assert "psm=6" in html  # paramètre
    # données de démo (sans spec) → pas de bloc config
    assert "<details>" not in (
        EngineProfileSection().render(_result(), SectionContext()) or ""
    )


def test_profile_parameters_are_the_effective_module_settings() -> None:
    """Pilote D-281, D12 : « Paramètres — » à côté d'une composition qui
    montrait ``lang`` et ``psm`` — les réglages vivent dans ``adapter_kwargs``
    du manifeste, pas dans ``step.params``. FR et EN lisent la même source."""
    from cinoc.domain.artifacts import ArtifactType
    from cinoc.domain.pipeline import PipelineSpec, PipelineStep

    base = _result()
    spec = PipelineSpec(
        name="tesseract",
        steps=(
            PipelineStep(
                id="ocr", kind="ocr", adapter_name="tesseract:fra_deu",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    manifest = base.manifest.model_copy(
        update={
            "pipeline_specs": (spec,),
            "adapter_kwargs": {
                "tesseract:fra_deu": {"label": "fra_deu", "lang": "fra+deu", "psm": 6}
            },
        }
    )
    result = base.model_copy(update={"manifest": manifest})
    for lang, entete in (("fr", "Paramètres"), ("en", "Parameters")):
        html = EngineProfileSection().render(result, SectionContext(lang=lang))
        assert html is not None
        debut = html.index("<details>")
        bloc = html[debut : html.index("</details>", debut)]
        assert f"<th>{entete}</th>" in bloc
        assert "lang=fra+deu · psm=6" in bloc
        assert "label=fra_deu" not in bloc  # nom de fichier, pas un réglage
        assert '<td class="lbl">—</td>' not in bloc


def test_none_without_pipelines() -> None:
    manifest = RunManifest(
        run_id="r", corpus_name="demo", n_documents=0,
        code_version="1.0", started_at=FIXED, completed_at=FIXED,
    )
    empty = RunResult(manifest=manifest)
    assert EngineProfileSection().render(empty, SectionContext()) is None


def test_deterministic() -> None:
    r = _result()
    a = EngineProfileSection().render(r, SectionContext())
    b = EngineProfileSection().render(r, SectionContext())
    assert a == b


def test_renders_english_labels() -> None:
    html = EngineProfileSection().render(_result(), SectionContext(lang="en"))
    assert html is not None
    # libellés EN introduits… (section détail : fil d'Ariane, pas d'en-tête de section)
    assert "← All engines" in html
    assert "CER per document " in html
    assert "engine 1 of 2" in html
    # … et leurs équivalents FR absents
    assert "← Tous les moteurs" not in html
    assert "CER par document " not in html
    assert "moteur 1 sur 2" not in html

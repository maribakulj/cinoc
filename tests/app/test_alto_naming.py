"""Un seul nom pour l'ALTO qu'un pipeline Cinoc écrit — lu tel qu'écrit (D-307).

Le testeur extérieur : ``cinoc hybrid imgs --out alto_hybrid`` écrit
``page_001.segmentation_puis_lecture_tesseract_layout_tesseract_alto.alto.xml``,
puis ``cinoc correct alto_hybrid`` répond « aucune paire ALTO + image ». Trois
règles d'appariement et deux noms d'export (CLI, web) coexistaient ; le nom
d'un document perdait ses points (``page.v2`` → ``page_v2``).
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from cinoc.app.alto_store import AltoStore
from cinoc.app.transcription import TranscriptionError, write_alto_files
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash

_XML = b"<alto/>"


def _sortie(tmp_path: Path, pipeline: str, document: str) -> dict[str, object]:
    source = tmp_path / f"src-{abs(hash((pipeline, document)))}.xml"
    source.write_bytes(_XML)
    artefact = Artifact(
        id=f"{document}:a",
        document_id=document,
        type=ArtifactType.ALTO_XML,
        uri=str(source),
        content_hash=compute_content_hash(_XML),
    )
    return {document: {"alto": {ArtifactType.ALTO_XML: artefact}}}


def test_the_name_written_is_the_name_alto_source_reads(tmp_path: Path) -> None:
    from cinoc.adapters.layout.alto_source import AltoLayoutSource
    from cinoc.domain.documents import DocumentRef

    sortie = tmp_path / "corpus"
    (ecrit,) = write_alto_files(
        sortie, {"ocr_simple · tesseract": _sortie(tmp_path, "p", "page.v2")}
    )
    lecteur = AltoLayoutSource(pipeline="ocr_simple_tesseract")
    document = DocumentRef(id="page.v2", image_uri=str(sortie / "page.v2.png"))
    assert lecteur.unit_inputs(document) == (ecrit,)


def test_a_document_id_keeps_its_dots(tmp_path: Path) -> None:
    (ecrit,) = write_alto_files(
        tmp_path / "out", {"ocr_simple · tesseract": _sortie(tmp_path, "p", "page.v2")}
    )
    assert ecrit.name == "page.v2.ocr_simple_tesseract.alto.xml"


def test_two_pipelines_that_would_write_one_file_are_refused(tmp_path: Path) -> None:
    sorties = {
        "ocr simple": _sortie(tmp_path, "a", "p"),
        "ocr_simple": _sortie(tmp_path, "b", "p"),
    }
    with pytest.raises(TranscriptionError, match="même ALTO"):
        write_alto_files(tmp_path / "out", sorties)


def test_the_web_export_is_named_like_the_cli(tmp_path: Path) -> None:
    store = AltoStore(tmp_path / "alto")
    store.save("run-1", "page.v2", "ocr_simple · tesseract", _XML)
    archive = store.archive("run-1")
    assert archive is not None
    with zipfile.ZipFile(io.BytesIO(archive)) as zf:
        assert zf.namelist() == ["page.v2.ocr_simple_tesseract.alto.xml"]


def test_the_web_export_never_overwrites_a_colliding_pipeline(tmp_path: Path) -> None:
    store = AltoStore(tmp_path / "alto")
    store.save("run-1", "p", "ocr simple", b"<alto>A</alto>")
    with pytest.raises(FileExistsError):
        store.save("run-1", "p", "ocr_simple", b"<alto>B</alto>")


def test_the_web_recipe_reads_a_deposited_cinoc_alto(tmp_path: Path) -> None:
    """Parité : la recette web ``alto_corrige`` (``POST /api/runs``) reçoit le
    même réglage que ``cinoc correct --pipeline`` ; un ZIP qui porte un ALTO
    écrit par Cinoc le dépose à côté de l'image, sans en faire une vérité."""
    pytest.importorskip("saknussemm")
    from cinoc.app.corpus_upload import extract_corpus_zip
    from cinoc.app.modules import ModuleRegistry, register_default_modules
    from cinoc.app.orchestrator import run as run_orchestrator
    from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run

    alto = (
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
        '<Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace><TextBlock ID="B1">'
        '<TextLine ID="L1"><String CONTENT="texte"/></TextLine></TextBlock>'
        "</PrintSpace></Page></Layout></alto>"
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("page.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        zf.writestr("page.ocr_simple_tesseract.alto.xml", alto)
        zf.writestr("page.gt.txt", "texte")
    corpus = extract_corpus_zip(buf, tmp_path / "c", name="c")
    (document,) = corpus.documents
    assert {t.type for t in document.ground_truths} == {ArtifactType.RAW_TEXT}
    spec = plan_recipe_run(
        corpus,
        (
            RecipeEntry(
                recipe="alto_corrige",
                params={"source": {"pipeline": "ocr_simple_tesseract"}},
            ),
        ),
        run_id="web",
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    result = run_orchestrator(spec, registry=registry, code_version="t")
    assert all(u.outcome == "ok" for u in result.usage)
    cer = next(
        s.value
        for p in result.pipelines
        if p.view == "texte"
        for s in result.principal_aggregate(p)
        if s.metric == "cer"
    )
    assert cer == 0.0

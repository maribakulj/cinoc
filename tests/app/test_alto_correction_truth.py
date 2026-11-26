"""``cinoc correct`` : aucun chiffre ne se lit comme une exactitude quand il
mesure la fidélité à l'entrée (D-307).

Le testeur extérieur, sur un dossier d'ALTO d'OCR produits par Cinoc :
``F1 RÉG. 1,0000 · CER RÉG. 0,0000 · LINE_IDENTITY_CER 0,0000`` sans un
avertissement — l'ALTO était déclaré vérité terrain de la vue ``structure``, et
la sortie se comparait à sa propre entrée. Les ``<nom>.gt.txt`` posés à côté
étaient ignorés, alors que la voie ZIP les prenait (CER 0,0152).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.alto_corpus import corpus_from_alto
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import CinocError

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="100" HEIGHT="50"><PrintSpace>'
    '<TextBlock ID="B1"><TextLine ID="L1"><String CONTENT="texte"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()


def _types(corpus_dir: Path, **options: object) -> list[set[ArtifactType]]:
    corpus = corpus_from_alto(corpus_dir, **options)  # type: ignore[arg-type]
    return [{t.type for t in d.ground_truths} for d in corpus.documents]


@pytest.fixture
def ocr(tmp_path: Path) -> Path:
    for nom in ("a", "b"):
        (tmp_path / f"{nom}.xml").write_bytes(_ALTO)
        (tmp_path / f"{nom}.png").write_bytes(b"png")
    return tmp_path


def test_an_ocr_alto_is_never_its_own_ground_truth(ocr: Path) -> None:
    assert _types(ocr) == [set(), set()]


def test_a_transcription_beside_the_image_is_the_ground_truth(ocr: Path) -> None:
    (ocr / "a.gt.txt").write_text("texte", encoding="utf-8")
    corpus = corpus_from_alto(ocr)
    a, b = corpus.documents
    assert a.gt_for(ArtifactType.RAW_TEXT) is not None
    assert a.metadata.get("gt_source") == "text"
    assert b.gt_for(ArtifactType.RAW_TEXT) is None


def test_with_an_ocr_sidecar_the_alto_is_a_transcription(ocr: Path) -> None:
    assert _types(ocr, ocr_sidecar="ocr.json") == [{ArtifactType.LAYOUT}] * 2


def test_no_ground_truth_means_none_at_all(ocr: Path) -> None:
    (ocr / "a.gt.txt").write_text("texte", encoding="utf-8")
    assert _types(ocr, ground_truth=False, ocr_sidecar="ocr.json") == [set(), set()]


def test_an_alto_named_dot_alto_is_paired(tmp_path: Path) -> None:
    (tmp_path / "page.alto.xml").write_bytes(_ALTO)
    (tmp_path / "page.png").write_bytes(b"png")
    assert [d.id for d in corpus_from_alto(tmp_path).documents] == ["page"]


def test_a_cinoc_alto_is_read_with_its_pipeline_never_as_truth(
    tmp_path: Path,
) -> None:
    (tmp_path / "page.ocr_simple_tesseract.alto.xml").write_bytes(_ALTO)
    (tmp_path / "page.png").write_bytes(b"png")
    corpus = corpus_from_alto(
        tmp_path, pipeline="ocr_simple_tesseract", ocr_sidecar="ocr.json"
    )
    assert [d.id for d in corpus.documents] == ["page"]
    assert corpus.documents[0].ground_truths == ()


def test_without_pipeline_the_error_names_the_pipelines_found(tmp_path: Path) -> None:
    for p in ("ocr_simple_tesseract", "segmentation_puis_lecture_x"):
        (tmp_path / f"page.{p}.alto.xml").write_bytes(_ALTO)
    (tmp_path / "page.png").write_bytes(b"png")
    with pytest.raises(CinocError) as exc:
        corpus_from_alto(tmp_path)
    message = str(exc.value)
    assert "--pipeline" in message
    assert "ocr_simple_tesseract, segmentation_puis_lecture_x" in message
    # Un message lu dans un terminal, pas du reStructuredText.
    assert "``" not in message


def test_a_pipeline_reads_only_its_own_alto(tmp_path: Path) -> None:
    (tmp_path / "page.xml").write_bytes(_ALTO)
    (tmp_path / "page.png").write_bytes(b"png")
    with pytest.raises(CinocError, match="<nom>.ocr.alto.xml"):
        corpus_from_alto(tmp_path, pipeline="ocr")


def test_a_path_is_not_a_pipeline_name(tmp_path: Path) -> None:
    (tmp_path / "page.png").write_bytes(b"png")
    with pytest.raises(CinocError, match="pipeline"):
        corpus_from_alto(tmp_path, pipeline="../x")

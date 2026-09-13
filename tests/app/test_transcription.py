"""Transcription locale : corpus depuis un dossier d'images + écriture des ALTO."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from cinoc.app.transcription import (
    TranscriptionError,
    corpus_from_images,
    write_alto_files,
)
from cinoc.domain.artifacts import Artifact, ArtifactType

_DOC_ID_RE = re.compile(r"^[A-Za-z0-9_.\-/]+$")


def test_corpus_one_document_per_image(tmp_path: Path) -> None:
    (tmp_path / "page1.png").write_bytes(b"x")
    (tmp_path / "page2.jpg").write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("ignore", encoding="utf-8")  # non-image
    corpus = corpus_from_images(tmp_path)
    assert corpus.name == tmp_path.name
    assert [d.id for d in corpus.documents] == ["page1", "page2"]
    assert all(d.image_uri and d.ground_truths == () for d in corpus.documents)


def test_corpus_sanitizes_and_dedupes_ids(tmp_path: Path) -> None:
    (tmp_path / "café.png").write_bytes(b"x")  # accent → caractère sûr
    (tmp_path / "cafe.png").write_bytes(b"x")
    ids = [d.id for d in corpus_from_images(tmp_path).documents]
    assert len(set(ids)) == len(ids)  # uniques (déduplication)
    assert all(_DOC_ID_RE.match(i) for i in ids)  # ids valides


def test_corpus_empty_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError):
        corpus_from_images(tmp_path)


def test_corpus_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(TranscriptionError):
        corpus_from_images(tmp_path / "absent")


def test_write_alto_files_copies_per_document(tmp_path: Path) -> None:
    src = tmp_path / "doc1.alto.xml"
    src.write_bytes(b"<alto/>")
    outputs = {
        "hybrid": {
            "doc1": {
                ArtifactType.ALTO_XML: Artifact(
                    id="doc1:assemble:alto_xml",
                    document_id="doc1",
                    type=ArtifactType.ALTO_XML,
                    uri=str(src),
                ),
            },
            "doc2": {  # pas d'ALTO → ignoré
                ArtifactType.RAW_TEXT: Artifact(
                    id="doc2:ocr:raw_text",
                    document_id="doc2",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(src),
                ),
            },
        }
    }
    out = tmp_path / "out"
    written = write_alto_files(out, outputs)
    assert written == [out / "doc1.hybrid.alto.xml"]
    assert (out / "doc1.hybrid.alto.xml").read_bytes() == b"<alto/>"


def test_two_pipelines_do_not_overwrite_each_other(tmp_path: Path) -> None:
    """**Le défaut que ce nom corrige.**

    Le fichier ne portait que l'identifiant de document. Comparer deux chaînes
    qui produisent toutes deux de l'ALTO — ce qu'un banc fait par définition —
    les faisait écrire au même endroit : la dernière écrasait l'autre, sans un
    mot, pendant que le compte annoncé restait juste. Trouvé en exécutant les
    deux chaînes NDNP côte à côte.
    """
    base = tmp_path / "base.xml"
    base.write_bytes(b"<alto>baseline</alto>")
    avance = tmp_path / "avance.xml"
    avance.write_bytes(b"<alto>advanced</alto>")

    def _sortie(chemin: Path) -> dict:
        return {
            "doc1": {
                ArtifactType.ALTO_XML: Artifact(
                    id="doc1:assemble:alto_xml",
                    document_id="doc1",
                    type=ArtifactType.ALTO_XML,
                    uri=str(chemin),
                )
            }
        }

    out = tmp_path / "out"
    written = write_alto_files(
        out,
        {"ndnp_baseline": _sortie(base), "ndnp_advanced": _sortie(avance)},
    )
    assert len(written) == 2, "deux pipelines, deux fichiers."
    lu = {p.name: p.read_bytes() for p in written}
    assert lu == {
        "doc1.ndnp_baseline.alto.xml": b"<alto>baseline</alto>",
        "doc1.ndnp_advanced.alto.xml": b"<alto>advanced</alto>",
    }


def test_a_pipeline_name_cannot_dig_a_path(tmp_path: Path) -> None:
    """Un nom de pipeline vient de la spec : il ne doit pas creuser d'arborescence
    ni couper l'extension attendue."""
    src = tmp_path / "a.xml"
    src.write_bytes(b"<alto/>")
    out = tmp_path / "out"
    written = write_alto_files(
        out,
        {
            "a/b.c": {
                "doc1": {
                    ArtifactType.ALTO_XML: Artifact(
                        id="i",
                        document_id="doc1",
                        type=ArtifactType.ALTO_XML,
                        uri=str(src),
                    )
                }
            }
        },
    )
    assert written == [out / "doc1.a_b_c.alto.xml"]
    assert written[0].parent == out

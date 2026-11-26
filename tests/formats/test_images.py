"""Une seule table d'extensions d'image, la même à chaque porte d'import (S29a).

Cinq copies divergeaient : le dépôt ZIP refusait ``.jp2`` et ``.webp``, l'import
distant nommait un ``.webp`` téléchargé ``.jpg``, le dossier à transcrire et le
corpus ALTO ignoraient ``.webp`` — seul Hugging Face les prenait tous. La table
vit en couche 2 (``cinoc.formats.images``) ; chaque porte la lit.
"""

from __future__ import annotations

import ast
import io
import zipfile
from pathlib import Path

import pytest

from cinoc.app import corpus_import
from cinoc.app.alto_corpus import corpus_from_alto
from cinoc.app.corpus_upload import CorpusUploadError, extract_corpus_zip
from cinoc.app.transcription import corpus_from_images
from cinoc.formats.images import IMAGE_SUFFIXES, looks_like_image

PIL = pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

#: Le format que Pillow écrit pour chaque extension acceptée.
_PILLOW = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".tif": "TIFF",
           ".tiff": "TIFF", ".jp2": "JPEG2000", ".webp": "WEBP"}


def _image(suffix: str) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (8, 6), "white").save(out, _PILLOW[suffix])
    return out.getvalue()


@pytest.mark.parametrize("suffix", IMAGE_SUFFIXES)
def test_every_accepted_suffix_is_read_by_pillow_and_recognised(suffix: str) -> None:
    """L'ensemble = ce que les moteurs qui lisent les pixels lisent ici : Pillow
    décode chaque format accepté, et sa signature est reconnue."""
    data = _image(suffix)
    assert looks_like_image(data)
    with Image.open(io.BytesIO(data)) as image:
        assert image.size == (8, 6)


def test_a_wrong_signature_is_not_an_image() -> None:
    assert not looks_like_image(b"RIFF\x00\x00\x00\x00WAVEfmt ")
    assert not looks_like_image(b"GIF89a")
    assert not looks_like_image(b"<svg/>")


@pytest.mark.parametrize("suffix", [".jp2", ".webp"])
def test_the_zip_upload_accepts_the_table(tmp_path: Path, suffix: str) -> None:
    """Rouge avant S29a : « extension non autorisée »."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"p1{suffix}", _image(suffix))
        archive.writestr("p1.gt.txt", "texte")
    corpus = extract_corpus_zip(buffer.getvalue(), tmp_path / "c", name="c")
    (document,) = corpus.documents
    assert (document.id, Path(document.image_uri or "").suffix) == ("p1", suffix)


def test_the_zip_upload_still_checks_the_signature(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("p1.webp", b"RIFF\x00\x00\x00\x00WAVEfmt ")
        archive.writestr("p1.gt.txt", "texte")
    with pytest.raises(CorpusUploadError, match="image non reconnue"):
        extract_corpus_zip(buffer.getvalue(), tmp_path / "c", name="c")


def test_a_remote_webp_keeps_its_suffix() -> None:
    """Rouge avant S29a : un ``.webp`` téléchargé était écrit en ``.jpg``."""
    assert corpus_import._image_ext("https://iiif.example/p/1.webp") == ".webp"
    assert corpus_import._image_ext("https://iiif.example/p/1") == ".jpg"


def test_the_local_folders_accept_the_table(tmp_path: Path) -> None:
    """Rouge avant S29a : ``.webp`` ignoré par le dossier à transcrire et par
    le corpus ALTO."""
    (tmp_path / "a.webp").write_bytes(_image(".webp"))
    (tmp_path / "a.xml").write_text("<alto/>", encoding="utf-8")
    assert [d.id for d in corpus_from_images(tmp_path).documents] == ["a"]
    assert [d.id for d in corpus_from_alto(tmp_path).documents] == ["a"]


def test_a_png_is_preferred_to_a_jpeg_of_the_same_name(tmp_path: Path) -> None:
    """L'ordre de la table est la préférence (un ensemble l'aurait tirée du
    hachage)."""
    for suffix in (".jpg", ".png"):
        (tmp_path / f"a{suffix}").write_bytes(_image(suffix))
    (tmp_path / "a.xml").write_text("<alto/>", encoding="utf-8")
    (document,) = corpus_from_alto(tmp_path).documents
    assert Path(document.image_uri or "").suffix == ".png"


def test_no_other_image_suffix_table() -> None:
    """Verrou : aucune autre collection littérale d'extensions d'image dans
    ``cinoc/`` (ensemble, tuple, liste). Les tables extension → type MIME d'un
    moteur répondent à une autre question (ce qu'il sait envoyer) : des
    ``dict``, hors du verrou."""
    copies = []
    for path in CINOC.rglob("*.py"):
        if "__pycache__" in path.parts or path == CINOC / "formats" / "images.py":
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
                values = {
                    e.value for e in node.elts
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
                if {".png", ".jpg"} <= values or {".png", ".tif"} <= values:
                    copies.append(f"{path.relative_to(CINOC)}:{node.lineno}")
    assert not copies, copies

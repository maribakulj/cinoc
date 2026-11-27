"""Ingestion ZIP : sécurité d'abord (traversal, bombe, quotas, dédup), puis nominal."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from cinoc.app.corpus_upload import (
    MAX_ENTRIES,
    CorpusStore,
    CorpusUploadError,
    extract_corpus_zip,
)
from cinoc.domain.artifacts import ArtifactType

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # en-tête PNG valide + remplissage


def _zip(entries: dict[str, bytes]) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, payload in entries.items():
            zf.writestr(name, payload)
    return buf


# --- Nominal -----------------------------------------------------------------


def test_pairs_image_with_ground_truth(tmp_path: Path) -> None:
    data = _zip({"folio_1.png": _PNG, "folio_1.gt.txt": b"verite", "folio_2.png": _PNG})
    spec = extract_corpus_zip(data, tmp_path / "c", name="mon-corpus")
    assert spec.name == "mon-corpus"
    by_id = {d.id: d for d in spec.documents}
    assert set(by_id) == {"folio_1", "folio_2"}
    assert by_id["folio_1"].ground_truths  # GT appariée par radical
    assert not by_id["folio_2"].ground_truths  # image sans GT → toléré
    # fichiers réellement écrits sous dest
    assert (tmp_path / "c" / "folio_1.png").exists()


def test_plain_txt_ground_truth_also_pairs(tmp_path: Path) -> None:
    spec = extract_corpus_zip(
        _zip({"a.png": _PNG, "a.txt": b"gt"}), tmp_path / "c", name="c"
    )
    assert spec.documents[0].ground_truths


# --- Sécurité ----------------------------------------------------------------


def test_path_traversal_entry_rejected(tmp_path: Path) -> None:
    data = _zip({"../escape.png": _PNG})
    with pytest.raises(CorpusUploadError, match="non sûre|non sûr"):
        extract_corpus_zip(data, tmp_path / "c", name="c")
    # rien n'a fui hors de dest
    assert not (tmp_path / "escape.png").exists()


def test_absolute_entry_rejected(tmp_path: Path) -> None:
    data = _zip({"/etc/passwd.png": _PNG})
    with pytest.raises(CorpusUploadError):
        extract_corpus_zip(data, tmp_path / "c", name="c")


def test_unsafe_name_rejected(tmp_path: Path) -> None:
    # espace/accent → id de document invalide → refus net (pas un crash Pydantic)
    with pytest.raises(CorpusUploadError, match="non sûr"):
        extract_corpus_zip(_zip({"mon image.png": _PNG}), tmp_path / "c", name="c")


def test_disallowed_extension_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="extension"):
        extract_corpus_zip(_zip({"evil.exe": b"MZ"}), tmp_path / "c", name="c")


def test_non_image_payload_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="image non reconnue"):
        extract_corpus_zip(_zip({"a.png": b"not-an-image"}), tmp_path / "c", name="c")


def test_duplicate_basename_rejected(tmp_path: Path) -> None:
    # même basename via deux chemins → dédup stricte
    data = _zip({"x/a.png": _PNG, "y/a.png": _PNG})
    with pytest.raises(CorpusUploadError, match="doublon"):
        extract_corpus_zip(data, tmp_path / "c", name="c")


def test_too_many_entries_rejected(tmp_path: Path) -> None:
    data = _zip({f"f{i}.txt": b"x" for i in range(MAX_ENTRIES + 1)})
    with pytest.raises(CorpusUploadError, match="trop d'entrées"):
        extract_corpus_zip(data, tmp_path / "c", name="c")


def test_zip_bomb_total_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # plafond total abaissé → un cumul trop gros est refusé (octets RÉELS lus).
    monkeypatch.setattr("cinoc.app.corpus_upload.MAX_TOTAL_UNCOMPRESSED", 64)
    data = _zip({"a.txt": b"x" * 50, "b.txt": b"y" * 50})
    with pytest.raises(CorpusUploadError, match="bombe|volumineuse décompressée"):
        extract_corpus_zip(data, tmp_path / "c", name="c")


def test_bad_zip_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="ZIP invalide"):
        extract_corpus_zip(io.BytesIO(b"not a zip"), tmp_path / "c", name="c")


def test_empty_archive_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="vide"):
        extract_corpus_zip(_zip({}), tmp_path / "c", name="c")


def test_no_image_rejected(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="aucune image"):
        extract_corpus_zip(_zip({"only.txt": b"gt"}), tmp_path / "c", name="c")


_JPEG = b"\xff\xd8\xff" + b"\x00" * 32


def test_stem_collision_across_extensions_is_clean_reject(tmp_path: Path) -> None:
    # a.png + a.jpg → deux DocumentRef id="a" → le domaine lèverait CorpusSpecError ;
    # ce doit être un rejet PROPRE (CorpusUploadError), jamais une 500.
    data = _zip({"a.png": _PNG, "a.jpg": _JPEG})
    with pytest.raises(CorpusUploadError, match="corpus invalide"):
        extract_corpus_zip(data, tmp_path / "c", name="c")


def test_invalid_stem_is_clean_reject(tmp_path: Path) -> None:
    # « ...png » passe le charset mais donne le radical « .. » → id invalide ;
    # traduit en CorpusUploadError, pas en CorpusSpecError nue.
    with pytest.raises(CorpusUploadError, match="corpus invalide"):
        extract_corpus_zip(_zip({"...png": _PNG}), tmp_path / "c", name="c")


# --- Store -------------------------------------------------------------------


def test_store_save_and_get(tmp_path: Path) -> None:
    store = CorpusStore(tmp_path)
    corpus_id, spec = store.save("c", _zip({"a.png": _PNG}), max_zip_bytes=2**20)
    assert store.get(corpus_id) is spec
    assert store.get("absent") is None
    assert (tmp_path / corpus_id / "a.png").exists()


# --- Vérité-terrain ALTO / PAGE (XML) ----------------------------------------

_ALTO = b"""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
 <Layout><Page WIDTH="100" HEIGHT="100" PHYSICAL_IMG_NR="1"><PrintSpace>
  <TextBlock ID="b1">
   <TextLine><String CONTENT="Beatus uir qui"/></TextLine>
   <TextLine><String CONTENT="non abiit"/></TextLine>
  </TextBlock>
 </PrintSpace></Page></Layout>
</alto>"""

_PAGE = b"""<?xml version="1.0" encoding="UTF-8"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
 <Page imageWidth="100" imageHeight="100"><TextRegion id="r1">
  <TextLine id="l1"><TextEquiv><Unicode>Gloria patri</Unicode></TextEquiv></TextLine>
 </TextRegion></Page></PcGts>"""


def test_alto_ground_truth_extracted_to_text(tmp_path: Path) -> None:
    spec = extract_corpus_zip(
        _zip({"0006.jpg": _JPEG, "0006.xml": _ALTO}), tmp_path / "c", name="c"
    )
    (doc,) = spec.documents
    (gt,) = doc.ground_truths
    assert gt.type is ArtifactType.RAW_TEXT
    assert Path(gt.uri).read_text(encoding="utf-8") == "Beatus uir qui\nnon abiit"


def test_page_ground_truth_extracted_to_text(tmp_path: Path) -> None:
    spec = extract_corpus_zip(
        _zip({"p1.png": _PNG, "p1.xml": _PAGE}), tmp_path / "c", name="c"
    )
    (doc,) = spec.documents
    (gt,) = doc.ground_truths
    assert gt.type is ArtifactType.RAW_TEXT
    assert "Gloria patri" in Path(gt.uri).read_text(encoding="utf-8")


def test_manual_txt_wins_over_xml(tmp_path: Path) -> None:
    spec = extract_corpus_zip(
        _zip({"a.png": _PNG, "a.xml": _ALTO, "a.gt.txt": b"texte manuel"}),
        tmp_path / "c",
        name="c",
    )
    (doc,) = spec.documents
    (gt,) = doc.ground_truths
    assert Path(gt.uri).read_text(encoding="utf-8") == "texte manuel"


def test_macos_appledouble_and_dir_entries_ignored(tmp_path: Path) -> None:
    # Les ZIP macOS ajoutent des sidecars AppleDouble ``._x`` et un dossier
    # ``__MACOSX/`` : ils doivent être ignorés, pas rejetés en « image non reconnue ».
    data = _zip(
        {
            "0006.png": _PNG,
            "0006.gt.txt": b"verite",
            "._0006.png": b"junk-applefile",
            "__MACOSX/._0006.png": b"junk",
        }
    )
    spec = extract_corpus_zip(data, tmp_path / "c", name="c")
    (doc,) = spec.documents
    assert doc.id == "0006"
    assert not (tmp_path / "c" / "._0006.png").exists()


def test_unreadable_xml_ground_truth_clean_reject(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="illisible|sans texte"):
        extract_corpus_zip(
            _zip({"a.png": _PNG, "a.xml": b"<alto>pas valable"}),
            tmp_path / "c",
            name="c",
        )


# --- Plafond de l'archive selon le déploiement (D-310) -----------------------


def test_the_archive_cap_is_resolved_from_public_mode() -> None:
    """Un dépôt sur un serveur exposé (mode public) garde le plafond serré d'un
    Space ; hors mode public, le plafond est celui d'une archive locale — le
    même que la CLI. Une seule règle, en couche app."""
    from cinoc.app.corpus_upload import (
        LOCAL_MAX_ZIP_BYTES,
        PUBLIC_MAX_ZIP_BYTES,
        upload_zip_limit,
    )

    assert upload_zip_limit(public_mode=True) == PUBLIC_MAX_ZIP_BYTES == 25 * 2**20
    assert upload_zip_limit(public_mode=False) == LOCAL_MAX_ZIP_BYTES
    assert LOCAL_MAX_ZIP_BYTES > PUBLIC_MAX_ZIP_BYTES


def test_an_archive_over_its_cap_is_refused_with_the_cap_named(tmp_path: Path) -> None:
    from cinoc.app.corpus_upload import ArchiveTooLargeError

    data = _zip({"a.png": _PNG})
    with pytest.raises(ArchiveTooLargeError, match="1 Mo au plus"):
        extract_corpus_zip(
            io.BytesIO(data.getvalue() + b"\x00" * 2**20), tmp_path / "c", name="c",
            max_zip_bytes=2**20,
        )
    assert not (tmp_path / "c").exists()  # refusé avant tout dézippage


def test_an_archive_is_read_from_a_file_not_from_memory(tmp_path: Path) -> None:
    """L'archive est lue **en place** (un fichier, comme celui où le serveur a
    déjà recopié le dépôt) : rien ne la recopie en mémoire d'un bloc."""
    archive = tmp_path / "c.zip"
    archive.write_bytes(_zip({"a.png": _PNG, "a.txt": b"gt"}).getvalue())
    with archive.open("rb") as source:
        spec = extract_corpus_zip(source, tmp_path / "c", name="c")
    assert spec.documents[0].ground_truths

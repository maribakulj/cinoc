"""``cinoc corpus standardize`` : la face du producteur de dataset curé (D-299).

``standardize_corpus`` (D-202) était la seule fonction publique de ``app/`` sans
commande ni route (D-257) : sa preuve de bout en bout avait tourné par un script
non committé. Une capacité sans face n'est pas dans le produit — celle-ci en
reçoit une, en ligne de commande : elle écrit sur le disque du curateur un
dossier que ``scripts/publish_dataset.py`` pousse sur HuggingFace, et que la
Bibliothèque découvre ensuite (``cinoc corpus discover``).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cinoc.interfaces.cli import main

_PAGE = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    '<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">\n'
    '  <Page imageFilename="p.jpg" imageWidth="800" imageHeight="1200">\n'
    '    <TextRegion id="r1"><Coords points="0,0 800,0 800,1200 0,1200"/>\n'
    '      <TextLine id="l1"><Coords points="0,0 800,0 800,40 0,40"/>'
    "<TextEquiv><Unicode>Hochfürstl. ſ Tafel</Unicode></TextEquiv></TextLine>\n"
    "    </TextRegion>\n"
    "  </Page>\n"
    "</PcGts>\n"
)

_CURATION = [
    "--name", "Hofdiarium (extrait)",
    "--stratum", "de/17e/kurrent",
    "--language", "de",
    "--license", "cc-by-4.0",
    "--image-rights", "Public Domain Mark",
    "--attribution", "SLUB Dresden",
]


def _brut(racine: Path) -> Path:
    from PIL import Image

    brut = racine / "brut"
    (brut / "page").mkdir(parents=True)
    (brut / "jpg").mkdir()
    (brut / "page" / "p 1.xml").write_text(_PAGE, encoding="utf-8")
    Image.new("RGB", (800, 1200), (200, 180, 160)).save(brut / "jpg" / "p 1.jpg")
    return brut


def test_standardize_writes_a_publishable_dataset(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sortie = tmp_path / "dataset"
    code = main(
        ["corpus", "standardize", str(_brut(tmp_path)), "--dest", str(sortie),
         *_CURATION, "--base-url", "https://hf.example/datasets/o/d/resolve/main"]
    )

    assert code == 0
    corpus = json.loads((sortie / "corpus.json").read_text(encoding="utf-8"))
    assert [d["id"] for d in corpus["documents"]] == ["p_1"]
    assert corpus["license"]["transcription"] == "cc-by-4.0"
    gt = (sortie / "ground_truth" / "p_1.gt.txt").read_text(encoding="utf-8")
    assert gt == "Hochfürstl. ſ Tafel"
    info = json.loads((sortie / "iiif" / "p_1" / "info.json").read_text())
    assert info["id"].startswith("https://hf.example/")
    assert "cinoc-corpus" in (sortie / "README.md").read_text(encoding="utf-8")
    dit = capsys.readouterr().out
    assert "1 page" in dit and "publish_dataset.py" in dit


def test_standardize_refuses_a_populated_destination(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    sortie = tmp_path / "dataset"
    sortie.mkdir()
    (sortie / "autre.json").write_text("{}", encoding="utf-8")

    code = main(
        ["corpus", "standardize", str(_brut(tmp_path)), "--dest", str(sortie),
         *_CURATION]
    )

    assert code == 1
    assert "n'est pas vide" in capsys.readouterr().err


def test_standardize_names_a_raw_folder_of_the_wrong_shape(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        ["corpus", "standardize", str(tmp_path), "--dest", str(tmp_path / "o"),
         *_CURATION]
    )

    assert code == 1
    assert "page/" in capsys.readouterr().err


def test_curation_metadata_is_required() -> None:
    """Licence, droits et attribution ne se devinent pas : sans eux, argparse
    refuse (un dataset publié sans licence n'est pas réutilisable)."""
    with pytest.raises(SystemExit):
        main(["corpus", "standardize", "brut", "--dest", "o", "--name", "x"])

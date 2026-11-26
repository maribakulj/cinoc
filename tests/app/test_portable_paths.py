"""Aucun chemin absolu local dans un ``RunResult`` (D-282, pilote D-281 D5).

Le ``RunResult`` du pilote citait 40 fois l'image de chaque document par son
chemin absolu, plus le dossier d'archive et le chemin de l'image dans chaque
message d'échec : publié tel quel, il disait l'arborescence de qui l'avait
produit. Les chemins y sont désormais relatifs à la racine de la spec, et le
rapport les relit contre elle.
"""

from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pytest

from cinoc.app.orchestrator import _redact
from cinoc.app.portable_paths import (
    portable_dir,
    portable_image_ref,
    relativize_message,
    resolve_image_ref,
)
from cinoc.app.report_images import build_served_hrefs, image_ref_for
from cinoc.app.resume import ResumeStore
from cinoc.interfaces.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def test_image_ref_is_written_relative_to_the_root(tmp_path: Path) -> None:
    image = tmp_path / "corpus" / "0003.png"
    assert portable_image_ref(str(image), tmp_path) == "corpus/0003.png"
    assert portable_image_ref("https://iiif.example/p1.jpg", tmp_path) == (
        "https://iiif.example/p1.jpg"
    )
    # Hors de la racine : pas de référence, plutôt qu'un absolu qui fuirait.
    assert portable_image_ref(str(tmp_path.parent / "0003.png"), tmp_path) is None
    assert portable_image_ref(None, tmp_path) is None


def test_archive_dir_outside_the_root_keeps_only_its_name(tmp_path: Path) -> None:
    assert portable_dir(str(tmp_path / "archive"), tmp_path) == "archive"
    ailleurs = tmp_path.parent / "campagnes" / "archive-bnl"
    assert portable_dir(str(ailleurs), tmp_path) == "archive-bnl"


def test_message_paths_become_relative_on_both_platforms() -> None:
    posix = relativize_message(
        "tesseract a échoué sur '/home/ana/bnl/corpus/0003.png' : timeout",
        Path("/home/ana/bnl"),
    )
    assert posix == "tesseract a échoué sur 'corpus/0003.png' : timeout"
    # Sous Windows, ``repr`` redouble les ``\`` du chemin cité.
    windows = relativize_message(
        r"tesseract a échoué sur 'C:\\Users\\ana\\bnl\\corpus\\0003.png' : timeout",
        PureWindowsPath(r"C:\Users\ana\bnl"),
    )
    assert windows == posix


def test_redact_relativizes_after_hiding_the_workspace(tmp_path: Path) -> None:
    image = tmp_path / "0003.png"
    message = _redact(
        f"échec sur {str(image)!r} (trace /tmp/cinoc-run-x/pipeline0/d.json)",
        (),
        "/tmp/cinoc-run-x",
        tmp_path,
    )
    assert message == "échec sur '0003.png' (trace <workspace>/pipeline0/d.json)"


def test_relative_ref_is_read_against_the_root_and_confined(tmp_path: Path) -> None:
    (tmp_path / "corpus").mkdir()
    assert resolve_image_ref("corpus/0003.png", tmp_path) == str(
        (tmp_path / "corpus" / "0003.png").resolve()
    )
    # Un ``RunResult`` servi peut venir d'ailleurs : ``..`` ne sort pas.
    assert resolve_image_ref("../secret.png", tmp_path) is None
    # Absolu (RunResult antérieur) et URL : rendus tels quels.
    absolu = str(tmp_path.parent / "0003.png")
    assert resolve_image_ref(absolu, tmp_path) == absolu
    assert resolve_image_ref("corpus/0003.png", None) == "corpus/0003.png"


def _example_with_images(tmp_path: Path) -> Path:
    """Copie de l'exemple livré, avec de vraies images à côté des sorties."""
    pil = pytest.importorskip("PIL.Image")
    projet = tmp_path / "projet"
    projet.mkdir()
    corpus = projet / "corpus"
    corpus.mkdir()
    for source in (EXAMPLES / "corpus").iterdir():
        (corpus / source.name).write_bytes(source.read_bytes())
        stem = source.name.split(".")[0]
        if not (corpus / f"{stem}.png").exists():
            pil.new("RGB", (40, 30), "white").save(corpus / f"{stem}.png")
    config = projet / "config.yaml"
    config.write_text(
        (EXAMPLES / "config.yaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return config


def test_cli_run_result_has_no_local_path_and_report_finds_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = _example_with_images(tmp_path)
    ailleurs = tmp_path / "ailleurs"
    ailleurs.mkdir()
    # Lancé depuis un autre dossier : les références relatives ne se lisent
    # pas contre le dossier courant, mais contre celui de la spec.
    monkeypatch.chdir(ailleurs)
    sortie = tmp_path / "r.json"
    html = tmp_path / "r.html"
    code = main(
        [
            "run", str(config), "-o", str(html), "--json", str(sortie),
            "--resume-dir", str(tmp_path / "archive"),
        ]
    )
    assert code == 0
    texte = sortie.read_text(encoding="utf-8")
    assert str(tmp_path) not in texte
    data = json.loads(texte)
    assert data["manifest"]["artifacts_dir"] == "archive"
    refs = {d["image_ref"] for d in data["documents"]}
    assert refs == {f"corpus/{d}.png" for d in (
        "folio_001", "folio_002", "folio_003", "imprime_001", "imprime_002"
    )}
    rapport = html.read_text(encoding="utf-8")
    assert str(tmp_path) not in rapport
    assert "data:image/jpeg;base64," in rapport  # vignettes retrouvées
    # Saveur servie : la route relit la référence contre la même racine.
    from cinoc.app.results import load_run_result

    result = load_run_result(sortie)
    racine = config.parent
    hrefs = build_served_hrefs(result, lambda doc: f"/i/{doc}", image_root=racine)
    assert set(hrefs) == {d["document_id"] for d in data["documents"]}
    chemin = image_ref_for(result, "folio_001", image_root=racine)
    assert chemin is not None and Path(chemin).is_file()
    assert ResumeStore(tmp_path / "archive").base_dir.is_dir()


def test_offline_rescore_reads_the_same_archive(tmp_path: Path) -> None:
    """La re-notation hors ligne ne dépend pas de la forme des références."""
    config = _example_with_images(tmp_path)
    archive = str(tmp_path / "archive")
    premier, second = tmp_path / "a.json", tmp_path / "b.json"
    assert main(["run", str(config), "-o", str(tmp_path / "a.html"),
                 "--json", str(premier), "--resume-dir", archive]) == 0
    assert main(["run", str(config), "-o", str(tmp_path / "b.html"),
                 "--json", str(second), "--resume-dir", archive, "--offline"]) == 0
    a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (premier, second))
    assert a["documents"] == b["documents"]
    assert a["pipelines"] == b["pipelines"]

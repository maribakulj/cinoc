"""Commande CLI ``hybrid`` : transcription de bout en bout (mode précalculé).

Mode ``precomputed`` (déterministe, CI-safe, sans tesseract ni PIL) : le crop est
**désactivé** (``crop=False``), le reconnaisseur lit le texte figé par ``region_id``
sur l'image page entière. Prouve la chaîne CLI → corpus → ``plan_hybrid_run`` →
orchestrateur → ALTO écrits.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cinoc.app import structure_planning
from cinoc.domain.errors import CinocError
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces.cli import main


def _scene(images: Path, regions: dict[str, str]) -> None:
    images.mkdir()
    (images / "doc1.png").write_bytes(b"\x89PNG stub")
    seg = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="r1", region_type="text"),
                    Region(id="r2", region_type="text"),
                ),
                reading_order=("r1", "r2"),
            ),
        )
    )
    (images / "doc1.layout.json").write_bytes(seg.model_dump_json().encode("utf-8"))
    (images / "doc1.eng.regions.json").write_text(
        json.dumps(regions), encoding="utf-8"
    )


def test_cli_hybrid_precomputed_end_to_end(tmp_path: Path) -> None:
    images = tmp_path / "imgs"
    _scene(images, {"r1": "hello world", "r2": "second block"})
    out = tmp_path / "alto"
    code = main(
        [
            "hybrid",
            str(images),
            "--out",
            str(out),
            "--segmenter",
            "precomputed_layout",
            "--ocr",
            "precomputed_region",
            "--source-label",
            "eng",
        ]
    )
    assert code == 0
    alto = out / "doc1.alto.xml"
    assert alto.is_file()
    # L'ALTO tokenise en mots (un ``<String CONTENT=…>`` par mot) ; le texte
    # reconnu par région survit l'assemblage.
    text = alto.read_text(encoding="utf-8")
    assert all(word in text for word in ("hello", "world", "second", "block"))


def test_cli_hybrid_empty_dir_reports_error(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    # Dossier sans image → TranscriptionError → code 1 (jamais une trace nue).
    assert main(["hybrid", str(empty), "--out", str(tmp_path / "o")]) == 1


def test_remote_segmenter_endpoint_reaches_the_planner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--segmenter remote_segmenter`` était **annoncé et inutilisable**.

    Le planificateur exige un ``endpoint`` — c'est lui qui porte le modèle de
    mise en page — et la CLI n'avait aucun drapeau pour le transmettre, alors
    que le composeur web exposait le champ. La commande échouait donc à tous les
    coups sur une option que sa propre aide propose.

    La sonde s'arrête au planificateur : ce qui est vérifié est le **passage**
    des deux valeurs, pas un appel réseau.
    """
    images = tmp_path / "imgs"
    _scene(images, {"r1": "x", "r2": "y"})
    vus: dict[str, object] = {}

    def _sonde(*args: object, **kwargs: object) -> object:
        vus.update(kwargs)
        raise CinocError("sonde : planification interrompue")

    monkeypatch.setattr(structure_planning, "plan_hybrid_run", _sonde)
    code = main(
        [
            "hybrid",
            str(images),
            "--out",
            str(tmp_path / "alto"),
            "--segmenter",
            "remote_segmenter",
            "--segmenter-endpoint",
            "https://exemple.test/detect",
            "--segmenter-token",
            "secret",
        ]
    )

    assert vus["endpoint"] == "https://exemple.test/detect"
    assert vus["token"] == "secret"
    # L'erreur du planificateur ressort proprement, jamais une trace nue.
    assert code == 1
    assert "sonde" in capsys.readouterr().err


def test_remote_segmenter_without_endpoint_says_what_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sans endpoint, l'échec doit **nommer** ce qui manque."""
    images = tmp_path / "imgs"
    _scene(images, {"r1": "x", "r2": "y"})

    code = main(
        [
            "hybrid",
            str(images),
            "--out",
            str(tmp_path / "alto"),
            "--segmenter",
            "remote_segmenter",
        ]
    )
    assert code == 1
    assert "endpoint" in capsys.readouterr().err


def test_the_flags_are_declared_on_the_hybrid_command() -> None:
    """La surface elle-même : les deux drapeaux existent et portent ces noms."""
    args = build_parser().parse_args(
        [
            "hybrid",
            "imgs",
            "--segmenter-endpoint",
            "https://x.test",
            "--segmenter-token",
            "t",
        ]
    )
    assert args.segmenter_endpoint == "https://x.test"
    assert args.segmenter_token == "t"

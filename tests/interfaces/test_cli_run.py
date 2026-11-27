"""CLI ``run`` : exécute un run décrit en YAML, de bout en bout (précalculé)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.results import load_run_result
from cinoc.interfaces.cli import main

_YAML = """
corpus:
  name: t
  documents:
    - id: doc1
      image_uri: doc1.png
      ground_truths:
        - {type: raw_text, uri: doc1.gt.txt}
pipelines:
  - name: eng
    initial_inputs: [image]
    steps:
      - id: ocr
        kind: ocr
        adapter_name: "precomputed:eng"
        input_types: [image]
        output_types: [raw_text]
adapter_kwargs:
  "precomputed:eng": {source_label: eng}
evaluation:
  views:
    - {name: text, candidate_types: [raw_text], metric_names: [cer]}
"""


def test_run_command_end_to_end(tmp_path: Path) -> None:
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    config = tmp_path / "run.yaml"
    config.write_text(_YAML, encoding="utf-8")
    output = tmp_path / "r.html"

    code = main(["run", str(config), "-o", str(output)])

    assert code == 0
    html = output.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "0.2500" in html  # CER(abcd, abxd) = 1/4
    assert "eng" in html


def test_run_command_ends_with_a_unit_tally(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-282 : le bilan est dit même quand tout va bien — son absence ne doit
    plus pouvoir se lire « rien à signaler » (le pilote sortait en 0 à 19/20)."""
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    config = tmp_path / "run.yaml"
    config.write_text(_YAML, encoding="utf-8")

    assert main(["run", str(config), "-o", str(tmp_path / "r.html")]) == 0
    assert "Bilan : 1 unité(s), aucune en échec." in capsys.readouterr().out


def test_run_command_writes_json(tmp_path: Path) -> None:
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    config = tmp_path / "run.yaml"
    config.write_text(_YAML, encoding="utf-8")
    json_out = tmp_path / "r.json"

    code = main(
        ["run", str(config), "-o", str(tmp_path / "r.html"), "--json", str(json_out)]
    )

    assert code == 0
    assert json_out.is_file()
    assert load_run_result(json_out).pipelines[0].aggregate[0].value == 0.25


def test_run_command_report_dir_writes_bundle(tmp_path: Path) -> None:
    pytest.importorskip("PIL")
    from PIL import Image

    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    Image.new("RGB", (200, 150), (210, 200, 180)).save(tmp_path / "doc1.png")
    config = tmp_path / "run.yaml"
    config.write_text(_YAML, encoding="utf-8")
    bundle = tmp_path / "out"

    code = main(["run", str(config), "--report-dir", str(bundle)])

    assert code == 0
    report = bundle / "report.html"
    assert report.is_file()
    html = report.read_text(encoding="utf-8")
    assert 'src="report-assets/' in html  # liens relatifs, pas de data-URI
    assert "data:image/jpeg" not in html
    assert list((bundle / "report-assets").glob("*.jpg"))  # dérivés réels écrits


def test_run_command_reports_errors_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # config inexistante → erreur typée → code 1 + message sur stderr (pas de trace).
    code = main(
        ["run", str(tmp_path / "absent.yaml"), "-o", str(tmp_path / "r.html")]
    )
    assert code == 1
    assert "Erreur" in capsys.readouterr().err


def test_run_command_writes_its_report_in_english_on_request(tmp_path: Path) -> None:
    """S34b, n° 13 : ``--lang en`` — le mécanisme de ``compare``, pas un autre."""
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "doc1.eng.txt").write_text("abxd", encoding="utf-8")
    config = tmp_path / "run.yaml"
    config.write_text(_YAML, encoding="utf-8")
    output = tmp_path / "r.html"
    assert main(["run", str(config), "--lang", "en", "-o", str(output)]) == 0
    html = output.read_text(encoding="utf-8")
    assert '<html lang="en">' in html and "Pipeline composition" in html

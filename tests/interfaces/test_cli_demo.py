"""CLI ``demo`` : déterminisme (golden octet-stable) + écriture du fichier."""

from __future__ import annotations

from pathlib import Path

from cinoc.interfaces.cli import demo_to_html, main


def test_demo_html_is_deterministic() -> None:
    first = demo_to_html()
    second = demo_to_html()
    assert first == second  # golden octet-stable
    assert first.startswith("<!DOCTYPE html>")
    assert "tesseract" in first
    assert "pero" in first
    assert "démonstration" in first


def test_main_demo_writes_file(tmp_path: Path) -> None:
    output = tmp_path / "rapport.html"
    code = main(["demo", "-o", str(output)])
    assert code == 0
    assert output.is_file()
    assert output.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


def test_demo_speaks_english_on_request(tmp_path: Path) -> None:
    """S34b, n° 13 : la doc est en anglais, ``compare`` avait ``--lang``,
    ``demo`` et ``run`` non — leur rapport ne sortait qu'en français."""
    output = tmp_path / "en.html"
    assert main(["demo", "--lang", "en", "-o", str(output)]) == 0
    html = output.read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert "Pipeline composition" in html and "Composition des chaînes" not in html
    assert demo_to_html() == demo_to_html(lang="fr")  # le golden ne bouge pas

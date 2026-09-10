"""Les sorties d'un ``cinoc run`` : valider sans exécuter, et garder les ALTO.

Deux manques de parité relevés par ``test_web_cli_parity`` (``D-224``) :

* le web valide une configuration avant de la lancer (``POST /api/runs/config``),
  la CLI n'avait pas d'équivalent — une spec de benchmark engage des appels
  facturés et des heures de calcul ;
* le web persiste les ``ALTO_XML`` d'un run (``/reports/{name}/alto.zip``) via un
  puits qui vit dans le ``JobRunner`` ; en CLI, un ALTO demandé par la spec était
  produit puis **détruit avec le workspace temporaire**.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from cinoc.app.demo import demo_run_spec, write_demo_corpus
from cinoc.interfaces.cli import main


def _config(tmp_path: Path) -> Path:
    """Un fichier de run valide, hors ligne (moteur ``precomputed``)."""
    racine = tmp_path / "corpus"
    racine.mkdir(parents=True, exist_ok=True)
    corpus = write_demo_corpus(racine)
    spec = demo_run_spec(corpus)
    chemin = tmp_path / "config.yaml"
    chemin.write_text(
        yaml.safe_dump(
            spec.model_dump(mode="json", exclude_defaults=True),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return chemin


def test_check_describes_the_plan(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path)
    sortie = tmp_path / "rapport.html"

    code = main(["run", str(config), "--check", "-o", str(sortie)])

    assert code == 0
    affiche = capsys.readouterr().out
    assert "Corpus" in affiche and "document(s)" in affiche
    assert "tesseract" in affiche and "pero" in affiche  # les deux candidats
    assert "cer" in affiche  # et ce qui les notera
    assert not sortie.exists(), "--check ne doit produire aucun artefact"


def test_check_refuses_an_invalid_spec(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """C'est tout l'intérêt : l'erreur arrive **avant** le premier appel payant."""
    config = tmp_path / "casse.yaml"
    config.write_text("corpus: {name: x, documents: []}\n", encoding="utf-8")

    assert main(["run", str(config), "--check"]) == 1
    assert capsys.readouterr().err.strip()


def test_alto_export_survives_the_workspace(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un run hybride produit des ALTO ; sans ``--alto-dir`` ils mouraient.

    On passe par ``cinoc hybrid`` pour fabriquer les ALTO, puis on vérifie que
    ``cinoc run`` sait les garder : c'est le **même écrivain** dans les deux cas
    (``write_alto_files``), pas une seconde implémentation.
    """
    from cinoc.app.structure_planning import plan_hybrid_run
    from cinoc.app.transcription import corpus_from_images
    from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region

    images = tmp_path / "imgs"
    images.mkdir()
    (images / "doc1.png").write_bytes(b"\x89PNG stub")
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(Region(id="r1", region_type="text"),),
                reading_order=("r1",),
            ),
        )
    )
    (images / "doc1.layout.json").write_bytes(layout.model_dump_json().encode())
    (images / "doc1.eng.regions.json").write_text('{"r1": "bonjour"}', encoding="utf-8")

    spec = plan_hybrid_run(
        corpus_from_images(images),
        "hybride",
        segmenter="precomputed_layout",
        ocr="precomputed_region",
        label="eng",
        source_label="eng",
    )(tmp_path / "ws")
    config = tmp_path / "hybride.yaml"
    config.write_text(
        yaml.safe_dump(
            spec.model_dump(mode="json", exclude_defaults=True),
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    alto = tmp_path / "alto"

    code = main(
        [
            "run",
            str(config),
            "-o",
            str(tmp_path / "r.html"),
            "--alto-dir",
            str(alto),
        ]
    )

    assert code == 0
    ecrits = sorted(alto.glob("*.alto.xml"))
    assert ecrits, "aucun ALTO gardé"
    assert "bonjour" in ecrits[0].read_text(encoding="utf-8")
    assert "ALTO écrit(s)" in capsys.readouterr().out


def test_the_two_sinks_compose(tmp_path: Path) -> None:
    """``--alto-dir`` et ``--hipe-jsonl`` doivent coexister.

    L'orchestrateur n'accepte qu'un puits : les composer était le point où une
    option aurait pu en écraser une autre en silence.
    """
    config = _config(tmp_path)
    jsonl = tmp_path / "hipe"
    code = main(
        [
            "run",
            str(config),
            "-o",
            str(tmp_path / "r.html"),
            "--hipe-jsonl",
            str(jsonl),
            "--alto-dir",
            str(tmp_path / "alto"),
        ]
    )
    assert code == 0
    # Le corpus de démo ne produit pas d'ALTO : le dossier peut rester vide,
    # mais l'export HIPE, lui, doit avoir eu lieu — aucun puits n'est perdu.
    assert list(jsonl.parent.glob("hipe*")), "l'export HIPE a été écrasé"

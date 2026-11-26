"""``cinoc run CORPUS --recipe NOM`` : la face CLI des recettes (pilote D24).

Avant : ``cinoc list recipes`` décrivait les recettes, rien ne les instanciait en
ligne de commande — la parité web ⇄ CLI déclarait « ``cinoc run`` l'exécute via
sa spec », ce qui demandait d'écrire la spec à la main. La CLI instancie
désormais une recette par **la** fonction de la page (``plan_recipe_run``), et
le rapport qui en sort est celui du web, vue pour vue.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cinoc.app.evaluation_views import EvaluationOptions
from cinoc.app.loader import RunSpecError, load_corpus_spec
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run, recipe_entries
from cinoc.app.recipes import RecipeError
from cinoc.app.results import load_run_result
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces._recipe_spec import spec_loader
from cinoc.interfaces.cli import main
from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER
from cinoc.reports.compare import compare_runs

_PAGES = (
    ("p1", "le soleil\nse lève", "le so1eil\nse lève"),
    ("p2", "la lune", "la lune"),
)
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _corpus(tmp_path: Path) -> Path:
    """Deux pages, leur GT, et la lecture que ``precomputed`` rejoue sous le
    nom de l'étape (``<doc>.ocr.txt``) ; le YAML qu'écrit ``corpus import``."""
    documents = []
    for doc, gt, lu in _PAGES:
        (tmp_path / f"{doc}.png").write_bytes(_PNG)
        (tmp_path / f"{doc}.gt.txt").write_text(gt, encoding="utf-8")
        (tmp_path / f"{doc}.ocr.txt").write_text(lu, encoding="utf-8")
        documents.append(
            f"  - id: {doc}\n    image_uri: {doc}.png\n    ground_truths:\n"
            f"    - type: raw_text\n      uri: {doc}.gt.txt\n"
        )
    chemin = tmp_path / "corpus.yaml"
    chemin.write_text("corpus:\n  name: c\n  documents:\n" + "".join(documents))
    return chemin


def _args(*argv: str) -> object:
    return build_parser().parse_args(["run", *argv])


def test_the_cli_plans_a_recipe_with_the_web_function(tmp_path: Path) -> None:
    """Aucune logique côté CLI : la spec est celle de ``plan_recipe_run`` sur le
    corpus du fichier, file et options comprises."""
    corpus = _corpus(tmp_path)
    args = _args(
        str(corpus), "--recipe", "ocr_simple", "--set", "ocr.lang=fra+deu",
        "--set", "ocr.dpi=300", "--metric-profile", "essentiel",
    )
    spec = spec_loader(args)(corpus)  # type: ignore[arg-type]
    attendu = plan_recipe_run(
        load_corpus_spec(corpus),
        (
            RecipeEntry(
                recipe="ocr_simple", params={"ocr": {"lang": "fra+deu", "dpi": 300}}
            ),
        ),
        run_id=None,
        options=EvaluationOptions(metric_profile="essentiel"),
    )
    assert spec.model_dump() == attendu.model_dump()
    assert spec.adapter_kwargs["tesseract:ocr"]["dpi"] == 300  # un entier, pas "300"


def test_a_recipe_runs_to_a_report_from_the_command_line(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    sortie = tmp_path / "r.json"
    code = main([
        "run", str(corpus), "--recipe", "ocr_simple", "--brick", "ocr=precomputed",
        "-o", str(tmp_path / "r.html"), "--json", str(sortie),
    ])
    assert code == 0
    result = load_run_result(sortie)
    assert {(p.pipeline, p.view) for p in result.pipelines} == {
        ("ocr_simple · precomputed", "texte"),
        ("ocr_simple · precomputed", "texte (lignes)"),
    }


def _attendre(client: TestClient, job_id: str) -> dict[str, object]:
    limite = time.time() + 30
    while time.time() < limite:
        corps = client.get(f"/api/runs/{job_id}").json()
        if corps["state"] in {"done", "failed", "cancelled"}:
            return dict(corps)
        time.sleep(0.02)
    raise AssertionError("job non terminé")


def test_the_cli_and_the_page_give_the_same_report(tmp_path: Path) -> None:
    """La même recette, aux mêmes options, par la page et par la CLI :
    ``cinoc compare`` apparie **toutes** les lignes, à écart nul."""
    (tmp_path / "cli").mkdir()
    corpus = _corpus(tmp_path / "cli")
    cli_json = tmp_path / "cli.json"
    assert main([
        "run", str(corpus), "--recipe", "ocr_simple", "--brick", "ocr=precomputed",
        "--char-exclude", ",", "-o", str(tmp_path / "cli.html"),
        "--json", str(cli_json),
    ]) == 0

    rapports = tmp_path / "web"
    client = TestClient(
        create_app(reports_dir=tmp_path / "vitrine", data_dir=rapports, rate_limit=1000)
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for doc, gt, lu in _PAGES:
            zf.writestr(f"{doc}.png", _PNG)
            zf.writestr(f"{doc}.gt.txt", gt)
            zf.writestr(f"{doc}.ocr.txt", lu)
    depot = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers={CSRF_HEADER: "1"},
    )
    reponse = client.post(
        "/api/runs",
        headers={CSRF_HEADER: "1"},
        json={
            "corpus_id": depot.json()["corpus_id"],
            "entries": [{"recipe": "ocr_simple", "choices": {"ocr": "precomputed"}}],
            "char_exclude": ",",
        },
    )
    assert reponse.status_code == 201, reponse.json()
    job = _attendre(client, reponse.json()["job_id"])
    assert job["state"] == "done", job.get("error")
    web = load_run_result(rapports / f"{job['report_name']}.json")
    cli = load_run_result(cli_json)
    deltas = compare_runs(cli, web)
    assert deltas
    # Le même pipeline porte le même nom par les deux entrées (D-298) : chaque
    # ligne est appariée.
    assert all(d.value_a is not None and d.value_b is not None for d in deltas)
    assert all(d.delta == 0 for d in deltas if d.delta is not None)
    assert {d.view for d in deltas} == {"texte", "texte (lignes)"}
    assert json.loads(cli_json.read_text())["pipelines"]  # un run noté


@pytest.mark.parametrize(
    ("argv", "motif"),
    [
        (("--set", "ocr.lang=fra"), "sans --recipe"),
        (("--normalization", "nfc"), "sans --recipe"),
        (("--recipe", "ocr_simple", "--set", "vlm.model=m"), "aucune recette visée"),
        (("--recipe", "ocr_simple", "--set", "ocr.lang"), "forme attendue"),
        (("--recipe", "ocr_simple", "--set", "ocrlang=fra"), "étape.réglage"),
        (("--recipe", "ocr_simple", "--brick", "2:ocr=kraken"), "hors de la file"),
        (("--recipe", "ocr_simple", "--set", "ocr.tempreature=1"), "tempreature"),
        (("--recipe", "inconnue"), "inconnue"),
    ],
)
def test_what_would_be_ignored_is_refused_by_name(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    argv: tuple[str, ...],
    motif: str,
) -> None:
    corpus = _corpus(tmp_path)
    assert main(["run", str(corpus), "--check", *argv]) == 1
    assert motif in capsys.readouterr().err


def test_a_file_that_also_describes_pipelines_is_refused(tmp_path: Path) -> None:
    corpus = _corpus(tmp_path)
    corpus.write_text(corpus.read_text() + "pipelines: []\n", encoding="utf-8")
    with pytest.raises(RunSpecError, match="pipelines"):
        load_corpus_spec(corpus)


def test_an_assignment_targets_every_recipe_or_the_nth() -> None:
    """Sans rang, le même OCR réglé pareil partout ; ``N:`` distingue deux fois
    la même recette — la file du web, en ligne de commande."""
    file = recipe_entries(
        ("ocr_simple", "ocr_simple", "vlm_seul"),
        bricks=("2:ocr=kraken", "vlm=ollama"),
        settings=("ocr.lang=fra", "3:vlm.model=qwen:3b", "ocr.dpi=300"),
    )
    assert [e.choices for e in file] == [{}, {"ocr": "kraken"}, {"vlm": "ollama"}]
    assert file[0].params == file[1].params == {"ocr": {"lang": "fra", "dpi": 300}}
    assert file[2].params == {"vlm": {"model": "qwen:3b"}}
    with pytest.raises(RecipeError, match="valeur simple"):
        recipe_entries(("ocr_simple",), settings=("ocr.lang=[a, b]",))


def test_correct_takes_the_same_scoring_options(tmp_path: Path) -> None:
    """``cinoc correct`` reçoit les options de notation de la page (parité
    avec la file de la page, D-297 ; la correction y est la recette
    ``alto_corrige`` depuis D-298)."""
    from cinoc.interfaces._recipe_spec import scoring_options

    args = build_parser().parse_args(
        ["correct", str(tmp_path), "--normalization", "nfc", "--char-exclude", ","]
    )
    assert scoring_options(args) == EvaluationOptions(
        normalization="nfc", char_exclude=","
    )


def test_an_optional_step_is_retained_from_the_command_line() -> None:
    """``--with`` : la case d'une étape facultative, en ligne de commande."""
    file = recipe_entries(
        ("ocr_simple", "segmentation_puis_lecture"), optional=("ner", "2:alto")
    )
    assert [e.optional for e in file] == [("ner",), ("ner", "alto")]
    with pytest.raises(RecipeError, match="aucune recette visée"):
        recipe_entries(("ocr_simple",), optional=("alto",))
    args = build_parser().parse_args(
        ["run", "c.yaml", "--recipe", "ocr_simple", "--with", "ner"]
    )
    assert args.with_steps == ["ner"]

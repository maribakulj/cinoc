"""Les sorties de chaque étape restent observables, et la cible se nomme (P5e 1b).

Contre-exemple reproduit sur ``examples/`` (D-261) : un pipeline
``ocr1 (precomputed:tesseract) → ocr2 (precomputed:pero)`` ne laissait noter que
pero (CER 0,0145) — l'exécuteur tenait ``by_step`` mais ne rendait que le pool,
dernier artefact **par type**, et le 0,029 de l'étape 1 n'était plus atteignable
dans le run. Ces tests rejouent l'exemple sur une **copie** (jamais
``examples/``) et verrouillent le critère de sortie : les deux étapes notées
**dans le même run**, sans réexécuter, chacune par une vue qui la nomme.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from cinoc.app import run
from cinoc.app.loader import load_run_spec
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.resume import CACHE_FORMAT, ResumeStore
from cinoc.domain.errors import CinocError
from cinoc.evaluation.result import MetricScore, RunResult
from cinoc.interfaces.cli import main
from cinoc.reports.renderer import default_report_renderer

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"

_TWO_STEPS = {
    "name": "ocr1_ocr2",
    "initial_inputs": ["image"],
    "steps": [
        {
            "id": "ocr1",
            "kind": "ocr",
            "adapter_name": "precomputed:tesseract",
            "input_types": ["image"],
            "output_types": ["raw_text"],
        },
        {
            "id": "ocr2",
            "kind": "ocr",
            "adapter_name": "precomputed:pero",
            "input_types": ["image"],
            "output_types": ["raw_text"],
            "inputs_from": {"image": "__initial__"},
        },
    ],
}


def _view(name: str, target: str | None = None) -> dict[str, object]:
    view: dict[str, object] = {
        "name": name,
        "candidate_types": ["raw_text"],
        "metric_names": ["cer"],
    }
    if target is not None:
        view["target_step"] = target
    return view


def _config(tmp_path: Path, views: list[dict[str, object]]) -> Path:
    """Copie de ``examples/`` dont le run est le pipeline à deux étapes."""
    target = tmp_path / "examples"
    shutil.copytree(EXAMPLES, target)
    config = yaml.safe_load((target / "config.yaml").read_text(encoding="utf-8"))
    config["pipelines"] = [_TWO_STEPS]
    config["evaluation"] = {"views": views}
    path = target / "two_steps.yaml"
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return path


def _images(config: Path) -> None:
    """Images factices : l'exemple n'en livre pas, et la clé de reprise hache
    les octets de l'image (``precomputed``, lui, ne les lit pas)."""
    for gt in (config.parent / "corpus").glob("*.gt.txt"):
        stem = gt.name.removesuffix(".gt.txt")
        (gt.parent / f"{stem}.png").write_bytes(stem.encode("utf-8"))


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _run(config: Path, resume_store: ResumeStore | None = None) -> RunResult:
    return run(
        load_run_spec(config),
        registry=_registry(),
        code_version="test",
        max_workers=1,
        resume_store=resume_store,
    )


def _cer(result: RunResult, view: str) -> MetricScore:
    (entry,) = [p for p in result.pipelines if p.view == view]
    return next(s for s in entry.aggregate if s.metric == "cer")


def _single_engine_cer(engine: str) -> float:
    """CER du moteur **seul**, par l'exemple livré tel quel : la référence."""
    result = run(
        load_run_spec(EXAMPLES / "config.yaml"),
        registry=_registry(),
        code_version="test",
        max_workers=1,
    )
    for entry in result.pipelines:
        if entry.pipeline == engine and entry.view == "text":
            value = next(s for s in entry.aggregate if s.metric == "cer").value
            assert value is not None
            return value
    raise AssertionError(engine)


def test_both_steps_are_scored_in_the_same_run(tmp_path: Path) -> None:
    """Le critère de sortie : deux vues, deux étapes, un seul run."""
    result = _run(
        _config(
            tmp_path,
            [_view("etape1", "ocr1"), _view("etape2", "ocr2"), _view("defaut")],
        )
    )

    tesseract = _single_engine_cer("tesseract")
    pero = _single_engine_cer("pero")
    assert tesseract == pytest.approx(0.029, abs=5e-4)
    assert pero == pytest.approx(0.0145, abs=5e-4)
    assert _cer(result, "etape1").value == pytest.approx(tesseract)
    assert _cer(result, "etape2").value == pytest.approx(pero)
    # Sans cible : l'étape la plus aval — la règle d'avant, devenue explicite.
    assert _cer(result, "defaut").value == pytest.approx(pero)
    assert _cer(result, "etape1").support == 5


def test_unknown_target_is_refused_when_the_spec_is_loaded(tmp_path: Path) -> None:
    config = _config(tmp_path, [_view("etape3", "ocr3")])

    with pytest.raises(CinocError) as excinfo:
        load_run_spec(config)

    message = str(excinfo.value)
    assert "'ocr3'" in message
    assert "'ocr1_ocr2'" in message
    assert "ocr1, ocr2" in message


def test_cli_refuses_an_unknown_target_before_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path, [_view("etape3", "ocr3")])

    code = main(["run", str(config), "-o", str(tmp_path / "r.html")])

    assert code == 1
    assert "ocr3" in capsys.readouterr().err
    assert not (tmp_path / "r.html").exists()


def test_json_names_the_target_only_when_there_is_one(tmp_path: Path) -> None:
    """Le JSON dit quelle étape une vue note ; une vue sans cible est inchangée."""
    result = _run(_config(tmp_path, [_view("etape1", "ocr1"), _view("defaut")]))

    views = {
        v["name"]: v
        for v in json.loads(result.model_dump_json())["manifest"]["view_specs"]
    }
    assert views["etape1"]["target_step"] == "ocr1"
    # Pas de ``"target_step": null`` : le JSON d'une spec sans cible est celui
    # d'avant, octet pour octet, et un lecteur v3 le relit encore.
    assert "target_step" not in views["defaut"]
    assert RunResult.model_validate_json(result.model_dump_json()) == result


@pytest.mark.parametrize(
    ("lang", "label"), [("fr", "Étape notée"), ("en", "Scored step")]
)
def test_report_says_which_step_a_view_scores(
    tmp_path: Path, lang: str, label: str
) -> None:
    result = _run(_config(tmp_path, [_view("etape1", "ocr1"), _view("defaut")]))

    html = default_report_renderer().render(result, title="t", lang=lang)

    assert label in html
    assert html.count(label) == 1  # la vue sans cible ne l'affiche pas


def test_resume_cache_keeps_every_step(tmp_path: Path) -> None:
    """Le cache de reprise garde ``by_step`` : une vue qui cible l'étape 1 se
    note encore sur un run rechargé, sans réexécution."""
    store = ResumeStore(tmp_path / "cache")
    config = _config(tmp_path, [_view("etape1", "ocr1"), _view("etape2", "ocr2")])
    _images(config)
    first = _run(config, store)

    # Les sorties précalculées disparaissent : seul le cache peut répondre.
    for moteur in ("tesseract", "pero"):
        for sortie in (tmp_path / "examples" / "corpus").glob(f"*.{moteur}.txt"):
            sortie.unlink()
    second = _run(config, store)

    assert _cer(second, "etape1").value == _cer(first, "etape1").value
    assert _cer(second, "etape2").value == _cer(first, "etape2").value
    assert [u.usage for u in second.usage] == [u.usage for u in first.usage]


def test_resume_cache_of_the_previous_format_is_re_executed(tmp_path: Path) -> None:
    """Un index d'avant (pool par type, usage agrégé) est **invalidé** : il ne
    dit pas ce que chaque étape a produit, et l'en déduire serait inventer."""
    store = ResumeStore(tmp_path / "cache")
    config = _config(tmp_path, [_view("etape1", "ocr1")])
    _images(config)
    _run(config, store)
    indexes = list((tmp_path / "cache").glob("*/index.json"))
    assert len(indexes) == 5
    for index in (tmp_path / "cache").glob("*/index.json"):
        index.write_text(json.dumps({"artifacts": {}, "usage": {}}), encoding="utf-8")

    result = _run(config, store)

    assert _cer(result, "etape1").support == 5
    for index in (tmp_path / "cache").glob("*/index.json"):
        assert json.loads(index.read_text(encoding="utf-8"))["format"] == CACHE_FORMAT


def test_check_shows_the_scored_step(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    config = _config(tmp_path, [_view("etape1", "ocr1"), _view("defaut")])

    assert main(["run", str(config), "--check"]) == 0

    sortie = capsys.readouterr().out
    assert "etape1 — cer (étape notée : ocr1)" in sortie
    assert "defaut — cer\n" in sortie

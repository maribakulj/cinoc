"""D13 (pilote D-281) : une langue Tesseract non installée est refusée avant le
premier appel — à ``cinoc run --check``, à ``cinoc run`` et au dépôt web.

``lang: grc+frm`` (absent de la machine) était déclaré « Spec valide », puis
chaque page échouait. La liste est lue une fois (``tesseract --list-langs``) ;
ici elle est injectée, la CI n'ayant pas le binaire.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from cinoc.adapters.ocr._tesseract_cli import Tessdata
from cinoc.app.models import ModelChoiceError, check_spec_languages, check_spec_models
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.cli import main

_INSTALLEES = Tessdata(directory="/td", languages=("deu", "eng", "fra", "osd"))


def _langues(monkeypatch: pytest.MonkeyPatch, listing: Tessdata | None) -> list[int]:
    """Injecte la liste ; rend le compteur d'appels de la sonde."""
    appels: list[int] = []

    def sonde(**_: object) -> Tessdata | None:
        appels.append(1)
        return listing

    monkeypatch.setattr(
        "cinoc.adapters.ocr._tesseract_cli.installed_languages", sonde
    )
    return appels


def _spec(steps: dict[str, dict[str, object]]) -> RunSpec:
    pipelines = tuple(
        PipelineSpec(
            name=f"p{i}",
            initial_inputs=(ArtifactType.IMAGE,),
            steps=(
                PipelineStep(
                    id="etape",
                    kind="ocr" if name.startswith("tesseract:") else "segmentation",
                    adapter_name=name,
                    input_types=(ArtifactType.IMAGE,),
                    output_types=(
                        (ArtifactType.RAW_TEXT,)
                        if name.startswith("tesseract:")
                        else (ArtifactType.LAYOUT,)
                    ),
                ),
            ),
        )
        for i, name in enumerate(steps)
    )
    return RunSpec(
        corpus=CorpusSpec(
            name="c", documents=(DocumentRef(id="d", image_uri="d.png"),)
        ),
        pipelines=pipelines,
        evaluation=EvaluationSpec(
            views=(
                EvaluationView(
                    name="texte",
                    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
                    metric_names=("cer",),
                ),
            )
        ),
        adapter_kwargs=steps,  # type: ignore[arg-type]
    )


def test_a_missing_language_is_refused_with_the_installed_ones(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appels = _langues(monkeypatch, _INSTALLEES)
    spec = _spec(
        {
            "tesseract:a": {"label": "a", "lang": "fra+deu"},
            "tesseract:b": {"label": "b", "lang": "grc+fra+frm"},
        }
    )
    with pytest.raises(ModelChoiceError) as refus:
        check_spec_models(spec, live=False)
    message = str(refus.value)
    assert "tesseract:b" in message and "'grc', 'frm'" in message
    assert "deu, eng, fra, osd" in message
    assert appels == [1], "la liste est lue une fois pour la spec"


def test_installed_languages_pass_and_defaults_are_checked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _langues(monkeypatch, _INSTALLEES)
    assert check_spec_languages(
        _spec({"tesseract:a": {"label": "a", "lang": "fra+deu"}})
    ) == ()
    # Sans ``lang`` : le défaut de la brique (``fra``) est vérifié aussi.
    _langues(monkeypatch, Tessdata(directory="/td", languages=("eng",)))
    with pytest.raises(ModelChoiceError, match="'fra'"):
        check_spec_languages(_spec({"tesseract:a": {"label": "a"}}))


def test_the_tesseract_segmenter_is_checked_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _langues(monkeypatch, _INSTALLEES)
    with pytest.raises(ModelChoiceError, match="tesseract_layout:s"):
        check_spec_languages(_spec({"tesseract_layout:s": {"lang": "lat"}}))


def test_without_the_binary_it_is_a_note_not_a_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _langues(monkeypatch, None)
    spec = _spec({"tesseract:a": {"label": "a", "lang": "grc"}})
    (note,) = check_spec_languages(spec)
    assert "non vérifiée" in note and "introuvable" in note


def test_a_spec_without_tesseract_does_not_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    appels = _langues(monkeypatch, _INSTALLEES)
    assert check_spec_languages(_spec({"precomputed:x": {"source_label": "x"}})) == ()
    assert appels == []


def _ecrire(tmp_path: Path, lang: str) -> Path:
    (tmp_path / "d.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    chemin = tmp_path / "spec.yaml"
    spec = _spec({"tesseract:a": {"label": "a", "lang": lang}})
    chemin.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    return chemin


def test_check_refuses_a_missing_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--check`` disait « Spec valide » de ``lang: grc+frm``."""
    _langues(monkeypatch, _INSTALLEES)
    assert main(["run", str(_ecrire(tmp_path, "grc+frm")), "--check"]) == 1
    capture = capsys.readouterr()
    assert "Spec valide" not in capture.out
    assert "'grc', 'frm'" in capture.err
    assert main(["run", str(_ecrire(tmp_path, "fra")), "--check"]) == 0
    assert "Spec valide" in capsys.readouterr().out


def test_the_web_deposit_refuses_a_missing_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cinoc.interfaces.web.app import create_app
    from cinoc.interfaces.web.security.csrf import CSRF_HEADER

    _langues(monkeypatch, _INSTALLEES)
    client = TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p1.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        zf.writestr("p1.gt.txt", "le soleil")
    corpus = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers={CSRF_HEADER: "1"},
    ).json()["corpus_id"]
    brut = _spec({"tesseract:a": {"label": "a", "lang": "grc"}}).model_dump(mode="json")
    del brut["corpus"]
    reponse = client.post(
        "/api/runs/spec",
        headers={CSRF_HEADER: "1"},
        json={"corpus_id": corpus, "spec": yaml.safe_dump(brut)},
    )
    assert reponse.status_code == 422
    assert "'grc'" in reponse.json()["detail"]

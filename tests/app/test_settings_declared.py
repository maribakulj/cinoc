"""Un réglage de spec est **lu, ou refusé** — jamais accepté puis ignoré.

Défauts reproduits ici (pilote D-281, restes de S21 / D-293), tous vécus :

* **D14** — ``tempreature: 0.5`` dans ``adapter_kwargs`` → « Spec valide » à
  ``cinoc run --check``, puis ignoré à l'exécution ; un ``prompt_name`` posé sur
  un OCR, pareil. Le run tournait sans le réglage qu'on croyait posé.
* **D15** — ``cinoc list prompts`` dit « à poser en ``prompt_name`` », mais une
  spec YAML ne le connaissait pas : il fallait recopier le prompt.
* **S21** — ``self_hosted`` (un marqueur d'économie) entrait dans l'empreinte de
  l'étape : le déclarer faisait réexécuter des inférences déjà payées ; un ``/``
  final à ``base_url`` changeait aussi l'empreinte.

Ces tests n'emploient que des surfaces qui existaient avant la déclaration des
réglages (registre, ``module_identities``, ``step_fingerprint``, la CLI, la
route de dépôt) : ils ont été vus **rouges** sur le code d'avant.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.run_manifest import module_identities
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.interfaces.cli import main
from cinoc.pipeline.fingerprint import step_fingerprint
from cinoc.prompts import load_prompt

ROOT = Path(__file__).resolve().parents[2]
_VUE = EvaluationView(
    name="texte",
    candidate_types=frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}),
    metric_names=("cer",),
)


def _registre() -> ModuleRegistry:
    registre = ModuleRegistry()
    register_default_modules(registre)
    return registre


def _spec(adapter_name: str, kwargs: dict[str, object]) -> RunSpec:
    llm = adapter_name.split(":", 1)[0] in {"openai", "ollama", "mistral", "anthropic"}
    etape = PipelineStep(
        id="etape",
        kind="vlm" if llm else "ocr",
        adapter_name=adapter_name,
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return RunSpec(
        corpus=CorpusSpec(
            name="c", documents=(DocumentRef(id="d", image_uri="d.png"),)
        ),
        pipelines=(
            PipelineSpec(
                name="p", initial_inputs=(ArtifactType.IMAGE,), steps=(etape,)
            ),
        ),
        evaluation=EvaluationSpec(views=(_VUE,)),
        adapter_kwargs={adapter_name: kwargs},  # type: ignore[dict-item]
    )


def _empreinte(adapter_name: str, kwargs: dict[str, object]) -> str:
    """L'empreinte de l'unique étape d'une spec — celle que l'archive indexe."""
    spec = _spec(adapter_name, kwargs)
    module = _registre().build(adapter_name, spec.adapter_kwargs[adapter_name])
    identite = module_identities(
        spec, {adapter_name: module}, recorded_binaries={}
    )[adapter_name]
    return step_fingerprint(spec.pipelines[0].steps[0], identite)


_VLM = {"label": "v", "model": "qwen2.5vl:3b", "role": "zero_shot"}
_LOCAL = {
    "label": "l",
    "model": "qwen2.5vl:3b",
    "role": "zero_shot",
    "base_url": "http://127.0.0.1:11434/v1",
}


# --------------------------------------------------------------------------- #
# D14 — un réglage inconnu est refusé, nommé
# --------------------------------------------------------------------------- #


def test_a_misspelled_setting_is_refused_with_its_name_and_a_suggestion() -> None:
    with pytest.raises(CinocError) as exc:
        _registre().build("ollama:v", {**_VLM, "tempreature": 0.5})
    message = str(exc.value)
    assert "tempreature" in message
    assert "temperature" in message.replace("tempreature", "")


def test_a_prompt_name_on_an_ocr_is_refused() -> None:
    """« ``prompt_name`` mal placé » (D14) : Tesseract n'a pas de prompt."""
    with pytest.raises(CinocError, match="prompt_name"):
        _registre().build(
            "tesseract:t", {"label": "t", "prompt_name": "correction_imprime_ancien"}
        )


def _ecrire_spec(tmp_path: Path, kwargs: dict[str, object]) -> Path:
    (tmp_path / "d.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    spec = _spec("ollama:v", kwargs)
    chemin = tmp_path / "spec.yaml"
    chemin.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    return chemin


def test_check_refuses_an_unknown_setting(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--check`` disait « Spec valide » d'une spec qui portait ``tempreature``."""
    monkeypatch.setattr(
        "cinoc.app.models.check_spec_models", lambda spec, *, live: ()
    )
    config = _ecrire_spec(tmp_path, {**_VLM, "tempreature": 0.5})

    assert main(["run", str(config), "--check"]) == 1
    capture = capsys.readouterr()
    assert "Spec valide" not in capture.out
    assert "tempreature" in capture.err


def test_check_refuses_settings_for_a_brick_no_step_uses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Des réglages sous ``ollama:qwen`` pour une étape ``ollama:v`` : personne
    ne les lit, de la même façon qu'un réglage mal orthographié."""
    monkeypatch.setattr(
        "cinoc.app.models.check_spec_models", lambda spec, *, live: ()
    )
    config = _ecrire_spec(tmp_path, _VLM)
    brut = yaml.safe_load(config.read_text(encoding="utf-8"))
    brut["adapter_kwargs"]["ollama:qwen"] = {"label": "qwen", "model": "m"}
    config.write_text(yaml.safe_dump(brut, allow_unicode=True), encoding="utf-8")

    assert main(["run", str(config), "--check"]) == 1
    assert "ollama:qwen" in capsys.readouterr().err


def _client_web(tmp_path: Path) -> tuple[TestClient, str]:
    from cinoc.interfaces.web.app import create_app
    from cinoc.interfaces.web.security.csrf import CSRF_HEADER

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
    return client, corpus


def test_a_submitted_spec_with_an_unknown_setting_is_refused(tmp_path: Path) -> None:
    """Le dépôt de spec web applique la même règle que ``--check`` (422)."""
    from cinoc.interfaces.web.security.csrf import CSRF_HEADER

    client, corpus = _client_web(tmp_path)
    spec = _spec("precomputed:ocr", {"source_label": "ocr", "sourcelabel": "x"})
    brut = spec.model_dump(mode="json")
    del brut["corpus"]
    reponse = client.post(
        "/api/runs/spec",
        headers={CSRF_HEADER: "1"},
        json={"corpus_id": corpus, "spec": yaml.safe_dump(brut)},
    )
    assert reponse.status_code == 422
    assert "sourcelabel" in reponse.json()["detail"]


# --------------------------------------------------------------------------- #
# D15 — prompt_name dans une spec YAML
# --------------------------------------------------------------------------- #


def test_a_curated_prompt_is_usable_from_a_yaml_spec() -> None:
    """Le prompt curé atteint l'adapter : c'est **son texte** qui est appliqué
    — et écrit au manifeste —, pas le prompt par défaut du mode."""
    nom = "correction_press_19c_european"
    module = _registre().build(
        "ollama:c",
        {"label": "c", "model": "m", "role": "text_only", "prompt_name": nom},
    )
    reglages = module.effective_settings()  # type: ignore[attr-defined]
    assert reglages["prompt"] == load_prompt(nom)


def test_a_curated_prompt_and_a_free_prompt_exclude_each_other() -> None:
    with pytest.raises(CinocError, match="pas les deux"):
        _registre().build(
            "ollama:c",
            {
                "label": "c",
                "model": "m",
                "prompt": "libre {ocr_text}",
                "prompt_name": "correction_press_19c_european",
            },
        )


def test_an_unknown_curated_prompt_is_refused_with_the_command_that_lists_them() -> (
    None
):
    with pytest.raises(CinocError, match="cinoc list prompts"):
        _registre().build(
            "ollama:c", {"label": "c", "model": "m", "prompt_name": "inexistant"}
        )


def test_naming_a_curated_prompt_or_copying_it_is_the_same_unit() -> None:
    """Le nom n'est qu'une façon d'écrire le prompt : l'archive d'une spec qui
    le recopiait (le pilote) sert telle quelle à celle qui le nomme."""
    nom = "correction_press_19c_european"
    base = {"label": "c", "model": "m", "role": "text_only"}
    assert _empreinte("ollama:c", {**base, "prompt_name": nom}) == _empreinte(
        "ollama:c", {**base, "prompt": load_prompt(nom)}
    )


# --------------------------------------------------------------------------- #
# Restes de S21 — l'empreinte ne bouge que si la sortie peut bouger
# --------------------------------------------------------------------------- #


def test_declaring_self_hosted_does_not_rerun_the_inference() -> None:
    assert _empreinte("openai:l", {**_LOCAL, "self_hosted": True}) == _empreinte(
        "openai:l", _LOCAL
    )


def test_a_trailing_slash_on_base_url_is_the_same_server() -> None:
    assert _empreinte(
        "openai:l", {**_LOCAL, "base_url": "http://127.0.0.1:11434/v1/"}
    ) == _empreinte("openai:l", _LOCAL)


def test_a_trailing_slash_on_openais_own_endpoint_keeps_its_price() -> None:
    """``…/v1/`` est l'endpoint d'OpenAI : son tarif s'applique, et
    ``self_hosted`` y reste refusé (ce n'est pas un serveur qu'on opère)."""
    module = _registre().build(
        "openai:o",
        {"label": "o", "model": "m", "base_url": "https://api.openai.com/v1/"},
    )
    assert module.effective_settings()["base_url"] == (  # type: ignore[attr-defined]
        "https://api.openai.com/v1"
    )


def test_raising_a_time_limit_does_not_rerun_the_pages_already_read() -> None:
    """Relever ``timeout`` pour sauver une page lente ne change aucune sortie."""
    assert _empreinte("tesseract:t", {"label": "t", "timeout": 600}) == _empreinte(
        "tesseract:t", {"label": "t"}
    )


def test_the_target_still_changes_the_unit() -> None:
    """Le contre-test : un **autre** serveur reste une autre unité (D-279)."""
    assert _empreinte(
        "openai:l", {**_LOCAL, "base_url": "http://127.0.0.1:8000/v1"}
    ) != _empreinte("openai:l", _LOCAL)


def test_self_hosted_still_reaches_the_manifest_for_the_economics(
    tmp_path: Path,
) -> None:
    """Hors de l'empreinte, mais **au manifeste** : c'est là que l'économie lit
    « auto-hébergé »."""
    from cinoc.app.run_manifest import build_manifest
    from cinoc.domain.run import utcnow

    spec = _spec("openai:l", {**_LOCAL, "self_hosted": True})
    module = _registre().build("openai:l", spec.adapter_kwargs["openai:l"])
    identites = module_identities(spec, {"openai:l": module}, recorded_binaries={})
    manifeste = build_manifest(
        spec, identites, "test", utcnow(), utcnow(), served={}
    )
    assert manifeste.adapter_kwargs["openai:l"]["self_hosted"] is True
    assert manifeste.adapter_kwargs["openai:l"]["base_url"] == (
        "http://127.0.0.1:11434/v1"
    )


# --------------------------------------------------------------------------- #
# Ce qui ne bouge pas : les archives existantes sans réglage d'exploitation
# --------------------------------------------------------------------------- #

#: Empreintes calculées **avant** la déclaration des réglages (S22), sans
#: binaire système : le pilote et l'exemple livré n'en posent aucun, leurs
#: archives restent valides.
_EMPREINTES_AVANT = {
    ("pilote.yaml", "tesseract_fra_deu", "ocr"): (
        "d2ebbdab58076503ef9230243fa198871b48ad9d5a9466f731ca704cc6728191"
    ),
    ("pilote.yaml", "tesseract_fraktur_fra", "ocr"): (
        "da56b5f84afc82e31e3e9c9b62990dbd67051bf8da6fff1cc812e273660b0fd6"
    ),
    ("pilote.yaml", "qwen25vl_3b_zero_shot", "vlm"): (
        "127ed62378f3170561059eafd8196e2c42d2382d8e877bc6ef00ce6d94d7e8f8"
    ),
    ("pilote.yaml", "tesseract_fraktur_fra_qwen_corr", "corr"): (
        "92071f9f23e58f773419eab510c83e1ce268ba0f271be0a608bf586b0ba588e7"
    ),
    ("config.yaml", "tesseract", "ocr"): (
        "05cb7fbf3a4861126487c456e25396a2bb976fd216067a3435fcc08aae7e5f4c"
    ),
    ("config.yaml", "pero", "ocr"): (
        "2877b7cc3ff6bdf4e8c664c81466dc37014443489ca980e13962cca92d110be3"
    ),
}


@pytest.mark.parametrize(
    "chemin",
    [
        ROOT / "campaigns" / "2026-11-26-pilote-local" / "pilote.yaml",
        ROOT / "examples" / "config.yaml",
    ],
    ids=["pilote", "exemple"],
)
def test_existing_archives_keep_their_fingerprints(chemin: Path) -> None:
    spec = RunSpec.model_validate(yaml.safe_load(chemin.read_text(encoding="utf-8")))
    registre = _registre()
    noms = sorted({s.adapter_name for p in spec.pipelines for s in p.steps})
    modules = {n: registre.build(n, spec.adapter_kwargs.get(n, {})) for n in noms}
    identites = module_identities(spec, modules, recorded_binaries={})
    for pipeline in spec.pipelines:
        for etape in pipeline.steps:
            attendue = _EMPREINTES_AVANT.get((chemin.name, pipeline.name, etape.id))
            if attendue is not None:
                assert (
                    step_fingerprint(etape, identites[etape.adapter_name]) == attendue
                ), (pipeline.name, etape.id)

"""La raison d'arrêt d'un LLM/VLM est lue, et une page coupée se voit (P5e 2).

Défaut d'audit (D-260) : les quatre adaptateurs ignoraient ``finish_reason``
(OpenAI, Mistral), ``stop_reason`` (Anthropic) et ``done_reason`` (Ollama). Une
page coupée au plafond de jetons était notée **comme complète** : son CER
mesurait la coupure, et rien ne le disait.

Les réponses viennent des cassettes ``tests/fixtures/cassettes/llm/`` — le corps
de l'API tel qu'il arrive sur le fil, validé contre le modèle de réponse du SDK
(voir la note de chaque cassette). Les conversions lisent ce **corps** (le dump du
modèle du SDK, celui que garde le sidecar ``NATIVE_JSON``, D-278) ; pour Ollama
(httpx direct), le dict est rendu tel quel par un faux client. Aucun réseau,
aucune clé.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.llm._base import LLMCompletion
from cinoc.adapters.llm.anthropic import _completion_from_message
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.ollama import _completion_from_chat as ollama_completion
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.evaluation.result import RunResult
from cinoc.reports.csv_export import run_result_csv
from cinoc.reports.renderer import default_report_renderer
from tests.adapters._native_fakes import OllamaStream

_CASSETTES = Path(__file__).resolve().parents[2] / "fixtures" / "cassettes" / "llm"


def _wire(provider: str, scenario: str) -> dict[str, Any]:
    data = json.loads((_CASSETTES / f"{provider}.json").read_text(encoding="utf-8"))
    response: dict[str, Any] = data["responses"][scenario]
    return response


# --------------------------------------------------------------------------- #
# Fonctions pures : réponse native → raison d'arrêt normalisée
# --------------------------------------------------------------------------- #

_CASES: list[tuple[str, str, Callable[[Any], LLMCompletion], str]] = [
    ("openai", "stop", openai_completion, "stop"),
    ("openai", "length", openai_completion, "length"),
    ("openai", "content_filter", openai_completion, "refusal"),
    ("mistral", "stop", mistral_completion, "stop"),
    ("mistral", "length", mistral_completion, "length"),
    ("mistral", "model_length", mistral_completion, "length"),
    ("mistral", "error", mistral_completion, "error"),
    ("anthropic", "end_turn", _completion_from_message, "stop"),
    ("anthropic", "max_tokens", _completion_from_message, "length"),
    ("anthropic", "model_context_window_exceeded", _completion_from_message, "length"),
    ("anthropic", "refusal", _completion_from_message, "refusal"),
]


@pytest.mark.parametrize(("provider", "scenario", "convert", "expected"), _CASES)
def test_the_native_stop_reason_is_normalised(
    provider: str,
    scenario: str,
    convert: Callable[[Any], LLMCompletion],
    expected: str,
) -> None:
    completion = convert(_wire(provider, scenario))
    assert completion.stop_reason == expected


@pytest.mark.parametrize(
    ("scenario", "expected"), [("stop", "stop"), ("length", "length")]
)
def test_ollama_done_reason_is_normalised(scenario: str, expected: str) -> None:
    completion = ollama_completion(_wire("ollama", scenario), "qwen2.5vl:3b")
    assert completion.stop_reason == expected
    assert (completion.tokens_in, completion.tokens_out) == (
        1530,
        32 if expected == "length" else 12,
    )


def test_a_cut_response_keeps_its_text_and_tokens() -> None:
    """Coupée n'est pas vide : le texte reçu et les jetons payés restent."""
    completion = openai_completion(_wire("openai", "length"))
    assert completion.text.endswith("emportant")
    assert (completion.tokens_in, completion.tokens_out) == (812, 32)


@pytest.mark.parametrize(
    ("convert", "response"),
    [
        (
            openai_completion,
            {
                "usage": None,
                "choices": [
                    {"message": {"content": "x"}, "finish_reason": "tool_calls"}
                ],
            },
        ),
        (
            _completion_from_message,
            {"usage": None, "content": [], "stop_reason": "pause_turn"},
        ),
        (
            mistral_completion,
            {
                "usage": None,
                "choices": [{"message": {"content": "x"}, "finish_reason": None}],
            },
        ),
    ],
)
def test_an_unexpected_or_missing_stop_reason_is_unknown(
    convert: Callable[[Any], LLMCompletion], response: Any
) -> None:
    """Une valeur hors table n'est ni « complète » ni « coupée » : inconnue."""
    assert convert(response).stop_reason == "unknown"


def test_ollama_without_done_reason_is_unknown() -> None:
    data = {"message": {"content": "x"}, "done": True}
    assert ollama_completion(data, "m").stop_reason == "unknown"


# --------------------------------------------------------------------------- #
# De bout en bout : cassette → plan → exécution → RunResult → rapport
# --------------------------------------------------------------------------- #

#: (fournisseur, scénario « coupé », scénario « refusé » ou None).
_PROVIDERS = [
    ("openai", "length", "content_filter"),
    ("anthropic", "max_tokens", "refusal"),
    ("mistral", "length", "error"),
    ("ollama", "length", None),
]


def _mock_provider(
    monkeypatch: pytest.MonkeyPatch, provider: str, scenario: str
) -> None:
    if provider == "ollama":
        reponse = _wire("ollama", scenario)

        class _Reponse:
            def raise_for_status(self) -> None: ...

            def json(self) -> dict[str, Any]:
                return reponse

        class _Client:
            def __init__(self, **_: Any) -> None: ...

            def close(self) -> None: ...

            def post(self, url: str, json: dict[str, Any]) -> _Reponse:  # noqa: A002
                return _Reponse()

            def stream(
                self, method: str, url: str, json: dict[str, Any], **_: Any  # noqa: A002
            ) -> OllamaStream:
                return OllamaStream(self.post(url, json))

            # Sonde du digest (``system_binaries`` → ``/api/tags``) : aucun
            # modèle listé, la sonde rend ``{}``.
            def __enter__(self) -> _Client:
                return self

            def __exit__(self, *_: object) -> None: ...

            def get(self, url: str) -> _Tags:
                return _Tags()

        class _Tags:
            def raise_for_status(self) -> None: ...

            def json(self) -> dict[str, Any]:
                return {"models": []}

        import httpx

        monkeypatch.setattr(httpx, "Client", _Client)
        return
    convert = {
        "openai": openai_completion,
        "anthropic": _completion_from_message,
        "mistral": mistral_completion,
    }[provider]
    completion = convert(_wire(provider, scenario))
    monkeypatch.setattr(
        f"cinoc.adapters.llm.{provider}._invoke_{provider}_vision",
        lambda **_: completion,
    )


def _zero_shot_run(tmp_path: Path, provider: str) -> RunResult:
    image = tmp_path / "folio.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    gt = tmp_path / "folio.gt.txt"
    # La page entière ; la cassette « coupée » s'arrête avant « deux maisons ».
    gt.write_text(
        "Le Petit Journal, 12 mars 1894. — On annonce de Boulogne-sur-Mer "
        "qu'une partie de la falaise s'est effondrée hier soir, emportant "
        "deux maisons.",
        encoding="utf-8",
    )
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="folio",
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    spec = plan_recipe_run(
        corpus,
        (
            RecipeEntry(
                recipe="vlm_seul",
                choices={"vlm": provider},
                params={"vlm": {"model": "m"}},
            ),
        ),
        run_id="s7",
    )
    registry = ModuleRegistry()
    register_default_modules(registry)
    return run(spec, registry=registry, code_version="1.0", max_workers=1)


@pytest.mark.parametrize(("provider", "cut", "_refused"), _PROVIDERS)
def test_max_tokens_reached_marks_the_unit_truncated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    cut: str,
    _refused: str | None,
) -> None:
    """La cassette « plafond atteint » donne une unité ``truncated`` : non notée
    par défaut (R6, ``CONTRATS.md`` § 2.1 e), avec sa couverture ; notée sur sa
    sortie réelle par la qualité opérationnelle."""
    _mock_provider(monkeypatch, provider, cut)
    result = _zero_shot_run(tmp_path, provider)

    (unit,) = result.usage
    assert unit.outcome == "truncated"
    assert unit.reason is None
    assert "max_tokens=8192" in (unit.message or "")
    # R6 : la fin manquante n'est pas imputée en silence — 0 noté sur 1 attendu,
    # la couverture dit pourquoi ; la qualité opérationnelle, elle, note la
    # sortie réelle (la coupure compte dans le CER).
    (pipeline,) = result.pipelines
    (cer,) = (s for s in pipeline.aggregate if s.metric == "cer")
    assert cer.value is None
    assert (cer.support, cer.expected) == (0, 1)
    assert cer.coverage == {"truncated_output": 1}
    (operational,) = (
        s for s in pipeline.operational_aggregate if s.metric == "cer"
    )
    assert operational.value == pytest.approx(14 / 143)  # « deux maisons. » manque


@pytest.mark.parametrize(
    ("provider", "_cut", "refused"), [p for p in _PROVIDERS if p[2]]
)
def test_a_refusal_or_an_error_fails_the_unit_as_engine(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
    _cut: str,
    refused: str,
) -> None:
    _mock_provider(monkeypatch, provider, refused)
    result = _zero_shot_run(tmp_path, provider)

    (unit,) = result.usage
    assert (unit.outcome, unit.reason) == ("failed", "engine")
    (cer,) = (s for s in result.pipelines[0].aggregate if s.metric == "cer")
    assert (cer.value, cer.support, cer.expected) == (None, 0, 1)


def test_the_report_and_the_csv_show_the_truncation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_provider(monkeypatch, "openai", "length")
    result = _zero_shot_run(tmp_path, "openai")
    renderer = default_report_renderer()

    fr = renderer.render(result, lang="fr")
    en = renderer.render(result, lang="en")
    # R6 : par défaut, une unité tronquée n'est pas notée — le rapport le dit.
    assert "Unités tronquées" in fr and "non notées par défaut" in fr
    assert "Truncated units" in en and "not scored by default" in en
    assert ",truncated" in run_result_csv(result)
    assert json.loads(result.model_dump_json())["usage"][0]["outcome"] == "truncated"


def test_the_composition_shows_the_effective_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Les réglages effectifs du manifeste se lisent dans la composition ; un
    réglage non transmis s'écrit « — », pas ``None``."""
    _mock_provider(monkeypatch, "anthropic", "end_turn")
    html = default_report_renderer().render(_zero_shot_run(tmp_path, "anthropic"))
    assert "max_tokens=8192" in html
    assert "temperature=—" in html and "temperature=None" not in html

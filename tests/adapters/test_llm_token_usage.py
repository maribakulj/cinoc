"""Étape 2d — les adapters cloud remontent bien ``tokens_in/out`` (économie).

On teste la **cartographie usage→jetons** de chaque fournisseur sur le **corps**
d'une réponse (le dict que le sidecar ``NATIVE_JSON`` garde et que les
conversions lisent), sans réseau ni clé. Chaque API nomme ses compteurs
différemment — c'est précisément ce qu'on vérifie.
"""

from __future__ import annotations

from typing import Any

from cinoc.adapters.llm.anthropic import _completion_from_message
from cinoc.adapters.llm.mistral import _completion_from_chat as mistral_completion
from cinoc.adapters.llm.openai import _completion_from_chat as openai_completion


def _chat_response(text: str, prompt_tokens: int, completion_tokens: int) -> Any:
    """Corps de la forme ``chat.completions`` (OpenAI / Mistral)."""
    return {
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
        },
        "choices": [{"message": {"content": text}}],
    }


def test_openai_maps_usage_to_tokens() -> None:
    out = openai_completion(_chat_response("corrigé", 12, 5))
    assert out.text == "corrigé"
    assert out.tokens_in == 12
    assert out.tokens_out == 5


def test_mistral_maps_usage_to_tokens() -> None:
    out = mistral_completion(_chat_response("corrigé", 31, 7))
    assert out.text == "corrigé"
    assert out.tokens_in == 31
    assert out.tokens_out == 7


def test_anthropic_maps_input_output_tokens() -> None:
    # Claude : noms propres (input_tokens/output_tokens) + content en blocs.
    response = {
        "usage": {"input_tokens": 20, "output_tokens": 9},
        "content": [
            {"type": "text", "text": "trans"},
            {"type": "text", "text": "crit"},
        ],
    }
    out = _completion_from_message(response)
    assert out.text == "transcrit"
    assert out.tokens_in == 20
    assert out.tokens_out == 9


def test_usage_absent_yields_none_not_crash() -> None:
    # Réponse sans bloc usage : jetons None (jamais 0 inventé), texte conservé.
    no_usage = {"usage": None, "choices": [{"message": {"content": "x"}}]}
    out = openai_completion(no_usage)
    assert out.text == "x"
    assert out.tokens_in is None
    assert out.tokens_out is None


def test_empty_choices_keeps_tokens() -> None:
    # Pas de choix → texte vide, mais les jetons (facturés) restent remontés.
    empty = {"usage": {"prompt_tokens": 4, "completion_tokens": 0}, "choices": []}
    out = openai_completion(empty)
    assert out.text == ""
    assert out.tokens_in == 4
    assert out.tokens_out == 0


def test_the_completion_keeps_the_body_it_was_read_from() -> None:
    """La complétion porte le corps lu (``native``) : c'est lui que le sidecar
    écrit, et le relire rend la même complétion."""
    body = _chat_response("corrigé", 12, 5)
    out = openai_completion(body)
    assert out.native is body
    assert openai_completion(out.native) == out

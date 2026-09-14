"""Les deux fournisseurs Mistral de ``saknussemm`` — texte et vision.

``saknussemm`` livrait une chaîne vision complète (``VisionEditProducer``,
gardes desserrées, découpe par ligne) que ce dépôt ne pouvait pas atteindre :
tous ses clients n'implémentaient que ``complete_structured``. Ces deux-ci
ferment le trou. Ce qui est vérifié ici est le **contrat**, pas la qualité d'un
modèle :

* la requête posée à l'API, dont le **repli** ``json_object`` — ``json_schema``
  n'est pas honoré par tout le catalogue, et sans repli un modèle par ailleurs
  capable échoue sur la forme de la requête, pas sur la tâche ;
* la traduction des échecs vers la liste blanche de recouvrabilité de
  ``saknussemm``. Hors liste, l'exception **fait échouer** le run au lieu d'être
  réessayée : confondre les deux, c'est soit abandonner sur un incident
  passager, soit réessayer en boucle une requête fautive ;
* le **plafond de huit images**, mesuré contre l'API (400/3051) et non lu dans
  une doc. Le franchir n'est pas une erreur de l'utilisateur mais un moteur mal
  renseigné : le message le dit.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
from typing import Any

import httpx
import pytest

from cinoc.adapters.correction.mistral_multimodal import (
    MAX_IMAGES_PER_CALL,
    MistralMultimodalClient,
)
from cinoc.adapters.correction.mistral_structured import (
    MistralStructuredClient,
    parse_chat_json,
    usage_from,
)

#: Les classes d'erreur attendues appartiennent au contrat de ``saknussemm`` :
#: sans la bibliothèque, il n'y a pas de contrat à vérifier.
_needs_saknussemm = pytest.mark.skipif(
    importlib.util.find_spec("saknussemm") is None,
    reason="saknussemm absent — les classes d'erreur du contrat viennent de là.",
)

_SCHEMA = {"type": "object", "properties": {"lines": {"type": "array"}}}


def _chat(
    content: str, usage: dict[str, int] | None = None, response_id: str | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"choices": [{"message": {"content": content}}]}
    if usage is not None:
        body["usage"] = usage
    if response_id is not None:
        body["id"] = response_id
    return body


class _Part:
    """Une découpe, dans la forme que ``VisionEditProducer`` passe au client."""

    def __init__(self, line_id: str, data: bytes = b"\x89PNG") -> None:
        self.line_id = line_id
        self.media_type = "image/png"
        self.data = data
        self.sha256 = "0" * 64


def _fake_client(
    *,
    payloads: list[Any] | None = None,
    statuses: list[int] | None = None,
    raises: Exception | None = None,
    calls: list[dict[str, Any]] | None = None,
) -> type:
    """Faux ``httpx.AsyncClient`` : capture chaque requête, rend les réponses
    dans l'ordre (une par POST — c'est ce qui rend le repli observable)."""

    class _Fake:
        def __init__(self, **kwargs: Any) -> None:
            self._n = 0

        async def __aenter__(self) -> _Fake:
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def post(
            self, url: str, json: Any = None, headers: Any = None
        ) -> httpx.Response:
            if calls is not None:
                calls.append({"url": url, "body": json, "headers": headers})
            if raises is not None:
                raise raises
            index = self._n
            self._n += 1
            status = (statuses or [200])[min(index, len(statuses or [200]) - 1)]
            payload = (payloads or [_chat('{"lines": []}')])[
                min(index, len(payloads or [None]) - 1)
            ]
            return httpx.Response(
                status, json=payload, request=httpx.Request("POST", url)
            )

    return _Fake


def _run_text(monkeypatch: pytest.MonkeyPatch, fake: type, **kw: Any) -> Any:
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return asyncio.run(
        MistralStructuredClient().complete_structured(
            kw.pop("api_key", "k"),
            kw.pop("model", "mistral-small-latest"),
            kw.pop("system_prompt", "corrige"),
            kw.pop("user_payload", {"lines": ["le ſoleil"]}),
            kw.pop("json_schema", _SCHEMA),
            **kw,
        )
    )


def _run_vision(monkeypatch: pytest.MonkeyPatch, fake: type, images: list[Any]) -> Any:
    monkeypatch.setattr(httpx, "AsyncClient", fake)
    return asyncio.run(
        MistralMultimodalClient().complete_structured_multimodal(
            api_key="k",
            model="mistral-medium-latest",
            system_prompt="regarde",
            user_payload={"lines": ["le ſoleil"]},
            images=images,
            json_schema=_SCHEMA,
        )
    )


# --------------------------------------------------------------------------- #
# La requête posée à l'API
# --------------------------------------------------------------------------- #


@_needs_saknussemm
def test_the_request_carries_the_schema_and_the_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, Any]] = []
    _run_text(monkeypatch, _fake_client(calls=calls))
    assert len(calls) == 1, "un schéma accepté ne doit pas coûter deux appels."
    body = calls[0]["body"]
    assert body["response_format"] == {"type": "json_schema", "json_schema": _SCHEMA}
    assert body["messages"][0] == {"role": "system", "content": "corrige"}
    assert json.loads(body["messages"][1]["content"]) == {"lines": ["le ſoleil"]}
    assert calls[0]["headers"]["Authorization"] == "Bearer k"


@_needs_saknussemm
def test_a_400_falls_back_to_plain_json_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Le repli est ce qui distingue « ce modèle refuse le schéma strict » de
    « ce modèle ne sait pas faire » — sans lui, les deux se ressemblent."""
    calls: list[dict[str, Any]] = []
    payload, _ = _run_text(
        monkeypatch,
        _fake_client(
            statuses=[400, 200],
            payloads=[{"error": "no schema"}, _chat('{"lines": ["ok"]}')],
            calls=calls,
        ),
    )
    assert len(calls) == 2
    assert calls[1]["body"]["response_format"] == {"type": "json_object"}
    assert payload == {"lines": ["ok"]}


@_needs_saknussemm
def test_a_400_on_the_fallback_too_is_permanent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deux refus de suite : la requête est fautive, la réessayer la referait
    échouer. C'est exactement ce que la liste blanche appelle permanent."""
    from saknussemm.core.protocols import ProviderPermanentError

    with pytest.raises(ProviderPermanentError):
        _run_text(
            monkeypatch,
            _fake_client(statuses=[400, 400], payloads=[{"e": 1}, {"e": 2}]),
        )


# --------------------------------------------------------------------------- #
# La traduction des échecs — la liste blanche de recouvrabilité
# --------------------------------------------------------------------------- #


@_needs_saknussemm
@pytest.mark.parametrize(
    ("status", "recoverable"),
    [
        (401, False),  # clé invalide : réessayer ne la rendra pas valide
        (422, False),  # corps refusé
        (429, True),  # débit dépassé : attendre suffit
        (500, True),  # panne côté fournisseur
        (503, True),
    ],
)
def test_http_failures_map_to_the_right_recoverability(
    monkeypatch: pytest.MonkeyPatch, status: int, recoverable: bool
) -> None:
    from saknussemm.core.protocols import (
        ProviderPermanentError,
        ProviderTransientError,
    )

    attendu = ProviderTransientError if recoverable else ProviderPermanentError
    autre = ProviderPermanentError if recoverable else ProviderTransientError
    with pytest.raises(attendu):
        _run_text(monkeypatch, _fake_client(statuses=[status], payloads=[{"e": 1}]))
    # Le pendant : la mauvaise classe ne doit pas passer non plus. Sans lui, un
    # test qui attrape une classe **parente** passerait pour les deux.
    assert not issubclass(attendu, autre)


@_needs_saknussemm
def test_a_transport_failure_is_transient(monkeypatch: pytest.MonkeyPatch) -> None:
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError):
        _run_text(
            monkeypatch, _fake_client(raises=httpx.ConnectError("réseau coupé"))
        )


@_needs_saknussemm
def test_a_reply_that_is_not_json_is_transient(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une réponse tronquée ressemble à une hallucination ; c'est un incident
    de génération, donc réessayable — pas une requête fautive."""
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError):
        _run_text(monkeypatch, _fake_client(payloads=[_chat('{"lines": [')]))


@_needs_saknussemm
def test_a_json_array_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """``[]`` est du JSON valide et pas un objet : l'accepter ferait planter le
    consommateur plus loin, là où la cause ne serait plus lisible."""
    from saknussemm.core.protocols import ProviderTransientError

    with pytest.raises(ProviderTransientError):
        parse_chat_json(_chat("[1, 2]"), "m")


# --------------------------------------------------------------------------- #
# Les jetons — l'axe coût du rapport
# --------------------------------------------------------------------------- #


@_needs_saknussemm
def test_usage_is_carried_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Les perdre rendrait un run payant indiscernable d'un run local.

    Le test vaut surtout par le **renommage** qu'il verrouille : l'API dit
    ``prompt``/``completion``, ``saknussemm`` dit ``input``/``output``, et son
    modèle accepte un nom inconnu **sans lever**. Une traduction manquante ne
    casserait donc rien — elle rendrait zéro jeton, c'est-à-dire un run payant
    qui se déclare gratuit.
    """
    _, usage = _run_text(
        monkeypatch,
        _fake_client(
            payloads=[
                _chat(
                    '{"lines": []}',
                    {"prompt_tokens": 12, "completion_tokens": 7},
                    response_id="cmpl-abc",
                )
            ]
        ),
    )
    assert (usage.input_tokens, usage.output_tokens) == (12, 7)
    assert usage.response_ids == ["cmpl-abc"]


@_needs_saknussemm
def test_a_reply_without_an_id_carries_no_response_id() -> None:
    """Pas d'identifiant inventé : la liste reste vide."""
    assert usage_from(_chat("{}", {"prompt_tokens": 1})).response_ids == []


def test_a_reply_without_usage_reports_none() -> None:
    """``None`` et pas zéro : « le fournisseur n'a rien dit » n'est pas
    « l'appel n'a rien coûté »."""
    assert usage_from(_chat("{}")) is None


# --------------------------------------------------------------------------- #
# Vision : les découpes, et le plafond mesuré
# --------------------------------------------------------------------------- #


@_needs_saknussemm
def test_each_crop_is_announced_with_the_line_it_shows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """La réponse est indexée par ``line_id`` et le modèle n'a aucun autre moyen
    d'apparier une image à une ligne : l'étiquette fait partie du contrat."""
    calls: list[dict[str, Any]] = []
    _run_vision(
        monkeypatch,
        _fake_client(calls=calls),
        [_Part("L1", b"\x89PNG1"), _Part("L2", b"\x89PNG2")],
    )
    blocs = calls[0]["body"]["messages"][1]["content"]
    assert blocs[0] == {"type": "text", "text": "Image de la ligne L1 :"}
    attendu = base64.standard_b64encode(b"\x89PNG1").decode("ascii")
    assert blocs[1]["image_url"] == f"data:image/png;base64,{attendu}"
    assert blocs[2] == {"type": "text", "text": "Image de la ligne L2 :"}
    # Le JSON ferme le message : le modèle voit les images puis la consigne.
    assert json.loads(blocs[-1]["text"]) == {"lines": ["le ſoleil"]}


@_needs_saknussemm
def test_a_ninth_crop_is_refused_before_any_encoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mesuré contre l'API : une neuvième image renvoie 400/3051. Émettre la
    requête quand même encoderait huit découpes pour rien, et l'erreur
    désignerait l'API alors que la cause est un moteur mal renseigné."""
    calls: list[dict[str, Any]] = []
    parts = [_Part(f"L{i}") for i in range(MAX_IMAGES_PER_CALL + 1)]
    with pytest.raises(ValueError, match="max_images"):
        _run_vision(monkeypatch, _fake_client(calls=calls), parts)
    assert calls == [], "rien ne doit partir sur le réseau."


@_needs_saknussemm
def test_exactly_eight_crops_go_through(monkeypatch: pytest.MonkeyPatch) -> None:
    """Le pendant du refus : le plafond est huit, pas sept."""
    calls: list[dict[str, Any]] = []
    parts = [_Part(f"L{i}") for i in range(MAX_IMAGES_PER_CALL)]
    _run_vision(monkeypatch, _fake_client(calls=calls), parts)
    assert len(calls) == 1

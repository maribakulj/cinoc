"""Sidecar ``NATIVE_JSON`` : la réponse brute d'un moteur distant (couche 5).

Un adaptateur distant ne garde du corps que l'API lui rend qu'une **lecture** —
le texte. Le reste (boîtes, blocs, confiances, en-têtes de page, raison d'arrêt)
était jeté, et toute autre lecture imposait de re-payer l'appel. Ce module écrit
ce corps à côté du texte, sous une forme unique (``native_json_bytes`` : clés
triées), pour que la lecture se refasse **depuis le sidecar** par la même
fonction de conversion que l'adaptateur — il n'y a pas de second chemin.

Ce qui y entre est le **corps** de la réponse, et lui seul : jamais la requête,
ni ses en-têtes, ni l'URL (la clé Google voyage en *query string*, celle
d'Azure et des SDK en en-tête). Pour un SDK, :func:`sdk_native` lit le modèle
pydantic par ``model_dump`` — qui ignore les attributs privés où les SDK rangent
l'identifiant de requête (``_request_id``) et l'espace de travail
(``_workspace_id``) — avec ``exclude_unset`` : ce qui est arrivé sur le fil,
sans les défauts que le modèle ajoute. Vérifié sur openai 3.59, anthropic 2.14
et mistralai 1.12.4, puis 3.9 (S22, blocs OCR compris) : le dump est égal
au corps reçu.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import (
    Artifact,
    ArtifactType,
    compute_content_hash,
    native_json_bytes,
)
from cinoc.domain.errors import AdapterStepError


def sdk_native(response: object, adapter: str) -> dict[str, Any]:
    """Objet de réponse d'un SDK → le corps JSON reçu (``dict``).

    Un objet qui n'est pas un modèle pydantic est refusé plutôt que deviné : la
    conversion lit ce dict, et un dict reconstruit à la main serait un second
    chemin vers le texte.
    """
    dump = getattr(response, "model_dump", None)
    if not callable(dump):
        raise AdapterStepError(
            f"{adapter} : réponse du SDK inattendue ({type(response).__name__}) "
            "— un modèle pydantic était attendu."
        )
    data = dump(mode="json", by_alias=True, exclude_unset=True)
    if not isinstance(data, dict):
        raise AdapterStepError(
            f"{adapter} : réponse du SDK sérialisée en {type(data).__name__}, "
            "pas en objet JSON."
        )
    return data


def native_artifact(
    *,
    native: object,
    workspace_uri: str,
    document_id: str,
    label: str,
    adapter_name: str,
) -> Artifact:
    """Écrit le sidecar ``NATIVE_JSON`` dans le workspace et rend son artefact."""
    try:
        payload = native_json_bytes(native)
    except (TypeError, ValueError) as exc:
        raise AdapterStepError(
            f"{adapter_name} : réponse native non sérialisable en JSON : {exc}"
        ) from exc
    path = workspace_artifact_path(workspace_uri, document_id, label, "native.json")
    path.write_bytes(payload)
    return Artifact(
        id=f"{document_id}:{adapter_name}:native_json",
        document_id=document_id,
        type=ArtifactType.NATIVE_JSON,
        uri=str(path),
        content_hash=compute_content_hash(payload),
    )


def served_model(body: object) -> str | None:
    """Le modèle que le fournisseur dit avoir **servi** : ``model`` du corps.

    OpenAI, Anthropic, Mistral (chat et OCR) et Ollama le rendent au premier
    niveau de leur réponse ; c'est l'identifiant résolu (``gpt-4o-mini`` demandé,
    ``gpt-4o-mini-2024-07-18`` servi). Absent, vide ou d'un autre type → ``None`` :
    rien n'est supposé.
    """
    value = body.get("model") if isinstance(body, dict) else None
    return value if isinstance(value, str) and value else None


def public_endpoint(url: str) -> str:
    """Une URL de cible, **sans** identifiants ni *query string* (une URL peut
    porter un jeton) : schéma, hôte, port et chemin — ce qui désigne la cible.
    C'est la forme écrite au manifeste et hachée dans l'empreinte de l'étape."""
    parts = urlsplit(url)
    host = parts.hostname or ""
    try:
        port = parts.port
    except ValueError:  # port illisible : on garde l'hôte, le client refusera
        port = None
    if port is not None:
        host = f"{host}:{port}"
    return urlunsplit((parts.scheme, host, parts.path, "", "")) or url


def validate_endpoint(value: object, owner: str, field: str = "base_url") -> str:
    """Un endpoint saisi **par instance** (``base_url``, ``host`` d'Ollama —
    ``field`` le nomme dans les refus) : une URL ``http(s)``
    qui ne porte rien d'autre que la cible.

    Refusés : un autre schéma (``file:``, ``ftp:``), l'absence d'hôte, un port
    illisible, des **identifiants** (``user:pw@``), une *query string* ou un
    fragment — l'un et l'autre peuvent porter un jeton, et ni le manifeste ni
    l'empreinte de l'étape ne doivent en recevoir (les messages ne citent pas
    l'URL refusée, pour la même raison). Une URL acceptée est donc
    égale à sa forme publique (``public_endpoint``) : celle qu'on appelle est
    celle qu'on écrit, au ``/`` final près (retiré). La clé, elle, se nomme à
    part (``api_key_env``).
    """
    if not isinstance(value, str):
        raise AdapterStepError(
            f"{owner} : {field} (str) attendu, reçu {type(value).__name__}."
        )
    url = value.strip()
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise AdapterStepError(
            f"{owner} : {field} illisible (attendu http(s)://hôte[:port]/…)."
        )
    if parts.username is not None or parts.password is not None:
        raise AdapterStepError(
            f"{owner} : {field} refusé, il porte des identifiants — nommer la "
            "variable de la clé par api_key_env."
        )
    if not parts.hostname:
        raise AdapterStepError(f"{owner} : {field} sans hôte.")
    try:
        parts.port  # noqa: B018 — lecture qui valide
    except ValueError as exc:
        raise AdapterStepError(f"{owner} : {field}, port illisible.") from exc
    if parts.query:
        raise AdapterStepError(
            f"{owner} : {field} refusé, il porte une query string (un jeton "
            "peut y voyager)."
        )
    if parts.fragment:
        raise AdapterStepError(f"{owner} : {field} refusé, il porte un fragment.")
    # Forme **normalisée** : sans ``/`` final. ``…/v1`` et ``…/v1/`` désignent le
    # même serveur (le SDK joint le chemin de la route lui-même) ; sans cela, un
    # ``/`` changeait l'empreinte de l'étape — donc réexécutait des unités déjà
    # payées — et l'endpoint d'OpenAI saisi ``…/v1/`` perdait son tarif.
    return url.rstrip("/")


__all__ = [
    "native_artifact",
    "public_endpoint",
    "sdk_native",
    "served_model",
    "validate_endpoint",
]

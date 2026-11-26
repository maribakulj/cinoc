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
et mistralai 1.12.4 : le dump est égal au corps reçu.
"""

from __future__ import annotations

from typing import Any

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


__all__ = ["native_artifact", "sdk_native"]

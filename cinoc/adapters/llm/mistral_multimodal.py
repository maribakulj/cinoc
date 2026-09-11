"""``MistralMultimodalClient`` — la moitié vision du fournisseur Mistral.

``saknussemm`` livre une chaîne vision complète : ``VisionEditProducer`` découpe
chaque ligne dans le scan, ``GuardConfig.vision()`` desserre la garde de
similarité (une lecture *correcte* d'une ligne mal océrisée s'écarte forcément du
texte source), et ``core/batching.py`` scinde un lot pour respecter
``ModelCapabilities.max_images``. Il ne manquait que le fournisseur : tous les
clients de ce dépôt n'implémentaient que ``complete_structured``, donc la vision
de la bibliothèque était inatteignable depuis le banc.

**Deux faits mesurés contre l'API, pas lus dans une doc**, hérités du client
archivé en ``campaigns/tooling/providers_multimodal.py`` :

* **une neuvième image est refusée** — HTTP 400 ``"Total number of images exceeds
  the maximum allowed of 8."`` (code 3051). D'où :data:`MAX_IMAGES_PER_CALL` = 8,
  déclaré au moteur via ``ModelCapabilities.max_images`` : c'est ce qui le fait
  scinder le lot au lieu d'émettre une requête qui ne peut pas aboutir ;
* **le scan de page entière est la mauvaise image.** Attacher la page complète et
  demander des corrections fait *décrire* la photographie au modèle : une légende
  est revenue réécrite de ``PHOTOGRAPHIE DE L'ÉBOULEMENT D'UNE FALAISE A
  BOULOGNE-SUR-MER`` en ``DEUX ASPECTS DE LA FALAISE ÉBOULÉE, MONTRANT LE
  GLISSEMENT DES TERRES``. Les découpes par ligne ne sont pas une optimisation :
  c'est ce qui rend la tâche lisible au modèle.

Délibérément **frère** de ``MistralStructuredClient`` et non un élargissement :
la bibliothèque garde sa couture texte sans image exprès, et mélanger les deux
ferait porter à chaque fournisseur texte une signature vision qu'il ne sait pas
honorer.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from cinoc.adapters.llm.mistral_structured import (
    parse_chat_json,
    post_chat,
    usage_from,
)

#: Mesuré, pas documenté : une neuvième image est refusée en 400/3051.
MAX_IMAGES_PER_CALL = 8


class MistralMultimodalClient:
    """``complete_structured_multimodal`` sur ``/v1/chat/completions``."""

    MAX_IMAGES_PER_CALL = MAX_IMAGES_PER_CALL

    def __init__(self, *, timeout: float = 300.0) -> None:
        self._timeout = timeout

    def _content_blocks(
        self, user_payload: dict[str, Any], images: list[Any]
    ) -> list[dict[str, Any]]:
        """Chaque découpe annoncée par la ligne qu'elle montre, puis le JSON.

        La réponse est indexée par ``line_id`` et le modèle n'a aucun autre moyen
        d'apparier une image à une ligne : l'étiquette fait partie du contrat,
        ce n'est pas de la décoration.
        """
        blocks: list[dict[str, Any]] = []
        for part in images:
            blocks.append(
                {"type": "text", "text": f"Image de la ligne {part.line_id} :"}
            )
            encoded = base64.standard_b64encode(part.data).decode("ascii")
            blocks.append(
                {
                    "type": "image_url",
                    "image_url": f"data:{part.media_type};base64,{encoded}",
                }
            )
        blocks.append(
            {"type": "text", "text": json.dumps(user_payload, ensure_ascii=False)}
        )
        return blocks

    async def complete_structured_multimodal(
        self,
        *,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        images: list[Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], Any]:
        if len(images) > MAX_IMAGES_PER_CALL:
            # Y arriver signifie que le moteur n'a pas reçu la limite : c'est le
            # descripteur de capacités qui scinde le lot, et une requête émise
            # quand même échouerait après avoir encodé les découpes pour rien.
            raise ValueError(
                f"{len(images)} découpes en un appel alors que Mistral en accepte "
                f"au plus {MAX_IMAGES_PER_CALL}. Déclare "
                f"ModelCapabilities(max_images={MAX_IMAGES_PER_CALL}) sur le "
                "producteur pour que le moteur scinde le lot en amont."
            )
        body: dict[str, Any] = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": self._content_blocks(user_payload, images)},
            ],
            "response_format": {"type": "json_schema", "json_schema": json_schema},
        }
        data = await post_chat(
            api_key=api_key,
            body=body,
            fallback_body={**body, "response_format": {"type": "json_object"}},
            model=model,
            timeout=self._timeout,
        )
        return parse_chat_json(data, model), usage_from(data)


__all__ = ["MAX_IMAGES_PER_CALL", "MistralMultimodalClient"]

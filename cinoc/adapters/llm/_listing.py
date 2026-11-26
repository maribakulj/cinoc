"""Les modèles d'un fournisseur, **demandés** à son API (couche 5).

Une liste de modèles figée est un cache qu'on a oublié d'invalider (D-268) :
elle proposait des modèles retirés et taisait les nouveaux. Chaque adaptateur
LLM/VLM expose donc ``list_models`` — un appel **en direct** à l'API du
fournisseur — et la lecture du corps reçu en ``ModelInfo`` est une fonction
pure, testée sur cassette.

**Rien n'est deviné.** Une capacité (vision, OCR) ou un cycle de vie
(déprécié, retiré, dates) n'est rempli que si le fournisseur le **déclare** ;
sinon ``None`` — « inconnu », jamais « non ». OpenAI ne déclare pas la vision ;
Anthropic, Mistral et Ollama la déclarent.

Une liste indisponible (SDK absent, clé absente, serveur injoignable, erreur de
l'API) lève ``ModelListingError`` avec sa raison : l'appelant (couche ``app``)
la montre au lieu d'une liste vide qui se lirait « aucun modèle ».
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from cinoc.domain.errors import AdapterStepError, CinocError

Lifecycle = Literal["active", "deprecated", "retired"]

#: Délai d'une demande de liste : une page du composeur l'attend.
LISTING_TIMEOUT = 10.0


class ModelListingError(CinocError):
    """La liste des modèles d'un fournisseur n'a pas pu être lue (raison)."""


class ModelInfo(BaseModel):
    """Un modèle tel que son fournisseur le décrit — rien de plus.

    ``vision``/``ocr`` : capacité **déclarée** (``None`` = inconnue).
    ``lifecycle`` : ``active``/``deprecated``/``retired`` si l'API le dit ;
    ``deprecated_at``/``retires_at`` : dates données par l'API (ISO), telles
    quelles. ``aliases`` : autres noms acceptés pour ce modèle (Mistral).
    ``digest`` : empreinte des poids (Ollama) — un autre digest est un autre
    modèle, même sous le même tag.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    vision: bool | None = None
    ocr: bool | None = None
    lifecycle: Lifecycle | None = None
    deprecated_at: str | None = None
    retires_at: str | None = None
    aliases: tuple[str, ...] = ()
    digest: str | None = None


def require_model(model: object, owner: str) -> str:
    """Le modèle **nommé** d'une instance : une chaîne non vide, sans défaut.

    Aucun modèle n'est codé (D-268) : un défaut implicite change de cible en
    silence quand le fournisseur le retire ou le réaffecte. La spec le nomme ;
    le registre, qui refuse une spec sans modèle, dit lesquels sont
    disponibles.
    """
    if not isinstance(model, str) or not model.strip():
        raise AdapterStepError(
            f"{owner} : 'model' requis (aucun modèle par défaut) — "
            "`cinoc list models <fournisseur>` dit lesquels sont disponibles."
        )
    return model


def declared_flag(value: object) -> bool | None:
    """Un booléen déclaré, sinon ``None`` (jamais ``False`` par défaut)."""
    return value if isinstance(value, bool) else None


def declared_text(value: object) -> str | None:
    """Une chaîne non vide déclarée (date ISO, identifiant), sinon ``None``."""
    return value if isinstance(value, str) and value else None


def declared_lifecycle(value: object) -> Lifecycle | None:
    if value == "active":
        return "active"
    if value == "deprecated":
        return "deprecated"
    if value == "retired":
        return "retired"
    return None


__all__ = [
    "LISTING_TIMEOUT",
    "Lifecycle",
    "ModelInfo",
    "ModelListingError",
    "declared_flag",
    "declared_lifecycle",
    "declared_text",
    "require_model",
]

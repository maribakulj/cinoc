"""Catalogue **canonique** de modèles par fournisseur LLM/VLM (couche 6) — pour l'UI.

Liste curée des modèles d'un fournisseur avec leur **capacité vision** (utile aux
modes ``zero_shot``/``text_and_image`` qui exigent un VLM). Alimente
``/api/models/{provider}`` → le formulaire suggère les modèles ; le champ ``model``
reste **libre** (un modèle hors liste est accepté). Concern **distinct** de
``pricing.json`` (coût) — on ne couple pas. Les modèles **réellement installés**
ollama/mistral ont leur propre canal *live* (``installed_*_models``).

Étendre la liste = modifier ``_CANONICAL`` **ici** (source unique des suggestions).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ModelInfo(BaseModel):
    """Un modèle suggéré : son nom + s'il accepte une image (vision)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    vision: bool


#: Modèles canoniques par fournisseur (nom, vision). Curé.
_CANONICAL: dict[str, tuple[tuple[str, bool], ...]] = {
    "openai": (("gpt-4o-mini", True), ("gpt-4o", True)),
    "anthropic": (
        ("claude-haiku-4-5-20251001", True),
        ("claude-sonnet-4-6", True),
    ),
    "mistral": (
        ("mistral-small-latest", False),
        ("mistral-large", False),
        ("pixtral-12b-latest", True),
    ),
}


def provider_models(provider: str) -> tuple[ModelInfo, ...]:
    """Modèles canoniques du ``provider`` ; **vide** si inconnu (fallback gracieux)."""
    return tuple(
        ModelInfo(name=name, vision=vision)
        for name, vision in _CANONICAL.get(provider, ())
    )


__all__ = ["ModelInfo", "provider_models"]

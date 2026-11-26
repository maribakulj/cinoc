"""Catalogue de **prompts curés par période** (DONNÉE, ≠ surface exécutable).

16 prompts ``.txt`` empaquetés — **correction** (texte OCR → corrigé, placeholder
``{ocr_text}``, modes ``text_only``/``text_and_image``) et **zero-shot** (image →
texte, sans placeholder, mode ``zero_shot``), par type de document et langue
(médiéval FR/EN, imprimé ancien, presse XIXe FR/EN/DE/européenne).

Lus **dynamiquement** du paquet (jamais une liste statique — la leçon des profils
de normalisation). La sélection (par nom, ``prompt_name``) est résolue par
``resolve_prompt`` — au plan du composeur (``app.run_planning``) comme au
registre pour une spec YAML — et passée comme ``prompt`` à l'adapter LLM/VLM ;
un prompt libre et un prompt curé s'excluent.
"""

from __future__ import annotations

from importlib import resources

from cinoc.domain.errors import CinocError

_SUFFIX = ".txt"


class PromptError(CinocError):
    """Nom de prompt curé inconnu (jamais un défaut muet)."""


def _names() -> list[str]:
    """Noms (sans extension) des prompts ``.txt`` du paquet, triés."""
    return sorted(
        entry.name[: -len(_SUFFIX)]
        for entry in resources.files(__name__).iterdir()
        if entry.name.endswith(_SUFFIX)
    )


def available_prompts() -> tuple[str, ...]:
    """Noms des prompts curés disponibles (reflètent le paquet, pas une liste figée)."""
    return tuple(_names())


def load_prompt(name: str) -> str:
    """Texte du prompt curé ``name`` ; ``PromptError`` si inconnu."""
    if name not in _names():
        raise PromptError(f"prompt curé inconnu : {name!r}.")
    return (
        resources.files(__name__)
        .joinpath(f"{name}{_SUFFIX}")
        .read_text(encoding="utf-8")
        .strip()
    )


def resolve_prompt(prompt: str | None, prompt_name: str | None) -> str | None:
    """Le texte d'un prompt saisi : libre **ou** curé (par nom), jamais les deux.

    Une seule règle pour le composeur web (``Competitor``) et pour une spec YAML
    (``adapter_kwargs.<brique>.prompt_name``). ``None`` : aucun des deux, la
    brique prend le prompt par défaut de son mode. Les deux à la fois, ou un nom
    inconnu → ``PromptError`` (jamais un choix silencieux).
    """
    if prompt and prompt_name:
        raise PromptError(
            "prompt : choisir un prompt libre OU un prompt curé (prompt_name), "
            "pas les deux."
        )
    if prompt_name:
        return load_prompt(prompt_name)
    return prompt or None


__all__ = ["PromptError", "available_prompts", "load_prompt", "resolve_prompt"]

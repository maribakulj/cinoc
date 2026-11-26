"""Déclaration des réglages qu'une brique accepte — ``PARAMS``, **facultative**.

Le contrat :class:`~cinoc.pipeline.protocols.Module` porte des ``params`` non
typés : rien ne disait quels réglages une brique lit. Une faute de frappe
(``tempreature``) entrait donc dans la spec, n'était lue par personne, et le run
tournait sans elle — un réglage qu'on croit posé et qui ne l'est pas produit un
résultat faux qu'aucun signal n'annonce (D-251, même motif que ``LABELS``).

Une brique **déclare** désormais ses réglages, en ``ClassVar`` sur sa classe ::

    class MonSegmenteur:
        PARAMS: ClassVar[tuple[Param, ...]] = (
            Param("min_score", "float", "Score minimal", "Minimum score",
                  default=0.5, minimum=0.0, maximum=1.0),
            Param("token", "str", "Jeton", "Token", secret=True,
                  affects_output=False),
        )

La déclaration est **passive** : elle décrit, elle n'exécute rien ; c'est la
couche ``app`` qui l'applique (refus d'un réglage inconnu, type, bornes), pour
la CLI comme pour le web. Elle n'est **pas obligatoire** : ``PARAMS`` absent ou
``None`` veut dire « je ne me prononce pas » — les réglages restent libres,
exactement comme avant ; ``PARAMS = ()`` affirme « aucun réglage » — tout
réglage est refusé. On ne refuse que ce qu'on peut réfuter (D-251).

Deux marques ne décrivent pas un formulaire mais ce qu'un réglage **devient** :

- ``secret`` — jamais écrit tel quel : ni au manifeste, ni dans l'empreinte, ni
  (plus tard) dans une recette enregistrée ; seul le **fait** qu'il a été fourni
  y figure ;
- ``affects_output=False`` — un réglage d'**exploitation** (un délai, le nom de
  la variable d'une clé, « auto-hébergé » pour l'économie) : écrit au manifeste,
  mais **hors** de l'empreinte de l'étape. Le changer ne fait pas réexécuter
  une inférence déjà payée.

Couche 4 (``pipeline``), à côté du contrat qu'elle complète : c'est une partie de
l'API publique d'extension (``cinoc.adapters.extension`` la réexporte).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cinoc.domain.errors import CinocError

#: Types qu'un réglage peut prendre — ceux d'une valeur de spec (YAML/JSON plat).
ParamType = Literal["str", "int", "float", "bool"]
#: Valeur d'un défaut ou d'un choix (même domaine que ``ParamValue``).
ParamDefault = str | int | float | bool

_PYTHON_TYPES: dict[str, tuple[type, ...]] = {
    "str": (str,),
    "int": (int,),
    # Un YAML écrit ``temperature: 0`` : un entier est un flottant admissible.
    "float": (int, float),
    "bool": (bool,),
}


class ParamDeclarationError(CinocError):
    """Une déclaration ``PARAMS`` mal formée (nom, type, défaut, bornes)."""


def value_matches(kind: ParamType, value: object) -> bool:
    """``value`` est-elle du type ``kind`` ? (``bool`` n'est jamais un nombre.)"""
    if isinstance(value, bool):
        return kind == "bool"
    return isinstance(value, _PYTHON_TYPES[kind])


@dataclass(frozen=True)
class Param:
    """Un réglage déclaré : nom, type, libellés, défaut, bornes, marques.

    ``default=None`` : aucun défaut **écrit ici** — soit le réglage est requis
    (``required``), soit la brique laisse décider le moteur (un ``dpi`` non
    fixé). ``choices`` : valeurs admises (une énumération) ; vide = libre.
    ``minimum``/``maximum`` : bornes incluses d'un nombre.
    """

    name: str
    type: ParamType
    label_fr: str
    label_en: str
    default: ParamDefault | None = None
    required: bool = False
    choices: tuple[ParamDefault, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    secret: bool = False
    affects_output: bool = True

    def __post_init__(self) -> None:
        if not self.name.isidentifier():
            raise ParamDeclarationError(f"Param : nom invalide {self.name!r}.")
        if self.type not in _PYTHON_TYPES:
            raise ParamDeclarationError(
                f"Param {self.name!r} : type inconnu {self.type!r}."
            )
        for value in (
            *self.choices,
            *(() if self.default is None else (self.default,)),
        ):
            if not value_matches(self.type, value):
                raise ParamDeclarationError(
                    f"Param {self.name!r} : {value!r} n'est pas du type {self.type}."
                )
        bornes = self.minimum is not None or self.maximum is not None
        if bornes and self.type not in ("int", "float"):
            raise ParamDeclarationError(
                f"Param {self.name!r} : des bornes sur un {self.type}."
            )

    def label(self, lang: str) -> str:
        """Libellé dans la langue demandée (repli français)."""
        return self.label_en if lang == "en" else self.label_fr


def declared_params(obj: object) -> tuple[Param, ...] | None:
    """La déclaration d'une brique (classe ou instance), ``None`` si absente.

    Lue sur la **classe** : une déclaration est une propriété de la brique, pas
    d'un réglage. Une déclaration mal formée (autre chose qu'une suite de
    :class:`Param`, un nom répété) est **refusée**, pas ignorée : l'ignorer
    rendrait libres, en silence, les réglages que l'auteur croyait bornés.
    """
    cls = obj if isinstance(obj, type) else type(obj)
    params = getattr(cls, "PARAMS", None)
    if params is None:
        return None
    if not isinstance(params, (tuple, list)) or not all(
        isinstance(p, Param) for p in params
    ):
        raise ParamDeclarationError(
            f"{cls.__name__}.PARAMS : une suite de Param est attendue."
        )
    names = [p.name for p in params]
    if len(set(names)) != len(names):
        raise ParamDeclarationError(f"{cls.__name__}.PARAMS : nom répété.")
    return tuple(params)


__all__ = [
    "Param",
    "ParamDeclarationError",
    "ParamDefault",
    "ParamType",
    "declared_params",
    "value_matches",
]

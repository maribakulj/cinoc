"""Lecture YAML d'une entrée **non fiable** — l'entonnoir, comme ``_xml``.

``yaml.safe_load`` ne construit que des types simples, mais il **partage** les
nœuds qu'un alias désigne. Neuf alias de neuf alias font, en moins d'un
kilo-octet, une structure de 9⁹ feuilles que toute validation parcourt ensuite
(« billion laughs ») : des minutes de calcul sur un fil du serveur. Une spec
déposée ou un profil de normalisation saisi n'a pas besoin d'alias ; on les
refuse donc **au moment de la composition**, avant que rien ne soit construit
(D-299). Une ancre seule est inoffensive et reste admise.

Le YAML que l'utilisateur lit sur son propre disque (``cinoc run spec.yaml``,
les recettes livrées) garde ``yaml.safe_load`` : il n'est pas une entrée d'un
tiers.
"""

from __future__ import annotations

import yaml
from yaml.nodes import Node

__all__ = ["safe_load_yaml"]


class _SansAlias(yaml.SafeLoader):
    """``SafeLoader`` qui refuse tout alias (``*nom``) dès qu'il le rencontre."""

    def compose_node(self, parent: Node | None, index: int) -> Node | None:
        if self.check_event(yaml.AliasEvent):
            raise yaml.composer.ComposerError(
                None,
                None,
                "alias YAML refusé (« *nom ») : une entrée non fiable n'en a "
                "pas besoin, et il permet une expansion exponentielle",
                self.peek_event().start_mark,  # type: ignore[no-untyped-call]
            )
        return super().compose_node(parent, index)


def safe_load_yaml(text: str) -> object:
    """``yaml.safe_load`` sans alias ; lève ``yaml.YAMLError`` sinon."""
    return yaml.load(text, Loader=_SansAlias)  # noqa: S506 -- SafeLoader durci

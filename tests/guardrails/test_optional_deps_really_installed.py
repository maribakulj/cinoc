"""Garde-fou : un `skip` conditionnel ne doit pas masquer une installation ratée.

La chaîne de correction structurée passe par ``saknussemm``, qui n'est pas
publié sur PyPI et s'installe donc depuis le dépôt à une révision vérifiée.
L'installation est obligatoire en CI : un échec bloque le gate.

Si l'installation **réussit** mais que le paquet reste
inimportable — extra renommé, dépendance transitive cassée, incompatibilité de
version de Python — les ~20 tests de la chaîne se sautent **exactement de la
même façon**, en silence, et la CI affirme « vert » sur la seule brique qui
touche à la mise en page. Un `skip` sans cause visible ressemble à un succès.

D'où le contrat : quand l'étape d'installation a réussi, elle pose
``CINOC_REQUIRE_SAKNUSSEMM=1``, et l'absence du paquet devient un **échec
nommé** au lieu d'un saut. La variable n'est jamais posée en local : hors CI,
travailler sans ``saknussemm`` reste légitime.
"""

from __future__ import annotations

import importlib.util
import os

import pytest

#: Posée par le job CI après l'installation obligatoire de l'extra.
_REQUIS = "CINOC_REQUIRE_SAKNUSSEMM"


def test_saknussemm_is_importable_when_its_install_succeeded() -> None:
    if not os.environ.get(_REQUIS):
        pytest.skip(
            f"{_REQUIS} non posée : installation de saknussemm non garantie "
            "(en local, travailler sans cet extra reste légitime)."
        )
    assert importlib.util.find_spec("saknussemm") is not None, (
        "saknussemm s'est installé mais reste inimportable : les tests de la "
        "chaîne de correction structurée allaient se sauter en silence et "
        "laisser la CI verte sur du code non exercé."
    )

"""Garde-fou : un `skip` conditionnel ne doit pas masquer une installation ratée.

La chaîne de correction structurée passe par ``saknussemm``, installé à la
version exacte vérifiée avec le pont (``pyproject.toml``). L'installation est
obligatoire en CI : un échec bloque le gate.

Si l'installation **réussit** mais que le paquet reste
inimportable — extra renommé, dépendance transitive cassée, incompatibilité de
version de Python — les ~20 tests de la chaîne se sautent **exactement de la
même façon**, en silence, et la CI affirme « vert » sur la seule brique qui
touche à la mise en page. Un `skip` sans cause visible ressemble à un succès.

D'où le contrat : quand l'étape d'installation a réussi, elle pose
``CINOC_REQUIRE_SAKNUSSEMM=1``, et l'absence du paquet devient un **échec
nommé** au lieu d'un saut. La variable n'est jamais posée en local : hors CI,
travailler sans ``saknussemm`` reste légitime.

Le job CI ``oracle`` (D-290) tient le même contrat pour ses oracles exécutés
(``roman``, dinglehopper) : ``CINOC_REQUIRE_ORACLES=1``.
"""

from __future__ import annotations

import importlib
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


#: Posée par le job CI ``oracle`` après l'installation des oracles (D-290).
_ORACLES_REQUIS = "CINOC_REQUIRE_ORACLES"


@pytest.mark.oracle
@pytest.mark.parametrize(
    "module",
    [
        "roman",
        # Le module qui importe ``ocrd_utils`` : installé ``--no-deps``, c'est
        # lui qui casse si l'extra ``oracle`` oublie une dépendance réelle.
        "dinglehopper.ocr_files",
        "dinglehopper.character_error_rate",
        "dinglehopper.word_error_rate",
    ],
)
def test_oracles_are_importable_when_their_install_succeeded(module: str) -> None:
    """Même contrat que ``saknussemm`` pour le job ``oracle`` : un oracle
    installé mais inimportable ferait sauter ses tests, job vert sur rien."""
    if not os.environ.get(_ORACLES_REQUIS):
        pytest.skip(f"{_ORACLES_REQUIS} non posée : hors du job CI oracle.")
    importlib.import_module(module)

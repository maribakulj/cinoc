"""L'exemple ``cinoc corpus search`` du guide trouve quelque chose (S34b, n° 10).

Le testeur a tapé ``cinoc corpus search "presse"``, l'exemple du guide :
« Aucune entrée ». L'exemple est relu ici dans le guide et cherché dans le
catalogue **embarqué** — celui que la commande sert hors ligne.
"""

from __future__ import annotations

import re
from pathlib import Path

from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue

GUIDE = Path(__file__).resolve().parents[2] / "docs" / "guide.md"


def test_the_guide_search_example_finds_entries_offline() -> None:
    termes = re.findall(r'cinoc corpus search "([^"]+)"', GUIDE.read_text("utf-8"))
    assert termes, "le guide ne donne plus d'exemple de recherche"
    for terme in termes:
        assert HTRUnitedCatalogue.from_demo().search(terme), terme


def test_the_guide_says_a_search_does_not_download() -> None:
    texte = GUIDE.read_text("utf-8")
    assert "does not download" in texte

"""YAML venu d'un client : aucun alias (« billion laughs »), D-299.

``yaml.safe_load`` ne construit que des types simples, mais il **partage** les
nœuds qu'un alias désigne : neuf alias de neuf alias font, en moins d'un
kilo-octet, une structure de 9⁹ feuilles que la validation parcourt ensuite
— des minutes de calcul sur un fil du serveur. Mesuré sur la porte « spec
complète » (``POST /api/runs/spec``) et sur l'aperçu de normalisation, avant
correction : profondeur 6 → 0,1 s, 7 → 0,7 s, chaque niveau × 9.
"""

from __future__ import annotations

import time

import pytest
import yaml

from cinoc.formats import safe_load_yaml


def _bombe(profondeur: int) -> str:
    lignes = ['a0: &a0 ["l","l","l","l","l","l","l","l","l"]']
    for i in range(1, profondeur):
        lignes.append(f"a{i}: &a{i} [" + ",".join([f"*a{i - 1}"] * 9) + "]")
    return "x:\n" + "\n".join("  " + ligne for ligne in lignes) + (
        f"\nname: *a{profondeur - 1}\n"
    )


def test_an_alias_is_refused_before_anything_is_built() -> None:
    debut = time.monotonic()
    with pytest.raises(yaml.YAMLError, match="alias"):
        safe_load_yaml(_bombe(9))
    assert time.monotonic() - debut < 1.0


def test_an_anchor_alone_is_harmless_and_plain_yaml_loads() -> None:
    assert safe_load_yaml("a: &x 1\nb: [2, 3]\n") == {"a": 1, "b": [2, 3]}


def test_no_python_object_is_built() -> None:
    with pytest.raises(yaml.YAMLError):
        safe_load_yaml("!!python/object/apply:os.system ['true']")


def test_the_web_doors_refuse_the_bomb() -> None:
    """Les deux portes qui lisent un YAML de client passent par l'entonnoir."""
    from cinoc.app.recipes import RecipeError, spec_for_corpus
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.formats.text.normalization import NormalizationProfile

    corpus = CorpusSpec(name="c", documents=())
    debut = time.monotonic()
    with pytest.raises(RecipeError, match="alias"):
        spec_for_corpus(_bombe(9), corpus, run_id="r")
    with pytest.raises(yaml.YAMLError, match="alias"):
        NormalizationProfile.from_yaml_text(_bombe(9))
    assert time.monotonic() - debut < 1.0

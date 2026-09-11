"""Distance d'ordre de lecture : ce qu'elle mesure, et ce qu'elle refuse de mesurer.

Un texte projeté dans le mauvais ordre a un CER catastrophique — mais ce CER ne
dit pas **où** est la faute : dans la reconnaissance ou dans l'ordonnancement.
Ces deux fonctions ne répondent qu'à la seconde question, et le fait qu'elles
s'y tiennent est l'essentiel de ce qui est vérifié ici.
"""

from __future__ import annotations

import pytest

from cinoc.evaluation.reading_order import kendall_distance, order_coverage

#: Une page à deux colonnes de trois blocs, lue colonne par colonne.
REFERENCE = ["G1", "G2", "G3", "D1", "D2", "D3"]


def test_the_same_order_is_zero() -> None:
    assert kendall_distance(REFERENCE, REFERENCE) == 0.0


def test_the_reversed_order_is_one() -> None:
    """La borne haute est atteinte, et elle vaut exactement 1."""
    assert kendall_distance(REFERENCE, list(reversed(REFERENCE))) == 1.0


def test_interleaved_columns_score_by_hand() -> None:
    """Le défaut que la stratégie « colonnes » existe pour corriger.

    Lue de haut en bas, la page donne G1 D1 G2 D2 G3 D3. Sur les quinze paires,
    trois sont discordantes — (D1,G2), (D1,G3), (D2,G3) — soit 3/15 = 0,2.
    Valeur posée à la main, pas relevée sur l'implémentation.
    """
    entrelace = ["G1", "D1", "G2", "D2", "G3", "D3"]
    assert kendall_distance(REFERENCE, entrelace) == pytest.approx(0.2)


def test_only_common_blocks_are_compared() -> None:
    """Un bloc non détecté relève de la détection, pas de l'ordre.

    Le compter ici mêlerait deux fautes que le rapport doit pouvoir distinguer —
    et pénaliserait un ordonnanceur pour le travail d'un segmenteur.
    """
    partiel = ["G1", "G2", "G3"]
    assert kendall_distance(REFERENCE, partiel) == 0.0


def test_an_unknown_block_is_ignored_not_counted_wrong() -> None:
    invente = ["G1", "G2", "FANTOME", "G3"]
    assert kendall_distance(REFERENCE, invente) == 0.0


@pytest.mark.parametrize("hypothese", [[], ["G1"]])
def test_fewer_than_two_common_blocks_has_no_order(hypothese: list[str]) -> None:
    """Une paire est le minimum pour qu'« ordre » veuille dire quelque chose."""
    assert kendall_distance(REFERENCE, hypothese) is None


def test_coverage_is_the_mandatory_companion() -> None:
    """Un ordre parfait sur deux blocs trouvés sur six n'est pas un bon résultat.

    La distance seule le dirait excellent (0,0) : c'est pourquoi la couverture
    est publiée à côté, et non en option.
    """
    partiel = ["G1", "G2"]
    assert kendall_distance(REFERENCE, partiel) == 0.0
    assert order_coverage(REFERENCE, partiel) == pytest.approx(2 / 6)


def test_coverage_without_a_reference_is_none() -> None:
    assert order_coverage([], ["G1"]) is None


def test_the_distance_is_comparable_across_page_sizes() -> None:
    """Normalisée par le nombre de paires : deux pages de tailles différentes,
    également désordonnées, reçoivent la même note."""
    petite = kendall_distance(["a", "b"], ["b", "a"])
    grande = kendall_distance(list("abcdef"), list("fedcba"))
    assert petite == grande == 1.0

"""Les mathématiques du prétraitement, sur des matrices construites à la main.

Aucune image décodée, aucun fichier : ces fonctions sont pures, elles se
vérifient sur des tableaux dont on connaît la réponse d'avance. C'est la
condition pour qu'un seuil ou un angle soit **calculé** et non postulé — la
mesure de qualité d'image retirée de ce dépôt l'avait été précisément pour ses
constantes non validées (D-190).
"""

from __future__ import annotations

import numpy as np
import pytest

from cinoc.adapters.preprocess._ops import (
    binarize,
    estimate_skew,
    otsu_threshold,
    to_grayscale,
)


def test_grayscale_uses_the_broadcast_luminance() -> None:
    """Rouge pur → 76, la luminance BT.601 (0,299 × 255), pas la moyenne (85)."""
    rouge = np.zeros((1, 1, 3), dtype=np.uint8)
    rouge[0, 0] = (255, 0, 0)
    assert int(to_grayscale(rouge)[0, 0]) == 76


def test_grayscale_is_idempotent() -> None:
    """Déjà en gris → inchangé : on chaîne les opérations sans y penser."""
    gris = np.array([[0, 128, 255]], dtype=np.uint8)
    assert np.array_equal(to_grayscale(gris), gris)


def test_otsu_separates_two_populations() -> None:
    """Deux pics nets (encre à 20, papier à 220) → seuil entre les deux."""
    image = np.array([[20] * 50 + [220] * 50], dtype=np.uint8)
    seuil = otsu_threshold(image)
    assert 20 <= seuil < 220
    # Et il sépare effectivement : tout le noir d'un côté, tout le blanc de l'autre.
    binaire = binarize(image, seuil)
    assert set(np.unique(binaire).tolist()) == {0, 255}
    assert binaire[0, :50].max() == 0 and binaire[0, 50:].min() == 255


def test_otsu_adapts_to_the_exposure() -> None:
    """Le seuil est **calculé sur l'image**, donc deux expositions en donnent deux.

    C'est ce qu'une constante ne saurait pas faire, et c'est la raison d'être de
    la méthode.
    """
    sombre = np.array([[10] * 50 + [120] * 50], dtype=np.uint8)
    claire = np.array([[130] * 50 + [240] * 50], dtype=np.uint8)
    assert otsu_threshold(sombre) < otsu_threshold(claire)


def test_a_uniform_image_gets_no_invented_contrast() -> None:
    """Une image plate n'a rien à séparer : on rend sa valeur, pas un milieu."""
    plate = np.full((8, 8), 137, dtype=np.uint8)
    assert otsu_threshold(plate) == 137


def _page_lignee(angle: float) -> np.ndarray:
    """Une page de texte simulée : cinq lignes d'encre, inclinée de ``angle``."""
    from PIL import Image

    page = np.full((300, 500), 200, dtype=np.uint8)
    for y in range(40, 280, 45):
        page[y : y + 9, 40:460] = 40
    tournee = Image.fromarray(page).rotate(
        angle, resample=Image.Resampling.BICUBIC, fillcolor=200
    )
    return np.asarray(tournee)


@pytest.mark.parametrize("angle", [0.0, 1.5, 3.0, -3.0, -4.5])
def test_skew_is_measured_exactly_in_both_directions(angle: float) -> None:
    pytest.importorskip("PIL")
    assert estimate_skew(_page_lignee(angle)) == pytest.approx(angle, abs=0.5)


def test_a_straight_page_measures_zero_not_the_search_bound() -> None:
    """Le défaut qui a coûté une réécriture de la méthode.

    Une première version rabattait les rangées hors cadre sur la première et la
    dernière ligne. Cet écrêtage y empilait de l'encre, d'autant plus que
    l'angle était grand, et la variance croissait donc **mécaniquement** avec
    l'angle : le maximum tombait toujours sur la borne de recherche — y compris,
    et c'est le symptôme qui l'a révélé, sur une page parfaitement droite.
    """
    pytest.importorskip("PIL")
    mesure = estimate_skew(_page_lignee(0.0), amplitude_deg=5.0)
    assert mesure == 0.0, f"page droite mesurée à {mesure}° (borne = 5.0°)"


def test_too_small_to_measure_returns_zero() -> None:
    """On ne devine pas une inclinaison sur une vignette."""
    assert estimate_skew(np.zeros((8, 8), dtype=np.uint8)) == 0.0

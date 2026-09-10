"""Opérations de prétraitement — **numpy pur**, sans décodage d'image.

Séparées de l'adapter pour qu'elles se testent sur des matrices construites à la
main, sans Pillow et sans fichier. C'est la même discipline que les métriques :
les maths d'un côté, l'entrée/sortie de l'autre.

**Aucun seuil arbitraire.** C'est une contrainte de conception, pas un hasard :
une mesure de qualité d'image a été retirée de ce dépôt précisément parce que son
score composite reposait sur des constantes non validées (D-190). Ici, le seuil
de binarisation est **calculé sur l'image** (Otsu maximise la variance
inter-classes), et l'angle de redressement est **cherché**, pas postulé. Les deux
seules constantes sont des **bornes de recherche** — l'amplitude et le pas —, qui
ne décident de rien : elles disent seulement où l'on cherche.
"""

from __future__ import annotations

import numpy as np


def to_grayscale(image: np.ndarray) -> np.ndarray:
    """RVB → niveaux de gris (luminance ITU-R BT.601), en ``uint8``.

    Déjà en gris (2 dimensions) → renvoyé tel quel : l'opération est idempotente,
    ce qui permet de la chaîner sans y penser.
    """
    if image.ndim == 2:
        return image.astype(np.uint8, copy=False)
    poids = np.array([0.299, 0.587, 0.114], dtype=np.float64)
    gris = image[..., :3].astype(np.float64) @ poids
    return np.clip(np.rint(gris), 0, 255).astype(np.uint8)


def otsu_threshold(gray: np.ndarray) -> int:
    """Seuil d'Otsu : celui qui **maximise la variance inter-classes**.

    Calculé sur l'histogramme de l'image, donc propre à elle : deux pages
    différemment exposées reçoivent deux seuils différents, ce qu'une constante
    ne saurait pas faire. Image uniforme → renvoie sa valeur (aucune séparation
    n'a de sens, et un seuil médian inventerait du contraste).
    """
    histogramme = np.bincount(gray.reshape(-1), minlength=256).astype(np.float64)
    total = histogramme.sum()
    if total == 0:
        return 0
    niveaux = np.arange(256, dtype=np.float64)
    poids_bas = np.cumsum(histogramme)
    poids_haut = total - poids_bas
    somme_totale = float(niveaux @ histogramme)
    somme_bas = np.cumsum(niveaux * histogramme)
    # Classes vides → variance nulle : on les écarte au lieu de diviser par zéro.
    valide = (poids_bas > 0) & (poids_haut > 0)
    if not valide.any():
        return int(gray.reshape(-1)[0])
    moy_bas = np.divide(somme_bas, poids_bas, out=np.zeros(256), where=valide)
    moy_haut = np.divide(
        somme_totale - somme_bas, poids_haut, out=np.zeros(256), where=valide
    )
    inter = poids_bas * poids_haut * (moy_bas - moy_haut) ** 2
    inter[~valide] = -1.0
    return int(np.argmax(inter))


def binarize(gray: np.ndarray, threshold: int) -> np.ndarray:
    """Gris → noir et blanc (0 / 255) au seuil donné. Encre = sombre = 0."""
    return np.where(gray > threshold, np.uint8(255), np.uint8(0))


def estimate_skew(
    gray: np.ndarray, *, amplitude_deg: float = 5.0, pas_deg: float = 0.5
) -> float:
    """Angle d'inclinaison, en degrés, par profil de projection.

    Une page droite a des lignes de texte horizontales : la somme de l'encre par
    rangée y est donc très **contrastée** — des pics sur le texte, des creux
    entre les lignes. Incliner la page lisse ce profil. On cherche l'angle qui
    maximise la variance du profil : c'est celui qui remet les lignes à plat.

    **L'accumulateur a une hauteur fixe**, dimensionnée pour l'angle maximal, et
    rien n'y est écrêté. C'est la seule façon de comparer des angles entre eux :
    une première version rabattait les rangées hors cadre sur la première et la
    dernière, ce qui y empilait de l'encre et gonflait la variance d'autant plus
    que l'angle était grand. Le maximum tombait alors **toujours** sur la borne
    de recherche — y compris pour une page parfaitement droite.

    ``amplitude_deg`` et ``pas_deg`` bornent la recherche, ils ne la décident
    pas. Amplitude volontairement modeste : au-delà, ce n'est plus une
    inclinaison de numérisation mais une page tournée, qui relève d'une autre
    opération. Image trop petite → ``0.0`` : rien à mesurer, et on ne devine pas.
    """
    if gray.ndim != 2 or min(gray.shape) < 16:
        return 0.0
    encre = 255.0 - gray.astype(np.float64)
    hauteur, largeur = encre.shape
    pas = max(pas_deg, 0.01)
    marge = int(np.ceil(np.tan(np.radians(amplitude_deg)) * largeur)) + 1
    etendue = hauteur + 2 * marge
    lignes = np.arange(hauteur, dtype=np.float64)[:, None]
    colonnes = np.arange(largeur, dtype=np.float64)[None, :]
    meilleur_angle, meilleure_variance = 0.0, -1.0
    for k in range(-int(amplitude_deg / pas), int(amplitude_deg / pas) + 1):
        angle = k * pas
        # Cisaillement vertical : approxime la rotation pour de petits angles,
        # sans ré-échantillonner l'image — donc sans en inventer les pixels.
        decal = np.tan(np.radians(angle)) * colonnes
        rangs = np.rint(lignes + decal).astype(np.int64) + marge
        profil = np.zeros(etendue, dtype=np.float64)
        np.add.at(profil, rangs.ravel(), encre.ravel())
        variance = float(profil.var())
        if variance > meilleure_variance:
            meilleure_variance, meilleur_angle = variance, angle
    return meilleur_angle


__all__ = ["binarize", "estimate_skew", "otsu_threshold", "to_grayscale"]

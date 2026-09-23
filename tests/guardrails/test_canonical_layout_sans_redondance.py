"""Garde-fou : un layout canonique ne décrit jamais deux fois la même aire.

**Pourquoi ce test existe.** Trois défauts de la chaîne hybride ont survécu à
toute la suite parce que le corpus d'essai ne pouvait pas les déclencher : ses
pages ne portaient qu'un bloc de texte, sans imbrication ni détection redondante.
Celui-ci en fige un.

Un détecteur peut rendre deux boîtes pour le même bloc — certaines architectures
suppriment les doublons par post-traitement, d'autres comptent sur leur
entraînement pour ne pas en produire, et cet apprentissage se dégrade hors
domaine. ``to_canonical_layout`` est l'entonnoir unique de tous les détecteurs :
c'est là que la promesse se tient, une fois, pour tous.

Mesuré sur une page de presse réelle : sans ce filtre, le fan-out océrisait les
deux régions et concaténait — le CER passait de 0,014 à 1,009, soit exactement le
texte compté deux fois.
"""

from __future__ import annotations

import pytest

from cinoc.adapters.layout._base import (
    REDONDANCE_IOU,
    DetectedRegion,
    LayoutDetection,
    to_canonical_layout,
)


def _detection(*regions: DetectedRegion) -> LayoutDetection:
    return LayoutDetection(page_width=1000, page_height=800, regions=regions)


def _feuilles(layout):
    return layout.pages[0].leaf_regions()


def test_deux_detections_identiques_ne_font_qu_une_region() -> None:
    """Le cas observé : même boîte, deux scores. C'est le doublon à retirer."""
    layout = to_canonical_layout(
        _detection(
            DetectedRegion(label="text", x=41, y=0, width=820, height=485, score=0.83),
            DetectedRegion(label="text", x=41, y=0, width=820, height=485, score=0.24),
        ),
        min_score=0.2,
    )
    feuilles = _feuilles(layout)
    assert len(feuilles) == 1
    # On garde la plus sûre : c'est elle qui porte la géométrie retenue.
    assert feuilles[0].geometry is not None
    assert feuilles[0].geometry.bbox.x == 41


def test_un_detecteur_sans_doublon_traverse_inchange() -> None:
    """Le filtre ne coûte rien à qui respecte déjà le contrat.

    C'est ce qui le rend acceptable partout : aucun modèle n'est nommé, et celui
    qui fait déjà sa suppression non-maximale ne voit pas la différence.
    """
    detection = _detection(
        DetectedRegion(label="text", x=0, y=0, width=400, height=100, score=0.9),
        DetectedRegion(label="text", x=0, y=200, width=400, height=100, score=0.8),
        DetectedRegion(label="title", x=0, y=400, width=400, height=60, score=0.7),
    )
    assert len(_feuilles(to_canonical_layout(detection, min_score=0.2))) == 3


def test_un_recouvrement_partiel_survit() -> None:
    """Une légende dans une figure se recouvrent : ce n'est pas une redondance.

    Le seuil est haut **pour cette raison**. Un NMS général à 0,5 effacerait de la
    structure légitime, et le remède serait pire que le mal.
    """
    detection = _detection(
        DetectedRegion(label="figure", x=0, y=0, width=400, height=400, score=0.9),
        DetectedRegion(label="caption", x=0, y=360, width=400, height=40, score=0.8),
    )
    assert len(_feuilles(to_canonical_layout(detection, min_score=0.2))) == 2


@pytest.mark.parametrize("decalage", [0, 1, 2])
def test_un_doublon_approximatif_compte_aussi(decalage: int) -> None:
    """Deux boîtes à un pixel près sont le même bloc — vu en conditions réelles."""
    detection = _detection(
        DetectedRegion(label="text", x=38, y=476, width=749, height=185, score=0.33),
        DetectedRegion(
            label="text", x=38 + decalage, y=477, width=749 - decalage, height=184,
            score=0.46,
        ),
    )
    assert len(_feuilles(to_canonical_layout(detection, min_score=0.2))) == 1


def test_le_seuil_est_documente_et_strict() -> None:
    """Le seuil doit rester strict : l'abaisser mangerait de la structure.

    Ce test n'est pas une tautologie — il rend explicite qu'un futur réglage vers
    0,5 est un changement de contrat, pas un ajustement.
    """
    assert REDONDANCE_IOU >= 0.85

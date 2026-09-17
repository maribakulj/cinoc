"""L'API d'écriture d'un module tiers : ce qu'elle promet, elle le tient.

Un point d'extension dont l'usage normal passe par des modules privés n'offre
aucun engagement de stabilité. ``cinoc.adapters.extension`` rassemble ce qu'il
faut ; ces tests vérifient qu'il suffit — un segmenteur complet s'y écrit sans
toucher à un seul `_module`.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import cinoc.adapters.extension as extension


def test_tout_ce_qui_est_promis_existe() -> None:
    manquants = [nom for nom in extension.__all__ if not hasattr(extension, nom)]
    assert manquants == []


def test_aucune_logique_propre() -> None:
    """Le module ne fait que réexporter : deux implémentations divergeraient."""
    source = Path(extension.__file__).read_text(encoding="utf-8")
    corps = [
        ligne
        for ligne in source.splitlines()
        if ligne.startswith(("def ", "class "))
    ]
    assert corps == []


def test_un_segmenteur_tiers_s_ecrit_sans_import_prive() -> None:
    """Le cas d'usage du docstring, exécuté."""
    from cinoc.adapters.extension import (
        ArtifactType,
        DetectedRegion,
        LayoutDetection,
        to_canonical_layout,
    )

    detection = LayoutDetection(
        page_width=100,
        page_height=200,
        regions=(
            DetectedRegion(label="text", x=0, y=50, width=10, height=10, score=0.9),
            DetectedRegion(label="title", x=0, y=0, width=10, height=10, score=0.8),
        ),
    )
    layout = to_canonical_layout(detection, min_score=0.0)
    page = layout.pages[0]
    assert page.width == 100
    # L'ordre déterministe du socle s'applique : le titre (y=0) passe devant.
    assert [r.region_type for r in page.regions] == ["title", "text"]
    assert ArtifactType.LAYOUT.value == "layout"


def test_les_symboles_sont_bien_ceux_du_socle() -> None:
    """Réexport, pas copie : l'identité doit être la même."""
    base = importlib.import_module("cinoc.adapters.layout._base")
    assert extension.to_canonical_layout is base.to_canonical_layout
    assert extension.layout_step_output is base.layout_step_output
    assert extension.DetectedRegion is base.DetectedRegion

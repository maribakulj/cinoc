"""``DocLayoutYoloSegmenter`` : le segmenteur qui s'installe sans rien d'autre.

Le banc avait deux segmenteurs et aucun n'était exécutable sur une machine nue —
l'un veut PaddleX, l'autre une adresse. Or le détecteur est **l'étage** que ce
banc existe pour comparer : sans lui, toute la famille hybride reste théorique.

Ce qui est vérifié ici est la **traduction** détections → ``CanonicalLayout``, le
détecteur étant injecté. Le vrai modèle est un test ``live`` : le charger ici
ferait dépendre le gate d'un téléchargement de poids.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout._base import DetectedRegion, LayoutDetection
from cinoc.adapters.layout.doclayout_yolo import (
    DEFAULT_IMGSZ,
    DEFAULT_MIN_SCORE,
    DocLayoutYoloSegmenter,
    resolve_weights,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext


def _detection(*regions: DetectedRegion) -> LayoutDetection:
    return LayoutDetection(page_width=800, page_height=1200, regions=regions)


def _region(label: str, x: int, y: int, score: float = 0.9) -> DetectedRegion:
    return DetectedRegion(
        label=label, x=x, y=y, width=300, height=40, score=score
    )


def _run(tmp_path: Path, detection: LayoutDetection, **kw: object) -> CanonicalLayout:
    module = DocLayoutYoloSegmenter(detector=lambda _: detection, **kw)  # type: ignore[arg-type]
    out = module.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="i",
                document_id="d",
                type=ArtifactType.IMAGE,
                uri=str(tmp_path / "p.png"),
                content_hash="0" * 64,
            )
        },
        {},
        RunContext(
            document_id="d",
            code_version="1.0",
            pipeline_name="p",
            workspace_uri=str(tmp_path),
        ),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.LAYOUT]
    assert artifact.uri is not None
    return CanonicalLayout.model_validate_json(Path(artifact.uri).read_bytes())


def test_detections_become_regions_without_lines(tmp_path: Path) -> None:
    """Une sortie de segmentation est un layout **à régions sans lignes** : la
    reconnaissance les remplit ensuite. Les livrer remplies ferait croire que la
    page est déjà lue."""
    layout = _run(
        tmp_path, _detection(_region("title", 50, 30), _region("texte", 50, 120))
    )
    page = layout.pages[0]
    assert (page.width, page.height) == (800, 1200)
    assert len(page.regions) == 2
    assert all(region.lines == () for region in page.regions)


def test_reading_order_is_sorted_not_the_detector_order(tmp_path: Path) -> None:
    """Le déterminisme du run ne peut pas dépendre de l'ordre où un modèle rend
    ses boîtes — c'est justement ce qu'un réseau ne garantit pas."""
    bas = _region("plain text", 50, 900)
    haut = _region("title", 50, 30)
    layout = _run(tmp_path, _detection(bas, haut))
    boites = [
        r.geometry.bbox.y
        for r in layout.pages[0].regions
        if r.geometry and r.geometry.bbox
    ]
    assert boites == sorted(boites), "les régions doivent sortir triées haut→bas."


def test_a_low_score_region_is_dropped(tmp_path: Path) -> None:
    """Le seuil est ré-appliqué ici, pas seulement passé au modèle : le contrat
    doit tenir quel que soit le détecteur injecté."""
    layout = _run(
        tmp_path,
        _detection(
            _region("title", 50, 30, score=0.95),
            _region("figure", 50, 200, score=0.01),
        ),
        min_score=0.5,
    )
    assert len(layout.pages[0].regions) == 1


def test_an_empty_detection_is_a_page_without_regions(tmp_path: Path) -> None:
    """Zéro région n'est pas une erreur : c'est une page blanche, et le rapport
    doit pouvoir le dire plutôt que faire échouer le run."""
    layout = _run(tmp_path, LayoutDetection(page_width=0, page_height=0, regions=()))
    assert layout.pages[0].regions == ()


@pytest.mark.parametrize("score", [-0.1, 1.5])
def test_an_out_of_range_threshold_is_refused(score: float) -> None:
    with pytest.raises(AdapterStepError, match="min_score"):
        DocLayoutYoloSegmenter(min_score=score)


def test_a_non_positive_imgsz_is_refused() -> None:
    """La résolution d'inférence est celle des poids publiés ; zéro ou négatif
    n'est pas une variante, c'est une erreur de saisie."""
    with pytest.raises(AdapterStepError, match="imgsz"):
        DocLayoutYoloSegmenter(imgsz=0)


def test_a_missing_image_is_named(tmp_path: Path) -> None:
    module = DocLayoutYoloSegmenter(detector=lambda _: _detection())
    with pytest.raises(AdapterStepError, match="IMAGE"):
        module.execute(
            {},
            {},
            RunContext(
                document_id="d",
                code_version="1.0",
                pipeline_name="p",
                workspace_uri=str(tmp_path),
            ),
            RunControl(),
        )


def test_a_local_weights_path_wins_over_the_hub(tmp_path: Path) -> None:
    """Hors ligne, ou avec des poids ré-entraînés, le Hub n'a pas à être
    consulté — et un test qui l'interrogerait dépendrait du réseau."""
    poids = tmp_path / "mes-poids.pt"
    poids.write_bytes(b"pas de vrais poids, mais un fichier")
    assert resolve_weights(str(poids)) == str(poids)


def test_registered_under_its_own_kind() -> None:
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build("doclayout_yolo", {})
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.LAYOUT})


def test_it_is_declared_available_to_the_launcher() -> None:
    """Un segmenteur enregistré mais non déclaré serait invisible au lanceur —
    exactement la dérive que le garde-fou des capacités poursuit."""
    from cinoc.app.engines import segmenter_statuses

    kinds = {s.kind for s in segmenter_statuses()}
    assert "doclayout_yolo" in kinds


def test_the_default_threshold_favours_recall() -> None:
    """Un choix, pas un hasard : une région manquée est perdue pour toute la
    chaîne, une région de trop se voit dans le rapport."""
    assert DEFAULT_MIN_SCORE < 0.5
    assert DEFAULT_IMGSZ == 1024

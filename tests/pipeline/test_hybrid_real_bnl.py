"""Pipeline **hybride réel** de bout en bout (le cas d'usage central de Cinoc).

Segmentation externe (ici les régions ABBYY réelles) → **crop** de chaque bloc du
vrai TIFF → **OCR réel par bloc** (Tesseract) → réassemblage → ``region_cer`` par
bloc contre la référence ABBYY. Opt-in (``live``) : binaire Tesseract + Pillow +
``CINOC_BNL_IMAGE`` (TIFF) + ``CINOC_BNL_ALTO`` (ALTO ABBYY de la même page).

Démontre que « module de segmentation → OCR des blocs issus de la segmentation »
tourne sur de la vraie donnée — un YOLO se branche dans le même emplacement
``Module``/cropper.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metrics.layout import region_cer
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

pytestmark = pytest.mark.live


def _skip_unless_ready() -> tuple[str, str]:
    if shutil.which("tesseract") is None:
        pytest.skip("binaire tesseract absent")
    pytest.importorskip("PIL.Image")
    image = os.environ.get("CINOC_BNL_IMAGE")
    alto = os.environ.get("CINOC_BNL_ALTO")
    if not image or not Path(image).is_file() or not alto or not Path(alto).is_file():
        pytest.skip("CINOC_BNL_IMAGE / CINOC_BNL_ALTO non fournis")
    return image, alto


def test_external_segmentation_then_per_block_ocr(tmp_path: Path) -> None:
    image_path, alto_path = _skip_unless_ready()
    from cinoc.adapters.layout.crop import crop_region
    from cinoc.adapters.ocr.tesseract import TesseractAdapter
    from cinoc.evaluation.representations import load_representation
    from cinoc.pipeline.fanout import run_region_fanout

    reference = load_representation(alto_path, ArtifactType.LAYOUT)
    from cinoc.domain.layout import CanonicalLayout

    assert isinstance(reference, CanonicalLayout)
    page_image = Artifact(
        id="bnl:init:image",
        document_id="bnl",
        type=ArtifactType.IMAGE,
        uri=image_path,
    )
    context = RunContext(
        document_id="bnl",
        code_version="1.0",
        pipeline_name="hybrid",
        workspace_uri=str(tmp_path),
    )
    # segmentation externe = régions ABBYY ; OCR par bloc = Tesseract sur le crop.
    filled, _usage = run_region_fanout(
        layout=reference,
        page_image=page_image,
        recognizer=TesseractAdapter(label="tess", lang="deu"),
        context=context,
        control=RunControl(),
        cropper=crop_region,
    )
    score = region_cer.fn(
        DocContext(document_id="bnl", reference=reference, hypothesis=filled)
    )
    assert score is not None
    # Tesseract par bloc vs ABBYY : divergence réelle, non triviale.
    assert 0.0 < score.value < 1.0

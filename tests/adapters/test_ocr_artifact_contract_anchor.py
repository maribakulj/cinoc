"""Ancrage Phase 1 — contrat exact de l'artefact ``RAW_TEXT`` produit par l'OCR.

La Phase 3.2 extraira un ``adapters/ocr/_base.py`` (miroir de ``llm/_base.py``)
pour mutualiser le squelette ``execute()`` dupliqué dans ~12 adapters OCR. Ce
helper devra reproduire **à l'identique** le contrat de l'artefact ``RAW_TEXT`` :

- ``id`` = ``f"{document_id}:{name}:raw_text"`` ;
- ``type`` = ``RAW_TEXT`` ;
- ``content_hash`` = SHA-256 du **texte UTF-8** (pas du fichier, pas d'autre
  encodage) ;
- ``uri`` pointe vers un fichier contenant exactement le texte reconnu.

Le test existant ``test_tesseract.test_execute_writes_output`` ne vérifie que
``content_hash is not None`` et ne fige ni le schéma d'``id`` ni la **valeur** du
hash. On les fige ici, sur le seuil d'injection déterministe de Tesseract (le
binaire est mocké), pour que la factorisation Phase 3.2 soit prouvée iso-contrat.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.ocr.tesseract import TesseractAdapter
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_TEXT = "Texte reconnu — ÿ accents"


def _image(path: Path) -> Artifact:
    return Artifact(
        id="doc1:init:image",
        document_id="doc1",
        type=ArtifactType.IMAGE,
        uri=str(path),
    )


def _ctx(workspace: Path) -> RunContext:
    return RunContext(
        document_id="doc1",
        code_version="t",
        pipeline_name="p",
        workspace_uri=str(workspace),
    )


def _mock_ocr(monkeypatch: pytest.MonkeyPatch, text: str) -> None:
    tsv = "level\tconf\ttext\n5\t93\tmot\n"
    monkeypatch.setattr(
        "cinoc.adapters.ocr.tesseract.run_tesseract",
        lambda **_: {"txt": text.encode("utf-8"), "tsv": tsv.encode("utf-8")},
    )


def test_raw_text_artifact_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mock_ocr(monkeypatch, _TEXT)
    adapter = TesseractAdapter(label="fra", lang="fra")
    out = adapter.execute(
        {ArtifactType.IMAGE: _image(tmp_path / "doc1.png")},
        {},
        _ctx(tmp_path),
        RunControl(),
    )
    artifact = out.artifacts[ArtifactType.RAW_TEXT]

    # Schéma d'identifiant : ``{document_id}:{name}:raw_text`` (name = "tesseract:fra").
    assert artifact.id == "doc1:tesseract:fra:raw_text"
    assert artifact.document_id == "doc1"
    assert artifact.type == ArtifactType.RAW_TEXT
    # Hash = SHA-256 du TEXTE UTF-8 (pas des octets du fichier).
    assert artifact.content_hash == compute_content_hash(_TEXT.encode("utf-8"))
    # L'URI pointe vers un fichier contenant exactement le texte reconnu.
    assert artifact.uri is not None
    assert Path(artifact.uri).read_text(encoding="utf-8") == _TEXT

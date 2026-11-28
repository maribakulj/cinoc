"""L'image d'une page stockée **une fois** dans l'archive, quel que soit le
nombre de pipelines qui la lisent (D20 du pilote D-281).

L'archive recopiait l'image de chaque page sous chaque unité (pipeline ×
document) : 45 Mo pour 10 pages × 4 pipelines, pour 12 Mo de corpus. Elle est
désormais rangée par son contenu (``images/<sha256><suffixe>``) et chaque unité
la nomme relativement à son dossier — la règle d'avant, sans format nouveau :
une archive d'avant se relit telle quelle.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cinoc.app.orchestrator import run
from cinoc.app.resume import ResumeStore
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run_spec import RunSpec
from tests.app.test_resume import _registry, _spec

_IMAGE = b"\x89PNG fake"


def _two_pipelines(tmp_path: Path) -> RunSpec:
    """La spec de ``test_resume``, son pipeline dédoublé (même image lue deux fois)."""
    spec = _spec(tmp_path)
    (pipeline,) = spec.pipelines
    twin = PipelineSpec.model_validate({**pipeline.model_dump(), "name": "p2"})
    return spec.model_copy(update={"pipelines": (pipeline, twin)})


def _copies(archive: Path) -> list[Path]:
    return [p for p in archive.rglob("*") if p.is_file() and p.read_bytes() == _IMAGE]


def _cer(result: object) -> dict[str, float | None]:
    return {
        p.pipeline: next(
            s.value
            for s in result.principal_aggregate(p)  # type: ignore[attr-defined]
            if s.metric == "cer"
        )
        for p in result.pipelines  # type: ignore[attr-defined]
    }


def test_the_page_image_is_stored_once_for_every_pipeline(tmp_path: Path) -> None:
    calls: list[str] = []
    store = ResumeStore(tmp_path / "archive")
    spec = _two_pipelines(tmp_path)

    first = run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)

    assert calls == ["d1", "d1"]
    (copy,) = _copies(store.base_dir)
    assert copy.parent == store.base_dir / "images"
    assert copy.suffix == ".png"
    second = run(
        spec,
        registry=_registry(calls),
        code_version="1.0",
        resume_store=store,
        offline=True,
    )
    assert calls == ["d1", "d1"]
    assert _cer(second) == _cer(first)


def test_a_reloaded_image_points_into_the_archive_store(tmp_path: Path) -> None:
    store = ResumeStore(tmp_path / "archive")
    spec = _two_pipelines(tmp_path)
    run(spec, registry=_registry([]), code_version="1.0", resume_store=store)
    key = next(store.base_dir.glob("*/index.json")).parent.name

    execution = store.load(key)

    assert execution is not None
    image = execution.by_step["__initial__"][ArtifactType.IMAGE]
    assert image.uri is not None
    assert Path(image.uri).parent == store.base_dir / "images"
    assert ".." not in Path(image.uri).parts
    assert Path(image.uri).read_bytes() == _IMAGE


def test_an_archive_of_the_previous_layout_is_still_read(tmp_path: Path) -> None:
    """Avant : l'image recopiée sous chaque unité, nommée sans dossier. Ces
    archives (le pilote, toute archive d'avant) se relisent hors ligne."""
    calls: list[str] = []
    store = ResumeStore(tmp_path / "archive")
    spec = _two_pipelines(tmp_path)
    first = run(spec, registry=_registry(calls), code_version="1.0", resume_store=store)
    for index in store.base_dir.glob("*/index.json"):
        data = json.loads(index.read_bytes())
        for entry in data["steps"]:
            image = entry["artifacts"].get("image")
            if image is not None:
                (index.parent / "__initial__.image.png").write_bytes(_IMAGE)
                image["uri"] = "__initial__.image.png"
        index.write_text(json.dumps(data), encoding="utf-8")
    shutil.rmtree(store.base_dir / "images")

    second = run(
        spec,
        registry=_registry(calls),
        code_version="1.0",
        resume_store=store,
        offline=True,
    )

    assert calls == ["d1", "d1"]
    assert _cer(second) == _cer(first)
    assert len(_copies(store.base_dir)) == 2


@pytest.mark.parametrize("uri", ["../../hors.png", "../images/../../hors.png"])
def test_an_archived_file_outside_the_archive_is_not_read(
    tmp_path: Path, uri: str
) -> None:
    """Une archive se télécharge : un nom relatif qui sort de l'archive n'est
    pas suivi — l'unité est incomplète, donc ré-exécutée (hors ligne : refusée)."""
    store = ResumeStore(tmp_path / "archive")
    spec = _two_pipelines(tmp_path)
    run(spec, registry=_registry([]), code_version="1.0", resume_store=store)
    (tmp_path / "hors.png").write_bytes(_IMAGE)
    index = next(store.base_dir.glob("*/index.json"))
    data = json.loads(index.read_bytes())
    for entry in data["steps"]:
        if "image" in entry["artifacts"]:
            entry["artifacts"]["image"]["uri"] = uri
    index.write_text(json.dumps(data), encoding="utf-8")

    assert store.load(index.parent.name) is None

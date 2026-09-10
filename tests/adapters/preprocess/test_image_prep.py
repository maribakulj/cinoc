"""``ImagePreprocessor`` : le rôle ``image → image``, de bout en bout.

Ce que vérifie ce fichier est le **contrat de brique** — types, déterminisme,
refus explicites, et le fait que le traitement fasse réellement ce qu'il dit sur
une page construite pour ça. Les mathématiques ont leurs tests à part.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cinoc.adapters.preprocess import ImagePreprocessor
from cinoc.adapters.preprocess._ops import estimate_skew, to_grayscale
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

pytest.importorskip("PIL", reason="décodage d'image : extra [images]")


def _page(chemin: Path, *, angle: float = 0.0) -> Path:
    from PIL import Image

    page = np.full((300, 500), 200, dtype=np.uint8)
    for y in range(40, 280, 45):
        page[y : y + 9, 40:460] = 40
    Image.fromarray(page).rotate(
        angle, resample=Image.Resampling.BICUBIC, fillcolor=200
    ).save(chemin)
    return chemin


def _lire(chemin: Path) -> np.ndarray:
    """Le PNG produit, en tableau."""
    from PIL import Image

    with Image.open(chemin) as ouverte:
        return np.asarray(ouverte.convert("L"))


def _executer(module: ImagePreprocessor, source: Path, dossier: Path) -> Path:
    contexte = RunContext(
        document_id="p1",
        workspace_uri=str(dossier),
        code_version="test",
        pipeline_name="p",
    )
    entree = Artifact(
        id="a", document_id="p1", type=ArtifactType.IMAGE, uri=str(source)
    )
    sortie = module.execute({ArtifactType.IMAGE: entree}, {}, contexte, RunControl())
    produit = sortie.artifacts[ArtifactType.IMAGE]
    assert produit.uri is not None
    return Path(produit.uri)


def test_the_brick_declares_image_to_image() -> None:
    module = ImagePreprocessor(label="prep")
    assert module.input_types == frozenset({ArtifactType.IMAGE})
    assert module.output_types == frozenset({ArtifactType.IMAGE})
    assert module.name == "preprocess:prep"


def test_deskew_actually_straightens_the_page(tmp_path: Path) -> None:
    source = _page(tmp_path / "p1.png", angle=3.0)
    module = ImagePreprocessor(label="prep", operations="deskew")

    apres = _lire(_executer(module, source, tmp_path))

    assert estimate_skew(to_grayscale(apres)) == pytest.approx(0.0, abs=0.5)


def test_binarize_leaves_only_two_values(tmp_path: Path) -> None:
    source = _page(tmp_path / "p1.png")
    module = ImagePreprocessor(label="prep", operations="binarize")

    apres = _lire(_executer(module, source, tmp_path))

    assert set(np.unique(apres).tolist()) == {0, 255}


def test_the_output_is_lossless(tmp_path: Path) -> None:
    """PNG, jamais JPEG : un banc ne peut pas mesurer un traitement que
    l'encodage a déjà modifié."""
    source = _page(tmp_path / "p1.png")
    produit = _executer(ImagePreprocessor(label="prep"), source, tmp_path)
    assert produit.suffix == ".png"
    assert produit.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_two_runs_produce_the_same_bytes(tmp_path: Path) -> None:
    """Déterminisme : c'est l'invariant du banc, pas un détail de cette brique."""
    source = _page(tmp_path / "p1.png", angle=2.0)
    module = ImagePreprocessor(label="prep")
    a = _executer(module, source, tmp_path).read_bytes()
    b = _executer(module, source, tmp_path).read_bytes()
    assert a == b


def test_operations_run_in_the_declared_order(tmp_path: Path) -> None:
    """Redresser puis binariser n'est pas binariser puis redresser.

    L'ordre est celui que l'utilisateur écrit : ce sont deux pipelines
    différents, et c'est précisément ce qu'un banc sert à départager.
    """
    source = _page(tmp_path / "p1.png", angle=3.0)
    endroit = _executer(
        ImagePreprocessor(label="a", operations="deskew,binarize"), source, tmp_path
    ).read_bytes()
    envers = _executer(
        ImagePreprocessor(label="b", operations="binarize,deskew"), source, tmp_path
    ).read_bytes()
    assert endroit != envers


def test_an_unknown_operation_is_refused_at_construction() -> None:
    """Nommée au montage, pas découverte en plein run."""
    with pytest.raises(AdapterStepError, match="inconnue"):
        ImagePreprocessor(label="prep", operations="deskew,magie")


def test_an_empty_operation_list_is_refused() -> None:
    """Une étape qui ne fait rien fausserait la comparaison en se faisant passer
    pour un traitement."""
    with pytest.raises(AdapterStepError, match="aucune opération"):
        ImagePreprocessor(label="prep", operations="  ,  ")


def test_a_missing_image_says_so(tmp_path: Path) -> None:
    module = ImagePreprocessor(label="prep")
    contexte = RunContext(
        document_id="p1",
        workspace_uri=str(tmp_path),
        code_version="t",
        pipeline_name="p",
    )
    absente = Artifact(
        id="a",
        document_id="p1",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "fantome.png"),
    )
    with pytest.raises(AdapterStepError, match="introuvable"):
        module.execute({ArtifactType.IMAGE: absente}, {}, contexte, RunControl())


def test_rotation_fills_with_paper_not_ink(tmp_path: Path) -> None:
    """Les coins découverts par une rotation sont du support, pas de l'encre.

    Les combler en noir créerait de fausses zones de texte que la binarisation
    prendrait ensuite au sérieux.
    """
    source = _page(tmp_path / "p1.png", angle=4.0)
    apres = _lire(
        _executer(
            ImagePreprocessor(label="prep", operations="deskew"), source, tmp_path
        )
    )
    coins = [apres[0, 0], apres[0, -1], apres[-1, 0], apres[-1, -1]]
    assert all(int(c) > 128 for c in coins), f"coins sombres : {coins}"

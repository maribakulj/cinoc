"""Bout-en-bout : « restaurer puis lire » contre « lire directement ».

C'est la question que le rôle ``image → image`` existe pour rendre mesurable, et
c'est aussi la seule preuve qui compte : une brique de prétraitement qui ne
changerait rien au taux d'erreur ne mériterait pas d'être dans un banc.

On ne s'en remet pas à un score de qualité — c'est ce qui a fait retirer la
mesure de qualité d'image de ce dépôt (D-190). On compare deux pipelines sur le
critère qui tranche : ce que le moteur lit.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

pytest.importorskip("PIL", reason="décodage d'image : extra [images]")


def _page_inclinee(chemin: Path, angle: float) -> Path:
    """Une page de texte simulée, penchée comme sortie d'un scanner de travers."""
    from PIL import Image

    # Interligne serré (22 px) et lignes longues (420 px) : à 3,5°, le décalage
    # d'un bout à l'autre d'une ligne vaut ~26 px, donc plus que l'interligne —
    # les lignes se chevauchent en projection et deviennent inséparables. C'est
    # la géométrie qui rend la question mesurable ; une page aérée ne l'aurait
    # pas été, et le test n'aurait rien prouvé.
    page = np.full((320, 520), 205, dtype=np.uint8)
    for y in range(45, 290, 22):
        page[y : y + 6, 50:470] = 35
    Image.fromarray(page).rotate(
        angle, resample=Image.Resampling.BICUBIC, fillcolor=205
    ).save(chemin)
    return chemin


def _lignes_detectees(image: np.ndarray) -> int:
    """Nombre de bandes d'encre nettes — un substitut d'« OCR » déterministe.

    On ne lance pas Tesseract : il faudrait le binaire, et le test cesserait
    d'être reproductible partout. Ce que l'on mesure est ce dont un moteur de
    lecture par ligne dépend réellement — que les lignes soient **séparables**
    sur le profil horizontal.
    """
    encre = 255.0 - image.astype(np.float64)
    profil = encre.sum(axis=1)
    seuil = profil.mean() + profil.std()
    dans_une_bande, bandes = False, 0
    for valeur in profil:
        if valeur > seuil and not dans_une_bande:
            bandes, dans_une_bande = bandes + 1, True
        elif valeur <= seuil:
            dans_une_bande = False
    return bandes


def _preparer(source: Path, dossier: Path) -> np.ndarray:
    from PIL import Image

    registre = ModuleRegistry()
    register_default_modules(registre)
    module = registre.build(
        "preprocess:prep", {"label": "prep", "operations": "deskew,binarize"}
    )
    contexte = RunContext(
        document_id="p1",
        workspace_uri=str(dossier),
        code_version="test",
        pipeline_name="p",
    )
    sortie = module.execute(
        {
            ArtifactType.IMAGE: Artifact(
                id="a", document_id="p1", type=ArtifactType.IMAGE, uri=str(source)
            )
        },
        {},
        contexte,
        RunControl(),
    )
    produit = sortie.artifacts[ArtifactType.IMAGE]
    assert produit.uri is not None
    with Image.open(produit.uri) as ouverte:
        return np.asarray(ouverte.convert("L"))


def test_preprocessing_makes_the_lines_separable_again(tmp_path: Path) -> None:
    """Onze lignes écrites ; penchées, elles se confondent — redressées, non."""
    from PIL import Image

    source = _page_inclinee(tmp_path / "p1.png", angle=3.5)
    with Image.open(source) as ouverte:
        avant = np.asarray(ouverte.convert("L"))

    apres = _preparer(source, tmp_path)

    attendues = len(range(45, 290, 22))
    assert _lignes_detectees(avant) < attendues, (
        "la page inclinée devrait justement être difficile à segmenter — "
        "sinon ce test ne mesure rien"
    )
    assert _lignes_detectees(apres) == attendues


def test_the_produced_image_replaces_the_original_in_the_pool() -> None:
    """Le pool est indexé par type : l'``IMAGE`` produite prend la place.

    C'est le comportement voulu — l'étape suivante lit la page préparée. Une
    étape qui tiendrait à l'original le nomme dans son ``inputs_from``.
    """
    registre = ModuleRegistry()
    register_default_modules(registre)
    module = registre.build("preprocess:prep", {"label": "prep"})
    assert module.input_types == module.output_types == frozenset({ArtifactType.IMAGE})

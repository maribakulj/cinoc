"""``ocrd`` — un processeur OCR-D, dont l'unité est un workspace, pas une image.

Ces tests portent sur ce que la brique **traduit** : la préparation du workspace
METS, le refus d'un nom de processeur qui n'en est pas un, et la récolte du seul
XML attendu. Le processeur lui-même est un faux : on teste l'adaptateur, pas
OCR-D.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from cinoc.adapters.layout.ocrd_processor import OcrdProcessor, mime_de
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_PAGE = b"""<?xml version="1.0"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page imageWidth="200" imageHeight="100">
    <TextRegion id="r1"><Coords points="10,10 90,10 90,40 10,40"/></TextRegion>
  </Page>
</PcGts>
"""


def _faux_bin(dossier: Path, *, corps_processeur: str) -> Path:
    """Un ``ocrd`` et un ``ocrd-faux`` qui se comportent comme les vrais."""
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, corps in (
        ("ocrd", "#!/bin/sh\nexit 0\n"),
        ("ocrd-faux", corps_processeur),
    ):
        chemin = dossier / nom
        chemin.write_text(corps, encoding="utf-8")
        chemin.chmod(chemin.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP)
    return dossier


_ECRIT_UN_PAGE = (
    "#!/bin/sh\nmkdir -p OCR-D-SEG\ncat > OCR-D-SEG/page.xml <<'XML'\n"
    + _PAGE.decode()
    + "XML\n"
)


def _executer(tmp_path: Path, corps: str, **kwargs: object) -> object:
    binaires = _faux_bin(tmp_path / "bin", corps_processeur=corps)
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    brique = OcrdProcessor(
        label="t", processor="ocrd-faux", bin_dir=str(binaires), **kwargs
    )
    artefact = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(image), content_hash="0" * 64,
    )
    contexte = RunContext(
        document_id="d", code_version="1", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    return brique.execute(
        {ArtifactType.IMAGE: artefact}, {}, contexte, RunControl()
    )


# --------------------------------------------------------------------------- #
# Ce que la brique refuse
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "nom", ["", "rm", "/bin/sh", "ocrd", "../ocrd-x", "ocrd-x; rm -rf ~"]
)
def test_un_nom_qui_n_est_pas_un_processeur_ocrd_est_refuse(nom: str) -> None:
    """Refusé **à la construction** : au plan, pas à la première page.

    La contrainte restreint ce qu'une spec peut nommer ; elle ne remplace pas le
    refus web (``CLI_ONLY_KINDS``), qui est la vraie frontière.
    """
    with pytest.raises(AdapterStepError, match="processor"):
        OcrdProcessor(label="t", processor=nom)


def test_une_extension_d_image_inconnue_est_refusee() -> None:
    """OCR-D exige le type MIME : le deviner ferait lire l'image de travers."""
    with pytest.raises(AdapterStepError, match="extension"):
        mime_de("page.webp")


def test_un_processeur_absent_du_bin_dir_le_dit(tmp_path: Path) -> None:
    (tmp_path / "bin").mkdir()
    brique = OcrdProcessor(
        label="t", processor="ocrd-absent", bin_dir=str(tmp_path / "bin")
    )
    artefact = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"), content_hash="0" * 64,
    )
    (tmp_path / "p.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    contexte = RunContext(
        document_id="d", code_version="1", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    with pytest.raises(AdapterStepError, match="absent"):
        brique.execute({ArtifactType.IMAGE: artefact}, {}, contexte, RunControl())


def test_un_processeur_en_echec_remonte_son_stderr(tmp_path: Path) -> None:
    corps = "#!/bin/sh\necho 'modele manquant' >&2\nexit 4\n"
    with pytest.raises(AdapterStepError, match="modele manquant"):
        _executer(tmp_path, corps)


def test_aucun_xml_produit_est_refuse(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError, match="aucun XML"):
        _executer(tmp_path, "#!/bin/sh\nmkdir -p OCR-D-SEG\nexit 0\n")


def test_deux_xml_produits_sont_refuses(tmp_path: Path) -> None:
    """En choisir un ferait dépendre le run de l'ordre du système de fichiers."""
    corps = _ECRIT_UN_PAGE + "cp OCR-D-SEG/page.xml OCR-D-SEG/autre.xml\n"
    with pytest.raises(AdapterStepError, match="2 XML"):
        _executer(tmp_path, corps)


# --------------------------------------------------------------------------- #
# Ce que la brique traduit
# --------------------------------------------------------------------------- #


def test_le_page_xml_du_groupe_de_sortie_devient_un_layout(tmp_path: Path) -> None:
    sortie = _executer(tmp_path, _ECRIT_UN_PAGE)

    assert sortie.artifacts[ArtifactType.LAYOUT].uri is not None  # type: ignore[attr-defined]


def test_une_image_deriveee_du_processeur_est_ignoree(tmp_path: Path) -> None:
    """**Le cas réel.** Un processeur OCR-D écrit aussi sa page binarisée.

    Elle vit dans le même groupe de sortie que le XML. Ne garder que le XML
    n'est pas un détail : sans ce filtre, la brique verrait deux fichiers et
    refuserait un run parfaitement valide.
    """
    corps = _ECRIT_UN_PAGE + "printf 'PNG' > OCR-D-SEG/page.IMG-BIN.png\n"

    sortie = _executer(tmp_path, corps)

    assert sortie.artifacts[ArtifactType.LAYOUT].uri is not None  # type: ignore[attr-defined]


def test_les_parametres_sont_passes_en_json_trie(tmp_path: Path) -> None:
    """Trié : deux runs de même spec doivent produire le même fichier.

    C'est l'invariant de déterminisme — le hash des paramètres entre dans le
    manifeste de reproductibilité.
    """
    # argv : -I <grp> -O <grp> -p <fichier>  →  le fichier est $6.
    temoin = tmp_path / "parametres-vus.json"
    corps = _ECRIT_UN_PAGE + f'cp "$6" "{temoin}"\n'
    _executer(tmp_path, corps, parameters={"b": 2, "a": 1})

    assert temoin.read_text(encoding="utf-8") == '{"a": 1, "b": 2}'


def test_la_brique_satisfait_le_protocole_module() -> None:
    brique = OcrdProcessor(label="seg", processor="ocrd-tesserocr-segment")

    assert isinstance(brique, Module)
    assert brique.name == "ocrd:seg"
    assert brique.input_types == frozenset({ArtifactType.IMAGE})
    assert brique.output_types == frozenset({ArtifactType.LAYOUT})
    assert brique.LABELS is None


def test_mime_connus() -> None:
    assert mime_de("a.PNG") == "image/png"
    assert mime_de("a.tiff") == "image/tiff"

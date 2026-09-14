"""``cli_layout`` — brancher un segmenteur sans écrire de Python.

L'interface d'un segmenteur n'est pas l'outil, c'est le **format** : ces tests
portent donc sur les deux seules choses que la brique promet — découper la
commande **sans shell**, et relire le XML **quel que soit son dialecte**.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from cinoc.adapters.layout._base import read_layout
from cinoc.adapters.layout.cli_source import (
    CliLayoutSource,
    _absolu,
    build_argv,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

_PAGE = b"""<?xml version="1.0"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page imageWidth="200" imageHeight="100">
    <TextRegion id="r1">
      <Coords points="10,10 90,10 90,40 10,40"/>
    </TextRegion>
  </Page>
</PcGts>
"""


# --------------------------------------------------------------------------- #
# La garde qui compte
# --------------------------------------------------------------------------- #


def test_un_chemin_biscornu_reste_un_seul_argument() -> None:
    """**Le test le plus important du fichier.**

    La brique exécute une commande. Si la substitution avait lieu *avant* le
    découpage, un chemin contenant ``;`` deviendrait une seconde commande. On
    découpe d'abord : ce qui vient de l'extérieur ne peut plus que **remplir**
    un argument, jamais en créer un.
    """
    argv = build_argv("tool -i {image} -o {out}", "/a/b; rm -rf ~", "/tmp/s")

    assert argv == ["tool", "-i", "/a/b; rm -rf ~", "-o", "/tmp/s"]
    assert "rm" not in argv  # le ``rm`` est *dans* un argument, pas à côté


def test_une_commande_sans_image_est_refusee_a_la_construction() -> None:
    """Refusée au plan, pas à la millième page d'un corpus."""
    with pytest.raises(AdapterStepError, match="image"):
        CliLayoutSource(label="x", command="tool -o {out}")


def test_une_commande_vide_est_refusee() -> None:
    with pytest.raises(AdapterStepError, match="command"):
        CliLayoutSource(label="x", command="   ")


# --------------------------------------------------------------------------- #
# Le format, pas l'outil
# --------------------------------------------------------------------------- #


def test_le_dialecte_est_reconnu_au_contenu_pas_a_l_extension() -> None:
    """PAGE et ALTO sortent tous deux en ``.xml`` : le nom ne tranche rien."""
    layout = read_layout(_PAGE, "test")

    assert len(layout.pages[0].regions) == 1


def test_un_xml_illisible_donne_une_erreur_d_adaptateur() -> None:
    with pytest.raises(AdapterStepError):
        read_layout(b"<PcGts>pas du PAGE</PcGts>", "test")


def test_la_brique_satisfait_le_protocole_module() -> None:
    brique = CliLayoutSource(label="eynollah", command="tool -i {image} -o {out}")

    assert isinstance(brique, Module)
    assert brique.name == "cli_layout:eynollah"
    assert brique.input_types == frozenset({ArtifactType.IMAGE})
    assert brique.output_types == frozenset({ArtifactType.LAYOUT})


def test_le_vocabulaire_n_est_pas_declare() -> None:
    """``None`` dit « je ne me prononce pas » — la brique ignore l'outil.

    Distinct de ``frozenset()``, qui dirait « aucune classe », et que le
    contrôle de cohérence des specs traite, lui, comme une réfutation.
    """
    assert CliLayoutSource(label="x", command="t {image}").LABELS is None


# --------------------------------------------------------------------------- #
# Bout en bout, avec un vrai sous-processus
# --------------------------------------------------------------------------- #


def _executer(tmp_path: Path, script: str, image: Path) -> object:
    outil = tmp_path / "faux_outil.py"
    outil.write_text(script, encoding="utf-8")
    brique = CliLayoutSource(
        label="faux",
        command=f"{sys.executable} {outil} {{image}} {{out}}",
    )
    artefact = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(image),
        content_hash="0" * 64,
    )
    contexte = RunContext(
        document_id="d",
        code_version="1",
        pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    return brique.execute(
        {ArtifactType.IMAGE: artefact}, {}, contexte, RunControl()
    )


def _script_qui_ecrit(nom: str) -> str:
    return (
        "import sys, pathlib\n"
        f"pathlib.Path(sys.argv[2], {nom!r}).write_bytes({_PAGE!r})\n"
    )


_ECRIT_UN_PAGE = _script_qui_ecrit("page.xml")


def test_un_outil_externe_est_relu_de_bout_en_bout(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    sortie = _executer(tmp_path, _ECRIT_UN_PAGE, image)

    layout = sortie.artifacts[ArtifactType.LAYOUT]  # type: ignore[attr-defined]
    assert layout.uri is not None


def test_deux_xml_ecrits_sont_refuses(tmp_path: Path) -> None:
    """En choisir un ferait dépendre le run de l'ordre du système de fichiers.

    C'est l'invariant de déterminisme qui parle ici, pas une préférence.
    """
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    script = _ECRIT_UN_PAGE + _script_qui_ecrit("autre.xml")

    with pytest.raises(AdapterStepError, match="2 fichiers"):
        _executer(tmp_path, script, image)


def test_aucun_xml_ecrit_est_refuse(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")

    with pytest.raises(AdapterStepError, match="aucun"):
        _executer(tmp_path, "import sys\n", image)


def test_un_outil_en_echec_remonte_son_stderr(tmp_path: Path) -> None:
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    script = "import sys\nsys.stderr.write('modele introuvable')\nsys.exit(3)\n"

    with pytest.raises(AdapterStepError, match="modele introuvable"):
        _executer(tmp_path, script, image)


def test_une_commande_introuvable_le_dit(tmp_path: Path) -> None:
    brique = CliLayoutSource(label="x", command="cinoc-outil-inexistant {image}")
    artefact = Artifact(
        id="i",
        document_id="d",
        type=ArtifactType.IMAGE,
        uri=str(tmp_path / "p.png"),
        content_hash="0" * 64,
    )
    contexte = RunContext(
        document_id="d",
        code_version="1",
        pipeline_name="p",
        workspace_uri=str(tmp_path),
    )

    with pytest.raises(AdapterStepError, match="introuvable"):
        brique.execute({ArtifactType.IMAGE: artefact}, {}, contexte, RunControl())


def test_le_chemin_de_l_image_est_rendu_absolu(tmp_path: Path) -> None:
    """**Le cas qui l'a imposé.** Rien ne promet que l'outil reste dans notre
    dossier : un processeur OCR-D fait ``cd`` dans son workspace, et une image
    nommée relativement devient introuvable. Le dossier de sortie est déjà
    absolu ; l'image doit l'être aussi.
    """
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG")
    relatif = os.path.relpath(image, Path.cwd())

    assert Path(_absolu(relatif)).is_absolute()
    assert Path(_absolu(relatif)) == image.resolve()


def test_un_uri_qui_n_est_pas_un_chemin_local_passe_inchange() -> None:
    """On ne résout que ce qui existe — le reste regarde l'outil."""
    assert _absolu("https://exemple.test/p.png") == "https://exemple.test/p.png"

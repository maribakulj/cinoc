"""``ocrd`` — un processeur OCR-D, dont l'unité est un workspace, pas une image.

Ces tests portent sur ce que la brique **traduit** : la préparation du workspace
METS, le refus d'un nom de processeur qui n'en est pas un, et la récolte du seul
XML attendu. Le processeur lui-même est un faux : on teste l'adaptateur, pas
OCR-D.

**Le faux est un objet Python, pas un script.** La première écriture de ces
tests posait de faux exécutables ``#!/bin/sh`` dans un ``bin_dir`` ; ils ont
tenu sur macOS et Linux, et fait tomber six tests sous Windows
(``WinError 193 : %1 is not a valid Win32 application``). Le projet a déjà son
motif pour ça — ``DetectorFn`` dans ``_base.py`` — et la règle qu'il applique :
aucun test ne saute selon le système. La brique accepte donc un ``runner``
injectable.

Reste que le lanceur par défaut, lui, *doit* lancer un vrai processus — c'est
tout son travail. Deux tests s'en chargent (:func:`_lancer_sous_processus`) en
appelant l'interpréteur Python qui fait tourner la suite : un exécutable réel,
présent partout, sur les trois systèmes.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from cinoc.adapters.layout.ocrd_processor import (
    OcrdProcessor,
    _lancer_sous_processus,
    mime_de,
)
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import Module, ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_PAGE = """<?xml version="1.0"?>
<PcGts xmlns="http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15">
  <Page imageWidth="200" imageHeight="100">
    <TextRegion id="r1"><Coords points="10,10 90,10 90,40 10,40"/></TextRegion>
  </Page>
</PcGts>
"""

_GROUPE_SORTIE = "OCR-D-SEG"


class _FauxOcrd:
    """OCR-D en Python : enregistre les appels, produit ce qu'on lui dit.

    Le vrai ``ocrd workspace …`` construit un METS dont la brique ne lit jamais
    rien ; le seul effet qui la concerne est ce que le *processeur* écrit dans
    le groupe de sortie. Le faux se limite donc à ça, et retient le reste pour
    que les tests puissent l'inspecter.
    """

    def __init__(self, produit: Callable[[Path], None] | None = None) -> None:
        self.appels: list[tuple[str, list[str]]] = []
        self.mets_vus: list[str] = []
        self.parametres_vus: str | None = None
        self.arreter_apres_le_premier = False
        self._produit = produit

    def __call__(
        self,
        nom: str,
        args: list[str],
        atelier: Path,
        delai: float,
        control: RunControl,
    ) -> None:
        assert delai > 0, "un délai nul ferait échouer tout vrai processeur"
        self.appels.append((nom, list(args)))
        self.mets_vus.append((atelier / "mets.xml").read_text(encoding="utf-8"))
        if self.arreter_apres_le_premier:
            control.trigger_cancel()
        if "-p" in args:
            reglages = Path(args[args.index("-p") + 1])
            self.parametres_vus = reglages.read_text(encoding="utf-8")
        groupe = atelier / args[args.index("-O") + 1]
        groupe.mkdir(parents=True, exist_ok=True)
        if self._produit is not None and groupe.name == _GROUPE_SORTIE:
            self._produit(groupe)

    @property
    def noms_appeles(self) -> list[str]:
        return [nom for nom, _ in self.appels]


def _ecrit_un_page(groupe: Path) -> None:
    (groupe / "page.xml").write_text(_PAGE, encoding="utf-8")


def _executer(
    tmp_path: Path,
    faux: _FauxOcrd,
    parameters: dict[str, ParamValue] | None = None,
    processor: str = "ocrd-faux",
) -> StepOutput:
    image = tmp_path / "p.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    brique = OcrdProcessor(
        label="t", processor=processor, runner=faux, parameters=parameters
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
    with pytest.raises(AdapterStepError, match="introuvable"):
        brique.execute({ArtifactType.IMAGE: artefact}, {}, contexte, RunControl())


def test_aucun_xml_produit_est_refuse(tmp_path: Path) -> None:
    with pytest.raises(AdapterStepError, match="aucun XML"):
        _executer(tmp_path, _FauxOcrd())


def test_deux_xml_produits_sont_refuses(tmp_path: Path) -> None:
    """En choisir un ferait dépendre le run de l'ordre du système de fichiers."""

    def deux(groupe: Path) -> None:
        _ecrit_un_page(groupe)
        (groupe / "autre.xml").write_text(_PAGE, encoding="utf-8")

    with pytest.raises(AdapterStepError, match="2 XML"):
        _executer(tmp_path, _FauxOcrd(deux))


# --------------------------------------------------------------------------- #
# Ce que la brique traduit
# --------------------------------------------------------------------------- #


def test_le_page_xml_du_groupe_de_sortie_devient_un_layout(tmp_path: Path) -> None:
    sortie = _executer(tmp_path, _FauxOcrd(_ecrit_un_page))

    assert sortie.artifacts[ArtifactType.LAYOUT].uri is not None


def test_le_workspace_est_un_mets_gabarit_ecrit_par_la_brique(tmp_path: Path) -> None:
    """**Un** processus par page et par processeur (audit D-264, défaut 17).

    ``ocrd workspace init`` puis ``add`` coûtaient deux interpréteurs Python de
    plus par page (~2,5 s mesurées, OCR-D 3.13) pour écrire un METS que la
    brique sait écrire : elle le pose, puis lance le seul processeur.
    """
    faux = _FauxOcrd(_ecrit_un_page)

    _executer(tmp_path, faux)

    assert faux.noms_appeles == ["ocrd-faux"]
    mets = faux.mets_vus[0]
    assert 'USE="OCR-D-IMG"' in mets and 'MIMETYPE="image/png"' in mets
    assert 'TYPE="page" ID="P_0001"' in mets
    assert f'xlink:href="{(tmp_path / "p.png").resolve()}"' in mets


def test_le_mets_echappe_le_chemin_de_l_image(tmp_path: Path) -> None:
    image = tmp_path / "a&b <c>.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n")
    faux = _FauxOcrd(_ecrit_un_page)
    brique = OcrdProcessor(label="t", processor="ocrd-faux", runner=faux)
    artefact = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(image), content_hash="0" * 64,
    )
    contexte = RunContext(
        document_id="d", code_version="1", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    brique.execute({ArtifactType.IMAGE: artefact}, {}, contexte, RunControl())
    from cinoc.formats._xml import safe_parse_xml

    racine = safe_parse_xml(faux.mets_vus[0].encode("utf-8"))
    assert racine is not None
    href = racine.find(".//{http://www.loc.gov/METS/}FLocat")
    assert href is not None
    assert href.get("{http://www.w3.org/1999/xlink}href") == str(image.resolve())


def test_une_chaine_de_processeurs_s_enchaine_groupe_par_groupe(
    tmp_path: Path,
) -> None:
    """``processor: ocrd-a,ocrd-b`` : binariser puis segmenter, sans script."""
    faux = _FauxOcrd(_ecrit_un_page)

    _executer(tmp_path, faux, processor="ocrd-binarise, ocrd-segmente")

    assert faux.noms_appeles == ["ocrd-binarise", "ocrd-segmente"]
    assert faux.appels[0][1] == ["-I", "OCR-D-IMG", "-O", "OCR-D-STEP-1"]
    assert faux.appels[1][1] == ["-I", "OCR-D-STEP-1", "-O", _GROUPE_SORTIE]


def test_un_arret_entre_deux_processeurs_n_en_lance_pas_un_de_plus(
    tmp_path: Path,
) -> None:
    from cinoc.domain.errors import RunCancelledError

    faux = _FauxOcrd(_ecrit_un_page)
    faux.arreter_apres_le_premier = True

    with pytest.raises(RunCancelledError):
        _executer(tmp_path, faux, processor="ocrd-a,ocrd-b")
    assert faux.noms_appeles == ["ocrd-a"]


@pytest.mark.parametrize("chaine", ["ocrd-a,,ocrd-b", "ocrd-a,rm", "ocrd-a,"])
def test_une_chaine_mal_formee_est_refusee(chaine: str) -> None:
    with pytest.raises(AdapterStepError, match="processor"):
        OcrdProcessor(label="t", processor=chaine)


def test_des_parametres_python_ne_visent_qu_un_seul_processeur() -> None:
    """``parameters`` est un objet : à quel maillon d'une chaîne irait-il ?
    Plutôt que de deviner, la brique le refuse."""
    with pytest.raises(AdapterStepError, match="parameters"):
        OcrdProcessor(label="t", processor="ocrd-a,ocrd-b", parameters={"x": 1})


def test_une_image_deriveee_du_processeur_est_ignoree(tmp_path: Path) -> None:
    """**Le cas réel.** Un processeur OCR-D écrit aussi sa page binarisée.

    Elle vit dans le même groupe de sortie que le XML. Ne garder que le XML
    n'est pas un détail : sans ce filtre, la brique verrait deux fichiers et
    refuserait un run parfaitement valide.
    """

    def page_et_image(groupe: Path) -> None:
        _ecrit_un_page(groupe)
        (groupe / "page.IMG-BIN.png").write_bytes(b"PNG")

    sortie = _executer(tmp_path, _FauxOcrd(page_et_image))

    assert sortie.artifacts[ArtifactType.LAYOUT].uri is not None


def test_les_parametres_sont_passes_en_json_trie(tmp_path: Path) -> None:
    """Trié : deux runs de même spec doivent produire le même fichier.

    C'est l'invariant de déterminisme — le hash des paramètres entre dans le
    manifeste de reproductibilité.
    """
    faux = _FauxOcrd(_ecrit_un_page)

    _executer(tmp_path, faux, parameters={"b": 2, "a": 1})

    assert faux.parametres_vus == '{"a": 1, "b": 2}'


def test_sans_parametres_aucun_fichier_de_reglages_n_est_passe(tmp_path: Path) -> None:
    """Un ``-p`` vide n'est pas neutre : certains processeurs le refusent."""
    faux = _FauxOcrd(_ecrit_un_page)

    _executer(tmp_path, faux)

    assert "-p" not in faux.appels[-1][1]


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


# --------------------------------------------------------------------------- #
# Le lanceur par défaut : lui, il lance un vrai processus
# --------------------------------------------------------------------------- #


def test_le_lanceur_par_defaut_remonte_le_stderr_du_processeur(tmp_path: Path) -> None:
    """Un processeur qui échoue doit se dire **avec son message**.

    Le cobaye est l'interpréteur qui fait tourner cette suite : un exécutable
    réel, présent sur les trois systèmes, et qu'on peut faire échouer à volonté
    — là où un ``#!/bin/sh`` ne s'exécute pas sous Windows.
    """
    python = Path(sys.executable)
    code = "import sys; sys.stderr.write('modele manquant'); sys.exit(4)"

    with pytest.raises(AdapterStepError, match="modele manquant"):
        _lancer_sous_processus(
            "ocrd:t", str(python.parent), python.name, ["-c", code], tmp_path,
            60.0, RunControl(),
        )


def test_le_lanceur_par_defaut_refuse_un_programme_absent(tmp_path: Path) -> None:
    """Refusé par son nom — pas déguisé en « code de retour 127 »."""
    with pytest.raises(AdapterStepError, match="ocrd-absent.*introuvable"):
        _lancer_sous_processus(
            "ocrd:t", str(tmp_path), "ocrd-absent", [], tmp_path, 60.0, RunControl()
        )


def test_le_lanceur_par_defaut_travaille_dans_l_atelier(tmp_path: Path) -> None:
    """``cwd`` = le workspace : c'est là qu'``ocrd`` attend de trouver son METS."""
    python = Path(sys.executable)
    atelier = tmp_path / "atelier"
    atelier.mkdir()
    code = "import pathlib; pathlib.Path('temoin.txt').write_text('ici')"

    _lancer_sous_processus(
        "ocrd:t", str(python.parent), python.name, ["-c", code], atelier, 60.0,
        RunControl(),
    )

    assert (atelier / "temoin.txt").read_text(encoding="utf-8") == "ici"


def test_le_lanceur_par_defaut_tue_le_processeur_a_l_arret(tmp_path: Path) -> None:
    """Un arrêt du run tue le processeur en vol : il ne finit plus sa page
    (``subprocess.run`` attendait jusqu'au délai, 900 s par défaut)."""
    import threading
    import time

    from cinoc.domain.errors import RunCancelledError

    python = Path(sys.executable)
    control = RunControl()
    threading.Timer(0.3, control.trigger_cancel).start()
    debut = time.monotonic()
    with pytest.raises(RunCancelledError):
        _lancer_sous_processus(
            "ocrd:t", str(python.parent), python.name,
            ["-c", "import time; time.sleep(30)"], tmp_path, 60.0, control,
        )
    assert time.monotonic() - debut < 5.0


def test_le_lanceur_par_defaut_tient_son_delai(tmp_path: Path) -> None:
    from cinoc.domain.errors import DeadlineExceeded

    python = Path(sys.executable)
    with pytest.raises(DeadlineExceeded):
        _lancer_sous_processus(
            "ocrd:t", str(python.parent), python.name,
            ["-c", "import time; time.sleep(30)"], tmp_path, 0.5, RunControl(),
        )


@pytest.mark.live
def test_une_chaine_reelle_ocrd_dummy(tmp_path: Path) -> None:
    """Contre le vrai OCR-D (``ocrd-dummy``, livré avec OCR-D core) : le METS
    gabarit est accepté, la chaîne passe de groupe en groupe et rend un PAGE
    que la brique lit — sans région (``ocrd-dummy`` ne segmente rien), ce
    qu'elle dit, au lieu d'un layout vide."""
    import shutil

    if shutil.which("ocrd-dummy") is None:
        pytest.skip("OCR-D absent (ocrd-dummy introuvable)")
    from PIL import Image

    image = tmp_path / "p.png"
    Image.new("L", (200, 100), 255).save(image)
    brique = OcrdProcessor(label="t", processor="ocrd-dummy,ocrd-dummy")
    artefact = Artifact(
        id="i", document_id="d", type=ArtifactType.IMAGE,
        uri=str(image), content_hash="0" * 64,
    )
    contexte = RunContext(
        document_id="d", code_version="1", pipeline_name="p",
        workspace_uri=str(tmp_path),
    )
    with pytest.raises(AdapterStepError, match="aucune région"):
        brique.execute({ArtifactType.IMAGE: artefact}, {}, contexte, RunControl())

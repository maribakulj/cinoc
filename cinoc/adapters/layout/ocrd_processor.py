"""``OcrdProcessor`` — brancher un **processeur OCR-D**, qui ne voit pas d'image.

Pourquoi une brique distincte de ``cli_layout`` — la question s'est posée, et
la réponse tient au **contrat**, pas à la commodité. ``cli_layout`` parle à un
outil qui prend une image et rend un XML. Un processeur OCR-D ne travaille pas
ainsi : son unité est un **workspace METS**, il lit un *groupe de fichiers* et
en écrit un autre. Faire semblant du contraire demanderait d'enchaîner trois
commandes — c'est-à-dire d'écrire un script shell, hors du dépôt, non testé.
Traduire un contrat étranger vers celui de cinoc est précisément le travail
d'un adaptateur de couche 5 ; c'est donc ici que ça se fait, et nulle part
ailleurs.

Le gain reste le même que pour ``cli_layout`` : **une brique, une famille**.
OCR-D compte une centaine de processeurs (binarisation, redressement,
segmentation, moteurs de reconnaissance), tous pilotés par les mêmes options
normalisées (``-I``, ``-O``, ``-p``, ``-m``). Changer de processeur est un
paramètre, pas un fichier Python :

```yaml
adapter_name: ocrd:segment
adapter_kwargs:
  ocrd:segment:
    label: segment
    processor: ocrd-tesserocr-segment
```

(``parameters`` — un objet — ne s'écrit pas dans une spec, dont les réglages
sont plats ; il n'est donc pas déclaré. Le constructeur l'accepte en Python,
pour un processeur seul.)

**Une chaîne** : ``processor: ocrd-cis-ocropy-binarize,ocrd-tesserocr-segment``
enchaîne les processeurs groupe par groupe (``OCR-D-IMG`` → ``OCR-D-STEP-1`` →
… → ``OCR-D-SEG``) ; le PAGE du dernier est la mise en page.

**Un processus par processeur, rien de plus** (D-301). Le workspace est un METS
**gabarit** écrit par la brique — une page, un fichier, son type MIME — au lieu
de ``ocrd workspace init`` puis ``add`` : deux interpréteurs Python de moins
par page (~2,5 s mesurées, OCR-D 3.13), un gabarit qu'OCR-D accepte tel quel
(vérifié contre ``ocrd-dummy``). Chaque processeur est attendu par tranches
courtes (``adapters._process``) : un arrêt du run le tue en vol et n'en lance
pas un de plus ; le délai de l'étape vaut pour la chaîne entière.

**Périmètre assumé : ``IMAGE → LAYOUT``.** OCR-D enchaîne aussi PAGE → PAGE ;
réinjecter un layout dans un workspace est un autre travail, qu'aucun
consommateur ne demande aujourd'hui — on ne l'écrit donc pas (règle « pas de
consommateur = supprimé »).

**Réservée à la ligne de commande** (:data:`cinoc.app.engines.CLI_ONLY_KINDS`),
comme ``cli_layout`` : la spec nomme un exécutable. Le nom est contraint à
``ocrd-…``, mais une contrainte de nom n'est pas une frontière de confiance —
et « instance privée » veut dire « les gens que je connais », pas « les gens à
qui je confie un exécutable ».
"""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import ClassVar
from xml.sax.saxutils import quoteattr

from cinoc.adapters._params import label_param, timeout_param
from cinoc.adapters._process import wait_or_stop
from cinoc.adapters.layout._base import layout_step_output, read_layout
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

#: 1.1 : METS gabarit et chaîne de processeurs (D-301) — la sortie d'un
#: processeur seul ne change pas, mais le workspace qu'il lit, si.
_VERSION = "1.1"

#: Groupes de fichiers du workspace jetable. Fixes : ils ne sortent jamais de
#: cette brique, donc les exposer n'offrirait qu'une occasion de se tromper.
_GROUPE_ENTREE = "OCR-D-IMG"
_GROUPE_SORTIE = "OCR-D-SEG"
#: Groupe intermédiaire du maillon ``n`` d'une chaîne (``OCR-D-STEP-1``…).
_GROUPE_ETAPE = "OCR-D-STEP-{}"

#: Le workspace d'une page : le METS qu'``ocrd workspace init`` + ``add``
#: écrivaient, sans en-tête daté (rien d'horodaté n'entre dans l'atelier).
_METS = """<?xml version="1.0" encoding="UTF-8"?>
<mets:mets xmlns:mets="http://www.loc.gov/METS/" \
xmlns:xlink="http://www.w3.org/1999/xlink">
  <mets:fileSec>
    <mets:fileGrp USE="{groupe}">
      <mets:file ID="IMG_0001" MIMETYPE={mime}>
        <mets:FLocat LOCTYPE="OTHER" OTHERLOCTYPE="FILE" xlink:href={href}/>
      </mets:file>
    </mets:fileGrp>
  </mets:fileSec>
  <mets:structMap TYPE="PHYSICAL">
    <mets:div TYPE="physSequence">
      <mets:div TYPE="page" ID="P_0001">
        <mets:fptr FILEID="IMG_0001"/>
      </mets:div>
    </mets:div>
  </mets:structMap>
</mets:mets>
"""

#: Un processeur OCR-D se nomme ``ocrd-<quelque chose>`` : c'est la convention
#: du projet, et la contrainte évite qu'une spec ne nomme un exécutable
#: quelconque. Elle **restreint** sans faire office de frontière de confiance :
#: celle-ci est le refus web (``CLI_ONLY_KINDS``).
_NOM_PROCESSEUR = re.compile(r"^ocrd-[A-Za-z0-9][A-Za-z0-9_-]*$")

#: OCR-D exige le type MIME à l'entrée du fichier dans le workspace. On ne
#: devine pas : une image annoncée sous un mauvais type est lue de travers.
_MIMES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

_DEFAULT_TIMEOUT = 900.0

#: Lanceur **injectable** : ``(programme, arguments, dossier, délai, contrôle)``.
#: Le défaut résout le programme puis le fait tourner (et le tue à l'arrêt) ;
#: les tests injectent un faux.
#:
#: Même motif que ``DetectorFn`` dans ``_base.py``, et pour la même raison : un
#: adaptateur se teste sans son outil. Ici le gain est double — les faux
#: exécutables auraient été des scripts ``#!/bin/sh``, donc la première suite du
#: projet à ne pas tourner sous Windows.
RunnerFn = Callable[[str, list[str], Path, float, RunControl], None]


def mime_de(chemin: str) -> str:
    """Type MIME déduit de l'extension, ou refus explicite."""
    suffixe = Path(chemin).suffix.lower()
    mime = _MIMES.get(suffixe)
    if mime is None:
        connus = ", ".join(sorted(_MIMES))
        raise AdapterStepError(
            f"ocrd : extension d'image non gérée ({suffixe!r}). Connues : {connus}."
        )
    return mime


def _resoudre(source: str, bin_dir: str | None, nom: str) -> str:
    """Chemin de l'exécutable, refusé tôt s'il manque.

    ``shutil.which`` plutôt qu'un test d'existence : il vérifie aussi que le
    fichier est *exécutable*, et honore ``PATHEXT``. Un processeur absent doit
    se dire avec son nom — pas se déguiser en « code de retour 127 » à la
    millième page.
    """
    trouve = shutil.which(nom, path=bin_dir) if bin_dir else shutil.which(nom)
    if trouve is None:
        ou = f"dans {bin_dir!r}" if bin_dir else "dans le PATH"
        raise AdapterStepError(
            f"{source} : {nom!r} introuvable {ou}. OCR-D est-il installé "
            "(et son environnement actif) ?"
        )
    return trouve


def processeurs(chaine: str) -> tuple[str, ...]:
    """``"ocrd-a, ocrd-b"`` → ``("ocrd-a", "ocrd-b")``, chaque nom contraint."""
    noms = tuple(nom.strip() for nom in chaine.split(","))
    for nom in noms:
        if not _NOM_PROCESSEUR.match(nom):
            raise AdapterStepError(
                f"ocrd : 'processor' invalide ({chaine!r}). Attendu un nom de "
                "processeur OCR-D, par exemple 'ocrd-tesserocr-segment', ou une "
                "chaîne séparée par des virgules."
            )
    return noms


def _lancer_sous_processus(
    source: str,
    bin_dir: str | None,
    nom: str,
    args: list[str],
    atelier: Path,
    delai: float,
    control: RunControl,
) -> None:
    """Lanceur par défaut : résout le programme, le fait tourner, et le tue à
    l'arrêt du run ou au délai (``wait_or_stop``) — ``stderr`` en fichier,
    pas de tube à remplir."""
    argv = [_resoudre(source, bin_dir, nom), *args]
    logger.info("[ocrd] %s", " ".join(argv))
    journal = atelier / f".{nom}.stderr.log"
    with journal.open("wb") as stderr:
        # ``shell=False`` : aucun argument n'est réinterprété.
        processus = subprocess.Popen(  # noqa: S603
            argv, cwd=atelier, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=stderr,
        )
        # Le délai de l'étape, pas une panne du processeur (D3, D-281).
        code = wait_or_stop(
            processus, timeout=delai, control=control, what=source, subject=nom
        )
    if code != 0:
        detail = journal.read_bytes().decode("utf-8", "replace").strip()[-400:]
        raise AdapterStepError(f"{source} : {nom} a terminé en {code} — {detail}")


class OcrdProcessor:
    """``IMAGE → LAYOUT`` en faisant tourner un processeur OCR-D."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        Param("processor", "str",
              "Processeur OCR-D (ocrd-…), ou chaîne séparée par des virgules",
              "OCR-D processor (ocrd-…), or a comma-separated chain",
              required=True),
        Param("bin_dir", "str", "Dossier des exécutables", "Executables folder"),
        timeout_param(900.0),
    )

    #: Vocabulaire non déclaré : il dépend du processeur choisi, que cette
    #: brique ne connaît pas. ``None`` dit « je ne me prononce pas ».
    LABELS = None

    DOMAIN = "dépend du processeur OCR-D branché"

    def __init__(
        self,
        *,
        label: str,
        processor: str = "",
        parameters: dict[str, ParamValue] | None = None,
        bin_dir: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
        runner: RunnerFn | None = None,
    ) -> None:
        self._chaine = processeurs(processor)
        if parameters and len(self._chaine) > 1:
            raise AdapterStepError(
                "ocrd : 'parameters' vise un processeur seul ; une chaîne "
                f"({processor!r}) n'en dit pas le maillon."
            )
        self._label = label
        self._processor = processor
        self._parameters = dict(parameters or {})
        self._bin_dir = bin_dir
        self._timeout = timeout
        self._runner = runner

    @property
    def name(self) -> str:
        return f"ocrd:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(f"{self.name} : artefact IMAGE sans URI.")
        chemin = Path(image.uri).resolve()
        if not chemin.exists():
            raise AdapterStepError(f"{self.name} : image introuvable ({image.uri}).")
        with tempfile.TemporaryDirectory(prefix="cinoc-ocrd-") as atelier:
            xml = self._traiter(chemin, Path(atelier), context, control)
        return layout_step_output(read_layout(xml, self.name), context, self.name)

    # ---------------------------------------------------------------- interne

    def _executer(
        self, nom: str, args: list[str], atelier: Path, delai: float,
        control: RunControl,
    ) -> None:
        if self._runner is not None:
            self._runner(nom, args, atelier, delai, control)
            return
        _lancer_sous_processus(
            self.name, self._bin_dir, nom, args, atelier, delai, control
        )

    def _traiter(
        self, image: Path, atelier: Path, context: RunContext, control: RunControl
    ) -> bytes:
        fin = time.monotonic() + max(
            1.0, context.deadline.clamp_to_remaining(self._timeout)
        )
        (atelier / "mets.xml").write_text(
            _METS.format(
                groupe=_GROUPE_ENTREE,
                mime=quoteattr(mime_de(str(image))),
                href=quoteattr(str(image)),
            ),
            encoding="utf-8",
        )
        entree = _GROUPE_ENTREE
        for rang, nom in enumerate(self._chaine, start=1):
            control.raise_if_cancelled()
            sortie = (
                _GROUPE_SORTIE if rang == len(self._chaine)
                else _GROUPE_ETAPE.format(rang)
            )
            args = ["-I", entree, "-O", sortie]
            if self._parameters:
                # Trié : deux runs de même spec doivent écrire le même fichier —
                # son empreinte entre dans le manifeste de reproductibilité.
                reglages = atelier / "parametres.json"
                reglages.write_text(
                    json.dumps(self._parameters, sort_keys=True), encoding="utf-8"
                )
                args += ["-p", str(reglages)]
            # Le délai de l'étape vaut pour la chaîne entière.
            reste = fin - time.monotonic()
            if reste <= 0:
                raise DeadlineExceeded(
                    f"{self.name} : délai de l'étape épuisé avant {nom}."
                )
            self._executer(nom, args, atelier, reste, control)
            entree = sortie
        return self._recolter(atelier / _GROUPE_SORTIE)

    def _recolter(self, groupe: Path) -> bytes:
        """Le PAGE-XML du groupe de sortie. **Un seul attendu**, et c'est vérifié.

        Un processeur écrit aussi des images dérivées (binarisée, redressée) dans
        le même groupe : on ne retient que le XML. S'il y en a plusieurs, en
        choisir un ferait dépendre le run de l'ordre du système de fichiers.
        """
        trouves = sorted(p for p in groupe.rglob("*.xml") if p.is_file())
        if not trouves:
            raise AdapterStepError(
                f"{self.name} : {self._chaine[-1]} n'a écrit aucun XML dans "
                f"{_GROUPE_SORTIE}. Est-ce bien un processeur qui produit du PAGE ?"
            )
        if len(trouves) > 1:
            noms = ", ".join(p.name for p in trouves[:5])
            raise AdapterStepError(
                f"{self.name} : {len(trouves)} XML écrits ({noms}…). Un seul est "
                "attendu par page."
            )
        return trouves[0].read_bytes()


__all__ = ["OcrdProcessor", "RunnerFn", "mime_de", "processeurs"]

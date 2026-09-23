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
    parameters: {find_tables: true}
```

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
from collections.abc import Callable
from pathlib import Path

from cinoc.adapters.layout._base import layout_step_output, read_layout
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"

#: Groupes de fichiers du workspace jetable. Fixes : ils ne sortent jamais de
#: cette brique, donc les exposer n'offrirait qu'une occasion de se tromper.
_GROUPE_ENTREE = "OCR-D-IMG"
_GROUPE_SORTIE = "OCR-D-SEG"

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

#: Lanceur **injectable** : ``(programme, arguments, dossier, délai)``. Le défaut
#: résout le programme puis le fait tourner ; les tests injectent un faux.
#:
#: Même motif que ``DetectorFn`` dans ``_base.py``, et pour la même raison : un
#: adaptateur se teste sans son outil. Ici le gain est double — les faux
#: exécutables auraient été des scripts ``#!/bin/sh``, donc la première suite du
#: projet à ne pas tourner sous Windows.
RunnerFn = Callable[[str, list[str], Path, float], None]


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


def _lancer_sous_processus(
    source: str,
    bin_dir: str | None,
    nom: str,
    args: list[str],
    atelier: Path,
    delai: float,
) -> None:
    """Lanceur par défaut : résout le programme, puis le fait tourner."""
    argv = [_resoudre(source, bin_dir, nom), *args]
    logger.info("[ocrd] %s", " ".join(argv))
    try:
        # ``shell=False`` : aucun argument n'est réinterprété.
        fini = subprocess.run(  # noqa: S603
            argv, cwd=atelier, capture_output=True, timeout=delai, check=False
        )
    except subprocess.TimeoutExpired as exc:
        raise AdapterStepError(
            f"{source} : {nom} n'a pas rendu la main en {delai:.0f}s."
        ) from exc
    if fini.returncode != 0:
        detail = fini.stderr.decode("utf-8", "replace").strip()[-400:]
        raise AdapterStepError(
            f"{source} : {nom} a terminé en {fini.returncode} — {detail}"
        )


class OcrdProcessor:
    """``IMAGE → LAYOUT`` en faisant tourner un processeur OCR-D."""

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
        if not _NOM_PROCESSEUR.match(processor):
            raise AdapterStepError(
                f"ocrd : 'processor' invalide ({processor!r}). Attendu un nom de "
                "processeur OCR-D, par exemple 'ocrd-tesserocr-segment'."
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
            xml = self._traiter(chemin, Path(atelier), context)
        return layout_step_output(read_layout(xml, self.name), context, self.name)

    # ---------------------------------------------------------------- interne

    def _executer(self, nom: str, args: list[str], atelier: Path, delai: float) -> None:
        if self._runner is not None:
            self._runner(nom, args, atelier, delai)
            return
        _lancer_sous_processus(self.name, self._bin_dir, nom, args, atelier, delai)

    def _traiter(self, image: Path, atelier: Path, context: RunContext) -> bytes:
        delai = max(1.0, context.deadline.clamp_to_remaining(self._timeout))

        self._executer("ocrd", ["workspace", "init"], atelier, delai)
        self._executer(
            "ocrd",
            ["workspace", "add", "-G", _GROUPE_ENTREE, "-i", "IMG_0001",
             "-g", "P_0001", "-m", mime_de(str(image)), str(image)],
            atelier, delai,
        )

        args = ["-I", _GROUPE_ENTREE, "-O", _GROUPE_SORTIE]
        if self._parameters:
            # Trié : deux runs de même spec doivent écrire le même fichier —
            # son empreinte entre dans le manifeste de reproductibilité.
            reglages = atelier / "parametres.json"
            reglages.write_text(
                json.dumps(self._parameters, sort_keys=True), encoding="utf-8"
            )
            args += ["-p", str(reglages)]
        self._executer(self._processor, args, atelier, delai)

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
                f"{self.name} : {self._processor} n'a écrit aucun XML dans "
                f"{_GROUPE_SORTIE}. Est-ce bien un processeur qui produit du PAGE ?"
            )
        if len(trouves) > 1:
            noms = ", ".join(p.name for p in trouves[:5])
            raise AdapterStepError(
                f"{self.name} : {len(trouves)} XML écrits ({noms}…). Un seul est "
                "attendu par page."
            )
        return trouves[0].read_bytes()


__all__ = ["OcrdProcessor", "RunnerFn", "mime_de"]

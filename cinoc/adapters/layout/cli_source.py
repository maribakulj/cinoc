"""``CliLayoutSource`` — brancher un outil de mise en page **sans écrire de code**.

L'interface d'un segmenteur n'est pas l'outil, c'est le **format**. Le patrimoine
s'est standardisé sur ALTO et PAGE-XML ; un adaptateur par *format* couvre donc
toute une famille d'outils là où un adaptateur par *outil* n'en couvre qu'un.

Cette brique lance une commande, lui donne l'image, et relit le XML qu'elle
écrit. Eynollah, ``kraken segment``, les processeurs OCR-D, dhSegment — tous
parlent PAGE-XML — deviennent des lignes de spec :

```yaml
adapter_name: cli_layout:eynollah
adapter_kwargs:
  cli_layout:eynollah:
    label: eynollah
    command: "eynollah -i {image} -o {out} -m ~/modeles/eynollah"
```

Aucune ligne de Python. C'est la différence entre « écrire un adaptateur » et
« nommer un outil ».

**Sécurité — la raison pour laquelle cette brique est réservée à la CLI.**
Exécuter une commande lue dans une spec est un vecteur d'exécution de code. Une
spec déposée par le web pourrait lancer n'importe quoi, sur une instance
publique **comme privée**. Elle est donc refusée par le lanceur web
inconditionnellement (:data:`cinoc.app.engines.CLI_ONLY_KINDS`), et pas seulement
en mode public : « privé » veut dire « les gens que je connais », pas « les gens
à qui je confie un shell ».

Trois défenses en plus, dans le code :

* **aucun shell.** ``shlex.split`` d'abord, substitution **ensuite**, jeton par
  jeton : un chemin contenant ``; rm -rf`` reste un argument, il ne devient
  jamais une commande. Passer par ``shell=True`` rendrait toute la suite vaine ;
* **sortie confinée** au dossier temporaire que l'étape alloue. L'outil ne
  choisit pas où il écrit, et zéro ou plusieurs ``.xml`` sont refusés — en
  choisir un ferait dépendre le run de l'ordre du système de fichiers ;
* **un layout sans région est refusé bruyamment.** Un XML bien formé mais vide
  se lit sans erreur et rendrait une page blanche, donc un CER de 1,0 **sans
  message** — le pire mode de défaillance d'un banc d'essai.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import tempfile
from pathlib import Path

from cinoc.adapters.layout._base import layout_step_output, read_layout
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"

#: Jetons substitués dans la commande. ``{image}`` est le chemin de la page,
#: ``{out}`` un dossier **vide** que l'étape alloue et nettoie.
IMAGE_TOKEN = "{image}"
OUT_TOKEN = "{out}"

_DEFAULT_TIMEOUT = 600.0


def build_argv(command: str, image: str, out: str) -> list[str]:
    """Commande → ``argv``, **découpée avant substitution**.

    L'ordre n'est pas un détail : découper d'abord garantit qu'un chemin, si
    biscornu soit-il, reste **un** argument. Substituer d'abord puis découper
    laisserait un nom de fichier contenant une espace — ou pire — se scinder en
    plusieurs jetons.
    """
    jetons = shlex.split(command)
    if not jetons:
        raise AdapterStepError("cli_layout : 'command' vide.")
    if not any(IMAGE_TOKEN in j for j in jetons):
        raise AdapterStepError(
            f"cli_layout : la commande ne place pas {IMAGE_TOKEN!r} — l'outil ne "
            "recevrait jamais la page à lire."
        )
    return [j.replace(IMAGE_TOKEN, image).replace(OUT_TOKEN, out) for j in jetons]


def _absolu(uri: str) -> str:
    """Chemin d'image rendu absolu avant d'être donné à l'outil.

    Un chemin relatif vaut par rapport au dossier courant — et rien ne promet
    que l'outil y reste : un enrobage OCR-D fait ``cd`` dans son workspace
    METS, et la page devient introuvable. Le dossier de sortie est déjà absolu
    (il vient de ``TemporaryDirectory``) ; l'image doit l'être aussi.

    On ne résout que ce qui existe : un URI qui n'est pas un chemin local passe
    inchangé, à charge pour l'outil de savoir quoi en faire.
    """
    chemin = Path(uri)
    return str(chemin.resolve()) if chemin.exists() else uri


class CliLayoutSource:
    """``IMAGE → LAYOUT`` en lançant un outil externe qui écrit du PAGE/ALTO."""

    #: Vocabulaire **non déclaré** : il dépend de l'outil branché, que cette
    #: brique ne connaît pas. ``None`` dit « je ne me prononce pas » — et le
    #: contrôle de cohérence ne refuse alors rien, faute de pouvoir réfuter.
    LABELS = None

    DOMAIN = "dépend de l'outil branché"

    def __init__(
        self, *, label: str, command: str = "", timeout: float = _DEFAULT_TIMEOUT
    ) -> None:
        if not command.strip():
            raise AdapterStepError(
                "cli_layout : 'command' requis — c'est tout le contenu de cette "
                "brique."
            )
        # Découpage à la construction : une commande malformée doit être refusée
        # au plan, pas à la première page d'un corpus de mille.
        build_argv(command, "x", "y")
        self._label = label
        self._command = command
        self._timeout = timeout

    @property
    def name(self) -> str:
        return f"cli_layout:{self._label}"

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
        if context.workspace_uri is None:
            raise AdapterStepError(f"{self.name} : workspace requis.")
        with tempfile.TemporaryDirectory(prefix="cinoc-cli-") as sortie:
            xml = self._lancer(_absolu(image.uri), sortie, context)
        return layout_step_output(read_layout(xml, self.name), context, self.name)

    def _lancer(self, image: str, sortie: str, context: RunContext) -> bytes:
        argv = build_argv(self._command, image, sortie)
        delai = max(1.0, context.deadline.clamp_to_remaining(self._timeout))
        logger.info("[cli_layout] %s", " ".join(argv))
        try:
            # ``shell=False`` : c'est la ligne qui rend la substitution sûre.
            fini = subprocess.run(  # noqa: S603
                argv, capture_output=True, timeout=delai, check=False
            )
        except FileNotFoundError as exc:
            raise AdapterStepError(
                f"{self.name} : commande introuvable ({argv[0]!r}). L'outil "
                "est-il installé et dans le PATH ?"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise AdapterStepError(
                f"{self.name} : l'outil n'a pas rendu la main en {delai:.0f}s."
            ) from exc
        if fini.returncode != 0:
            detail = fini.stderr.decode("utf-8", "replace").strip()[:400]
            raise AdapterStepError(
                f"{self.name} : l'outil a terminé en {fini.returncode} — {detail}"
            )
        return self._recolter(Path(sortie))

    def _recolter(self, dossier: Path) -> bytes:
        """Le XML écrit par l'outil. **Un seul attendu**, et c'est vérifié.

        Un outil qui en écrit plusieurs traite sans doute plusieurs pages, ou
        écrit des sous-produits : en choisir un au hasard donnerait un run dont
        le résultat dépend de l'ordre du système de fichiers.
        """
        trouves = sorted(p for p in dossier.rglob("*.xml") if p.is_file())
        if not trouves:
            raise AdapterStepError(
                f"{self.name} : l'outil n'a écrit aucun .xml dans le dossier de "
                f"sortie. La commande place-t-elle bien {OUT_TOKEN!r} ?"
            )
        if len(trouves) > 1:
            noms = ", ".join(p.name for p in trouves[:5])
            raise AdapterStepError(
                f"{self.name} : {len(trouves)} fichiers .xml écrits ({noms}…). "
                "Un seul est attendu par page — en choisir un ferait dépendre le "
                "résultat de l'ordre du système de fichiers."
            )
        return trouves[0].read_bytes()


__all__ = ["IMAGE_TOKEN", "OUT_TOKEN", "CliLayoutSource", "build_argv"]

"""``TesseractAdapter`` — moteur OCR réel (binaire Tesseract 5).

Implémente le ``Module`` Protocol (couche 4) **directement**. L'OCR a lieu dans
le binaire C ``tesseract``, lancé par Cinoc **une fois par page** avec toutes
ses sorties (``_tesseract_cli`` : texte, TSV des confidences, ALTO si demandé)
— ``pytesseract`` le relançait une fois par sortie. Aucune dépendance Python :
importer ce module ne requiert pas le binaire, seule l'exécution l'exige.

Sécurité : ``lang`` est validé (anti-injection ligne de commande), et la ligne
de commande est une liste (aucun shell) ; le délai de l'étape (``timeout``) est
borné par la ``Deadline``, et un arrêt du run tue le binaire. Les
**confidences** par mot (TSV natif, 0-100 → [0,1]) sont écrites en sidecar
JSON (``ConfidenceToken``) et publiées comme artefact ``CONFIDENCES`` —
best-effort : un TSV absent ou illisible dégrade en sidecar vide, jamais en
panne de l'OCR.

**ALTO natif** (``alto=True``) : Tesseract émet en plus un artefact
``ALTO_XML`` (géométrie + texte par mot) — la forme ré-importable dans un outil
de relecture (eScriptorium, Transkribus). Contrairement aux confidences, l'ALTO
est ici le **livrable demandé** : une sortie absente lève
(``AdapterStepError``), elle ne dégrade pas en silence.

**Résolution** (``dpi``). Tesseract déduit la résolution des métadonnées du
fichier quand elle n'est pas donnée. Une numérisation patrimoniale déclare
volontiers 96 DPI alors qu'elle en fait 300 : tesseract en conclut une page de
plus d'un mètre de large et son analyse de mise en page rend « Empty page!! »,
zéro mot, sans erreur — mesuré sur une page de presse de la BnF, 5121 × 7198 px :
aucun mot à la volée, **6 987 mots** avec ``--dpi 300``. Le défaut reste
``None`` : on ne force rien à qui ne demande rien.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from typing import ClassVar

from cinoc.adapters._params import label_param, timeout_param
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.adapters.ocr._tesseract_cli import run_tesseract, tesseract_provenance
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.fanout import REGION_TYPE_PARAM
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

#: Version d'adaptateur. Inchangée par le passage à un seul appel du binaire :
#: texte, confidences et ALTO sont identiques à l'octet (D-300).
_VERSION = "1.0"
DEFAULT_TIMEOUT = 120.0

#: Plafond de réglage. Une valeur au-delà ne protège plus de rien :
#: la deadline du run borne déjà l'étape, et un délai d'une heure sur
#: un sous-processus muet est indiscernable d'un blocage.
_TIMEOUT_MAX = 3600.0

#: Codes langue Tesseract : ISO 639-3 (≥3 lettres ASCII), combinables par ``+``
#: (``fra+lat``). ``lang`` finit sur la ligne de commande tesseract → on refuse
#: tout caractère interprétable comme flag/séparateur (anti-injection).
_LANG_RE = re.compile(r"^[a-zA-Z]{3,}(?:\+[a-zA-Z]{3,})*$")


def tsv_confidences(tsv: str) -> list[ConfidenceToken]:
    """TSV natif de Tesseract → confidences par mot (0-100 → [0, 1]). **Pur.**

    Lecture identique à celle de ``pytesseract.image_to_data``, qu'elle
    remplace : colonnes nommées par l'en-tête, texte en dernière colonne,
    confiance **tronquée à l'entier** (``int(float(…))``) — garder les décimales
    changerait les sidecars des runs existants. Une ligne de structure (page,
    bloc, ligne : ``conf`` = -1, texte vide) n'est pas un mot. Une confiance
    illisible lève ``ValueError`` : l'appelant dégrade en sidecar vide.
    """
    rows = [row.split("\t") for row in tsv.strip().split("\n")]
    if len(rows) < 2:
        return []
    header = rows.pop(0)
    if len(rows[-1]) < len(header):  # dernier mot vide : cellule finale absente
        rows[-1].append("")
    conf_at = header.index("conf")
    tokens: list[ConfidenceToken] = []
    for row in rows:
        word = row[-1].strip() if len(row) >= len(header) else ""
        if not word:
            continue
        value = float(int(float(row[conf_at])))
        if value < 0:  # -1 : entrée non textuelle du TSV
            continue
        tokens.append(ConfidenceToken(text=word, confidence=min(value / 100.0, 1.0)))
    return tokens


def parse_psm_by_class(spec: str) -> dict[str, int]:
    """``"article:6,advertisement:3"`` → ``{"article": 6, "advertisement": 3}``.

    Plat par contrat : les paramètres d'adapter sont des scalaires, donc une
    table se transporte en chaîne. Une entrée malformée **lève** au lieu d'être
    ignorée — un réglage silencieusement perdu ne se voit que dans le CER, des
    heures plus tard.
    """
    table: dict[str, int] = {}
    for morceau in (m.strip() for m in spec.split(",")):
        if not morceau:
            continue
        classe, _, valeur = morceau.partition(":")
        classe = classe.strip()
        if not classe or not valeur.strip().isdigit():
            raise AdapterStepError(
                f"TesseractAdapter : psm_by_class illisible en {morceau!r} "
                "(forme attendue : 'classe:psm', séparées par des virgules)."
            )
        psm = int(valeur)
        if not 0 <= psm <= 13:
            raise AdapterStepError(
                f"TesseractAdapter : psm ∈ [0, 13] pour la classe {classe!r}, "
                f"reçu {psm}."
            )
        table[classe] = psm
    return table


class TesseractAdapter:
    """OCR Tesseract 5 ; écrit le texte dans le workspace, renvoie un ``RAW_TEXT``."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        Param("lang", "str", "Langue(s) (fra+lat)", "Language(s) (fra+lat)",
              default="fra"),
        Param("psm", "int", "Découpe de page (psm)", "Page segmentation (psm)",
              default=6, minimum=0, maximum=13),
        Param("oem", "int", "Moteur (oem)", "Engine mode (oem)",
              default=3, minimum=0, maximum=3),
        Param("alto", "bool", "Produire aussi l'ALTO", "Also produce ALTO",
              default=False),
        Param("psm_by_class", "str", "psm par classe de région (classe:psm,…)",
              "psm per region class (class:psm,…)", default=""),
        Param("dpi", "int", "Résolution imposée (défaut : celle du fichier)",
              "Forced resolution (default: the file's)", minimum=70, maximum=2400),
        timeout_param(DEFAULT_TIMEOUT),
    )

    def __init__(
        self,
        *,
        label: str,
        lang: str = "fra",
        psm: int = 6,
        oem: int = 3,
        alto: bool = False,
        psm_by_class: str = "",
        dpi: int | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(
                f"TesseractAdapter : label invalide {label!r} "
                "(alphanumérique + _ - uniquement)."
            )
        if not _LANG_RE.fullmatch(lang):
            raise AdapterStepError(
                f"TesseractAdapter : lang invalide {lang!r} "
                "(ISO 639-3, combinable par '+' : ex. 'fra+lat')."
            )
        if not 0 <= psm <= 13:
            raise AdapterStepError(f"TesseractAdapter : psm ∈ [0, 13], reçu {psm}.")
        if not 0 <= oem <= 3:
            raise AdapterStepError(f"TesseractAdapter : oem ∈ [0, 3], reçu {oem}.")
        if dpi is not None and not 70 <= dpi <= 2400:
            raise AdapterStepError(
                f"TesseractAdapter : dpi ∈ [70, 2400], reçu {dpi}."
            )
        if not 0 < timeout <= _TIMEOUT_MAX:
            raise AdapterStepError(
                f"TesseractAdapter : timeout ∈ ]0, {_TIMEOUT_MAX:g}] secondes, "
                f"reçu {timeout}."
            )
        self._psm_by_class = parse_psm_by_class(psm_by_class)
        self._label = label
        self._lang = lang
        self._psm = psm
        self._oem = oem
        #: Résolution imposée à tesseract. ``None`` = il la déduit lui-même, ce qui
        #: le trompe quand le fichier déclare une valeur fausse (cf. ``_config``).
        self._dpi = dpi
        #: Délai au-delà duquel le sous-processus est abandonné. Réglable parce
        #: qu'il n'existe pas de bonne valeur universelle : le défaut convient à
        #: une page ordinaire et **perd** une page de 37 Mpx, qu'aucun réglage ne
        #: permettait de rattraper. Toujours borné par la deadline du run, qui
        #: reste l'autorité — ceci n'est qu'un plafond par étape.
        self._timeout = timeout
        #: Émet en plus un artefact ``ALTO_XML`` (ré-import eScriptorium/Transkribus).
        self._alto = alto

    def _psm_for(self, params: Mapping[str, ParamValue]) -> int:
        """Le psm de cette région, ou le psm par défaut.

        Un pavé d'article et une publicité ne se lisent pas au même réglage :
        NDNP-Open-OCR bascule de ``--psm 6`` (bloc uniforme) à ``--psm 3``
        (analyse complète) selon la classe. Sans table, rien ne change — c'est
        le comportement historique, et il reste le défaut.
        """
        if not self._psm_by_class:
            return self._psm
        classe = params.get(REGION_TYPE_PARAM)
        if not isinstance(classe, str) or not classe:
            return self._psm
        return self._psm_by_class.get(classe, self._psm)

    @property
    def name(self) -> str:
        return f"tesseract:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    def system_binaries(self) -> dict[str, str]:
        """Binaire **et** données de langue pour le ``RunManifest`` et la clé
        d'unité (reproductibilité ; D19 du pilote) : la version de
        ``tesseract``, son dossier ``tessdata`` et l'empreinte de chaque
        ``*.traineddata`` lu — un autre ``fra.traineddata`` est une autre unité.

        Hook de **provenance optionnel** (hors ``Module`` Protocol, qui reste le
        contrat d'exécution unique) : l'orchestrateur l'appelle par *duck-typing*
        sur les modules qui l'exposent et fusionne le résultat dans
        ``system_binaries_lock``. Best-effort : binaire absent → ``{}``.
        """
        return tesseract_provenance(
            self._lang, {self._psm, *self._psm_by_class.values()}
        )

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.IMAGE})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        types = {ArtifactType.RAW_TEXT, ArtifactType.CONFIDENCES}
        if self._alto:
            types.add(ArtifactType.ALTO_XML)
        return frozenset(types)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact IMAGE manquant ou sans URI."
            )
        if context.workspace_uri is None:
            raise AdapterStepError(
                f"{self.name} : workspace requis (RunContext.workspace_uri)."
            )
        timeout = max(0.001, context.deadline.clamp_to_remaining(self._timeout))
        # **Un** appel du binaire pour toutes les sorties (D-300).
        produced = run_tesseract(
            image_path=image.uri,
            lang=self._lang,
            psm=self._psm_for(params),
            oem=self._oem,
            dpi=self._dpi,
            renderers=("txt", "tsv", "alto") if self._alto else ("txt", "tsv"),
            workspace=context.workspace_uri,
            timeout=timeout,
            control=control,
        )
        raw = produced.get("txt")
        if raw is None:
            raise AdapterStepError(
                f"tesseract : aucun texte produit pour {image.uri!r}."
            )
        try:
            text = raw.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise AdapterStepError(
                f"tesseract : texte illisible (UTF-8) pour {image.uri!r} : {exc}"
            ) from exc
        output_path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "txt"
        )
        output_path.write_text(text, encoding="utf-8")
        # Confidences best-effort : un TSV absent ou illisible ne doit pas faire
        # échouer un OCR réussi — sidecar vide + avertissement.
        try:
            tokens = tsv_confidences(produced["tsv"].decode("utf-8"))
        except (KeyError, ValueError) as exc:
            logger.warning(
                "[tesseract] confidences dégradées (sidecar vide) : %s", exc
            )
            tokens = []
        sidecar = json.dumps(
            [token.model_dump() for token in tokens], ensure_ascii=False
        ).encode("utf-8")
        sidecar_path = workspace_artifact_path(
            context.workspace_uri,
            context.document_id,
            self._label,
            "confidences.json",
        )
        sidecar_path.write_bytes(sidecar)
        artifacts: dict[ArtifactType, Artifact] = {
            ArtifactType.RAW_TEXT: Artifact(
                id=f"{context.document_id}:{self.name}:raw_text",
                document_id=context.document_id,
                type=ArtifactType.RAW_TEXT,
                uri=str(output_path),
                content_hash=compute_content_hash(text.encode("utf-8")),
            ),
            ArtifactType.CONFIDENCES: Artifact(
                id=f"{context.document_id}:{self.name}:confidences",
                document_id=context.document_id,
                type=ArtifactType.CONFIDENCES,
                uri=str(sidecar_path),
                content_hash=compute_content_hash(sidecar),
            ),
        }
        if self._alto:
            # ALTO demandé → livrable : une sortie absente lève (≠ confidences).
            alto_bytes = produced.get("alto")
            if alto_bytes is None:
                raise AdapterStepError(
                    f"tesseract ALTO : aucune sortie ALTO pour {image.uri!r}."
                )
            alto_path = workspace_artifact_path(
                context.workspace_uri,
                context.document_id,
                self._label,
                "alto.xml",
            )
            alto_path.write_bytes(alto_bytes)
            artifacts[ArtifactType.ALTO_XML] = Artifact(
                id=f"{context.document_id}:{self.name}:alto_xml",
                document_id=context.document_id,
                type=ArtifactType.ALTO_XML,
                uri=str(alto_path),
                content_hash=compute_content_hash(alto_bytes),
            )
        return StepOutput(artifacts=artifacts)


__all__ = ["TesseractAdapter", "parse_psm_by_class", "tsv_confidences"]

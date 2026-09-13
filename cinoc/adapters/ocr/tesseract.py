"""``TesseractAdapter`` — moteur OCR réel (Tesseract 5 via ``pytesseract``).

Implémente le ``Module`` Protocol (couche 4) **directement**. L'OCR a lieu dans
le binaire C ``tesseract`` lancé en sous-processus (le thread relâche le GIL).
``pytesseract`` est un **extra optionnel** (``cinoc[tesseract]``), importé
**paresseusement** dans ``_invoke_tesseract`` : importer ce module ne requiert ni
la lib ni le binaire — seule l'exécution les exige.

Sécurité : ``lang`` est validé (anti-injection ligne de commande) ; ``timeout``
est borné par la ``Deadline`` (un sous-processus figé ne doit pas geler le run).
Les **confidences** par mot (TSV natif, 0-100 → [0,1]) sont écrites en
sidecar JSON (``ConfidenceToken``) et publiées comme artefact ``CONFIDENCES``
— best-effort : un échec d'extraction dégrade en sidecar vide, jamais en
panne de l'OCR.

**ALTO natif** (``alto=True``) : Tesseract émet en plus un artefact
``ALTO_XML`` (géométrie + texte par mot, ``image_to_alto_xml``) — la forme
ré-importable dans un outil de relecture (eScriptorium, Transkribus). Contrairement
aux confidences, l'ALTO est ici le **livrable demandé** : un échec d'émission lève
(``AdapterStepError``), il ne dégrade pas en silence.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
from collections.abc import Callable, Mapping

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.fanout import REGION_TYPE_PARAM
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"
_DEFAULT_TIMEOUT = 120.0

#: Codes langue Tesseract : ISO 639-3 (≥3 lettres ASCII), combinables par ``+``
#: (``fra+lat``). ``lang`` finit sur la ligne de commande tesseract → on refuse
#: tout caractère interprétable comme flag/séparateur (anti-injection).
_LANG_RE = re.compile(r"^[a-zA-Z]{3,}(?:\+[a-zA-Z]{3,})*$")

#: Lanceur de sous-processus, injectable → version sondable en test sans binaire.
BinaryRunner = Callable[..., "subprocess.CompletedProcess[str]"]


def tesseract_binary_version(*, run: BinaryRunner = subprocess.run) -> str | None:
    """Version du binaire ``tesseract`` (1ʳᵉ ligne de ``tesseract --version``).

    **Best-effort, jamais bloquant** : binaire absent, timeout, ou sortie illisible
    → ``None`` (jamais une panne). Sert la **reproductibilité** (``RunManifest`` §12) :
    deux runs ne sont comparables qu'à version de binaire égale — la version
    d'*adapter* (``_VERSION``) ne dit rien du Tesseract réellement installé.
    ``run`` est injecté → la sonde est déterministe en test, sans le binaire.

    Tesseract émet sa bannière tantôt sur ``stdout`` tantôt sur ``stderr`` selon le
    build → on lit les deux et garde la 1ʳᵉ ligne non vide (ex. ``tesseract 5.3.0``).
    """
    try:
        completed = run(
            ["tesseract", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    lines = ((completed.stdout or "") + "\n" + (completed.stderr or "")).splitlines()
    for line in lines:
        if line.strip():
            return line.strip()
    return None


def _invoke_tesseract(  # pragma: no cover -- binaire requis (cf. marqueur 'live')
    *, image_path: str, lang: str, psm: int, oem: int, timeout: float
) -> str:
    """Lance tesseract et renvoie le texte. **Isolé → mockable** (CI sans binaire)."""
    try:
        import pytesseract  # type: ignore[import-not-found, import-untyped]
    except ImportError as exc:
        raise AdapterStepError(
            "tesseract : pytesseract non installé "
            "(pip install 'cinoc[tesseract]' + binaire tesseract)."
        ) from exc
    config = f"--oem {oem} --psm {psm}"
    try:
        text = pytesseract.image_to_string(
            image_path, lang=lang, config=config, timeout=timeout
        )
    except (
        pytesseract.TesseractNotFoundError,
        pytesseract.TesseractError,
        RuntimeError,
    ) as exc:
        raise AdapterStepError(
            f"tesseract a échoué sur {image_path!r} : {type(exc).__name__}: {exc}"
        ) from exc
    return str(text).strip()


def invoke_tesseract_alto(  # pragma: no cover -- binaire requis ('live')
    *, image_path: str, lang: str, psm: int, oem: int, timeout: float
) -> bytes:
    """ALTO XML natif via ``image_to_alto_xml`` (géométrie + texte par mot).

    Renvoie les octets XML bruts (déjà conformes ALTO) — destinés à la
    ré-importation dans un outil de relecture. Une panne du binaire lève
    ``AdapterStepError`` : l'ALTO est le livrable demandé, pas un extra dégradable.
    """
    try:
        import pytesseract  # type: ignore[import-not-found, import-untyped]
    except ImportError as exc:
        raise AdapterStepError(
            "tesseract : pytesseract non installé "
            "(pip install 'cinoc[tesseract]' + binaire tesseract)."
        ) from exc
    try:
        xml = pytesseract.image_to_alto_xml(
            image_path, lang=lang, config=f"--oem {oem} --psm {psm}", timeout=timeout
        )
    except (
        pytesseract.TesseractNotFoundError,
        pytesseract.TesseractError,
        RuntimeError,
    ) as exc:
        raise AdapterStepError(
            f"tesseract ALTO a échoué sur {image_path!r} : "
            f"{type(exc).__name__}: {exc}"
        ) from exc
    return bytes(xml)


def _invoke_tesseract_confidences(  # pragma: no cover -- binaire requis ('live')
    *, image_path: str, lang: str, psm: int, oem: int, timeout: float
) -> list[ConfidenceToken]:
    """Confidences par mot via ``image_to_data`` (TSV natif, conf 0-100)."""
    import pytesseract  # type: ignore[import-not-found]

    data = pytesseract.image_to_data(
        image_path,
        lang=lang,
        config=f"--psm {psm} --oem {oem}",
        timeout=timeout,
        output_type=pytesseract.Output.DICT,
    )
    tokens: list[ConfidenceToken] = []
    for word, conf in zip(data["text"], data["conf"], strict=False):
        if not isinstance(word, str) or not word.strip():
            continue
        value = float(conf)
        if value < 0:  # -1 : entrée non textuelle du TSV
            continue
        tokens.append(
            ConfidenceToken(text=word.strip(), confidence=min(value / 100.0, 1.0))
        )
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

    def __init__(
        self,
        *,
        label: str,
        lang: str = "fra",
        psm: int = 6,
        oem: int = 3,
        alto: bool = False,
        psm_by_class: str = "",
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
        self._psm_by_class = parse_psm_by_class(psm_by_class)
        self._label = label
        self._lang = lang
        self._psm = psm
        self._oem = oem
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
        """Version du **binaire externe** pour le ``RunManifest`` (reproductibilité).

        Hook de **provenance optionnel** (hors ``Module`` Protocol, qui reste le
        contrat d'exécution unique) : l'orchestrateur l'appelle par *duck-typing*
        sur les modules qui l'exposent et fusionne le résultat dans
        ``system_binaries_lock``. Best-effort : binaire absent → ``{}``.
        """
        version = tesseract_binary_version()
        return {"tesseract": version} if version is not None else {}

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
        timeout = max(0.001, context.deadline.clamp_to_remaining(_DEFAULT_TIMEOUT))
        psm = self._psm_for(params)
        text = _invoke_tesseract(
            image_path=image.uri,
            lang=self._lang,
            psm=psm,
            oem=self._oem,
            timeout=timeout,
        )
        output_path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "txt"
        )
        output_path.write_text(text, encoding="utf-8")
        # Confidences best-effort : un échec d'extraction ne doit pas faire
        # échouer un OCR réussi — sidecar vide + avertissement.
        try:
            tokens = _invoke_tesseract_confidences(
                image_path=image.uri,
                lang=self._lang,
                psm=psm,
                oem=self._oem,
                timeout=timeout,
            )
        except (
            AdapterStepError,
            ImportError,
            RuntimeError,
            ValueError,
            OSError,
        ) as exc:
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
            # ALTO demandé → livrable : un échec lève (≠ confidences best-effort).
            alto_bytes = invoke_tesseract_alto(
                image_path=image.uri,
                lang=self._lang,
                psm=psm,
                oem=self._oem,
                timeout=timeout,
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


__all__ = [
    "invoke_tesseract_alto",
    "parse_psm_by_class","TesseractAdapter", "tesseract_binary_version"]

"""Helpers partagés des adapters LLM/VLM (post-correction + transcription).

Les adapters concrets (openai, anthropic, mistral, ollama) implémentent le
``Module`` Protocol et ne fournissent que leurs **appels réseau** (isolés,
mockables). Toute la logique commune — choix des entrées/sorties selon le
**mode**, chargement du texte OCR et/ou de l'image, écriture de l'artefact —
vit **ici**, dans ``run_llm_step`` : un seul endroit, aucun mode dupliqué par
fournisseur (anti « 8+8+8 », cf. CLAUDE.md §8.8).

Modes (``PipelineMode``, source de vérité unique en ``domain``) :

- ``text_only``      — ``RAW_TEXT`` → ``CORRECTED_TEXT`` (le LLM ne voit pas l'image).
- ``text_and_image`` — ``{RAW_TEXT, IMAGE}`` → ``CORRECTED_TEXT`` (le VLM voit l'image).
- ``zero_shot``      — ``IMAGE`` → ``RAW_TEXT`` (transcription directe, sans OCR amont).
"""

from __future__ import annotations

from base64 import b64encode
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, NamedTuple, cast

from cinoc.adapters._native import native_artifact
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.pipeline import PipelineMode
from cinoc.domain.usage import ResourceUsage
from cinoc.formats.text import read_plaintext
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: Prompt de post-correction (modes ``text_only`` / ``text_and_image``) ;
#: ``{ocr_text}`` est substitué par le texte OCR amont.
DEFAULT_CORRECTION_PROMPT = (
    "Tu es un correcteur de transcriptions OCR de documents patrimoniaux. "
    "Corrige uniquement les erreurs manifestes de reconnaissance, sans "
    "reformuler ni moderniser l'orthographe historique. Réponds par le seul "
    "texte corrigé.\n\n{ocr_text}"
)

#: Prompt de transcription directe (mode ``zero_shot`` : le VLM lit l'image).
DEFAULT_TRANSCRIPTION_PROMPT = (
    "Transcris fidèlement le texte de cette image de document patrimonial. "
    "Conserve l'orthographe historique et la ponctuation d'origine. N'ajoute "
    "aucun commentaire : réponds par le seul texte transcrit."
)

#: Extension de fichier → media type (sous-ensemble image courant).
_MEDIA_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

#: Raison d'arrêt **normalisée** d'une réponse, lue dans la réponse native de
#: chaque fournisseur (``finish_reason``, ``stop_reason``, ``done_reason``).
#: ``stop`` : fin naturelle ; ``length`` : coupée par un plafond de jetons (de la
#: requête ou de la fenêtre du modèle) ; ``refusal`` : déclinée ou filtrée ;
#: ``error`` : génération interrompue côté serveur ; ``unknown`` : absente ou hors
#: table (un appel d'outil, une valeur nouvelle) — ni prouvée complète, ni coupée.
StopReason = Literal["stop", "length", "refusal", "error", "unknown"]


def stop_reason_from(native: object, table: Mapping[str, StopReason]) -> StopReason:
    """Valeur native → ``StopReason`` ; ``unknown`` pour tout ce que la table ignore."""
    return table.get(native, "unknown") if isinstance(native, str) else "unknown"


class LLMCompletion(NamedTuple):
    """Réponse d'un fournisseur : texte, jetons (si exposés), raison d'arrêt.

    ``native`` est le **corps** de la réponse dont tout le reste est lu — celui
    qu'écrit le sidecar ``NATIVE_JSON``. Les quatre ``_completion_from_*`` le
    posent toujours : ils lisent ce corps, et le relire depuis le sidecar rend la
    même ``LLMCompletion``. ``None`` n'existe que pour un faux client de test qui
    fabrique une complétion sans réponse.
    """

    text: str
    tokens_in: int | None = None
    tokens_out: int | None = None
    stop_reason: StopReason = "unknown"
    native: object | None = None


def wire_field(data: object, key: str) -> Any:
    """Champ ``key`` d'un objet JSON décodé ; ``None`` s'il manque ou si ``data``
    n'est pas un objet. Les conversions lisent le corps reçu, jamais un objet de
    SDK : c'est ce qui les rend applicables au sidecar."""
    return data.get(key) if isinstance(data, Mapping) else None


#: Réglages d'inférence par défaut, **les mêmes pour les quatre fournisseurs** :
#: un banc qui compare des modèles sous des réglages différents ne compare pas
#: des modèles. ``temperature=0`` + ``seed=0`` : la sortie la plus reproductible
#: qu'une API permette (aucune ne la garantit). ``max_tokens`` borne la sortie —
#: 8 192, le plus haut plafond qu'acceptent **sans flux** tous les modèles visés
#: (le SDK anthropic borne Claude Opus 4 à 8 192 sans flux, et refuse tout modèle
#: au-delà de ~21 000). Une page plus longue — une page de journal dense peut
#: l'être — **se voit** (unité ``truncated``) au lieu d'être notée complète.
DEFAULT_TEMPERATURE = 0.0
DEFAULT_SEED = 0
DEFAULT_MAX_TOKENS = 8192


def _number(
    value: object, key: str, *, low: float, high: float, low_open: bool
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AdapterStepError(f"réglage {key!r} : nombre attendu, reçu {value!r}.")
    number = float(value)
    if (number <= low if low_open else number < low) or number > high:
        borne = "]" if low_open else "["
        raise AdapterStepError(
            f"réglage {key!r} : {number} hors de {borne}{low}, {high}]."
        )
    return number


def _integer(value: object, key: str, *, low: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < low:
        raise AdapterStepError(
            f"réglage {key!r} : entier ≥ {low} attendu, reçu {value!r}."
        )
    return value


@dataclass(frozen=True)
class InferenceSettings:
    """Réglages d'échantillonnage d'un appel LLM/VLM — ``None`` = **non transmis**.

    Une valeur ``None`` laisse le fournisseur décider ; c'est ce que le manifeste
    écrit alors, plutôt qu'un défaut supposé. Construit par :meth:`build`, qui
    valide (les kwargs d'un run viennent d'un YAML : ``temperature: 0`` est un
    entier, ``max_tokens: 12.5`` une erreur à refuser avant le premier appel).
    """

    temperature: float | None = DEFAULT_TEMPERATURE
    top_p: float | None = None
    seed: int | None = DEFAULT_SEED
    max_tokens: int = DEFAULT_MAX_TOKENS

    @classmethod
    def build(
        cls,
        *,
        temperature: object = DEFAULT_TEMPERATURE,
        top_p: object = None,
        seed: object = DEFAULT_SEED,
        max_tokens: object = DEFAULT_MAX_TOKENS,
    ) -> InferenceSettings:
        return cls(
            temperature=(
                None
                if temperature is None
                else _number(
                    temperature, "temperature", low=0.0, high=2.0, low_open=False
                )
            ),
            top_p=(
                None
                if top_p is None
                else _number(top_p, "top_p", low=0.0, high=1.0, low_open=True)
            ),
            seed=None if seed is None else _integer(seed, "seed", low=0),
            max_tokens=_integer(max_tokens, "max_tokens", low=1),
        )

    def as_manifest(self) -> dict[str, float | int | None]:
        """Valeurs **effectives**, défauts compris — ce que le manifeste écrit."""
        return {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "seed": self.seed,
            "max_tokens": self.max_tokens,
        }


#: Appel d'un LLM texte : ``prompt → réponse`` (fournisseur + modèle capturés).
TextInvoke = Callable[[str], LLMCompletion]
#: Appel d'un VLM : ``prompt, media_type, image_b64 → réponse``.
VisionInvoke = Callable[[str, str, str], LLMCompletion]


def usage_tokens(value: Any) -> int | None:
    """Coercition prudente d'un compteur de jetons SDK (``None`` si absent)."""
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def normalize_llm_content(raw: Any) -> str:
    """Aplati une réponse LLM (``str`` ou liste de blocs) en chaîne."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        parts: list[str] = []
        for chunk in raw:
            if isinstance(chunk, str):
                parts.append(chunk)
            elif isinstance(chunk, dict) and isinstance(chunk.get("text"), str):
                parts.append(chunk["text"])
            else:
                text = getattr(chunk, "text", None)
                if isinstance(text, str):
                    parts.append(text)
        return "".join(parts)
    return str(raw)


def validate_llm_label(label: str, adapter: str) -> str:
    """Valide un label d'adapter LLM (alphanum + ``_ -``) et le renvoie.

    Le label compose le ``name`` du module (``<kind>:<label>``) ; le restreindre
    garde les noms de modules sûrs et stables (provenance ``RunManifest``).
    """
    if not label or not all(c.isalnum() or c in "_-" for c in label):
        raise AdapterStepError(
            f"{adapter} : label invalide {label!r} (alphanum + _ -)."
        )
    return label


def validate_role(role: str, adapter: str, supported: frozenset[str]) -> PipelineMode:
    """Valide un mode d'adapter contre ceux que le fournisseur supporte."""
    if role not in supported:
        raise AdapterStepError(
            f"{adapter} : mode {role!r} non supporté "
            f"(modes : {', '.join(sorted(supported))})."
        )
    return cast(PipelineMode, role)


def llm_input_types(role: PipelineMode) -> frozenset[ArtifactType]:
    """Types d'entrée requis par le ``role`` (mode du pipeline)."""
    if role == "text_only":
        return frozenset({ArtifactType.RAW_TEXT})
    if role == "text_and_image":
        return frozenset({ArtifactType.RAW_TEXT, ArtifactType.IMAGE})
    if role == "refine":
        # Reprend une sortie **déjà corrigée** : c'est le seul mode qui ferme la
        # boucle du texte, et donc qui rend une chaîne de correcteurs possible.
        return frozenset({ArtifactType.CORRECTED_TEXT})
    return frozenset({ArtifactType.IMAGE})  # zero_shot


def llm_output_types(role: PipelineMode) -> frozenset[ArtifactType]:
    """Ce que publie une étape LLM/VLM : son texte **et** la réponse native."""
    return frozenset({llm_output_type(role), ArtifactType.NATIVE_JSON})


def llm_output_type(role: PipelineMode) -> ArtifactType:
    """Type produit : ``RAW_TEXT`` en transcription, sinon ``CORRECTED_TEXT``."""
    return (
        ArtifactType.RAW_TEXT
        if role == "zero_shot"
        else ArtifactType.CORRECTED_TEXT
    )


def default_prompt_for_role(role: PipelineMode) -> str:
    """Prompt par défaut adapté au mode (transcription vs correction)."""
    return (
        DEFAULT_TRANSCRIPTION_PROMPT
        if role == "zero_shot"
        else DEFAULT_CORRECTION_PROMPT
    )


def build_prompt(template: str, ocr_text: str) -> str:
    return template.replace("{ocr_text}", ocr_text)


def load_text(
    inputs: dict[ArtifactType, Artifact],
    adapter_name: str,
    *,
    kind: ArtifactType = ArtifactType.RAW_TEXT,
) -> str:
    """Charge le texte d'entrée du ``kind`` demandé.

    ``kind`` distingue le texte **brut** (sortie d'OCR) du texte **déjà
    corrigé** (mode ``refine``) : deux étages d'une chaîne consomment des types
    différents, et confondre les deux ferait re-corriger la sortie d'OCR au lieu
    de reprendre celle du correcteur précédent.
    """
    artifact = inputs.get(kind)
    if artifact is None or artifact.uri is None:
        raise AdapterStepError(
            f"{adapter_name} : input {kind.value.upper()} manquant ou sans URI."
        )
    return read_plaintext(Path(artifact.uri).read_bytes())


def load_ocr_text(inputs: dict[ArtifactType, Artifact], adapter_name: str) -> str:
    """Texte brut d'entrée — conservé pour les appelants existants."""
    return load_text(inputs, adapter_name)


def load_image_b64(
    inputs: dict[ArtifactType, Artifact], adapter_name: str
) -> tuple[str, str]:
    """Charge l'``IMAGE`` d'entrée → ``(media_type, base64)`` pour un VLM."""
    artifact = inputs.get(ArtifactType.IMAGE)
    if artifact is None or artifact.uri is None:
        raise AdapterStepError(
            f"{adapter_name} : input IMAGE manquant ou sans URI."
        )
    path = Path(artifact.uri)
    media_type = _MEDIA_TYPES.get(path.suffix.lower(), "image/png")
    return media_type, b64encode(path.read_bytes()).decode("ascii")


def write_text_artifact(
    workspace_uri: str,
    document_id: str,
    label: str,
    adapter_name: str,
    text: str,
    *,
    output_type: ArtifactType,
) -> dict[ArtifactType, Artifact]:
    """Écrit ``text`` dans le workspace → artefact du type produit par le mode."""
    is_corrected = output_type == ArtifactType.CORRECTED_TEXT
    suffix = "corrected.txt" if is_corrected else "raw.txt"
    output_path = workspace_artifact_path(
        workspace_uri, document_id, label, suffix
    )
    output_path.write_text(text, encoding="utf-8")
    return {
        output_type: Artifact(
            id=f"{document_id}:{adapter_name}:{output_type.value}",
            document_id=document_id,
            type=output_type,
            uri=str(output_path),
            content_hash=compute_content_hash(text.encode("utf-8")),
        )
    }


def run_llm_step(
    *,
    role: PipelineMode,
    label: str,
    name: str,
    prompt: str,
    inputs: dict[ArtifactType, Artifact],
    context: RunContext,
    control: RunControl,
    text_invoke: TextInvoke,
    vision_invoke: VisionInvoke | None,
    max_tokens: int | None = None,
) -> StepOutput:
    """Exécute une étape LLM/VLM selon le ``role`` — logique de mode unique.

    Aiguille sur le mode : charge les bonnes entrées (texte et/ou image), appelle
    l'invocation fournisseur idoine, écrit l'artefact du bon type. ``zero_shot``
    et ``text_and_image`` exigent ``vision_invoke`` (un fournisseur texte-seul,
    ex. ollama, passe ``None`` → ces modes sont refusés proprement). Les jetons
    exposés par le fournisseur remontent dans ``StepOutput.usage`` ; le corps de
    la réponse (``completion.native``) est écrit en sidecar ``NATIVE_JSON``.

    La **raison d'arrêt** décide de l'issue : ``length`` → l'artefact est écrit
    (c'est une sortie réelle, qui sera notée) **et** signalé
    (``StepOutput.truncation``, d'où l'unité ``truncated``) ; ``refusal`` ou
    ``error`` → ``AdapterStepError`` (unité ``failed``, motif ``engine``) — un
    refus filtré n'est pas une transcription, même partielle. ``stop`` et
    ``unknown`` passent : sans preuve de coupure, rien n'est affirmé.
    """
    control.raise_if_cancelled()
    if context.workspace_uri is None:
        raise AdapterStepError(
            f"{name} : workspace requis (RunContext.workspace_uri)."
        )
    if role == "zero_shot":
        if vision_invoke is None:
            raise AdapterStepError(f"{name} : mode zero_shot requiert un VLM (vision).")
        media_type, image_b64 = load_image_b64(inputs, name)
        completion = vision_invoke(prompt, media_type, image_b64)
    elif role == "text_and_image":
        if vision_invoke is None:
            raise AdapterStepError(
                f"{name} : mode text_and_image requiert un VLM (vision)."
            )
        ocr_text = load_ocr_text(inputs, name)
        media_type, image_b64 = load_image_b64(inputs, name)
        completion = vision_invoke(
            build_prompt(prompt, ocr_text), media_type, image_b64
        )
    elif role == "refine":
        # Un correcteur qui reprend un texte corrigé : même invocation, autre
        # entrée. C'est la seule différence, et c'est voulu — un deuxième étage
        # n'est pas un autre outil, c'est le même appliqué plus loin.
        precedent = load_text(inputs, name, kind=ArtifactType.CORRECTED_TEXT)
        completion = text_invoke(build_prompt(prompt, precedent))
    else:  # text_only
        ocr_text = load_ocr_text(inputs, name)
        completion = text_invoke(build_prompt(prompt, ocr_text))
    if completion.stop_reason in ("refusal", "error"):
        cause = (
            "refusée par le fournisseur"
            if completion.stop_reason == "refusal"
            else "interrompue par une erreur du fournisseur"
        )
        raise AdapterStepError(
            f"{name} : réponse {cause} (raison d'arrêt {completion.stop_reason!r}) "
            "— sortie écartée."
        )
    artifacts = write_text_artifact(
        context.workspace_uri,
        context.document_id,
        label,
        name,
        completion.text,
        output_type=llm_output_type(role),
    )
    if completion.native is not None:
        artifacts[ArtifactType.NATIVE_JSON] = native_artifact(
            native=completion.native,
            workspace_uri=context.workspace_uri,
            document_id=context.document_id,
            label=label,
            adapter_name=name,
        )
    usage = (
        ResourceUsage(
            tokens_in=completion.tokens_in, tokens_out=completion.tokens_out
        )
        if completion.tokens_in is not None or completion.tokens_out is not None
        else None
    )
    truncation = None
    if completion.stop_reason == "length":
        plafond = f", max_tokens={max_tokens}" if max_tokens is not None else ""
        truncation = (
            f"{name} : réponse coupée par un plafond de jetons "
            f"(raison d'arrêt 'length'{plafond})"
        )
    return StepOutput(artifacts=artifacts, usage=usage, truncation=truncation)


__all__ = [
    "DEFAULT_CORRECTION_PROMPT",
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_SEED",
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TRANSCRIPTION_PROMPT",
    "InferenceSettings",
    "LLMCompletion",
    "StopReason",
    "TextInvoke",
    "VisionInvoke",
    "build_prompt",
    "default_prompt_for_role",
    "llm_input_types",
    "llm_output_type",
    "llm_output_types",
    "load_image_b64",
    "load_ocr_text",
    "normalize_llm_content",
    "run_llm_step",
    "stop_reason_from",
    "usage_tokens",
    "validate_llm_label",
    "validate_role",
    "wire_field",
    "write_text_artifact",
]

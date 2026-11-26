"""Squelette commun des adapters OCR « image → un seul RAW_TEXT » (couche 5).

Le même ``execute()`` était recopié dans chaque adapter OCR mono-sortie : sonde
d'annulation, garde IMAGE, garde workspace, écriture du ``.txt`` dans le workspace,
construction de l'artefact ``RAW_TEXT`` (id ``{doc}:{name}:raw_text`` + hash du
texte). On le mutualise ici (miroir de ``llm/_base``) ; le **détail moteur** (params,
clé API, deadline) reste dans chaque adapter, porté par la closure ``recognize``.

Un moteur **distant** passe par :func:`run_remote_image_to_text` : même squelette,
mais l'appel rend le corps de la réponse (``call``), le texte en est une lecture
(``extract``), et ce corps est gardé en sidecar ``NATIVE_JSON`` — la lecture se
refait depuis lui, par la même ``extract``, sans re-payer l'appel. Les
confiances par mot, quand la réponse en porte (Azure, Google), en sont une
autre lecture (``confidences``) → sidecar ``CONFIDENCES``, même forme que celui
de Tesseract. Les pages facturées (``BillingMeter``, tentatives comprises)
remontent dans ``StepOutput.usage`` — et accompagnent l'erreur si l'étape échoue
après un appel facturé.

N'est PAS pour les adapters multi-sorties (``tesseract`` : RAW_TEXT + CONFIDENCES
+ ALTO optionnel) — eux gardent leur ``execute()`` propre. Contrat de l'artefact
``RAW_TEXT`` figé par ``tests/adapters/test_ocr_artifact_contract_anchor``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping

from cinoc.adapters._native import native_artifact
from cinoc.adapters._resilience import BillingMeter
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput


def run_image_to_text(
    *,
    name: str,
    label: str,
    inputs: Mapping[ArtifactType, Artifact],
    context: RunContext,
    control: RunControl,
    recognize: Callable[[str], str],
) -> StepOutput:
    """Exécute un OCR image → ``RAW_TEXT`` unique, gardes + persistance mutualisées.

    ``recognize(image_uri) -> texte`` porte la reconnaissance réelle (et ses gardes
    propres : clé API, modèle…). Ordre identique à l'ancien code par adapter :
    annulation → IMAGE → workspace → ``recognize`` → écriture ``.txt`` → artefact.
    """
    return _run(
        name=name, label=label, inputs=inputs, context=context, control=control,
        recognize=lambda uri: (recognize(uri), None),
    )


def run_remote_image_to_text(
    *,
    name: str,
    label: str,
    inputs: Mapping[ArtifactType, Artifact],
    context: RunContext,
    control: RunControl,
    call: Callable[[str, BillingMeter], object],
    extract: Callable[[object], str],
    served: Callable[[object], str | None] | None = None,
    layout: Callable[[object], CanonicalLayout | None] | None = None,
    confidences: Callable[[object], list[ConfidenceToken]] | None = None,
) -> StepOutput:
    """OCR distant : ``RAW_TEXT`` **et** ``NATIVE_JSON`` (le corps de la réponse).

    ``call(image_uri, meter)`` rend le corps JSON décodé de la réponse et compte
    dans ``meter`` ses tentatives facturables ; ``extract`` en lit le texte. Le
    texte n'est jamais lu ailleurs que par ``extract`` — c'est ce qui rend la
    relecture du sidecar identique à l'exécution. ``served``, pour un
    fournisseur qui le rend, lit dans ce même corps le modèle **servi**.
    ``layout``, de même, en projette la mise en page : un ``LAYOUT`` est publié
    **en plus** quand elle rend un ``CanonicalLayout``, rien quand elle rend
    ``None`` (la réponse n'en porte pas). ``confidences`` en lit les confiances
    par mot : un sidecar ``CONFIDENCES`` est **toujours** publié quand elle est
    donnée (vide si la réponse n'en porte pas, comme celui de Tesseract).
    """
    corps: list[object] = []
    meter = BillingMeter()

    def recognize(image_uri: str) -> tuple[str, object]:
        try:
            native = call(image_uri, meter)
            corps.append(native)
            return extract(native), native
        except AdapterStepError as exc:
            # Échec après un appel facturé : la page est payée, l'unité perdue.
            if exc.billed is None:
                exc.billed = meter.usage()
            raise

    output = _run(
        name=name, label=label, inputs=inputs, context=context, control=control,
        recognize=recognize,
    )
    artifacts = dict(output.artifacts)
    mise_en_page = layout(corps[0]) if layout is not None and corps else None
    if mise_en_page is not None and context.workspace_uri is not None:
        artifacts[ArtifactType.LAYOUT] = _layout_artifact(
            mise_en_page, context.workspace_uri, context.document_id, label, name
        )
    if confidences is not None and corps and context.workspace_uri is not None:
        artifacts[ArtifactType.CONFIDENCES] = _confidences_artifact(
            confidences(corps[0]), context.workspace_uri, context.document_id,
            label, name,
        )
    modele = served(corps[0]) if served is not None and corps else None
    return StepOutput(
        artifacts=artifacts,
        served_models=(modele,) if modele is not None else (),
        usage=meter.usage(),
    )


def _confidences_artifact(
    tokens: list[ConfidenceToken],
    workspace_uri: str,
    document_id: str,
    label: str,
    name: str,
) -> Artifact:
    payload = json.dumps(
        [token.model_dump() for token in tokens], ensure_ascii=False
    ).encode("utf-8")
    path = workspace_artifact_path(
        workspace_uri, document_id, label, "confidences.json"
    )
    path.write_bytes(payload)
    return Artifact(
        id=f"{document_id}:{name}:confidences",
        document_id=document_id,
        type=ArtifactType.CONFIDENCES,
        uri=str(path),
        content_hash=compute_content_hash(payload),
    )


def word_confidence(text: object, confidence: object) -> ConfidenceToken | None:
    """Un mot et sa confiance déclarée → jeton, ou ``None`` s'ils n'en font pas
    un : texte vide ou de plus de 256 caractères, confiance absente, non
    numérique ou hors [0, 1] (rien n'est borné ni inventé)."""
    if not isinstance(text, str) or not text.strip() or len(text.strip()) > 256:
        return None
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        return None
    value = float(confidence)
    if not 0.0 <= value <= 1.0:  # NaN y échoue aussi
        return None
    return ConfidenceToken(text=text.strip(), confidence=value)


def _layout_artifact(
    layout: CanonicalLayout,
    workspace_uri: str,
    document_id: str,
    label: str,
    name: str,
) -> Artifact:
    payload = layout.model_dump_json().encode("utf-8")
    path = workspace_artifact_path(workspace_uri, document_id, label, "layout.json")
    path.write_bytes(payload)
    return Artifact(
        id=f"{document_id}:{name}:layout",
        document_id=document_id,
        type=ArtifactType.LAYOUT,
        uri=str(path),
        content_hash=compute_content_hash(payload),
    )


def _run(
    *,
    name: str,
    label: str,
    inputs: Mapping[ArtifactType, Artifact],
    context: RunContext,
    control: RunControl,
    recognize: Callable[[str], tuple[str, object | None]],
) -> StepOutput:
    control.raise_if_cancelled()
    image = inputs.get(ArtifactType.IMAGE)
    if image is None or image.uri is None:
        raise AdapterStepError(f"{name} : artefact IMAGE manquant ou sans URI.")
    if context.workspace_uri is None:
        raise AdapterStepError(f"{name} : workspace requis.")
    text, native = recognize(image.uri)
    output_path = workspace_artifact_path(
        context.workspace_uri, context.document_id, label, "txt"
    )
    output_path.write_text(text, encoding="utf-8")
    artifacts = {
        ArtifactType.RAW_TEXT: Artifact(
            id=f"{context.document_id}:{name}:raw_text",
            document_id=context.document_id,
            type=ArtifactType.RAW_TEXT,
            uri=str(output_path),
            content_hash=compute_content_hash(text.encode("utf-8")),
        )
    }
    if native is not None:
        artifacts[ArtifactType.NATIVE_JSON] = native_artifact(
            native=native,
            workspace_uri=context.workspace_uri,
            document_id=context.document_id,
            label=label,
            adapter_name=name,
        )
    return StepOutput(artifacts=artifacts)


__all__ = ["run_image_to_text", "run_remote_image_to_text", "word_confidence"]

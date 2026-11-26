"""``SpacyNerExtractor`` — extraction d'entités nommées via spaCy (couche 5).

Brique de pipeline ``RAW_TEXT|CORRECTED_TEXT → ENTITIES`` (la NER est une étape
explicite, CLAUDE.md §3). Implémente le ``Module`` Protocol **directement**. Le
SDK ``spacy`` + le **modèle** sont un extra optionnel (``cinoc[ner]`` + ``python
-m spacy download <modèle>``), importés paresseusement.

**Anti-silence (réparation R14 amont, bug du modèle source).** Si spaCy ou le
modèle manque, l'adapter **lève** ``AdapterStepError`` avec le message
d'installation — il ne renvoie **jamais** ``[]`` (le défaut de la source : un
benchmark qui « réussit » avec un rappel 0 sans message). L'orchestrateur isole
alors ce (concurrent × document) ; le document reste simplement non scoré.

L'artefact ``ENTITIES`` embarque **le texte d'entrée** (``{"text", "entities"}``)
— c'est lui qui rend la reprojection R14 auto-suffisante côté évaluation.
"""

from __future__ import annotations

import json
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import Any, ClassVar

from cinoc.adapters._params import label_param, model_param
from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.params import Param
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

logger = logging.getLogger(__name__)

_VERSION = "1.0"

#: Normalisation des labels spaCy vers les conventions courtes HIPE/CoNLL.
_DEFAULT_LABEL_MAPPING: dict[str, str] = {
    "PERSON": "PER",
    "PER": "PER",
    "LOC": "LOC",
    "GPE": "LOC",
    "ORG": "ORG",
    "DATE": "DATE",
    "TIME": "DATE",
    "MISC": "MISC",
}

#: Texte d'entrée accepté : sortie OCR brute **ou** corrigée par un LLM.
_INPUT_TYPES = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})


class SpacyNerExtractor:
    """NER spaCy : ``RAW_TEXT|CORRECTED_TEXT`` → ``ENTITIES`` (fail-closed)."""

    #: Réglages acceptés (``pipeline.params``) : tout autre est refusé, nommé.
    PARAMS: ClassVar[tuple[Param, ...]] = (
        label_param(),
        model_param("Modèle spaCy", "spaCy model", default="fr_core_news_sm"),
    )

    def __init__(
        self,
        *,
        label: str,
        model: str = "fr_core_news_sm",
        loader: Any | None = None,
    ) -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(f"ner : label invalide {label!r}.")
        self._label = label
        self._model = model
        #: Injectable en test : ``(model_name) -> nlp`` ; défaut = ``spacy.load``.
        self._loader = loader
        self._nlp: Any | None = None
        self._model_version: str | None = None

    @property
    def name(self) -> str:
        return f"ner:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return _INPUT_TYPES

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.ENTITIES})

    def system_binaries(self) -> dict[str, str]:
        """Versions spaCy + modèle (reproductibilité), **sans rien charger**.

        Lues dans les métadonnées des distributions installées — spaCy et son
        modèle sont des paquets pip (``fr_core_news_sm``) —, donc connues avant
        la première page : elles entrent dans l'empreinte de l'étape (clé de
        reprise) autant qu'au manifeste. Un modèle déjà chargé fait foi
        (``nlp.meta``, chargeur injecté compris). Rien d'installé → ``{}``.
        """
        out: dict[str, str] = {}
        for distribution, key in (
            ("spacy", "spacy"),
            (self._model, f"spacy_model:{self._model}"),
        ):
            try:
                out[key] = version(distribution)
            except PackageNotFoundError:
                continue
        if self._model_version is not None:
            out[f"spacy_model:{self._model}"] = self._model_version
        return out

    def _load(self) -> Any:
        """Charge le modèle (idempotent). Fail-closed : lève si SDK/modèle absent."""
        if self._nlp is not None:
            return self._nlp
        if self._loader is not None:
            self._nlp = self._loader(self._model)
            self._model_version = self._probe_model_version(self._nlp)
            return self._nlp
        try:
            import spacy  # type: ignore[import-not-found]
        except ImportError as exc:
            raise AdapterStepError(
                "ner : spaCy non installé — `pip install 'cinoc[ner]'`."
            ) from exc
        try:
            self._nlp = spacy.load(self._model)
        except OSError as exc:
            raise AdapterStepError(
                f"ner : modèle spaCy {self._model!r} introuvable — "
                f"`python -m spacy download {self._model}`."
            ) from exc
        self._model_version = self._probe_model_version(self._nlp)
        return self._nlp

    @staticmethod
    def _probe_model_version(nlp: Any) -> str | None:
        meta = getattr(nlp, "meta", None)
        if isinstance(meta, dict):
            version = meta.get("version")
            return str(version) if version is not None else None
        return None

    def _extract(self, text: str) -> list[dict[str, object]]:
        nlp = self._load()
        doc = nlp(text)
        entities: list[dict[str, object]] = []
        for ent in doc.ents:
            label = _DEFAULT_LABEL_MAPPING.get(ent.label_, ent.label_)
            entities.append(
                {
                    "label": label,
                    "start": int(ent.start_char),
                    "end": int(ent.end_char),
                    "text": ent.text,
                }
            )
        return entities

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        source = inputs.get(ArtifactType.CORRECTED_TEXT) or inputs.get(
            ArtifactType.RAW_TEXT
        )
        if source is None or source.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact texte (RAW_TEXT/CORRECTED_TEXT) manquant."
            )
        if context.workspace_uri is None:
            raise AdapterStepError(f"{self.name} : workspace requis.")
        text = _read_text(source.uri, self.name)
        entities = self._extract(text)
        payload = json.dumps(
            {"text": text, "entities": entities}, ensure_ascii=False
        ).encode("utf-8")
        out_path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label, "entities.json"
        )
        out_path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.ENTITIES: Artifact(
                    id=f"{context.document_id}:{self.name}:entities",
                    document_id=context.document_id,
                    type=ArtifactType.ENTITIES,
                    uri=str(out_path),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


def _read_text(uri: str, name: str) -> str:
    from pathlib import Path

    try:
        return Path(uri).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise AdapterStepError(
            f"{name} : texte d'entrée illisible {uri!r} : {exc}"
        ) from exc


__all__ = ["SpacyNerExtractor"]

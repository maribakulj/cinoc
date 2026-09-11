"""Registre + factory de modules (couche 6).

Résout un ``adapter_name`` (convention ``<kind>:<label>``) vers une instance de
``Module`` (couche 4) en appelant un **builder** enregistré pour le ``kind``.
C'est le **seul** point d'extension du produit : le socle est enregistré
**en dur** (``register_default_modules``) ; la **découverte de plugins tiers**
(entry-points ``cinoc.modules``, cf. ``app.modules.discovery``) — même résolution
``name → Module``, source différente.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from cinoc.domain.errors import CinocError
from cinoc.pipeline.protocols import Module, ParamValue

#: Construit une instance de module depuis ses kwargs de construction.
ModuleBuilder = Callable[[Mapping[str, ParamValue]], Module]


class ModuleResolutionError(CinocError):
    """``kind`` inconnu, kwargs invalides, ou nom construit incohérent."""


class ModuleRegistry:
    """Associe un ``kind`` à un builder, et construit les modules d'un run."""

    def __init__(self) -> None:
        self._builders: dict[str, ModuleBuilder] = {}

    def register_builder(self, kind: str, builder: ModuleBuilder) -> None:
        """Enregistre (ou remplace) le builder d'un ``kind``. Idempotent."""
        self._builders[kind] = builder

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))

    def build(self, adapter_name: str, kwargs: Mapping[str, ParamValue]) -> Module:
        """Construit le module ``adapter_name`` (``kind`` = avant le ``:``)."""
        kind = adapter_name.split(":", 1)[0]
        builder = self._builders.get(kind)
        if builder is None:
            raise ModuleResolutionError(
                f"aucun builder pour le kind {kind!r} (module {adapter_name!r})."
            )
        module = builder(kwargs)
        if module.name != adapter_name:
            raise ModuleResolutionError(
                f"module construit {module.name!r} ≠ nom déclaré "
                f"{adapter_name!r} (kwargs incohérents ?)."
            )
        return module


def _build_precomputed(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("source_label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "precomputed : 'source_label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.precomputed import PrecomputedTextAdapter

    return PrecomputedTextAdapter(source_label=label)


def _build_kraken(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    model = kwargs.get("model")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "kraken : 'label' (str) requis dans adapter_kwargs."
        )
    if not isinstance(model, str) or not model:
        raise ModuleResolutionError(
            "kraken : 'model' (chemin .mlmodel) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.kraken import KrakenAdapter

    return KrakenAdapter(label=label, model=model)


def _build_mistral_ocr(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "mistral_ocr : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.mistral_ocr import MistralOCRAdapter

    return MistralOCRAdapter(
        label=label, model=str(kwargs.get("model", "mistral-ocr-latest"))
    )


def _build_pero(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    model = kwargs.get("model")
    if not isinstance(label, str):
        raise ModuleResolutionError("pero : 'label' (str) requis dans adapter_kwargs.")
    if not isinstance(model, str) or not model:
        raise ModuleResolutionError(
            "pero : 'model' (chemin de config PERO) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.pero import PeroAdapter

    return PeroAdapter(label=label, model=model)


def _build_calamari(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    model = kwargs.get("model")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "calamari : 'label' (str) requis dans adapter_kwargs."
        )
    if not isinstance(model, str) or not model:
        raise ModuleResolutionError(
            "calamari : 'model' (checkpoint) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.calamari import CalamariAdapter

    return CalamariAdapter(label=label, model=model)


def _build_google_vision(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "google_vision : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.google_vision import GoogleVisionAdapter

    # `lang` (passé par le planificateur à tout moteur OCR) est ignoré : Vision
    # détecte la langue en `DOCUMENT_TEXT_DETECTION` (pas de hint fragile à mapper).
    return GoogleVisionAdapter(label=label)


def _build_azure_di(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "azure_di : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.azure_di import AzureDocIntelAdapter

    # `lang` (passé par le planificateur à tout moteur OCR) ignoré : le modèle
    # `prebuilt-read` détecte la langue (pas de paramètre de langue à mapper).
    return AzureDocIntelAdapter(label=label)


def _build_tesseract(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "tesseract : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.ocr.tesseract import TesseractAdapter

    return TesseractAdapter(
        label=label,
        lang=str(kwargs.get("lang", "fra")),
        psm=int(kwargs.get("psm", 6)),
        oem=int(kwargs.get("oem", 3)),
        alto=bool(kwargs.get("alto", False)),
    )


def _build_openai(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "openai : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.llm.openai import OpenAIAdapter

    prompt = kwargs.get("prompt")
    return OpenAIAdapter(
        label=label,
        model=str(kwargs.get("model", "gpt-4o-mini")),
        role=str(kwargs.get("role", "text_only")),
        prompt=prompt if isinstance(prompt, str) else None,
    )


def _build_ollama(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "ollama : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.llm.ollama import OllamaAdapter

    prompt = kwargs.get("prompt")
    extra = {"prompt": prompt} if isinstance(prompt, str) else {}
    return OllamaAdapter(
        label=label,
        model=str(kwargs.get("model", "llama3")),
        host=str(kwargs.get("host", "http://localhost:11434")),
        role=str(kwargs.get("role", "text_only")),
        **extra,
    )


def _build_mistral(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "mistral : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.llm.mistral import MistralAdapter

    prompt = kwargs.get("prompt")
    return MistralAdapter(
        label=label,
        model=str(kwargs.get("model", "mistral-small-latest")),
        role=str(kwargs.get("role", "text_only")),
        prompt=prompt if isinstance(prompt, str) else None,
    )


def _build_anthropic(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "anthropic : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.llm.anthropic import AnthropicAdapter

    prompt = kwargs.get("prompt")
    return AnthropicAdapter(
        label=label,
        model=str(kwargs.get("model", "claude-haiku-4-5-20251001")),
        role=str(kwargs.get("role", "text_only")),
        prompt=prompt if isinstance(prompt, str) else None,
    )


def _build_precomputed_layout(kwargs: Mapping[str, ParamValue]) -> Module:
    from cinoc.adapters.layout.precomputed import PrecomputedLayoutSource

    return PrecomputedLayoutSource()


def _build_page_assembler(kwargs: Mapping[str, ParamValue]) -> Module:
    """``page_assembler`` — sortie PAGE XML, ré-importable en relecture.

    Sans paramètre, comme ``alto_assembler`` : un assembleur n'a rien à régler,
    il traduit.
    """
    from cinoc.adapters.layout.page_assembler import PageAssembler  # noqa: PLC0415

    del kwargs
    return PageAssembler()


def _build_vote(kwargs: Mapping[str, ParamValue]) -> Module:
    """``vote:<label>`` — fusionne N transcriptions par vote majoritaire.

    Brique de **fusion** : l'exécuteur l'appelle par ``execute_merge``, sur les
    étapes que ``merge_from`` nomme. Elle ne peut pas être utilisée comme une
    étape ordinaire, et c'est voulu — fusionner exige plusieurs avis.
    """
    from cinoc.adapters.merge import TextVoteMerger  # noqa: PLC0415

    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError("vote : 'label' (str) requis dans adapter_kwargs.")
    return TextVoteMerger(  # type: ignore[return-value]
        label=label, kind=str(kwargs.get("kind", "raw_text"))
    )


def _build_reading_order(kwargs: Mapping[str, ParamValue]) -> Module:
    """``reading_order:<label>`` — ordonne les blocs d'une mise en page.

    ``strategy`` choisit entre la ligne de base (``topdown``) et le regroupement
    en colonnes : ce sont deux hypothèses sur la page, et c'est précisément ce
    qu'un banc sert à départager.
    """
    from cinoc.adapters.layout.reading_order import ReadingOrderModule  # noqa: PLC0415

    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "reading_order : 'label' (str) requis dans adapter_kwargs."
        )
    return ReadingOrderModule(
        label=label, strategy=str(kwargs.get("strategy", "columns"))
    )


def _build_preprocess(kwargs: Mapping[str, ParamValue]) -> Module:
    """``preprocess:<label>`` — prépare l'image avant lecture (``IMAGE → IMAGE``).

    ``operations`` est une chaîne séparée par des virgules : les paramètres
    d'adapter sont plats par contrat, et l'ordre déclaré est respecté tel quel —
    redresser puis binariser n'est pas la même chose que l'inverse.
    """
    from cinoc.adapters.preprocess import ImagePreprocessor  # noqa: PLC0415

    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "preprocess : 'label' (str) requis dans adapter_kwargs."
        )
    operations = kwargs.get("operations", "deskew,binarize")
    amplitude = kwargs.get("skew_amplitude_deg", 5.0)
    return ImagePreprocessor(
        label=label,
        operations=str(operations),
        skew_amplitude_deg=float(amplitude),  # type: ignore[arg-type]
    )


def _build_saknussemm(kwargs: Mapping[str, ParamValue]) -> Module:
    from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector
    from cinoc.adapters.llm._base import validate_llm_label

    return SaknussemmCorrector(
        label=validate_llm_label(str(kwargs["label"]), "SaknussemmCorrector"),
        producer=str(kwargs.get("producer", "rules")),
        model=str(kwargs.get("model", "")),
        host=str(kwargs.get("host", "http://localhost:11434")),
    )


def _build_alto_source(kwargs: Mapping[str, ParamValue]) -> Module:
    from cinoc.adapters.layout.alto_source import AltoLayoutSource

    return AltoLayoutSource(ocr_sidecar=str(kwargs.get("ocr_sidecar", "")))


def _build_pp_doclayout(kwargs: Mapping[str, ParamValue]) -> Module:
    import os

    from cinoc.adapters.layout.pp_doclayout import PPDocLayoutSegmenter

    # Variante du modèle : kwarg explicite > env (l'image Space bake la variante
    # légère via ``CINOC_PPDOCLAYOUT_MODEL=PP-DocLayout-S``) > défaut (-L qualité).
    model = kwargs.get("model")
    if not isinstance(model, str) or not model:
        model = os.environ.get("CINOC_PPDOCLAYOUT_MODEL", "PP-DocLayout-L")
    return PPDocLayoutSegmenter(model=model)


def _build_remote_segmenter(kwargs: Mapping[str, ParamValue]) -> Module:
    endpoint = kwargs.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise ModuleResolutionError(
            "remote_segmenter : 'endpoint' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.layout.remote import RemoteSegmenter

    token = kwargs.get("token")
    min_score = kwargs.get("min_score")
    return RemoteSegmenter(
        endpoint=endpoint,
        token=token if isinstance(token, str) else None,
        min_score=float(min_score) if isinstance(min_score, (int, float)) else 0.5,
    )


def _build_precomputed_region(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("source_label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "precomputed_region : 'source_label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.layout.precomputed import PrecomputedRegionRecognizer

    return PrecomputedRegionRecognizer(source_label=label)


def _build_alto_assembler(kwargs: Mapping[str, ParamValue]) -> Module:
    from cinoc.adapters.layout.assembler import AltoAssembler

    return AltoAssembler()


def _build_layout_to_text(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError(
            "layout_to_text : 'label' (str) requis dans adapter_kwargs."
        )
    from cinoc.adapters.layout.to_text import LayoutToTextExtractor

    return LayoutToTextExtractor(label=label)


def _build_ner(kwargs: Mapping[str, ParamValue]) -> Module:
    label = kwargs.get("label")
    if not isinstance(label, str):
        raise ModuleResolutionError("ner : 'label' (str) requis dans adapter_kwargs.")
    from cinoc.adapters.ner.spacy_extractor import SpacyNerExtractor

    return SpacyNerExtractor(
        label=label, model=str(kwargs.get("model", "fr_core_news_sm"))
    )


def register_default_modules(registry: ModuleRegistry) -> None:
    """Enregistre le socle (starter pack). Aucun effet de bord à l'import."""
    registry.register_builder("precomputed", _build_precomputed)
    registry.register_builder("tesseract", _build_tesseract)
    registry.register_builder("kraken", _build_kraken)
    registry.register_builder("pero", _build_pero)
    registry.register_builder("calamari", _build_calamari)
    registry.register_builder("mistral_ocr", _build_mistral_ocr)
    registry.register_builder("google_vision", _build_google_vision)
    registry.register_builder("azure_di", _build_azure_di)
    registry.register_builder("openai", _build_openai)
    registry.register_builder("ollama", _build_ollama)
    registry.register_builder("mistral", _build_mistral)
    registry.register_builder("anthropic", _build_anthropic)
    # Segmenteurs réels (étape IMAGE → LAYOUT), composables dès aujourd'hui.
    registry.register_builder("pp_doclayout", _build_pp_doclayout)
    registry.register_builder("remote_segmenter", _build_remote_segmenter)
    registry.register_builder("ner", _build_ner)
    # --- Enveloppe T5 : pipeline hybride seg → reconnaissance par région → ALTO ---
    # Ces 3 briques (``Module`` Protocol) sont composées par
    # ``run_planning.plan_hybrid_run`` (finition T5 livrée) : segmentation →
    # reconnaissance par région (fanout, couche 4) → assemblage ALTO. Consommateur
    # vérifié de bout en bout par ``tests/pipeline/test_t5_envelope.py``.
    # Fait entrer un ALTO **existant** dans le banc sans l'aplatir : jusqu'ici
    # un corpus livré avec sa mise en page ne pouvait y entrer qu'en texte.
    registry.register_builder("alto_source", _build_alto_source)
    # Post-correction **dans** la mise en page : l'identite de ligne survit au
    # correcteur, donc l'appariement avant/apres est connu et non devine.
    registry.register_builder("saknussemm", _build_saknussemm)
    registry.register_builder("precomputed_layout", _build_precomputed_layout)
    registry.register_builder("precomputed_region", _build_precomputed_region)
    registry.register_builder("alto_assembler", _build_alto_assembler)
    registry.register_builder("layout_to_text", _build_layout_to_text)
    registry.register_builder("preprocess", _build_preprocess)
    registry.register_builder("reading_order", _build_reading_order)
    registry.register_builder("vote", _build_vote)
    registry.register_builder("page_assembler", _build_page_assembler)


__all__ = [
    "ModuleBuilder",
    "ModuleRegistry",
    "ModuleResolutionError",
    "register_default_modules",
]

"""Registre + factory de modules (couche 6).

Résout un ``adapter_name`` (convention ``<kind>:<label>``) vers une instance de
``Module`` (couche 4) en appelant un **builder** enregistré pour le ``kind``.
C'est le **seul** point d'extension du produit : le socle est enregistré
**en dur** (``register_default_modules``) ; la **découverte de plugins tiers**
(entry-points ``cinoc.modules``, cf. ``app.modules.discovery``) — même résolution
``name → Module``, source différente.

**Les réglages sont vérifiés ici, contre la déclaration de la brique**
(``PARAMS``, ``pipeline.params``) : un réglage inconnu, mal typé, hors bornes
ou un requis absent est refusé **en le nommant**, avant toute construction. Tout
chemin qui construit un module passe par :meth:`ModuleRegistry.build` — le run,
``cinoc run --check``, le dépôt de spec web : le contrôle vaut partout. Une
brique du socle se lit sans être construite (``declared_by``) ; un module tiers
est contrôlé sur la déclaration de sa classe, une fois construit, et n'est pas
contrôlé du tout s'il n'en déclare pas.

Les réglages étant vérifiés d'avance, la plupart des builders du socle se
réduisent à ``Classe(**réglages)`` (:func:`_direct`) : les noms de réglages
**sont** les paramètres du constructeur, et un défaut n'existe qu'à un endroit
de plus que le constructeur — la déclaration, qu'un test confronte à lui.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import Any

from cinoc.app.modules.params import (
    ModuleResolutionError,
    ModuleSettingsError,
    check_settings,
    closest_hint,
)
from cinoc.domain.run_spec import RunSpec
from cinoc.pipeline.params import Param, declared_params
from cinoc.pipeline.protocols import Module, ParamValue

#: Construit une instance de module depuis ses kwargs de construction.
ModuleBuilder = Callable[[Mapping[str, ParamValue]], Module]


def _load_class(path: str) -> Any:
    """``"paquet.module:Classe"`` → la classe (import paresseux : un SDK lourd
    n'est jamais chargé pour lire une déclaration)."""
    module, _, attr = path.partition(":")
    return getattr(importlib.import_module(module), attr)


class ModuleRegistry:
    """Associe un ``kind`` à un builder, et construit les modules d'un run."""

    def __init__(self) -> None:
        self._builders: dict[str, ModuleBuilder] = {}
        self._declared_by: dict[str, str] = {}

    def register_builder(
        self, kind: str, builder: ModuleBuilder, *, declared_by: str | None = None
    ) -> None:
        """Enregistre (ou remplace) le builder d'un ``kind``. Idempotent.

        ``declared_by`` (``"paquet.module:Classe"``) nomme la classe qui porte la
        déclaration ``PARAMS`` : elle se lit alors **sans construire** — pour
        refuser un réglage avant même d'appeler le builder, et pour décrire la
        brique (``cinoc list engines <brique>``).
        """
        self._builders[kind] = builder
        if declared_by is None:
            self._declared_by.pop(kind, None)
        else:
            self._declared_by[kind] = declared_by

    def kinds(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))

    def declared_params(self, kind: str) -> tuple[Param, ...] | None:
        """La déclaration d'un ``kind``, lue sans construire ; ``None`` si elle
        ne se lit qu'à la construction (module tiers) ou n'existe pas."""
        path = self._declared_by.get(kind)
        return None if path is None else declared_params(_load_class(path))

    def build(self, adapter_name: str, kwargs: Mapping[str, ParamValue]) -> Module:
        """Construit le module ``adapter_name`` (``kind`` = avant le ``:``)."""
        kind = adapter_name.split(":", 1)[0]
        builder = self._builders.get(kind)
        if builder is None:
            raise ModuleResolutionError(
                f"aucun builder pour le kind {kind!r} (module {adapter_name!r})."
            )
        params = self.declared_params(kind)
        if params is not None:
            _require_model(adapter_name, params, kwargs)
            check_settings(adapter_name, params, kwargs)
        module = builder(kwargs)
        if module.name != adapter_name:
            raise ModuleResolutionError(
                f"module construit {module.name!r} ≠ nom déclaré "
                f"{adapter_name!r} (kwargs incohérents ?)."
            )
        if params is None:
            # Module tiers : sa déclaration (s'il en a une) se lit sur sa classe.
            tiers = declared_params(module)
            if tiers is not None:
                check_settings(adapter_name, tiers, kwargs)
        return module


def _require_model(
    adapter_name: str, params: tuple[Param, ...], kwargs: Mapping[str, ParamValue]
) -> None:
    """Un modèle **nommé** — aucun défaut (D-268). Absent chez un fournisseur
    qui sait lister les siens : le refus les liste, ou dit pourquoi la liste
    n'a pas pu être lue — plus utile que « réglage requis »."""
    from cinoc.app.models import missing_model_message, model_providers  # noqa: PLC0415

    model = kwargs.get("model")
    if isinstance(model, str) and model.strip():
        return
    if adapter_name.split(":", 1)[0] in model_providers() and any(
        p.name == "model" and p.required for p in params
    ):
        raise ModuleResolutionError(missing_model_message(adapter_name, kwargs))


def _direct(path: str) -> ModuleBuilder:
    """Builder d'une brique dont les réglages **sont** les paramètres du
    constructeur : vérifiés d'avance contre sa déclaration, passés tels quels."""

    def build(kwargs: Mapping[str, ParamValue]) -> Module:
        return _load_class(path)(**dict(kwargs))  # type: ignore[no-any-return]

    return build


def _llm(path: str) -> ModuleBuilder:
    """Builder d'un adapter LLM/VLM : ``prompt_name`` (un prompt curé) est résolu
    en ``prompt`` — la règle du composeur web, ``resolve_prompt`` — puis tout le
    reste passe tel quel. C'est donc le **texte** du prompt qui atteint
    l'adapter, son manifeste et l'empreinte de l'étape."""

    def build(kwargs: Mapping[str, ParamValue]) -> Module:
        from cinoc.prompts import PromptError, resolve_prompt  # noqa: PLC0415

        reglages: dict[str, Any] = dict(kwargs)
        name = reglages.pop("prompt_name", None)
        if name is not None:
            prompt = reglages.get("prompt")
            try:
                reglages["prompt"] = resolve_prompt(
                    prompt if isinstance(prompt, str) else None, str(name)
                )
            except PromptError as exc:
                raise ModuleResolutionError(
                    f"{path.rsplit(':', 1)[1]} : {exc} (cinoc list prompts)"
                ) from exc
        return _load_class(path)(**reglages)  # type: ignore[no-any-return]

    return build


def _build_saknussemm(kwargs: Mapping[str, ParamValue]) -> Module:
    """Le libellé suit la règle des LLM : il nomme une brique qui en appelle un."""
    from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector
    from cinoc.adapters.llm._base import validate_llm_label

    reglages: dict[str, Any] = dict(kwargs)
    reglages["label"] = validate_llm_label(str(kwargs["label"]), "SaknussemmCorrector")
    return SaknussemmCorrector(**reglages)


def _build_pp_doclayout(kwargs: Mapping[str, ParamValue]) -> Module:
    import os

    from cinoc.adapters.layout.pp_doclayout import PPDocLayoutSegmenter

    # Variante du modèle : kwarg explicite > env (l'image Space bake la variante
    # légère via ``CINOC_PPDOCLAYOUT_MODEL=PP-DocLayout-S``) > défaut (-L qualité).
    model = kwargs.get("model")
    if not isinstance(model, str) or not model:
        model = os.environ.get("CINOC_PPDOCLAYOUT_MODEL", "PP-DocLayout-L")
    label = kwargs.get("label")
    return PPDocLayoutSegmenter(
        model=model, label=label if isinstance(label, str) else None
    )


_A = "cinoc.adapters."

#: Le socle : ``kind → (classe déclarante, builder)``. Builder absent = direct.
#:
#: Quelques notes que les builders portaient et qui restent vraies :
#: ``google_vision`` et ``azure_di`` détectent la langue (aucun ``lang``) ;
#: ``tesseract`` sans ``dpi`` croit les métadonnées du fichier, qui mentent
#: souvent sur les numérisations patrimoniales ; ``cli_layout`` et ``ocrd``
#: exécutent ce que la spec nomme — **réservés à la CLI** (``CLI_ONLY_KINDS``) ;
#: ``vote`` et ``gap_fill`` sont des briques de **fusion**, appelées par
#: ``execute_merge`` sur les étapes que ``merge_from`` nomme ; ``alto_source``
#: fait entrer un ALTO existant sans l'aplatir ; ``saknussemm`` corrige **dans**
#: la mise en page (l'identité de ligne survit au correcteur).
_SOCLE: tuple[tuple[str, str, ModuleBuilder | None], ...] = (
    ("precomputed", "ocr.precomputed:PrecomputedTextAdapter", None),
    ("tesseract", "ocr.tesseract:TesseractAdapter", None),
    ("kraken", "ocr.kraken:KrakenAdapter", None),
    ("pero", "ocr.pero:PeroAdapter", None),
    ("calamari", "ocr.calamari:CalamariAdapter", None),
    ("mistral_ocr", "ocr.mistral_ocr:MistralOCRAdapter", None),
    ("google_vision", "ocr.google_vision:GoogleVisionAdapter", None),
    ("azure_di", "ocr.azure_di:AzureDocIntelAdapter", None),
    ("openai", "llm.openai:OpenAIAdapter", _llm(_A + "llm.openai:OpenAIAdapter")),
    ("ollama", "llm.ollama:OllamaAdapter", _llm(_A + "llm.ollama:OllamaAdapter")),
    ("mistral", "llm.mistral:MistralAdapter", _llm(_A + "llm.mistral:MistralAdapter")),
    (
        "anthropic",
        "llm.anthropic:AnthropicAdapter",
        _llm(_A + "llm.anthropic:AnthropicAdapter"),
    ),
    # Segmenteurs réels (étape IMAGE → LAYOUT).
    ("pp_doclayout", "layout.pp_doclayout:PPDocLayoutSegmenter", _build_pp_doclayout),
    ("doclayout_yolo", "layout.doclayout_yolo:DocLayoutYoloSegmenter", None),
    ("tesseract_layout", "layout.tesseract_layout:TesseractLayoutSegmenter", None),
    ("cli_layout", "layout.cli_source:CliLayoutSource", None),
    ("ocrd", "layout.ocrd_processor:OcrdProcessor", None),
    ("remote_segmenter", "layout.remote:RemoteSegmenter", None),
    ("ner", "ner.spacy_extractor:SpacyNerExtractor", None),
    ("text_confidences", "quality.text_confidences:LanguageConfidenceScorer", None),
    ("alto_source", "layout.alto_source:AltoLayoutSource", None),
    ("saknussemm", "layout.saknussemm_correct:SaknussemmCorrector", _build_saknussemm),
    ("precomputed_layout", "layout.precomputed:PrecomputedLayoutSource", None),
    ("precomputed_region", "layout.precomputed:PrecomputedRegionRecognizer", None),
    ("alto_assembler", "layout.assembler:AltoAssembler", None),
    ("layout_to_text", "layout.to_text:LayoutToTextExtractor", None),
    ("preprocess", "preprocess:ImagePreprocessor", None),
    ("reading_order", "layout.reading_order:ReadingOrderModule", None),
    ("vote", "merge:TextVoteMerger", None),
    ("gap_fill", "layout.gap_fill:LayoutGapFiller", None),
    ("page_assembler", "layout.page_assembler:PageAssembler", None),
)


def check_spec_settings(spec: RunSpec, registry: ModuleRegistry) -> None:
    """Chaque brique d'une spec **se construit** avec ses réglages — rien ne
    s'exécute : un réglage inconnu ou mal typé est refusé avant le premier
    appel, à ``cinoc run --check`` comme au dépôt d'une spec web (D14 du pilote).

    Refuse aussi des réglages posés pour une brique qu'**aucune étape**
    n'emploie (``ollama:qwen`` pour une étape ``ollama:qwen_vlm``) : ils
    seraient ignorés de la même façon, en silence.
    """
    used = sorted({s.adapter_name for p in spec.pipelines for s in p.steps})
    for name in sorted(set(spec.adapter_kwargs) - set(used)):
        raise ModuleSettingsError(
            f"adapter_kwargs : réglages pour {name!r}, qu'aucune étape n'emploie"
            f"{closest_hint(name, used) or '.'} Ils ne seraient lus par personne."
        )
    for name in used:
        registry.build(name, spec.adapter_kwargs.get(name, {}))


def check_replay_sources(spec: RunSpec, registry: ModuleRegistry) -> None:
    """Une brique qui **rejoue** des fichiers déposés à côté des images
    (``precomputed``, ``precomputed_layout``, ``precomputed_region``,
    ``alto_source``) doit en trouver pour **au moins une** page du corpus.

    Elle les déclare par le hook ``unit_inputs`` (celui de la reprise) : sans
    aucun de ces fichiers, chaque page échouerait une à une, sans refus
    préalable (D-299). Un fichier manquant sur une partie des pages reste un
    échec d'unité, nommé au rapport. Seuls les corpus à images **locales**
    sont sondés ; le refus nomme le fichier attendu, jamais un chemin.
    """
    documents = [
        d
        for d in spec.corpus.documents
        if d.image_uri is not None and "://" not in d.image_uri
    ]
    if not documents:
        return
    used = sorted({s.adapter_name for p in spec.pipelines for s in p.steps})
    for name in used:
        module = registry.build(name, spec.adapter_kwargs.get(name, {}))
        probe = getattr(module, "unit_inputs", None)
        if probe is None:
            continue
        attendus = [tuple(probe(d)) for d in documents]
        if not any(attendus) or any(
            chemin.exists() for chemins in attendus for chemin in chemins
        ):
            continue
        exemple = next(chemins[0].name for chemins in attendus if chemins)
        raise ModuleSettingsError(
            f"{name!r} rejoue des fichiers déposés avec le corpus, et n'en "
            f"trouve pour aucune de ses {len(documents)} page(s) — par exemple "
            f"{exemple!r}. Dépose-les à côté des images, ou choisis une "
            "autre brique."
        )


def socle_params(kind: str) -> tuple[Param, ...] | None:
    """La déclaration d'une brique du **socle**, sans registre à construire."""
    for socle_kind, path, _ in _SOCLE:
        if socle_kind == kind:
            return declared_params(_load_class(_A + path))
    return None


def register_default_modules(registry: ModuleRegistry) -> None:
    """Enregistre le socle (starter pack). Aucun effet de bord à l'import."""
    for kind, path, builder in _SOCLE:
        registry.register_builder(
            kind, builder or _direct(_A + path), declared_by=_A + path
        )


__all__ = [
    "ModuleBuilder",
    "check_replay_sources",
    "check_spec_settings",
    "ModuleRegistry",
    "ModuleResolutionError",
    "register_default_modules",
    "socle_params",
]

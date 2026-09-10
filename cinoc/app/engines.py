"""Détection runtime de **disponibilité des moteurs** (couche 6).

Alimente l'onglet « Moteurs » : pour chaque kind du socle, dit s'il est
**utilisable ici et maintenant** et *pourquoi pas* le cas échéant. Les sondes
sont **bon marché et sans effet de bord** — on ne lance aucun moteur, on ne
touche pas le réseau : présence d'un binaire (``shutil.which``), d'un SDK
(``importlib.util.find_spec``, **sans importer**), d'une clé d'API (env). Un
moteur cloud est dispo dès que **SDK + clé** sont là (« clé posée → ça marche »),
sans masquage par mode public — la sécurité d'un Space exposé tient à sa visibilité.

Sondes **injectables** → la détection est déterministe en test, indépendante de
l'environnement de CI (où tesseract peut être présent ou non).
"""

from __future__ import annotations

import importlib.util
import os
import shutil
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict

BinaryProbe = Callable[[str], str | None]
ModuleProbe = Callable[[str], bool]
EnvProbe = Callable[[str], str | None]


class EngineStatus(BaseModel):
    """État d'un moteur du socle pour l'onglet « Moteurs »."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    label: str
    available: bool
    detail: str


#: Fournit l'état courant des moteurs (capturé par ``create_app`` avec le mode).
#: Source unique du contrat ; les routeurs (couche 8) l'importent — pas de copie.
StatusProvider = Callable[[], tuple[EngineStatus, ...]]

#: **Socle first-party gratuit** exécutable sur une instance **publique** (Space).
#: Seuls ces kinds tournent en mode public : ils sont **gratuits, sans clé et
#: locaux** (aucun secret exposé, aucun appel cloud facturé). Tout le reste —
#: moteurs cloud (clé), HTR lourds, et a fortiori les **plugins tiers** — reste
#: *gated* (``403``, fail-closed) : un kind ajouté plus tard est refusé par défaut
#: tant qu'il n'est pas explicitement inscrit ici. ``precomputed`` est le moteur de
#: **démonstration** (jamais un concurrent OCR câblé) ; ``tesseract`` est le seul
#: moteur réel offert au visiteur du Space public.
PUBLIC_ENGINE_KINDS: frozenset[str] = frozenset({"precomputed", "tesseract"})


def _module_present(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):  # parent absent / nom dégénéré
        return False


def engine_statuses(
    *,
    has_binary: BinaryProbe = shutil.which,
    has_module: ModuleProbe = _module_present,
    get_env: EnvProbe = os.environ.get,
) -> tuple[EngineStatus, ...]:
    """État de chaque moteur du socle (ordre stable), selon les sondes fournies.

    Un moteur cloud (OpenAI/Anthropic/Mistral) est disponible **dès que son SDK et
    sa clé sont présents** — indépendamment du mode public (« clé posée → ça
    marche »). La protection d'un Space exposé relève de sa **visibilité** (privé)
    et de la présence/absence de la clé, pas d'un masquage côté appli.
    """
    return (
        EngineStatus(
            kind="precomputed",
            label="Pré-calculé",
            available=True,
            detail="intégré (aucune dépendance)",
        ),
        _tesseract_status(has_binary, has_module),
        _kraken_status(has_module),
        _pero_status(has_module),
        _calamari_status(has_module),
        _mistral_ocr_status(has_module, get_env),
        _google_vision_status(has_module, get_env),
        _azure_di_status(has_module, get_env),
        _openai_status(has_module, get_env),
        _anthropic_status(has_module, get_env),
        _mistral_status(has_module, get_env),
        _ollama_status(has_module),
    )


def _tesseract_status(has_binary: BinaryProbe, has_module: ModuleProbe) -> EngineStatus:
    if has_binary("tesseract") is None:
        detail, ok = "binaire « tesseract » introuvable", False
    elif not has_module("pytesseract"):
        detail, ok = "pytesseract non installé (extra [tesseract])", False
    else:
        detail, ok = "prêt (binaire + pytesseract)", True
    return EngineStatus(
        kind="tesseract", label="Tesseract", available=ok, detail=detail
    )


def _kraken_status(has_module: ModuleProbe) -> EngineStatus:
    if not has_module("kraken"):
        detail, ok = "SDK kraken non installé (extra [kraken])", False
    else:
        detail, ok = "prêt (SDK ; fournir un modèle .mlmodel au lancement)", True
    return EngineStatus(
        kind="kraken", label="Kraken (HTR)", available=ok, detail=detail
    )


def _pero_status(has_module: ModuleProbe) -> EngineStatus:
    if not has_module("pero_ocr"):
        detail, ok = "lib pero_ocr non installée (extra [pero])", False
    else:
        detail, ok = "prêt (lib ; fournir un modèle PERO au lancement)", True
    return EngineStatus(kind="pero", label="PERO", available=ok, detail=detail)


def _calamari_status(has_module: ModuleProbe) -> EngineStatus:
    if not has_module("calamari_ocr"):
        detail, ok = "lib calamari_ocr non installée (extra [calamari])", False
    else:
        detail, ok = "prêt (lib ; fournir un checkpoint au lancement)", True
    return EngineStatus(kind="calamari", label="Calamari", available=ok, detail=detail)


def _mistral_ocr_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("mistralai"):
        detail, ok = "SDK mistralai non installé (extra [mistral])", False
    elif not get_env("MISTRAL_API_KEY"):
        detail, ok = "clé MISTRAL_API_KEY absente", False
    else:
        detail, ok = "prêt (SDK + clé)", True
    return EngineStatus(
        kind="mistral_ocr", label="Mistral OCR", available=ok, detail=detail
    )


def _google_vision_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("httpx"):
        detail, ok = "httpx non installé (extra [google])", False
    elif not get_env("GOOGLE_VISION_API_KEY"):
        detail, ok = "clé GOOGLE_VISION_API_KEY absente", False
    else:
        detail, ok = "prêt (REST + clé)", True
    return EngineStatus(
        kind="google_vision", label="Google Vision", available=ok, detail=detail
    )


def _azure_di_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("httpx"):
        detail, ok = "httpx non installé (extra [azure])", False
    elif not get_env("AZURE_DOC_INTEL_ENDPOINT"):
        detail, ok = "endpoint AZURE_DOC_INTEL_ENDPOINT absent", False
    elif not get_env("AZURE_DOC_INTEL_KEY"):
        detail, ok = "clé AZURE_DOC_INTEL_KEY absente", False
    else:
        detail, ok = "prêt (REST + endpoint + clé)", True
    return EngineStatus(
        kind="azure_di",
        label="Azure Document Intelligence",
        available=ok,
        detail=detail,
    )


def _openai_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("openai"):
        detail, ok = "SDK openai non installé (extra [openai])", False
    elif not get_env("OPENAI_API_KEY"):
        detail, ok = "clé OPENAI_API_KEY absente", False
    else:
        detail, ok = "prêt (SDK + clé)", True
    return EngineStatus(kind="openai", label="OpenAI", available=ok, detail=detail)


def _anthropic_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("anthropic"):
        detail, ok = "SDK anthropic non installé (extra [anthropic])", False
    elif not get_env("ANTHROPIC_API_KEY"):
        detail, ok = "clé ANTHROPIC_API_KEY absente", False
    else:
        detail, ok = "prêt (SDK + clé)", True
    return EngineStatus(
        kind="anthropic", label="Anthropic", available=ok, detail=detail
    )


def _mistral_status(has_module: ModuleProbe, get_env: EnvProbe) -> EngineStatus:
    if not has_module("mistralai"):
        detail, ok = "SDK mistralai non installé (extra [mistral])", False
    elif not get_env("MISTRAL_API_KEY"):
        detail, ok = "clé MISTRAL_API_KEY absente", False
    else:
        detail, ok = "prêt (SDK + clé)", True
    return EngineStatus(kind="mistral", label="Mistral", available=ok, detail=detail)


def _ollama_status(has_module: ModuleProbe) -> EngineStatus:
    if not has_module("httpx"):
        detail, ok = "httpx non installé", False
    else:
        detail, ok = "serveur local attendu (non sondé)", True
    return EngineStatus(kind="ollama", label="Ollama", available=ok, detail=detail)


def ner_status(*, has_module: ModuleProbe = _module_present) -> EngineStatus:
    """Disponibilité de l'**étape NER** (extra ``[ner]``, spaCy).

    Catégorie **distincte** des moteurs de transcription : la NER est une brique
    de post-traitement (``texte → ENTITIES``), pas un moteur — elle n'apparaît
    pas dans le ``<select>`` moteur. **Jamais masquée en mode public** : spaCy est
    une lib **locale** first-party (pas de clé, pas d'appel cloud), comme
    ``tesseract``. Le modèle spaCy lui-même est résolu à l'exécution (un modèle
    absent → erreur d'étape claire, fail-closed)."""
    if has_module("spacy"):
        detail, ok = "prêt (spaCy installé)", True
    else:
        detail, ok = "spaCy non installé (extra [ner])", False
    return EngineStatus(kind="ner", label="NER (spaCy)", available=ok, detail=detail)


def correction_status(*, has_module: ModuleProbe = _module_present) -> EngineStatus:
    """Disponibilité de la **post-correction structurée** (extra ``[saknussemm]``).

    Catégorie distincte des moteurs, comme la NER : c'est une brique de
    post-traitement (``LAYOUT → LAYOUT``), pas un moteur de transcription. La
    bibliothèque n'étant pas publiée sur PyPI, elle s'installe depuis son dépôt —
    le détail le dit, parce qu'un ``pip install cinoc[saknussemm]`` qui échoue
    sans explication est le pire des silences.

    Le **producteur** de corrections, lui, est choisi au run : ``rules``
    (déterministe, hors ligne) ou ``ollama`` (serveur local). Cette sonde ne
    répond que de la bibliothèque ; un serveur ollama injoignable est un échec
    d'étape nommé, à l'exécution.
    """
    if has_module("saknussemm"):
        detail, ok = "prêt (saknussemm installé)", True
    else:
        detail, ok = (
            "saknussemm non installé (extra [saknussemm] — depuis le dépôt, "
            "le paquet n'est pas publié sur PyPI)",
            False,
        )
    return EngineStatus(
        kind="saknussemm",
        label="Post-correction structurée",
        available=ok,
        detail=detail,
    )


def preprocess_status(*, has_module: ModuleProbe = _module_present) -> EngineStatus:
    """Disponibilité du **prétraitement d'image** (extra ``[images]``, Pillow).

    Brique de pré-traitement, comme la NER et la post-correction sont des briques
    de post-traitement : ni l'une ni l'autre n'est un moteur de transcription.
    Les mathématiques sont en numpy pur — c'est le **décodage** de l'image qui
    demande Pillow, et rien d'autre.
    """
    if has_module("PIL"):
        detail, ok = "prêt (Pillow installé)", True
    else:
        detail, ok = "Pillow non installé (extra [images])", False
    return EngineStatus(
        kind="preprocess",
        label="Prétraitement d'image",
        available=ok,
        detail=detail,
    )


def segmenter_statuses(
    *, has_module: ModuleProbe = _module_present
) -> tuple[EngineStatus, ...]:
    """Disponibilité des **segmenteurs** de mise en page du socle.

    Catégorie **distincte** des moteurs de transcription : un segmenteur produit
    un ``LAYOUT`` (géométrie), pas du texte — il n'apparaît donc pas dans le
    ``<select>`` moteur du lanceur OCR. **Jamais masqué en mode public** : un
    segmenteur du socle tourne en **local** (PaddleX) ou **délègue** à un endpoint
    distant (``remote_segmenter``) → pas de surface filesystem cloud à masquer.

    Deux segmenteurs maison :

    - ``pp_doclayout`` — modèle **local** PP-DocLayout (extra ``[segment]`` +
      poids) ;
    - ``remote_segmenter`` — **délégué** à un endpoint object-detection HF
      (``httpx``), le modèle tourne à distance : on change de modèle en
      changeant l'``endpoint``, rien à installer ni à baker.
    """
    if has_module("paddlex"):
        paddle_detail, paddle_ok = "prêt (PaddleX installé)", True
    else:
        paddle_detail, paddle_ok = "PaddleX non installé (extra [segment])", False
    if has_module("httpx"):
        remote_detail, remote_ok = "prêt (endpoint distant à fournir)", True
    else:
        remote_detail, remote_ok = "httpx non installé", False
    return (
        EngineStatus(
            kind="pp_doclayout",
            label="PP-DocLayout",
            available=paddle_ok,
            detail=paddle_detail,
        ),
        EngineStatus(
            kind="remote_segmenter",
            label="Segmenteur distant (HF)",
            available=remote_ok,
            detail=remote_detail,
        ),
    )


def installed_ollama_models() -> tuple[str, ...]:
    """Modèles **réellement installés** sur le serveur ollama local (commodité UI).

    Best-effort : serveur injoignable / extra absent → ``()`` (l'UI retombe sur la
    saisie libre). Sert à proposer un **menu déroulant** des modèles disponibles
    au lieu d'une saisie à l'aveugle. Import local : ne charge ``httpx`` que si on
    interroge réellement le serveur.
    """
    from cinoc.adapters.llm.ollama import list_installed_models

    return list_installed_models()


def installed_mistral_models() -> tuple[str, ...]:
    """Modèles Mistral disponibles pour la clé courante (menu déroulant, UI).

    Best-effort : clé/SDK absent → ``()`` (saisie libre). Rien de hardcodé : la
    liste vient de l'API Mistral. Import local (ne charge le SDK qu'au besoin).
    """
    from cinoc.adapters.llm.mistral import list_mistral_models

    return list_mistral_models()


def normalization_profiles() -> tuple[str, ...]:
    """Noms des profils de normalisation, lus **dynamiquement** (jamais une
    liste statique — un profil ajouté en couche 2 apparaît ici sans câblage)."""
    from cinoc.formats.text.normalization import NORMALIZATION_PROFILES

    return tuple(sorted(NORMALIZATION_PROFILES))


def curated_prompts() -> tuple[str, ...]:
    """Noms des **prompts curés** (``cinoc.prompts``), lus **dynamiquement**.

    Comme les profils de normalisation : un prompt ``.txt`` ajouté au paquet
    apparaît ici (et au formulaire) sans câblage. Import local (zéro effet de bord)."""
    from cinoc.prompts import available_prompts

    return available_prompts()


#: Fournisseurs LLM/VLM du socle, avec les modes que **leur adapter déclare**.
#:
#: Source unique : la capacité est lue là où elle est implémentée, pas recopiée.
#: Une seconde liste tenue à la main dérive — c'est exactement ce qui est arrivé
#: à ``_VLM_ENGINES`` (D-233), qui a privé ollama de ses deux modes vision
#: pendant des semaines après que l'adapter les eut gagnés.
_LLM_ADAPTERS: tuple[tuple[str, str, str], ...] = (
    ("openai", "cinoc.adapters.llm.openai", "OpenAIAdapter"),
    ("anthropic", "cinoc.adapters.llm.anthropic", "AnthropicAdapter"),
    ("mistral", "cinoc.adapters.llm.mistral", "MistralAdapter"),
    ("ollama", "cinoc.adapters.llm.ollama", "OllamaAdapter"),
)


def llm_modes() -> dict[str, frozenset[str]]:
    """``{fournisseur: modes déclarés}`` — lu sur les classes d'adapter.

    L'import est **léger** : les adapters n'importent leur SDK qu'à
    l'exécution, jamais au chargement du module (garde-fou
    ``no_side_effect_imports``).
    """
    import importlib  # noqa: PLC0415

    modes: dict[str, frozenset[str]] = {}
    for nom, module, classe in _LLM_ADAPTERS:
        adapter = getattr(importlib.import_module(module), classe)
        modes[nom] = frozenset(adapter.SUPPORTED_MODES)
    return modes


def providers_for_mode(mode: str) -> frozenset[str]:
    """Fournisseurs déclarant supporter ``mode``."""
    return frozenset(nom for nom, m in llm_modes().items() if mode in m)


__all__ = [
    "normalization_profiles",
    "curated_prompts",
    "EngineStatus",
    "PUBLIC_ENGINE_KINDS",
    "StatusProvider",
    "correction_status",
    "llm_modes",
    "preprocess_status",
    "providers_for_mode",
    "engine_statuses",
    "ner_status",
    "segmenter_statuses",
]

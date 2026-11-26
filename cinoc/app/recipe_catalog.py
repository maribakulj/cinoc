"""Le catalogue de recettes **tel que la page le montre** : chaque étape nommée
en clair, chaque brique avec sa disponibilité et ce qu'il faut lui donner.

Vit en couche ``app`` et non dans le routeur : c'est ici que se décide ce qu'une
brique *peut* faire sur cette instance (``CLI_ONLY_KINDS``, mode public, sonde de
disponibilité) — les mêmes règles que le lanceur applique au refus. Une page qui
proposerait ce que la route refuse en ``403`` enseignerait l'inverse de la règle.

Chaque brique porte ses réglages **déclarés** (``PARAMS``) : les requis (un
modèle, une adresse), que la page demande d'emblée, et les autres, qui ont un
défaut et vont dans un pli. C'est ce qui rend à la recette tout ce que le
composeur offrait — prompt curé ou libre, export ALTO de Tesseract, modèle spaCy,
producteur de la correction — sans une ligne écrite pour l'un d'eux (D-298). Le
libellé, le mode (``role``) et la source rejouée (``source_label``) sont posés
par la recette elle-même, jamais demandés.

:func:`brick_statuses` est **la** sonde : le catalogue grise ce qu'elle dit
indisponible, le lanceur refuse en ``409`` la même chose.
"""

from __future__ import annotations

from collections.abc import Iterable

from cinoc.app.engines import (
    CLI_ONLY_KINDS,
    PUBLIC_BRICK_KINDS,
    EngineStatus,
    correction_status,
    curated_prompts,
    ner_status,
    preprocess_status,
)
from cinoc.app.models import model_providers
from cinoc.app.recipes import describe, load_recipes, plan_from_recipe, roles
from cinoc.pipeline.params import Param

#: Nom de chaque rôle à l'écran (français, anglais). Écrit à la main pour être
#: lisible ; confronté à ``roles()`` par un test — un rôle ajouté sans nom
#: s'afficherait par son identifiant technique.
ROLE_LABELS: dict[str, tuple[str, str]] = {
    "preprocess": ("Prétraitement", "Preprocessing"),
    "ocr": ("Reconnaissance (OCR)", "Recognition (OCR)"),
    "segmenter": ("Segmentation", "Segmentation"),
    "alto_source": ("ALTO existant", "Existing ALTO"),
    "region_recognizer": ("Reconnaissance par région", "Recognition per region"),
    "reading_order": ("Ordre de lecture", "Reading order"),
    "structured_correction": ("Correction structurée", "Structured correction"),
    "projection": ("Projection texte", "Text projection"),
    "alto_export": ("Export ALTO", "ALTO export"),
    "page_export": ("Export PAGE", "PAGE export"),
    "correction": ("Correction par un LLM", "LLM correction"),
    "refine": ("Affinage par un LLM", "LLM refinement"),
    "zero_shot": ("Lecture par un modèle de vision", "Vision model reading"),
    "text_and_image": (
        "Correction par un modèle qui voit l'image",
        "Correction by a model that sees the image",
    ),
    "ner": ("Entités nommées", "Named entities"),
    "ner_corrige": (
        "Entités nommées du texte corrigé", "Named entities of the corrected text"
    ),
    "vote": ("Vote", "Vote"),
}

#: Réglages que la recette pose elle-même : la page ne les demande jamais.
_POSES_PAR_LA_RECETTE = frozenset({"label", "role", "source_label"})

_PUBLIC = {
    "fr": "refusé en mode public (seul le socle gratuit est exécuté)",
    "en": "refused in public mode (only the free core runs)",
}
_PRET = {"fr": "intégré", "en": "built in"}


def brick_statuses(statuses: Iterable[EngineStatus]) -> tuple[EngineStatus, ...]:
    """Sondes par brique — celles des moteurs et segmenteurs, plus les briques
    de pré- et post-traitement sondées à part. La post-correction se sonde sous
    le nom de sa catégorie ; sa brique s'appelle ``saknussemm``.

    Une seule fonction pour le catalogue (qui grise) et le lanceur (qui refuse
    en ``409``) : une page qui proposerait ce que la route refuse enseignerait
    l'inverse de la règle.
    """
    par_kind = {s.kind: s for s in statuses}
    for statut in (preprocess_status(), ner_status()):
        par_kind.setdefault(statut.kind, statut)
    correction = correction_status()
    par_kind.setdefault(
        "saknussemm", correction.model_copy(update={"kind": "saknussemm"})
    )
    return tuple(par_kind.values())


def _reglage(param: Param, kind: str, langue: str) -> dict[str, object]:
    """Un réglage tel que la page le rend : requis en clair, les autres au pli.

    Deux enrichissements que la déclaration ne peut pas porter, parce qu'ils
    dépendent de l'instance : les prompts curés (``prompt_name``) en choix, et
    l'adresse qui liste les modèles du fournisseur (``model`` d'une brique
    LLM/VLM) — la page la lit en direct, comme le composeur le faisait.
    """
    choix: list[object] = list(param.choices)
    if param.name == "prompt_name":
        choix = ["", *curated_prompts()]
    return {
        "name": param.name,
        "type": param.type,
        "label": param.label(langue),
        "required": param.required,
        "default": param.default,
        "secret": param.secret,
        "choices": choix,
        "models_url": (
            f"/api/models/{kind}"
            if param.name == "model" and kind in model_providers()
            else None
        ),
    }


def _brique(
    kind: str, statut: EngineStatus | None, public_mode: bool, langue: str
) -> dict[str, object]:
    from cinoc.app.modules.registry import socle_params  # noqa: PLC0415

    if public_mode and kind not in PUBLIC_BRICK_KINDS:
        disponible, detail = False, _PUBLIC[langue]
    elif statut is not None:
        disponible, detail = statut.available, statut.detail
    else:
        disponible, detail = True, _PRET[langue]
    return {
        "kind": kind,
        "available": disponible,
        "detail": detail,
        "params": [
            _reglage(p, kind, langue)
            for p in socle_params(kind) or ()
            if p.name not in _POSES_PAR_LA_RECETTE
        ],
    }


def recipe_catalog(
    lang: str = "fr",
    *,
    statuses: Iterable[EngineStatus] = (),
    public_mode: bool = False,
) -> list[dict[str, object]]:
    """Catalogue des recettes, prêt à afficher : intention, forme, et pour
    chaque étape le rôle nommé, la brique par défaut et celles qu'on peut lui
    substituer (indisponibles comprises, avec leur raison)."""
    table = roles()
    langue = "en" if lang == "en" else "fr"
    par_kind = {s.kind: s for s in brick_statuses(statuses)}
    sorties: list[dict[str, object]] = []
    for recette in load_recipes():
        pipeline, _ = plan_from_recipe(recette)
        etapes: list[dict[str, object]] = []
        for step in recette.steps:
            role = table[step.role]
            defaut = recette.brique_de(step)
            candidates = dict.fromkeys((defaut, *role.briques))
            etapes.append(
                {
                    "step": step.id,
                    "role": step.role,
                    "role_label": ROLE_LABELS[step.role][langue == "en"],
                    "fanout": role.fanout,
                    "optional": step.optional,
                    "default": defaut,
                    "bricks": [
                        _brique(k, par_kind.get(k), public_mode, langue)
                        for k in candidates
                        if k not in CLI_ONLY_KINDS
                    ],
                }
            )
        sorties.append(
            {
                "name": recette.name,
                "title": describe(recette, langue),
                "description": recette.description.get(langue, ""),
                "shape": [etape.kind for etape in pipeline.steps],
                "steps": etapes,
            }
        )
    return sorties


__all__ = ["ROLE_LABELS", "brick_statuses", "recipe_catalog"]

"""Le catalogue de recettes **tel que la page le montre** : chaque étape nommée
en clair, chaque brique avec sa disponibilité et ce qu'il faut lui donner.

Vit en couche ``app`` et non dans le routeur : c'est ici que se décide ce qu'une
brique *peut* faire sur cette instance (``CLI_ONLY_KINDS``, mode public, sonde de
disponibilité) — les mêmes règles que le lanceur applique au refus. Une page qui
proposerait ce que la route refuse en ``403`` enseignerait l'inverse de la règle.

Ce que la page **demande** à l'utilisateur se limite aux réglages **requis** de
la brique (un modèle, une adresse) : sans eux, la recette ne se construit pas.
Les autres réglages ont un défaut ; les exposer est le pli de réglages, tranche 5
de ``PLAN_UI_COMPOSEUR.md``. Le libellé, le mode (``role``) et la source rejouée
(``source_label``) sont posés par la recette elle-même, jamais demandés.
"""

from __future__ import annotations

from collections.abc import Iterable

from cinoc.app.engines import (
    CLI_ONLY_KINDS,
    PUBLIC_ENGINE_KINDS,
    EngineStatus,
    correction_status,
    ner_status,
    preprocess_status,
)
from cinoc.app.recipes import describe, load_recipes, plan_from_recipe, roles

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
    "vote": ("Vote", "Vote"),
}

#: Réglages que la recette pose elle-même : la page ne les demande jamais.
_POSES_PAR_LA_RECETTE = frozenset({"label", "role", "source_label"})

_PUBLIC = {
    "fr": "refusé en mode public (seul le socle gratuit est exécuté)",
    "en": "refused in public mode (only the free core runs)",
}
_PRET = {"fr": "intégré", "en": "built in"}


def _statuts(statuses: Iterable[EngineStatus]) -> dict[str, EngineStatus]:
    """Sondes par ``kind`` de brique — celles du lanceur, plus les briques de
    pré- et post-traitement qu'il sonde à part. La post-correction se sonde
    sous le nom de sa catégorie ; sa brique s'appelle ``saknussemm``."""
    par_kind = {s.kind: s for s in statuses}
    for statut in (preprocess_status(), ner_status()):
        par_kind.setdefault(statut.kind, statut)
    par_kind.setdefault("saknussemm", correction_status())
    return par_kind


def _brique(
    kind: str, statut: EngineStatus | None, public_mode: bool, langue: str
) -> dict[str, object]:
    from cinoc.app.modules.registry import socle_params  # noqa: PLC0415

    if public_mode and kind not in PUBLIC_ENGINE_KINDS:
        disponible, detail = False, _PUBLIC[langue]
    elif statut is not None:
        disponible, detail = statut.available, statut.detail
    else:
        disponible, detail = True, _PRET[langue]
    requis = [
        {
            "name": p.name,
            "type": p.type,
            "label": p.label_en if langue == "en" else p.label_fr,
            "secret": p.secret,
            "choices": list(p.choices or ()),
        }
        for p in socle_params(kind) or ()
        if p.required and p.name not in _POSES_PAR_LA_RECETTE
    ]
    return {
        "kind": kind,
        "available": disponible,
        "detail": detail,
        "required": requis,
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
    par_kind = _statuts(statuses)
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


__all__ = ["ROLE_LABELS", "recipe_catalog"]

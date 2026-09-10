"""Garde-fou : **le web ne fait aucune capacité que la CLI ne sache faire**.

La règle, et la distinction qui la rend applicable :

* une **capacité** — importer un corpus, savoir quels moteurs sont disponibles,
  exporter un ALTO — doit exister des **deux** côtés ;
* un **transport** — SSE, CSRF, une page HTML, servir un fichier déjà produit —
  n'a pas à être dupliqué. L'équivalent CLI de « suivre la progression en SSE »
  est stdout, pas une seconde implémentation.

**Pourquoi un test et pas une intention.** L'app web a grandi pendant que la CLI
suivait de loin, et personne ne l'a vu : au moment d'écrire ce garde-fou, huit
capacités d'acquisition de corpus et quatre d'introspection n'existaient qu'en
web. C'est la même dérive que le statut périmé de ``CLAUDE.md`` §0, et elle se
soigne pareil — par un contrôle mécanique, pas par de la vigilance.

**Comment il mord.** Chaque route de l'app doit avoir une entrée dans
:data:`PARITE`. Ajouter une route sans statuer sur son pendant CLI rend la CI
rouge. Une dette doit en plus être **déclarée** dans :data:`DETTES` avec ce qui
la ferme : on peut donc en porter, jamais en accumuler par inadvertance.

Le modèle est celui de ``test_file_budgets`` : la valeur porte le fait
vérifiable, le commentaire au-dessus porte le *pourquoi*.
"""

from __future__ import annotations

import tempfile
from functools import lru_cache
from pathlib import Path

from cinoc.interfaces._cli_parser import SUBCOMMANDS

#: Dettes connues : identifiant → ce qui la ferme. Une entrée ici est un
#: engagement, pas une excuse ; la liste ne doit que rétrécir.
DETTES: dict[str, str] = {
    # Introspection. `app/engines.py` expose déjà `engine_statuses`,
    # `installed_ollama_models`, `normalization_profiles`, `curated_prompts` ;
    # le web les met en HTML. La CLI doit les mettre en texte — deux transports
    # d'une même capacité, aucune logique nouvelle.
    "introspection": "tranche c — `cinoc list engines|models|profiles|prompts`",
    # Valider une configuration sans l'exécuter. Le web valide un
    # `LaunchRequest` ; l'équivalent CLI est de valider le YAML et d'afficher le
    # plan. Un drapeau, pas une commande.
    "run-check": "tranche d — `cinoc run --check`",
    # Segmentation seule + aperçu de mise en page. `plan_segmentation_run`
    # existe en couche `app` et n'a **aucun** appelant CLI.
    "segmentation": "tranche d — `cinoc hybrid --segment-only`",
    # Export ALTO d'un run YAML. Le sink qui persiste les `ALTO_XML` vit dans
    # `JobRunner` (chemin web) ; un `cinoc run` qui demande le type produit
    # l'artefact, qui meurt ensuite avec le workspace.
    "alto-export": "tranche d — `cinoc run --alto-dir`",
}

#: Route → statut. Trois formes, et trois seulement :
#: ``"transport"`` · ``"cli:<sous-commande>"`` · ``"dette:<identifiant>"``.
PARITE: dict[str, str] = {
    # --- Pages HTML et sondes : du transport, par nature. ---------------------
    "GET /": "transport",
    "GET /benchmark": "transport",
    "GET /health": "transport",
    # --- Pages qui portent une capacité, pas seulement un rendu. -------------
    # `/library` expose le catalogue HTR-United et la découverte des datasets
    # curés : de la **découverte de corpus**, pas de la mise en page.
    "GET /library": "cli:corpus",
    "GET /engines": "dette:introspection",
    "GET /history": "cli:history",
    # --- Acquisition de corpus. ----------------------------------------------
    # `cinoc corpus import <source>` appelle **les mêmes** builders que ces
    # routes ; seule la destination change (dossier + `corpus.yaml` au lieu d'un
    # store serveur indexé par id).
    "POST /api/corpus": "cli:corpus",
    "POST /api/corpus/import/iiif": "cli:corpus",
    "POST /api/corpus/import/escriptorium": "cli:corpus",
    "POST /api/corpus/import/gallica": "cli:corpus",
    "POST /api/corpus/import/huggingface": "cli:corpus",
    "POST /api/corpus/import/curated": "cli:corpus",
    # Supprimer : le corpus d'une CLI **est** un dossier, et l'effacer relève du
    # système de fichiers. Fournir un `cinoc corpus rm` doublerait `rm -rf` sans
    # rien garantir de plus. Le web, lui, a besoin de la route parce que son
    # store est un registre serveur que l'utilisateur ne peut pas atteindre.
    "DELETE /api/corpus/{corpus_id}": "transport",
    # --- Introspection. ------------------------------------------------------
    "GET /api/models/{model_provider}": "dette:introspection",
    "POST /api/normalization/preview": "dette:introspection",
    # --- Lancement et suivi d'un run. ----------------------------------------
    # `cinoc run` est **plus général** que le composeur web : il accepte un
    # `RunSpec` complet là où le web assemble des `Competitor`.
    "POST /api/runs": "cli:run",
    "POST /api/runs/config": "dette:run-check",
    # L'état d'un job, son annulation et son flux d'événements n'existent que
    # parce que le web exécute **en arrière-plan**. En CLI le run est au premier
    # plan : la progression va sur stdout, l'annulation est Ctrl-C (coopérative,
    # même mécanisme `RunControl` en dessous).
    "GET /api/runs/{job_id}": "transport",
    "POST /api/runs/{job_id}/cancel": "transport",
    "GET /api/runs/{job_id}/events": "transport",
    # --- Segmentation. -------------------------------------------------------
    "POST /api/segmentation/run": "dette:segmentation",
    "GET /api/segmentation/preview": "dette:segmentation",
    # Sert une image du store serveur : transport pur (en CLI, le fichier est
    # déjà sur le disque de l'utilisateur).
    "GET /api/segmentation/{seg_id}/image": "transport",
    # --- Rapports. -----------------------------------------------------------
    # Servir un rapport déjà produit est du transport ; le **produire** est
    # `cinoc run`, et le bundle dossier est `--report-dir`.
    "GET /reports/{name}": "transport",
    "GET /reports/{name}/bundle.zip": "cli:run",
    "GET /reports/{name}/alto.zip": "dette:alto-export",
}


@lru_cache(maxsize=1)
def _web_routes() -> frozenset[str]:
    """Les routes réellement servies, lues dans le schéma OpenAPI de l'app.

    Lues de l'app **construite**, pas d'une expression régulière sur la source :
    une route montée par un routeur, une redirection ou un `include_router`
    échapperait à un grep, et c'est précisément la route oubliée qu'on cherche.
    """
    from cinoc.interfaces.web.app import create_app

    base = Path(tempfile.mkdtemp(prefix="cinoc-parite-"))
    app = create_app(
        reports_dir=base / "reports",
        uploads_dir=base / "uploads",
        data_dir=base / "data",
    )
    chemins = app.openapi()["paths"]
    return frozenset(
        f"{methode.upper()} {chemin}"
        for chemin, methodes in chemins.items()
        for methode in methodes
    )


def test_every_route_has_a_declared_counterpart() -> None:
    """Aucune route hors table, aucune entrée orpheline."""
    routes, declarees = _web_routes(), frozenset(PARITE)
    non_declarees = sorted(routes - declarees)
    fantomes = sorted(declarees - routes)
    assert not non_declarees, (
        f"routes web sans statut de parité : {non_declarees}. Déclare pour "
        "chacune si la CLI la couvre (`cli:<commande>`), si c'est du transport "
        "(`transport`), ou si c'est une dette (`dette:<id>`, à inscrire aussi "
        "dans DETTES)."
    )
    assert not fantomes, (
        f"entrées de parité sans route correspondante : {fantomes}. La route "
        "a été renommée ou retirée — mets la table à jour."
    )


def test_statuses_are_well_formed() -> None:
    mauvais = {
        route: statut
        for route, statut in PARITE.items()
        if statut != "transport"
        and not statut.startswith(("cli:", "dette:"))
    }
    assert not mauvais, (
        f"statuts hors grammaire : {mauvais}. Trois formes seulement — "
        "'transport', 'cli:<sous-commande>', 'dette:<identifiant>'."
    )


def test_declared_cli_counterparts_exist() -> None:
    """Un pendant CLI qui n'existe pas est pire qu'une dette : il la cache."""
    inconnues = sorted(
        {
            statut.removeprefix("cli:")
            for statut in PARITE.values()
            if statut.startswith("cli:")
        }
        - set(SUBCOMMANDS)
    )
    assert not inconnues, (
        f"sous-commandes citées mais inexistantes : {inconnues}. "
        f"Surface réelle : {sorted(SUBCOMMANDS)}."
    )


def test_debts_are_declared_and_none_is_stale() -> None:
    """Chaque dette porte son identifiant **et** ce qui la ferme, dans les deux
    sens : pas de dette non déclarée, pas de dette déclarée puis oubliée."""
    citees = {
        statut.removeprefix("dette:")
        for statut in PARITE.values()
        if statut.startswith("dette:")
    }
    non_declarees = sorted(citees - set(DETTES))
    obsoletes = sorted(set(DETTES) - citees)
    assert not non_declarees, (
        f"dettes citées mais non déclarées : {non_declarees}. Ajoute-les à "
        "DETTES avec la tranche qui les ferme — une dette sans échéance est un "
        "abandon qui n'ose pas dire son nom."
    )
    assert not obsoletes, (
        f"dettes déclarées que plus aucune route ne porte : {obsoletes}. "
        "Elles sont fermées : retire-les de DETTES."
    )

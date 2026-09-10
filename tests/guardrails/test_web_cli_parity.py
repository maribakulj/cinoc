"""Garde-fou : **le web ne fait aucune capacité que la CLI ne sache faire**.

La règle, et la distinction qui la rend applicable :

* une **capacité** — importer un corpus, savoir quels moteurs sont disponibles,
  exporter un ALTO — doit exister des **deux** côtés, et le contrôle va **dans
  les deux sens** : :data:`PARITE` (chaque route web a son pendant CLI) et
  :data:`PARITE_CLI` (chaque commande a son pendant web) ;
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
#:
#: Dettes connues : identifiant → ce qui la ferme.
#:
#: **Vide.** Les cinq dettes ouvertes par D-224 (sens web → CLI) sont fermées par
#: D-225→D-227, et `correction-web` (sens CLI → web) par D-229. Le dictionnaire
#: reste : c'est lui qui rend une nouvelle dette *déclarable*, donc visible et
#: datée, plutôt que tolérée en silence — comme l'a été pendant des mois
#: l'absence de surface web de la post-correction.
DETTES: dict[str, str] = {}

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
    "GET /engines": "cli:list",
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
    # Mêmes sondes de la couche `app` : le web les rend en HTML, `cinoc list`
    # en texte. L'aperçu de normalisation est `cinoc list profiles --preview`,
    # sans persistance des deux côtés.
    "GET /api/models/{model_provider}": "cli:list",
    "POST /api/normalization/preview": "cli:list",
    # --- Lancement et suivi d'un run. ----------------------------------------
    # `cinoc run` est **plus général** que le composeur web : il accepte un
    # `RunSpec` complet là où le web assemble des `Competitor`.
    "POST /api/runs": "cli:run",
    # Valider avant de lancer : `cinoc run --check` relit la spec, affiche
    # le plan et n'exécute rien — une spec de benchmark engage des appels
    # facturés.
    "POST /api/runs/config": "cli:run",
    # La correction structurée n'est pas un concurrent de plus dans la file du
    # composeur : c'est une **autre forme de run** (un ALTO déjà là qu'on
    # corrige), planifiée par `plan_correction_run`. Elle a donc sa route,
    # comme la segmentation a la sienne.
    "POST /api/runs/correction": "cli:correct",
    # L'état d'un job, son annulation et son flux d'événements n'existent que
    # parce que le web exécute **en arrière-plan**. En CLI le run est au premier
    # plan : la progression va sur stdout, l'annulation est Ctrl-C (coopérative,
    # même mécanisme `RunControl` en dessous).
    "GET /api/runs/{job_id}": "transport",
    "POST /api/runs/{job_id}/cancel": "transport",
    "GET /api/runs/{job_id}/events": "transport",
    # --- Segmentation. -------------------------------------------------------
    # `cinoc hybrid --segment-only` écrit un LAYOUT par page, relisible par
    # `precomputed_layout`. L'« aperçu » web est le rendu de ce même LAYOUT :
    # côté CLI le fichier **est** l'aperçu, on l'ouvre avec ses outils.
    "POST /api/segmentation/run": "cli:hybrid",
    "GET /api/segmentation/preview": "cli:hybrid",
    # Sert une image du store serveur : transport pur (en CLI, le fichier est
    # déjà sur le disque de l'utilisateur).
    "GET /api/segmentation/{seg_id}/image": "transport",
    # --- Rapports. -----------------------------------------------------------
    # Servir un rapport déjà produit est du transport ; le **produire** est
    # `cinoc run`, et le bundle dossier est `--report-dir`.
    "GET /reports/{name}": "transport",
    "GET /reports/{name}/bundle.zip": "cli:run",
    # Saveur **servie** : la page ne porte que des URL, ces routes produisent
    # les vignettes à la demande. Du transport — l'équivalent en ligne de
    # commande n'est pas une commande de plus mais l'autre saveur,
    # `cinoc run --report-dir`, qui écrit les mêmes dérivés sur disque.
    "GET /reports/{name}/image/{document_id}": "transport",
    "GET /reports/{name}/facsimile/{document_id}": "transport",
    "GET /reports/{name}/alto.zip": "cli:run",
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


#: Sous-commande CLI → statut, dans l'autre sens. Trois formes :
#: ``"web:<route>"`` · ``"cli-only: <raison>"`` · ``"dette:<identifiant>"``.
#:
#: **Pourquoi la table symétrique.** La première version de ce garde-fou ne
#: regardait que web → CLI, parce que c'est le manque qu'on venait de constater.
#: Un contrôle unidirectionnel laisse l'autre sens dériver exactement pareil — et
#: c'était déjà le cas : `cinoc correct` existait depuis des mois sans surface
#: web, sous la forme d'un « arbitrage à rendre » que rien ne rappelait.
PARITE_CLI: dict[str, str] = {
    # Le run de démonstration est ce que lance `POST /api/runs` sans concurrent.
    "demo": "web:POST /api/runs",
    "run": "web:POST /api/runs",
    "hybrid": "web:POST /api/runs",
    "corpus": "web:POST /api/corpus",
    "list": "web:GET /engines",
    "history": "web:GET /history",
    # Le rapport autonome embarque son propre comparateur (client-side, sans
    # réseau) : la « route » du web est celle qui sert ce rapport.
    "compare": "web:GET /reports/{name}",
    # `serve` **est** le web : lui chercher un pendant web n'aurait pas de sens.
    "serve": "cli-only: c'est la commande qui démarre l'app web.",
    "correct": "web:POST /api/runs/correction",
}


def _cli_status_targets() -> set[str]:
    """Routes citées par :data:`PARITE_CLI`, sans le préfixe ``web:``."""
    return {
        statut.removeprefix("web:")
        for statut in PARITE_CLI.values()
        if statut.startswith("web:")
    }


def test_every_cli_command_has_a_declared_counterpart() -> None:
    """Aucune commande hors table, aucune entrée orpheline."""
    commandes, declarees = set(SUBCOMMANDS), set(PARITE_CLI)
    non_declarees = sorted(commandes - declarees)
    fantomes = sorted(declarees - commandes)
    assert not non_declarees, (
        f"commandes sans statut de parité : {non_declarees}. Déclare pour "
        "chacune la route web équivalente (`web:<route>`), pourquoi elle n'a de "
        "sens qu'en CLI (`cli-only: …`), ou la dette (`dette:<id>`)."
    )
    assert not fantomes, (
        f"entrées de parité sans commande correspondante : {fantomes}."
    )


def test_cli_statuses_are_well_formed() -> None:
    mauvais = {
        commande: statut
        for commande, statut in PARITE_CLI.items()
        if not statut.startswith(("web:", "cli-only:", "dette:"))
    }
    assert not mauvais, (
        f"statuts hors grammaire : {mauvais}. Trois formes seulement — "
        "'web:<route>', 'cli-only: <raison>', 'dette:<identifiant>'."
    )


def test_declared_web_counterparts_exist() -> None:
    """Une route citée qui n'existe pas cacherait la dette au lieu de la dire."""
    inconnues = sorted(_cli_status_targets() - _web_routes())
    assert not inconnues, (
        f"routes citées mais inexistantes : {inconnues}. "
        "Elles ont été renommées ou retirées."
    )


def test_a_cli_only_command_says_why() -> None:
    """« CLI seulement » sans raison est une dette déguisée."""
    muettes = sorted(
        commande
        for commande, statut in PARITE_CLI.items()
        if statut.startswith("cli-only:")
        and len(statut.removeprefix("cli-only:").strip()) < 15
    )
    assert not muettes, (
        f"« cli-only » sans justification : {muettes}. Écris pourquoi cette "
        "capacité n'a de sens qu'en ligne de commande."
    )


def test_debts_are_declared_and_none_is_stale() -> None:
    """Chaque dette porte son identifiant **et** ce qui la ferme, dans les deux
    sens : pas de dette non déclarée, pas de dette déclarée puis oubliée."""
    citees = {
        statut.removeprefix("dette:")
        for statut in (*PARITE.values(), *PARITE_CLI.values())
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

"""Déclaration de la **surface** de la CLI (couche 8) — un seul endroit.

Séparé de ``cli.py`` pour deux raisons, pas par goût du découpage :

* ``cli.py`` porte le **dispatch** et les implémentations ; y garder aussi les
  ~200 lignes d'``argparse`` le poussait vers son budget de taille, et mélangeait
  « ce que la CLI offre » avec « ce qu'elle fait ».
* La surface devient **interrogeable** : les garde-fous lisent
  ``build_parser().subcommands`` au lieu de deviner par expression régulière
  dans la source. Un contrat se lit, il ne se devine pas.

Ce module ne fait **aucun travail** : il déclare des arguments. Toute logique
vit en couche ``app`` (``CLAUDE.md`` §5 — ``interfaces`` est du transport mince).
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

# Les producteurs de correction sont lus en couche `app`, pas recopiés ici :
# une interface qui énumère est une interface qui dérive.
from cinoc.app.alto_corpus import PRODUCERS
from cinoc.app.evaluation_views import METRIC_PROFILES
from cinoc.interfaces._corpus_command import add_standardize_parser

if TYPE_CHECKING:  # pragma: no cover
    # Type de l'objet rendu par ``add_subparsers`` : ``argparse`` n'en publie
    # pas d'alias, et la classe n'est pas indiçable à l'exécution. Sous
    # ``TYPE_CHECKING`` uniquement — c'est du **typage** de la stdlib, pas un
    # accès à l'état interne d'une lib tierce.
    _SousCommandes = argparse._SubParsersAction[argparse.ArgumentParser]  # noqa: SLF001


def _add_list(subparsers: _SousCommandes) -> None:
    """Sous-arbre ``cinoc list`` : lire l'état de son installation.

    Un verbe, des **sujets** — moteurs, modèles, profils, prompts. Ce sont les
    mêmes sondes que celles que le web rend en HTML ; les mettre en texte est un
    transport, pas une lentille d'analyse (``CLAUDE.md`` §8.4).
    """
    list_cmd = subparsers.add_parser(
        "list",
        help="Liste moteurs, modèles, profils de normalisation, prompts curés.",
    )
    sujets = list_cmd.add_subparsers(dest="topic", required=True)

    moteurs = sujets.add_parser(
        "engines",
        help="Moteurs, segmenteurs et étape NER, avec la cause d'indisponibilité.",
    )
    moteurs.add_argument(
        "brick",
        nargs="?",
        default=None,
        help="Une brique (tesseract, openai…) : les réglages qu'elle accepte.",
    )

    modeles = sujets.add_parser(
        "models",
        help="Modèles d'un fournisseur, demandés en direct (Ollama : installés).",
    )
    modeles.add_argument(
        "provider",
        nargs="?",
        default=None,
        help="openai, anthropic, mistral, mistral_ocr, ollama. Omis : tous.",
    )
    modeles.add_argument(
        "--host",
        default=None,
        help="Serveur ollama à interroger (défaut : http://localhost:11434).",
    )

    profils = sujets.add_parser(
        "profiles", help="Profils de normalisation, et leur effet sur un texte."
    )
    profils.add_argument(
        "--preview",
        default=None,
        metavar="TEXTE",
        help="Affiche ce que le profil fait de ce texte (rien n'est persisté).",
    )
    profils.add_argument(
        "--profile", default=None, help="Profil nommé à appliquer à --preview."
    )
    profils.add_argument(
        "--config",
        default=None,
        help="Fichier YAML de normalisation custom, appliqué à la volée.",
    )

    sujets.add_parser("prompts", help="Prompts curés par période.")

    recettes = sujets.add_parser(
        "recipes",
        help="Recettes : des formes de pipeline nommées par leur intention.",
    )
    recettes.add_argument(
        "--lang", default="fr", choices=("fr", "en"), help="Langue des libellés."
    )


def _add_scoring(parser: argparse.ArgumentParser, avec: str) -> None:
    """Les options de notation du web (une seule politique de vues, D-297)."""
    parser.add_argument(
        "--normalization",
        default=None,
        metavar="PROFIL",
        help=f"{avec}profil de normalisation (`cinoc list profiles`) ; défaut : "
        "flat_text, plus la vue « texte (lignes) » si la GT a des lignes.",
    )
    parser.add_argument(
        "--metric-profile",
        dest="metric_profile",
        default=None,
        choices=tuple(METRIC_PROFILES),
        help=f"{avec}colonnes de la vue texte (défaut : standard).",
    )
    parser.add_argument(
        "--char-exclude",
        dest="char_exclude",
        default=None,
        metavar="CARACTÈRES",
        help=f"{avec}caractères retirés de la GT et de l'hypothèse avant calcul.",
    )


def _add_corpus(subparsers: _SousCommandes) -> None:
    """Sous-arbre ``cinoc corpus`` : acquérir un corpus, chercher, découvrir.

    Un **verbe** (``corpus``) plutôt qu'un par source : le §8.4 interdit de
    multiplier les commandes, et « acquérir un corpus » est **une** capacité,
    quelle que soit la source d'où elle vient.
    """
    corpus_cmd = subparsers.add_parser(
        "corpus",
        help="Acquiert un corpus (IIIF, Gallica, eScriptorium, HF, ZIP) et "
        "écrit son YAML ; ou standardise un corpus brut en dataset curé.",
    )
    verbes = corpus_cmd.add_subparsers(dest="corpus_command", required=True)

    imp = verbes.add_parser("import", help="Matérialise un corpus depuis une source.")
    sources = imp.add_subparsers(dest="source", required=True)

    def _commun(parser: argparse.ArgumentParser, *, defaut: str) -> None:
        """Options que toute source partage : où matérialiser, comment nommer."""
        parser.add_argument(
            "--dest",
            default=defaut,
            help=f"Dossier où matérialiser les fichiers (défaut : {defaut}/).",
        )
        parser.add_argument(
            "-o",
            "--output",
            default=None,
            help="Fichier YAML du corpus (défaut : <dest>/corpus.yaml).",
        )
        parser.add_argument("--name", default=None, help="Nom du corpus.")

    iiif = sources.add_parser("iiif", help="Manifeste IIIF (URL).")
    iiif.add_argument("manifest_url", help="URL du manifeste IIIF.")
    iiif.add_argument("--limit", type=int, default=None, help="Borne le nb de pages.")
    _commun(iiif, defaut="corpus-iiif")

    gallica = sources.add_parser("gallica", help="Document Gallica (ark).")
    gallica.add_argument("ark", help="Identifiant ark (ex. ark:/12148/bpt6k...).")
    gallica.add_argument("--limit", type=int, default=None, help="Borne le nb de vues.")
    gallica.add_argument(
        "--no-ocr",
        dest="include_ocr",
        action="store_false",
        help="N'importe pas l'OCR de Gallica comme vérité terrain. Sans ce "
        "drapeau, l'OCR est importé — c'est de l'OCR, pas une transcription "
        "vérifiée : le savoir change la lecture des scores.",
    )
    _commun(gallica, defaut="corpus-gallica")

    escr = sources.add_parser("escriptorium", help="Document eScriptorium (API).")
    escr.add_argument("base_url", help="URL de l'instance eScriptorium.")
    escr.add_argument("doc_pk", type=int, help="Identifiant du document.")
    escr.add_argument("--token", required=True, help="Jeton d'API.")
    escr.add_argument(
        "--layer", default="manual", help="Couche de transcription (défaut : manual)."
    )
    escr.add_argument("--limit", type=int, default=None, help="Borne le nb de pages.")
    _commun(escr, defaut="corpus-escriptorium")

    hf = sources.add_parser("hf", help="Dataset HuggingFace (streaming).")
    hf.add_argument("dataset_id", help="Identifiant du dataset (owner/nom).")
    hf.add_argument("--split", default="train", help="Split (défaut : train).")
    hf.add_argument("--limit", type=int, default=None, help="Borne le nb de pages.")
    _commun(hf, defaut="corpus-hf")

    cure = sources.add_parser("curated", help="Dataset curé Cinoc publié sur HF.")
    cure.add_argument("repo_id", help="Dépôt du dataset curé (owner/nom).")
    cure.add_argument(
        "--revision", default=None, help="Révision à épingler (repro exacte)."
    )
    _commun(cure, defaut="corpus-cure")

    zip_cmd = sources.add_parser("zip", help="Archive ZIP locale (images + GT).")
    zip_cmd.add_argument("archive", help="Fichier .zip du corpus.")
    _commun(zip_cmd, defaut="corpus-zip")

    cherche = verbes.add_parser(
        "search", help="Cherche dans le catalogue HTR-United."
    )
    cherche.add_argument("query", nargs="?", default="", help="Termes de recherche.")
    cherche.add_argument("--language", default=None, help="Filtre par langue.")
    cherche.add_argument(
        "--limit", type=int, default=20, help="Entrées affichées (défaut : 20)."
    )

    add_standardize_parser(verbes)
    trouve = verbes.add_parser(
        "discover", help="Liste les datasets curés Cinoc d'un compte HuggingFace."
    )
    trouve.add_argument(
        "--author",
        default=None,
        help="Compte HF. Par défaut : CINOC_HF_AUTHOR, puis un jeton HF, puis "
        "le propriétaire du SPACE_ID — comme la page Bibliothèque.",
    )


class _VersionAction(argparse.Action):
    """``--version`` : la version **calculée à la demande**, pas à la déclaration.

    L'action ``version`` d'``argparse`` veut sa chaîne à la construction du
    parseur, donc à chaque invocation de la CLI ; ce module ne fait aucun
    travail. Elle lit la même source que la provenance des runs
    (``resolve_code_version``) : deux sources de version se contrediraient.
    """

    def __init__(self, option_strings: list[str], dest: str, **kwargs: object) -> None:
        del kwargs  # ``help`` est fixé ici : l'option n'a qu'un sens
        super().__init__(
            option_strings,
            dest=dest,
            nargs=0,
            default=argparse.SUPPRESS,
            help="Affiche la version de cinoc et quitte.",
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: object,
        option_string: str | None = None,
    ) -> None:
        from cinoc.app import resolve_code_version  # noqa: PLC0415 — à la demande

        # Sur la sortie standard, comme l'action ``version`` d'``argparse`` :
        # c'est une réponse, pas un diagnostic, et elle doit pouvoir se capturer.
        print(f"cinoc {resolve_code_version()}")
        parser.exit()


def build_parser() -> argparse.ArgumentParser:
    """Le parseur complet de ``cinoc``. Aucun effet de bord."""
    parser = argparse.ArgumentParser(
        prog="cinoc",
        description="Banc d'essai déterministe de pipelines de transcription.",
    )
    parser.add_argument("--version", action=_VersionAction, dest="version")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser(
        "demo",
        help="Génère un rapport de démonstration déterministe (sans moteur).",
    )
    demo.add_argument(
        "-o", "--output", default="rapport_demo.html", help="Fichier HTML de sortie."
    )
    run_cmd = subparsers.add_parser(
        "run",
        help="Exécute un run décrit dans un fichier YAML.",
        description="Exécute un run décrit dans un fichier YAML et écrit son "
        "rapport. Code de sortie : 0 si chaque unité (pipeline × document) a "
        "produit une sortie ; 3 si au moins une a échoué — le rapport est écrit "
        "et les liste ; 1 si le run n'a pas pu se faire (spec invalide, archive "
        "incomplète hors ligne…).",
    )
    run_cmd.add_argument(
        "config",
        help="Fichier YAML décrivant le run — avec --recipe, le corpus seul "
        "(clé `corpus`, tel que l'écrit `cinoc corpus import`).",
    )
    run_cmd.add_argument(
        "--recipe",
        action="append",
        default=[],
        metavar="NOM",
        help="Instancie une recette (`cinoc list recipes`) sur le corpus de "
        "CONFIG, comme la file du banc d'essai web. Répétable : les recettes "
        "se comparent dans un seul run.",
    )
    run_cmd.add_argument(
        "--brick",
        action="append",
        default=[],
        metavar="[N:]ÉTAPE=BRIQUE",
        help="Avec --recipe : la brique d'une étape (ocr=kraken). Sans N:, "
        "chaque recette qui a l'étape ; N: vise la N-ième.",
    )
    run_cmd.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="[N:]ÉTAPE.RÉGLAGE=VALEUR",
        help="Avec --recipe : un réglage d'étape (ocr.lang=fra+deu, "
        "vlm.model=MODÈLE), valeur lue comme en YAML. "
        "`cinoc list engines <brique>` liste les réglages.",
    )
    run_cmd.add_argument(
        "--with",
        dest="with_steps",
        action="append",
        default=[],
        metavar="[N:]ÉTAPE",
        help="Avec --recipe : retient une étape facultative (ner, alto), "
        "comme sa case dans la page. `cinoc list recipes` les liste.",
    )
    _add_scoring(run_cmd, "Avec --recipe : ")
    run_cmd.add_argument(
        "--resume-dir",
        default=None,
        help="Cache de reprise et dossier d'artefacts du run : les (pipeline × "
        "document) déjà produits à l'identique y sont rechargés au lieu d'être "
        "ré-exécutés, et les sorties y survivent au run — réponses natives des "
        "moteurs distants et unités en échec comprises. C'est l'archive du run.",
    )
    run_cmd.add_argument(
        "--offline",
        action="store_true",
        help="Avec --resume-dir : re-note l'archive SANS aucun appel de moteur "
        "(après une montée de version d'une métrique, ou chez un tiers qui a "
        "reçu l'archive). Une unité absente de l'archive — jamais produite, ou "
        "produite par une autre version d'un module ou d'un binaire — fait "
        "échouer le run au lieu d'être exécutée.",
    )
    run_cmd.add_argument(
        "--analyses",
        default=None,
        help="Analyses détaillées : 'toutes', ou une liste séparée par des "
        "virgules ('diagnostics,word_errors'). Par défaut le run est en mode "
        "rapide — seules les métriques déclarées par les vues et leurs tests "
        "inter-moteurs sont calculés ('inference' y ajoute l'IC bootstrap). "
        "Prime sur ce que dit la spec.",
    )
    run_cmd.add_argument(
        "--csv",
        default=None,
        dest="csv_output",
        help="Export CSV tableur (agrégats + détail par-document).",
    )
    run_cmd.add_argument(
        "-o", "--output", default="rapport.html", help="Fichier HTML de sortie."
    )
    run_cmd.add_argument(
        "--report-dir",
        dest="report_dir",
        default=None,
        help="Écrit un bundle dossier (report.html + report-assets/ d'images "
        "réelles, liens relatifs) au lieu du HTML autonome de -o. Recommandé pour "
        "les gros corpus à images.",
    )
    run_cmd.add_argument(
        "--json",
        dest="json_output",
        default=None,
        help="Écrit aussi le RunResult en JSON (pour comparer plus tard).",
    )
    run_cmd.add_argument(
        "--hipe-jsonl",
        dest="hipe_jsonl",
        default=None,
        help="Exporte les sorties au format JSONL HIPE-OCRepair "
        "(un fichier par pipeline — soumission leaderboard).",
    )
    run_cmd.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Exécute la même spec N fois et écrit une FOURCHETTE par métrique "
        "au lieu d'une décimale isolée (≥5 recommandé). Le rapport et le JSON "
        "portent le dernier run ; le bilan de variance va dans "
        "<sortie>.variance.json. Avec --resume-dir, chaque répétition archive "
        "dans son dossier neuf (<archive>/repetition-<k>) : aucune ne relit "
        "une autre, et --offline les re-note toutes.",
    )
    run_cmd.add_argument(
        "--check",
        action="store_true",
        help="Valide le fichier et affiche le plan, SANS rien exécuter. Une "
        "spec de benchmark engage des appels facturés : la relire d'abord "
        "n'est pas un confort.",
    )
    run_cmd.add_argument(
        "--alto-dir",
        dest="alto_dir",
        default=None,
        help="Écrit les ALTO produits par le run dans ce dossier. Sans lui, un "
        "ALTO demandé par la spec meurt avec le workspace temporaire.",
    )
    run_cmd.add_argument(
        "--workers",
        type=int,
        default=None,
        help="Threads d'exécution (gros corpus). Défaut : CINOC_MAX_WORKERS "
        "puis le nombre de CPU. 1 = séquentiel. Résultat identique quel que "
        "soit le nombre (assemblage ordonné par le spec).",
    )
    history_cmd = subparsers.add_parser(
        "history",
        help="Historique longitudinal : séries (corpus, profil, pipeline, vue) "
        "d'un pipeline, ou régressions.",
    )
    history_cmd.add_argument("db", help="Base SQLite de l'historique.")
    history_cmd.add_argument("--view", default="texte")
    history_cmd.add_argument("--metric", default="cer")
    history_cmd.add_argument(
        "--pipeline",
        default=None,
        help="Série chronologique de ce pipeline (sinon : régressions).",
    )
    history_cmd.add_argument("--threshold", type=float, default=0.0)

    compare_cmd = subparsers.add_parser(
        "compare", help="Compare deux RunResult JSON → rapport de deltas."
    )
    compare_cmd.add_argument("run_a", help="Premier RunResult (JSON).")
    compare_cmd.add_argument("run_b", help="Second RunResult (JSON).")
    compare_cmd.add_argument(
        "-o", "--output", default="comparaison.html", help="Fichier HTML de sortie."
    )
    compare_cmd.add_argument(
        "--lang", default="fr", choices=("fr", "en"),
        help="Langue du rapport (libellés et séparateur décimal).",
    )
    hybrid_cmd = subparsers.add_parser(
        "hybrid",
        help="Transcription hybride : segmente → OCR par bloc → ALTO/page "
        "(la recette segmentation_puis_lecture, export ALTO retenu).",
    )
    hybrid_cmd.add_argument("images", help="Dossier d'images à transcrire.")
    hybrid_cmd.add_argument(
        "--out", default="alto", help="Dossier de sortie des ALTO (défaut : alto/)."
    )
    hybrid_cmd.add_argument(
        "--segmenter",
        default="pp_doclayout",
        help="Segmenteur (pp_doclayout, tesseract_layout, doclayout_yolo, "
        "remote_segmenter ; precomputed_layout en démo).",
    )
    hybrid_cmd.add_argument(
        "--ocr",
        default="tesseract",
        help="Reconnaisseur par bloc : OCR réel (tesseract, mistral_ocr, "
        "google_vision, azure_di, kraken, pero, calamari) ou VLM zero-shot "
        "(openai, anthropic, mistral) ; precomputed_region en démo.",
    )
    hybrid_cmd.add_argument(
        "--source-label",
        default=None,
        help="Jeu de textes par région (mode precomputed_region).",
    )
    hybrid_cmd.add_argument(
        "--lang",
        default=None,
        help="Langue OCR par bloc (défaut : celui du moteur ; moteurs qui la "
        "déclarent).",
    )
    hybrid_cmd.add_argument(
        "--model",
        default=None,
        help="Modèle du reconnaisseur (chemin/checkpoint OCR ou modèle VLM).",
    )
    hybrid_cmd.add_argument(
        "--prompt",
        default=None,
        help="Prompt de transcription pour un reconnaisseur VLM (zero-shot).",
    )
    hybrid_cmd.add_argument(
        "--segment-only",
        dest="segment_only",
        action="store_true",
        help="S'arrête après la segmentation : écrit un LAYOUT par page au "
        "lieu d'un ALTO. Relisible par `precomputed_layout` — on segmente une "
        "fois, on rejoue plusieurs reconnaissances dessus.",
    )
    hybrid_cmd.add_argument(
        "--segmenter-endpoint",
        dest="segmenter_endpoint",
        default=None,
        help="Endpoint object-detection (REQUIS avec --segmenter "
        "remote_segmenter : c'est lui qui porte le modèle de mise en page).",
    )
    hybrid_cmd.add_argument(
        "--segmenter-token",
        dest="segmenter_token",
        default=None,
        help="Jeton d'authentification de l'endpoint de segmentation distant.",
    )

    correct_cmd = subparsers.add_parser(
        "correct",
        help="Corrige un dossier d'ALTO existants (post-correction structurée).",
    )
    correct_cmd.add_argument(
        "alto_dir", help="Dossier de paires <nom>.xml + <nom>.png/.jpg."
    )
    correct_cmd.add_argument(
        "-o", "--output", default="rapport.html", help="Fichier HTML de sortie."
    )
    correct_cmd.add_argument(
        "--producer",
        default="rules",
        # Dérivés de l'adapter : une troisième copie de la liste aurait laissé
        # la CLI offrir deux producteurs sur quatre, en silence.
        choices=PRODUCERS,
        help="Producteur de corrections. 'rules' est déterministe et hors "
        "ligne ; les autres interrogent un modèle et exigent --model "
        "('mistral_vision' découpe en plus chaque ligne dans le scan).",
    )
    correct_cmd.add_argument(
        "--model",
        default="",
        help="Modèle du producteur (requis hors 'rules' ; "
        "`cinoc list models <fournisseur>` les liste).",
    )
    correct_cmd.add_argument(
        "--host", default="http://localhost:11434", help="Serveur ollama."
    )
    correct_cmd.add_argument(
        "--ocr-sidecar",
        dest="ocr_sidecar",
        default="",
        help="JSON d'OCR réel {'ocr': {fichier: {line_id: texte}}} qui remplace "
        "le texte des lignes. INDISPENSABLE sur un corpus à vérité terrain : "
        "sans lui la source lit la référence, il n'y a rien à corriger, et le "
        "CER vaut zéro par construction.",
    )
    correct_cmd.add_argument(
        "--no-ground-truth",
        dest="ground_truth",
        action="store_false",
        help="L'ALTO est de l'OCR, pas une transcription : aucune vue de "
        "structure n'est ajoutée (il n'y aurait rien à quoi comparer).",
    )
    _add_scoring(correct_cmd, "")
    correct_cmd.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Exécute N fois et écrit une fourchette (≥5 recommandé).",
    )
    _add_corpus(subparsers)
    _add_list(subparsers)
    serve_cmd = subparsers.add_parser(
        "serve", help="Sert la vitrine web des rapports (extra [serve])."
    )
    serve_cmd.add_argument(
        "--host", default="127.0.0.1", help="Adresse d'écoute (défaut : local)."
    )
    serve_cmd.add_argument(
        "--port", type=int, default=8000, help="Port d'écoute (défaut : 8000)."
    )
    serve_cmd.add_argument(
        "--reports-dir",
        default=None,
        help="Dossier des rapports RunResult JSON à servir.",
    )
    return parser


#: Les sous-commandes de ``cinoc`` — la **surface** de la CLI.
#:
#: Déclarée ici plutôt que relue dans le parseur : ``argparse`` n'expose aucune
#: API publique pour ses sous-commandes, et fouiller ses internes pour un simple
#: contrat de surface serait un couplage fragile (cf. le garde-fou
#: ``test_no_foreign_private_access``). La constante ne peut pas dériver : le
#: test ``test_declared_surface_matches_the_parser`` la confronte au parseur réel.
SUBCOMMANDS: tuple[str, ...] = (
    "demo",
    "run",
    "correct",
    "history",
    "hybrid",
    "compare",
    "corpus",
    "list",
    "serve",
)


__all__ = ["SUBCOMMANDS", "build_parser"]

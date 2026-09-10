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


def build_parser() -> argparse.ArgumentParser:
    """Le parseur complet de ``cinoc``. Aucun effet de bord."""
    parser = argparse.ArgumentParser(
        prog="cinoc",
        description="Banc d'essai déterministe de pipelines de transcription.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser(
        "demo",
        help="Génère un rapport de démonstration déterministe (sans moteur).",
    )
    demo.add_argument(
        "-o", "--output", default="rapport_demo.html", help="Fichier HTML de sortie."
    )
    run_cmd = subparsers.add_parser(
        "run", help="Exécute un run décrit dans un fichier YAML."
    )
    run_cmd.add_argument("config", help="Fichier YAML décrivant le run.")
    run_cmd.add_argument(
        "--resume-dir",
        default=None,
        help="Cache de reprise : les (pipeline × document) déjà produits à "
        "l'identique y sont rechargés au lieu d'être ré-exécutés.",
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
        "<sortie>.variance.json. Incompatible avec --resume-dir : rejouer un "
        "cache mesurerait le cache.",
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
        help="Historique longitudinal : série d'un pipeline ou régressions.",
    )
    history_cmd.add_argument("db", help="Base SQLite de l'historique.")
    history_cmd.add_argument("--view", default="text")
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
    hybrid_cmd = subparsers.add_parser(
        "hybrid",
        help="Transcription hybride : segmente → OCR par bloc → ALTO/page.",
    )
    hybrid_cmd.add_argument("images", help="Dossier d'images à transcrire.")
    hybrid_cmd.add_argument(
        "--out", default="alto", help="Dossier de sortie des ALTO (défaut : alto/)."
    )
    hybrid_cmd.add_argument(
        "--segmenter",
        default="pp_doclayout",
        help="Segmenteur (pp_doclayout, remote_segmenter, precomputed_layout).",
    )
    hybrid_cmd.add_argument(
        "--ocr",
        default="tesseract",
        help="Reconnaisseur par bloc : OCR réel (tesseract, mistral_ocr, "
        "google_vision, azure_di, kraken, pero, calamari) ou VLM zero-shot "
        "(openai, anthropic, mistral) ; precomputed_region en démo.",
    )
    hybrid_cmd.add_argument(
        "--label", default="hybrid", help="Étiquette du moteur (identité)."
    )
    hybrid_cmd.add_argument(
        "--source-label",
        default=None,
        help="Jeu de textes par région (mode precomputed_region).",
    )
    hybrid_cmd.add_argument(
        "--lang", default="fra", help="Langue OCR par bloc (moteurs OCR réels)."
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
        choices=("rules", "ollama"),
        help="Producteur de corrections. 'rules' est déterministe et hors "
        "ligne ; 'ollama' parle à un serveur local (exige --model).",
    )
    correct_cmd.add_argument(
        "--model", default="", help="Modèle ollama (ex. gemma4:e2b)."
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
    correct_cmd.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Exécute N fois et écrit une fourchette (≥5 recommandé).",
    )
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
    "serve",
)


__all__ = ["SUBCOMMANDS", "build_parser"]

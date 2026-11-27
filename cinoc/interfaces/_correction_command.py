"""Commande ``cinoc correct`` : post-correction structurée d'ALTO existants (couche 8).

Extraite de ``cli.py`` : le fichier de transport a un budget de taille, et une
commande qui compose planification + orchestration + rendu n'y tient pas sans le
faire dériver. Le transport reste dans ``cli.py`` (les arguments) ; l'assemblage
vit ici.

Corriger **dans** la mise en page : chaque ligne garde son identifiant, donc
l'appariement avant/après est connu et le rapport peut dire ce qui a été changé,
ce qui a été **refusé**, et pourquoi.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from cinoc.app import resolve_code_version
from cinoc.app import run as run_orchestrator

# Les producteurs de correction sont lus en couche `app`, pas recopiés ici :
# une interface qui énumère est une interface qui dérive.
from cinoc.app.alto_corpus import PRODUCERS, corpus_from_alto, truth_summary
from cinoc.app.evaluation_views import EvaluationOptions
from cinoc.app.modules import (
    ModuleRegistry,
    discover_plugins,
    register_default_modules,
)
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.app.report_images import build_facsimiles, build_thumbnails
from cinoc.app.variance import VarianceSummary, run_repeatedly
from cinoc.evaluation.result import RunResult
from cinoc.interfaces._run_summary import console_safe, print_progress, unit_summary
from cinoc.reports import default_report_renderer

if TYPE_CHECKING:  # pragma: no cover
    _SousCommandes = argparse._SubParsersAction[argparse.ArgumentParser]  # noqa: SLF001


def add_correct_parser(
    subparsers: _SousCommandes,
    add_scoring: Callable[[argparse.ArgumentParser, str], None],
) -> None:
    """``cinoc correct`` : sa surface, à côté de son assemblage (budget de
    ``_cli_parser.py``). ``add_scoring`` : les options de notation communes."""
    correct_cmd = subparsers.add_parser(
        "correct",
        help="Corrige un dossier d'ALTO existants (post-correction structurée).",
    )
    correct_cmd.add_argument(
        "alto_dir",
        help="Dossier d'images, chacune avec son ALTO : <nom>.xml (ou "
        "<nom>.alto.xml) à côté de <nom>.png ; une transcription <nom>.gt.txt "
        "posée à côté est la vérité terrain.",
    )
    correct_cmd.add_argument(
        "-o", "--output", default="rapport.html", help="Fichier HTML de sortie."
    )
    correct_cmd.add_argument(
        "--pipeline",
        default="",
        help="Lit l'ALTO qu'un run Cinoc a écrit pour ce pipeline "
        "(<nom>.<pipeline>.alto.xml, sortie de --alto-dir et de cinoc hybrid) ; "
        "il n'est jamais pris pour une vérité terrain.",
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
        "le texte des lignes : l'ALTO est alors une transcription, vérité de la "
        "vue structure. INDISPENSABLE sur un corpus à vérité terrain : sans lui "
        "la source lit la référence et il n'y a rien à corriger.",
    )
    correct_cmd.add_argument(
        "--no-ground-truth",
        dest="ground_truth",
        action="store_false",
        help="N'utilise aucune vérité terrain (ni <nom>.gt.txt, ni l'ALTO sous "
        "--ocr-sidecar) : rien n'est noté, la commande et le rapport le disent.",
    )
    add_scoring(correct_cmd, "")
    correct_cmd.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Exécute N fois et écrit une fourchette (≥5 recommandé).",
    )


def write_variance(output: Path, variance: VarianceSummary) -> None:
    """Écrit la fourchette à côté du rapport et l'affiche.

    Affichée **et** écrite : un fichier qu'on ne regarde pas ne protège de rien,
    et c'est le chiffre le plus large qui borne ce qu'on a le droit d'affirmer.
    """
    chemin = output.with_suffix(output.suffix + ".variance.json")
    chemin.write_text(variance.model_dump_json(indent=2), encoding="utf-8")
    print(f"\nVariance sur {variance.runs} runs ({variance.corpus}) :")
    pires = variance.widest()
    if not pires:
        print("  aucune métrique applicable sur plusieurs runs.")
    for spread in pires:
        # La vue est nommée : un même ``cer`` existe en ``texte`` et en
        # ``texte (lignes)``, deux fourchettes qu'on ne distinguait pas (S34b).
        ligne = (
            f"  {spread.pipeline} · {spread.view} · {spread.metric} : "
            f"{spread.minimum:.4f} – {spread.maximum:.4f} "
            f"(médiane {spread.median_value:.4f}, étendue {spread.spread:.1%})"
        )
        print(console_safe(ligne, sys.stdout))
    if pires:
        print(
            "  Toute comparaison plus serrée que l'étendue la plus large "
            "est du bruit sur ce corpus."
        )
    print(
        f"Bilan de variance écrit : {chemin} — le rapport HTML porte le dernier "
        "run ; la fourchette vit dans ce fichier."
    )


def run_correction(
    alto_dir: str,
    output: str,
    *,
    pipeline: str = "",
    producer: str,
    model: str,
    host: str,
    ocr_sidecar: str,
    ground_truth: bool,
    repeat: int,
    options: EvaluationOptions | None = None,
) -> int:
    """Post-correction **structurée** d'un dossier d'ALTO existants.

    Corrige **dans** la mise en page : chaque ligne garde son identifiant, donc
    l'appariement avant/après est connu et le rapport peut dire ce qui a été
    changé, ce qui a été **refusé**, et pourquoi. Code de sortie : celui de
    ``cinoc run`` (``0``, ou ``3`` si une unité a échoué, rapport écrit).
    """
    corpus = corpus_from_alto(
        alto_dir, pipeline=pipeline, ocr_sidecar=ocr_sidecar, ground_truth=ground_truth
    )
    # Dit avant le run : ce que les chiffres mesureront, ou qu'il n'y en aura
    # pas (D-307) — jamais un tableau vide ou un zéro sans explication.
    print(truth_summary(corpus))
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    # La recette ``alto_corrige``, par la file de la page (D-298) : les options
    # ne font que nommer ses réglages.
    correcteur = {"producer": producer, "host": host, "model": model}
    source = {"ocr_sidecar": ocr_sidecar, "pipeline": pipeline}
    spec = plan_recipe_run(
        corpus,
        (
            RecipeEntry(
                recipe="alto_corrige",
                params={
                    "correction": {k: v for k, v in correcteur.items() if v},
                    **(
                        {"source": {k: v for k, v in source.items() if v}}
                        if any(source.values())
                        else {}
                    ),
                },
            ),
        ),
        run_id="correction",
        options=options,
    )

    # Les images sont à côté des ALTO : le ``RunResult`` les y rapporte (D-282).
    root = Path(alto_dir)

    def _once(index: int) -> RunResult:
        if repeat > 1:
            print(f"run {index + 1}/{repeat}…", flush=True)
        return run_orchestrator(
            spec,
            registry=registry,
            code_version=resolve_code_version(),
            paths_root=root,
            on_progress=print_progress,
        )

    results, variance = run_repeatedly(_once, repeat)
    if repeat > 1:
        write_variance(Path(output), variance)
    Path(output).write_text(
        default_report_renderer().render(
            results[-1],
            title=f"Cinoc — correction de {corpus.name}",
            images=build_thumbnails(results[-1], image_root=root),
            facsimiles=build_facsimiles(results[-1], image_root=root),
        ),
        encoding="utf-8",
    )
    print(f"{len(corpus.documents)} document(s) corrigé(s) — rapport : {output}")
    # Même bilan et même code de sortie que ``cinoc run`` (code 3 si une unité
    # a échoué) : une correction qui perd des pages ne sort plus en 0.
    return unit_summary(results)

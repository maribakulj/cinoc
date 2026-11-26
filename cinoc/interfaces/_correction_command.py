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

from pathlib import Path

from cinoc.app import resolve_code_version
from cinoc.app import run as run_orchestrator
from cinoc.app.correction_planning import corpus_from_alto, plan_correction_run
from cinoc.app.modules import (
    ModuleRegistry,
    discover_plugins,
    register_default_modules,
)
from cinoc.app.report_images import build_facsimiles, build_thumbnails
from cinoc.app.variance import VarianceSummary, run_repeatedly
from cinoc.evaluation.result import RunResult
from cinoc.reports import default_report_renderer


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
        print(
            f"  {spread.pipeline} · {spread.metric} : "
            f"{spread.minimum:.4f} – {spread.maximum:.4f} "
            f"(médiane {spread.median_value:.4f}, étendue {spread.spread:.1%})"
        )
    if pires:
        print(
            "  Toute comparaison plus serrée que l'étendue la plus large "
            "est du bruit sur ce corpus."
        )
    print(f"Bilan de variance écrit : {chemin}")


def run_correction(
    alto_dir: str,
    output: str,
    *,
    producer: str,
    model: str,
    host: str,
    ocr_sidecar: str,
    ground_truth: bool,
    repeat: int,
) -> int:
    """Post-correction **structurée** d'un dossier d'ALTO existants.

    Corrige **dans** la mise en page : chaque ligne garde son identifiant, donc
    l'appariement avant/après est connu et le rapport peut dire ce qui a été
    changé, ce qui a été **refusé**, et pourquoi.
    """
    corpus = corpus_from_alto(alto_dir, ground_truth=ground_truth)
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    spec = plan_correction_run(
        corpus,
        "correction",
        producer=producer,
        model=model,
        host=host,
        ocr_sidecar=ocr_sidecar,
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
    return 0

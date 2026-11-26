"""CLI Cinoc (couche 8) : ``demo``, ``run``, ``compare``, ``serve``.

``argparse`` (stdlib, aucune dépendance — journal D-007). ``demo`` génère un
rapport de démonstration **déterministe** sans moteur réel : un mini-corpus
pré-calculé en mémoire → ``precomputed`` → CER → ``RunResult`` → HTML autonome.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING

from cinoc.app import (
    dump_run_result,
    load_run_result,
    load_run_spec,
    resolve_code_version,
)
from cinoc.app import run as run_orchestrator
from cinoc.app.analyses_demandees import appliquer_analyses
from cinoc.app.demo import demo_run_spec, write_demo_corpus
from cinoc.app.modules import (
    ModuleRegistry,
    discover_plugins,
    register_default_modules,
)
from cinoc.app.orchestrator import PipelineOutputs
from cinoc.app.report_images import (
    build_facsimiles,
    build_thumbnails,
    write_report_bundle,
)
from cinoc.app.resume import ResumeStore, repetition_dir
from cinoc.app.variance import run_repeatedly
from cinoc.domain.errors import CinocError
from cinoc.domain.run import RunManifest
from cinoc.domain.run_spec import RunSpec
from cinoc.domain.usage import ResourceUsage
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.evaluation.result import RunResult
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces._corpus_command import (
    run_corpus_discover,
    run_corpus_import,
    run_corpus_search,
    run_corpus_standardize,
)
from cinoc.interfaces._correction_command import run_correction, write_variance
from cinoc.interfaces._list_command import (
    run_list_engines,
    run_list_models,
    run_list_profiles,
    run_list_prompts,
    run_list_recipes,
)
from cinoc.interfaces._recipe_spec import scoring_options, spec_loader
from cinoc.interfaces._run_summary import unit_summary
from cinoc.interfaces._serve_command import serve_command
from cinoc.reports import default_report_renderer, render_comparison
from cinoc.reports.csv_export import run_result_csv

if TYPE_CHECKING:
    from cinoc.adapters.storage.history_store import SeriesKey

#: Horodatage figé du rapport de démo (golden octet-stable, cf. ``demo_to_html``).
_DEMO_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def demo_to_html() -> str:
    """Exécute la démo et renvoie le rapport HTML (déterministe).

    La démo est la **vitrine du déterminisme** (golden octet-stable entre deux
    exécutions) : on retire du ``RunResult`` les canaux **environnementaux**
    avant rendu — les durées de ``usage`` (wall-clock) et l'analyse ``economics`` qui
    en dérive varient d'un run à l'autre par nature (arbitrage D-068 ; un run
    réel, lui, les rend : le rapport reste une fonction pure du ``RunResult``).
    """
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    with TemporaryDirectory() as tmp:
        corpus = write_demo_corpus(Path(tmp))
        result = run_orchestrator(
            demo_run_spec(corpus),
            registry=registry,
            code_version=resolve_code_version(),
        )
    stable = result.model_copy(
        update={
            # Horodatages du manifeste = environnementaux (wall-clock) → figés pour
            # le golden. Le run_id en dérive (``run-<timestamp>``) : figé aussi.
            "manifest": result.manifest.model_copy(
                update={
                    "run_id": "demo",
                    "started_at": _DEMO_EPOCH,
                    "completed_at": _DEMO_EPOCH,
                }
            ),
            # Durées vidées, **issues gardées** : l'issue d'une unité est une
            # donnée du run, pas une mesure d'environnement.
            "usage": tuple(
                u.model_copy(update={"usage": ResourceUsage()}) for u in result.usage
            ),
            # Réfs image = chemins du TemporaryDirectory (éphémères) → neutralisés
            # comme les autres canaux environnementaux (golden octet-stable).
            "documents": tuple(
                d.model_copy(update={"image_ref": None}) for d in result.documents
            ),
            "analyses": tuple(
                analysis
                for analysis in result.analyses
                if not isinstance(analysis.payload, EconomicsPayload)
            ),
        }
    )
    return default_report_renderer().render(stable, title="Cinoc — démonstration")


def _run_history(
    db: str, view: str, metric: str, pipeline: str | None, threshold: float
) -> int:
    """Lit le ``HistoryStore`` : séries d'un pipeline, ou régressions de la vue.

    Une série = (corpus, profil, pipeline, vue) : chaque série est imprimée
    sous son en-tête, jamais mêlée à une autre (D-288).
    """
    from cinoc.adapters.storage.history_store import HistoryStore

    store = HistoryStore(Path(db))
    if pipeline is not None:
        series = store.series(view, metric, pipeline=pipeline)
        if not series:
            print(f"Aucune mesure pour {pipeline!r} ({view}:{metric}).")
            return 0
        for key, records in series:
            print(f"[{_series_label(key)}]")
            for record in records:
                print(
                    f"  {record.completed_at}  {record.run_id}  "
                    f"{record.metric}={record.value:.6f}  "
                    f"(code {record.code_version})"
                )
        return 0
    regressions = store.regressions(view, metric, threshold=threshold)
    if not regressions:
        print(f"Aucune régression ({view}:{metric}, seuil {threshold:g}).")
        return 0
    # ASCII : une console Windows redirigée est en cp1252, sans « → » ni « Δ ».
    for reg in regressions:
        print(
            f"{reg.pipeline}: {reg.previous:.6f} -> {reg.latest:.6f} "
            f"(delta {reg.delta:+.6f}, run {reg.latest_run_id}) "
            f"[corpus {reg.corpus_name}, profil {reg.normalization_profile or 'brut'}]"
        )
    return 0


def _series_label(key: SeriesKey) -> str:
    profile = key.normalization_profile or "brut"
    return f"corpus {key.corpus_name} | profil {profile} | {key.pipeline} | {key.view}"


def _run_demo(output: str) -> int:
    path = Path(output)
    path.write_text(demo_to_html(), encoding="utf-8")
    print(f"Rapport de démonstration écrit : {path}")
    return 0



#: Signature du puits d'artefacts de l'orchestrateur.
ArtifactSink = Callable[[PipelineOutputs, RunManifest], None]


def _combined_sink(sinks: list[ArtifactSink]) -> ArtifactSink | None:
    """Compose plusieurs puits en un seul (l'orchestrateur n'en accepte qu'un)."""
    if not sinks:
        return None
    if len(sinks) == 1:
        return sinks[0]

    def _tous(outputs: PipelineOutputs, manifest: RunManifest) -> None:
        for sink in sinks:
            sink(outputs, manifest)

    return _tous


def _report_alto(out_dir: Path, outputs: PipelineOutputs) -> None:
    from cinoc.app.transcription import write_alto_files

    ecrits = write_alto_files(out_dir, outputs)
    print(f"{len(ecrits)} ALTO écrit(s) dans {out_dir}")


def _print_plan(spec: RunSpec, registry: ModuleRegistry) -> int:
    """Décrit ce qu'un run **ferait**, sans rien exécuter.

    Une spec de benchmark engage des appels facturés et des heures de calcul ;
    pouvoir la relire avant de la lancer n'est pas un confort.

    La cohérence est contrôlée **ici aussi**, et pas seulement au run : une spec
    dont le montage ne ferait pas ce qu'il annonce doit être refusée avant le
    premier appel facturé, pas après. De même pour les réglages : chaque brique
    est construite (sans rien exécuter), donc un réglage qu'elle ne déclare pas
    est refusé ici, nommé — pas accepté puis ignoré au run (D14).
    """
    from cinoc.app.models import check_spec_models  # noqa: PLC0415
    from cinoc.app.modules.registry import check_spec_settings  # noqa: PLC0415
    from cinoc.app.spec_coherence import check  # noqa: PLC0415

    check(spec)
    # Chaque modèle nommé est demandé **en direct** au fournisseur (D13) : un
    # modèle absent est refusé ; une liste illisible est dite, pas tranchée.
    notes = check_spec_models(spec, live=True)
    check_spec_settings(spec, registry)
    print(f"Corpus     : {spec.corpus.name} — {len(spec.corpus.documents)} document(s)")
    print(f"Pipelines  : {len(spec.pipelines)}")
    for pipeline in spec.pipelines:
        etapes = " → ".join(
            f"{step.kind}:{step.adapter_name}" for step in pipeline.steps
        )
        print(f"  {pipeline.name}\n    {etapes or '(aucune étape)'}")
    print(f"Évaluation : {len(spec.evaluation.views)} vue(s)")
    for view in spec.evaluation.views:
        cible = f" (étape notée : {view.target_step})" if view.target_step else ""
        metriques = ", ".join(view.metric_names) or "(aucune métrique)"
        print(f"  {view.name} — {metriques}{cible}")
    for note in notes:
        print(f"Attention  : {note}")
    print("\nSpec valide. Rien n'a été exécuté (--check).")
    return 0


def _run_config(
    config_path: str,
    output: str,
    json_output: str | None,
    resume_dir: str | None = None,
    csv_output: str | None = None,
    hipe_jsonl: str | None = None,
    max_workers: int | None = None,
    report_dir: str | None = None,
    repeat: int = 1,
    check: bool = False,
    alto_dir: str | None = None,
    analyses: str | None = None,
    offline: bool = False,
    load: Callable[[str | Path], RunSpec] = load_run_spec,
) -> int:
    if offline and not resume_dir:
        raise CinocError(
            "--offline re-note une archive : il exige --resume-dir <archive>."
        )
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    spec = load(config_path)  # une spec, ou un corpus + recettes (--recipe)
    # L'option de lancement prime sur la spec : répondre à une question
    # ponctuelle ne doit pas demander d'éditer un fichier partagé.
    spec = appliquer_analyses(spec, analyses)
    if check:
        # Valider **sans exécuter** : le chargement a déjà refusé une spec
        # invalide (Pydantic + chemins sécurisés) ; reste à montrer ce qui
        # serait lancé, pour qu'on le lise avant de payer des appels d'API.
        return _print_plan(spec, registry)
    # Même contrôle hors ``--check`` : un run lancé sans relecture ne doit pas
    # échapper à ce qu'une relecture aurait refusé.
    from cinoc.app.models import check_spec_models  # noqa: PLC0415
    from cinoc.app.modules.registry import check_spec_settings  # noqa: PLC0415
    from cinoc.app.spec_coherence import check as _coherent  # noqa: PLC0415

    _coherent(spec)
    check_spec_models(spec, live=False)  # aucun modèle par défaut
    check_spec_settings(spec, registry)  # aucun réglage ignoré en silence
    # Export HIPE = sink d'artefacts (les textes sont lus avant le nettoyage du
    # workspace) — le format JSONL porte les textes, pas les scores.
    sinks: list[ArtifactSink] = []
    if hipe_jsonl is not None:
        from cinoc.app.hipe_export import hipe_jsonl_sink

        sinks.append(hipe_jsonl_sink(Path(hipe_jsonl), spec.corpus))
    if alto_dir is not None:
        # Un run qui produit des ALTO les laissait mourir avec le workspace :
        # seule la voie web les persistait. Même écrivain que `cinoc hybrid`.

        cible = Path(alto_dir)
        sinks.append(lambda outputs, _manifest: _report_alto(cible, outputs))
    artifact_sink = _combined_sink(sinks)
    # Racine des chemins de la spec (``load_run_spec``) : le ``RunResult`` y
    # rapporte ses images et son archive, le rapport les y relit (D-282).
    root = Path(config_path).parent

    def _once(index: int) -> RunResult:
        if repeat > 1:
            print(f"run {index + 1}/{repeat}…", flush=True)
        return run_orchestrator(
            spec,
            registry=registry,
            code_version=resolve_code_version(),
            # Une archive par répétition : aucune ne relit une autre.
            resume_store=(
                ResumeStore(repetition_dir(Path(resume_dir), index, repeat))
                if resume_dir
                else None
            ),
            artifact_sink=artifact_sink,
            max_workers=max_workers,
            offline=offline,
            paths_root=root,
        )

    results, variance = run_repeatedly(_once, repeat)
    # Le rapport porte le DERNIER run : un rapport qui mélangerait des runs
    # n'en décrirait aucun. La fourchette vit à côté, dans son propre fichier.
    result = results[-1]
    if repeat > 1:
        write_variance(Path(output), variance)
    title = f"Cinoc — {spec.corpus.name}"
    if report_dir is not None:
        # Saveur dossier : images réelles dans report-assets/, HTML à liens
        # relatifs. Le renderer (couche 7) est injecté — app n'importe pas reports.
        report = write_report_bundle(
            result,
            report_dir,
            render=default_report_renderer().render,
            title=title,
            image_root=root,
        )
        written = str(report)
    else:
        # Saveur fichier unique : vignettes data-URI inlinées dans le HTML.
        Path(output).write_text(
            default_report_renderer().render(
                result,
                title=title,
                images=build_thumbnails(result, image_root=root),
                facsimiles=build_facsimiles(result, image_root=root),
            ),
            encoding="utf-8",
        )
        written = output
    if json_output is not None:
        dump_run_result(result, json_output)
    if csv_output is not None:
        Path(csv_output).write_text(run_result_csv(result), encoding="utf-8")
    print(f"Rapport écrit : {written}")
    return unit_summary(results)


def _run_hybrid(
    images: str,
    out: str,
    *,
    segmenter: str,
    ocr: str,
    source_label: str | None,
    lang: str | None = None,
    model: str | None = None,
    prompt: str | None = None,
    endpoint: str | None = None,
    token: str | None = None,
    segment_only: bool = False,
) -> int:
    """Transcription **hybride** : segmente, reconnaît par bloc, assemble un ALTO/page.

    Part d'un dossier d'images (sans GT) → ``CorpusSpec`` → la recette
    ``segmentation_puis_lecture``, export ALTO retenu — la file de la page et
    de ``cinoc run --recipe`` (``plan_recipe_run``, D-298), les options ne
    faisant que nommer ses briques et ses réglages ; les ``ALTO_XML`` sont
    écrits dans ``out`` par un sink (avant nettoyage du workspace).

    ``segment_only`` s'arrête à la mise en page : même corpus, même orchestrateur,
    mais ``plan_segmentation_run`` et un ``LAYOUT`` par page en sortie.
    """
    from cinoc.app import structure_planning
    from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
    from cinoc.app.transcription import (
        corpus_from_images,
        write_alto_files,
        write_layout_files,
    )

    corpus = corpus_from_images(images)
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    if segment_only:
        # La mise en page est un livrable en soi : on la relit, on la corrige,
        # on rejoue plusieurs reconnaissances dessus sans re-segmenter.
        spec = structure_planning.plan_segmentation_run(
            corpus, "segmentation", segmenter=segmenter,
            endpoint=endpoint, token=token,
        )(Path(out))
        ecrire = write_layout_files
    else:
        reglages = {
            "seg": {"endpoint": endpoint, "token": token},
            "reco": {"source_label": source_label, "lang": lang,
                     "model": model, "prompt": prompt},
        }
        spec = plan_recipe_run(
            corpus,
            (
                RecipeEntry(
                    recipe="segmentation_puis_lecture",
                    choices={"seg": segmenter, "reco": ocr},
                    params={
                        etape: {k: v for k, v in valeurs.items() if v}
                        for etape, valeurs in reglages.items()
                    },
                    optional=("alto",),
                ),
            ),
            run_id="hybrid",
        )
        ecrire = write_alto_files
    out_dir = Path(out)
    written: list[Path] = []

    def _sink(outputs: PipelineOutputs, manifest: RunManifest) -> None:
        written.extend(ecrire(out_dir, outputs))

    run_orchestrator(
        spec,
        registry=registry,
        code_version=resolve_code_version(),
        artifact_sink=_sink,
    )
    quoi = "LAYOUT" if segment_only else "ALTO"
    print(f"{len(written)} {quoi} écrit(s) dans {out_dir}")
    return 0


def _compare_command(path_a: str, path_b: str, output: str, lang: str) -> int:
    runs = load_run_result(a := Path(path_a)), load_run_result(b := Path(path_b))
    html = render_comparison(*runs, lang=lang, source_a=a.name, source_b=b.name)
    Path(output).write_text(html, encoding="utf-8")
    print(f"Comparaison écrite : {output}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Les erreurs métier (spec invalide, chemin hors zone…) et d'E/S sont
    # rapportées proprement sur stderr + code de sortie 1 — jamais une trace nue.
    try:
        if args.command == "demo":
            return _run_demo(args.output)
        if args.command == "run":
            return _run_config(
                args.config,
                args.output,
                args.json_output,
                args.resume_dir,
                args.csv_output,
                args.hipe_jsonl,
                args.workers,
                args.report_dir,
                args.repeat,
                args.check,
                args.alto_dir,
                args.analyses,
                args.offline,
                spec_loader(args),
            )
        if args.command == "correct":
            return run_correction(
                args.alto_dir,
                args.output,
                pipeline=args.pipeline,
                producer=args.producer,
                model=args.model,
                host=args.host,
                ocr_sidecar=args.ocr_sidecar,
                ground_truth=args.ground_truth,
                repeat=args.repeat,
                options=scoring_options(args),
            )
        if args.command == "history":
            return _run_history(
                args.db, args.view, args.metric, args.pipeline, args.threshold
            )
        if args.command == "hybrid":
            return _run_hybrid(
                args.images,
                args.out,
                segmenter=args.segmenter,
                ocr=args.ocr,
                source_label=args.source_label,
                lang=args.lang,
                model=args.model,
                prompt=args.prompt,
                endpoint=args.segmenter_endpoint,
                token=args.segmenter_token,
                segment_only=args.segment_only,
            )
        if args.command == "corpus":
            # Sous-arbre : le verbe choisi porte la capacité (importer,
            # chercher, standardiser, découvrir) ; argparse a déjà borné les valeurs.
            if args.corpus_command == "import":
                return run_corpus_import(args)
            if args.corpus_command == "search":
                return run_corpus_search(args)
            if args.corpus_command == "standardize":
                return run_corpus_standardize(args)
            return run_corpus_discover(args)
        if args.command == "list":
            sujets = {
                "engines": run_list_engines,
                "models": run_list_models,
                "profiles": run_list_profiles,
                "prompts": run_list_prompts,
                "recipes": run_list_recipes,
            }
            return sujets[args.topic](args)
        if args.command == "compare":
            return _compare_command(args.run_a, args.run_b, args.output, args.lang)
        if args.command == "serve":
            return serve_command(args.host, args.port, args.reports_dir)
    except (CinocError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 1  # pragma: no cover (sous-commande requise)


__all__ = ["demo_to_html", "main"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

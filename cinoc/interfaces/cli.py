"""CLI Cinoc (couche 8) : ``demo``, ``run``, ``compare``, ``serve``.

``argparse`` (stdlib, aucune dépendance — journal D-007). ``demo`` génère un
rapport de démonstration **déterministe** sans moteur réel : un mini-corpus
pré-calculé en mémoire → ``precomputed`` → CER → ``RunResult`` → HTML autonome.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from cinoc.app import (
    dump_run_result,
    load_run_result,
    load_run_spec,
    resolve_code_version,
)
from cinoc.app import run as run_orchestrator
from cinoc.app.demo import demo_run_spec, write_demo_corpus
from cinoc.app.modules import (
    ModuleRegistry,
    discover_plugins,
    register_default_modules,
)
from cinoc.app.report_images import (
    build_facsimiles,
    build_thumbnails,
    write_report_bundle,
)
from cinoc.app.resume import ResumeStore
from cinoc.app.variance import run_repeatedly
from cinoc.domain.errors import CinocError
from cinoc.evaluation.analysis import EconomicsPayload
from cinoc.evaluation.result import RunResult
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces._corpus_command import (
    run_corpus_discover,
    run_corpus_import,
    run_corpus_search,
)
from cinoc.interfaces._correction_command import run_correction, write_variance
from cinoc.interfaces._list_command import (
    run_list_engines,
    run_list_models,
    run_list_profiles,
    run_list_prompts,
)
from cinoc.reports import default_report_renderer, render_comparison
from cinoc.reports.csv_export import run_result_csv

#: Horodatage figé du rapport de démo (golden octet-stable, cf. ``demo_to_html``).
_DEMO_EPOCH = datetime(2026, 1, 1, tzinfo=UTC)


def demo_to_html() -> str:
    """Exécute la démo et renvoie le rapport HTML (déterministe).

    La démo est la **vitrine du déterminisme** (golden octet-stable entre deux
    exécutions) : on retire du ``RunResult`` les canaux **environnementaux**
    avant rendu — ``usage`` (durées wall-clock) et l'analyse ``economics`` qui
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
            "usage": (),
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
    """Lit le ``HistoryStore`` : série d'un pipeline, ou régressions de la vue."""
    from cinoc.adapters.storage.history_store import HistoryStore

    store = HistoryStore(Path(db))
    if pipeline is not None:
        records = store.history(pipeline, view, metric)
        if not records:
            print(f"Aucune mesure pour {pipeline!r} ({view}:{metric}).")
            return 0
        for record in records:
            print(
                f"{record.completed_at}  {record.run_id}  "
                f"{record.metric}={record.value:.6f}  ({record.corpus_name}, "
                f"code {record.code_version})"
            )
        return 0
    regressions = store.regressions(view, metric, threshold=threshold)
    if not regressions:
        print(f"Aucune régression ({view}:{metric}, seuil {threshold:g}).")
        return 0
    for reg in regressions:
        print(
            f"{reg.pipeline}: {reg.previous:.6f} → {reg.latest:.6f} "
            f"(Δ {reg.delta:+.6f}, run {reg.latest_run_id})"
        )
    return 0


def _run_demo(output: str) -> int:
    path = Path(output)
    path.write_text(demo_to_html(), encoding="utf-8")
    print(f"Rapport de démonstration écrit : {path}")
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
) -> int:
    if repeat > 1 and resume_dir:
        raise CinocError(
            "--repeat et --resume-dir s'excluent : rejouer un cache de reprise "
            "mesurerait le cache, pas la variance du dispositif."
        )
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    spec = load_run_spec(config_path)
    resume_store = ResumeStore(Path(resume_dir)) if resume_dir else None
    # Export HIPE = sink d'artefacts (les textes sont lus avant le nettoyage du
    # workspace) — le format JSONL porte les textes, pas les scores.
    artifact_sink = None
    if hipe_jsonl is not None:
        from cinoc.app.hipe_export import hipe_jsonl_sink

        artifact_sink = hipe_jsonl_sink(Path(hipe_jsonl), spec.corpus)
    def _once(index: int) -> RunResult:
        if repeat > 1:
            print(f"run {index + 1}/{repeat}…", flush=True)
        return run_orchestrator(
            spec,
            registry=registry,
            code_version=resolve_code_version(),
            resume_store=resume_store,
            artifact_sink=artifact_sink,
            max_workers=max_workers,
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
            result, report_dir, render=default_report_renderer().render, title=title
        )
        written = str(report)
    else:
        # Saveur fichier unique : vignettes data-URI inlinées dans le HTML.
        Path(output).write_text(
            default_report_renderer().render(
                result,
                title=title,
                images=build_thumbnails(result),
                facsimiles=build_facsimiles(result),
            ),
            encoding="utf-8",
        )
        written = output
    if json_output is not None:
        dump_run_result(result, json_output)
    if csv_output is not None:
        Path(csv_output).write_text(run_result_csv(result), encoding="utf-8")
    print(f"Rapport écrit : {written}")
    return 0


def _run_hybrid(
    images: str,
    out: str,
    *,
    segmenter: str,
    ocr: str,
    label: str,
    source_label: str | None,
    lang: str = "fra",
    model: str | None = None,
    prompt: str | None = None,
    endpoint: str | None = None,
    token: str | None = None,
) -> int:
    """Transcription **hybride** : segmente, reconnaît par bloc, assemble un ALTO/page.

    Part d'un dossier d'images (sans GT) → ``CorpusSpec`` → ``plan_hybrid_run``
    (pp_doclayout + tesseract par défaut ; tout OCR réel ou un VLM zero-shot via
    ``--ocr``) → orchestrateur ; les ``ALTO_XML`` sont écrits dans ``out`` par un
    sink (avant nettoyage du workspace).
    """
    from cinoc.app.orchestrator import PipelineOutputs
    from cinoc.app.structure_planning import plan_hybrid_run
    from cinoc.app.transcription import corpus_from_images, write_alto_files
    from cinoc.domain.run import RunManifest

    corpus = corpus_from_images(images)
    registry = ModuleRegistry()
    register_default_modules(registry)
    discover_plugins(registry, enabled=True)  # CLI local : code de confiance
    spec = plan_hybrid_run(
        corpus, "hybrid", segmenter=segmenter, ocr=ocr, label=label,
        source_label=source_label, lang=lang, model=model, prompt=prompt,
        endpoint=endpoint, token=token,
    )(Path(out))
    out_dir = Path(out)
    written: list[Path] = []

    def _sink(outputs: PipelineOutputs, manifest: RunManifest) -> None:
        written.extend(write_alto_files(out_dir, outputs))

    run_orchestrator(
        spec,
        registry=registry,
        code_version=resolve_code_version(),
        artifact_sink=_sink,
    )
    print(f"{len(written)} ALTO écrit(s) dans {out_dir}")
    return 0


def _compare_command(path_a: str, path_b: str, output: str) -> int:
    run_a = load_run_result(path_a)
    run_b = load_run_result(path_b)
    Path(output).write_text(render_comparison(run_a, run_b), encoding="utf-8")
    print(f"Comparaison écrite : {output}")
    return 0


def _load_dotenv(path: Path = Path(".env")) -> list[str]:
    """Charge un fichier ``.env`` (``CLE=valeur`` par ligne) dans l'environnement.

    Sans dépendance. **Ne remplace jamais** une variable déjà définie : l'env réel
    prime (un secret HuggingFace l'emporte sur le ``.env`` local). ``#`` et lignes
    vides ignorés. Renvoie les **noms** chargés (jamais les valeurs) pour une trace
    lisible. C'est le moyen d'entrer ses clés en local (``MISTRAL_API_KEY=…``).
    """
    if not path.is_file():
        return []
    loaded: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
            loaded.append(key)
    return loaded


def _serve_command(host: str, port: int, reports_dir: str | None) -> int:
    # Clés locales depuis ``.env`` (avant tout : la disponibilité des moteurs est
    # capturée au démarrage). Sur HuggingFace, les secrets du Space priment.
    loaded = _load_dotenv()
    if loaded:
        print(f"Clés chargées depuis .env : {', '.join(loaded)}")
    # uvicorn = extra [serve], importé paresseusement : la CLI reste utilisable
    # (demo/run/compare) sans la pile web installée.
    try:
        import uvicorn  # type: ignore[import-not-found]

        from cinoc.interfaces.web.app import REPORTS_DIR_ENV
    except ImportError:
        print(
            "Erreur : serveur non installé (pip install 'cinoc[serve]').",
            file=sys.stderr,
        )
        return 1
    if host not in ("127.0.0.1", "localhost"):
        # 0.0.0.0 expose le service au réseau : sécurité = responsabilité du
        # déploiement (reverse-proxy, mode public). On le signale, sans bloquer.
        print(
            f"Attention : écoute sur {host} (exposé au réseau). "
            "En public, placez un reverse-proxy et activez le mode public.",
            file=sys.stderr,
        )
    if reports_dir is not None:
        os.environ[REPORTS_DIR_ENV] = reports_dir
    print(f"Cinoc sert sur http://{host}:{port} (Ctrl-C pour arrêter).")
    # On passe la FACTORY à uvicorn (factory=True), jamais un app de module :
    # zéro effet de bord à l'import (gate no_side_effect_imports).
    uvicorn.run(
        "cinoc.interfaces.web.app:create_app",
        host=host,
        port=port,
        factory=True,
    )
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
            )
        if args.command == "correct":
            return run_correction(
                args.alto_dir,
                args.output,
                producer=args.producer,
                model=args.model,
                host=args.host,
                ocr_sidecar=args.ocr_sidecar,
                ground_truth=args.ground_truth,
                repeat=args.repeat,
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
                label=args.label,
                source_label=args.source_label,
                lang=args.lang,
                model=args.model,
                prompt=args.prompt,
                endpoint=args.segmenter_endpoint,
                token=args.segmenter_token,
            )
        if args.command == "corpus":
            # Sous-arbre : le verbe choisi porte la capacité (importer,
            # chercher, découvrir) ; argparse a déjà borné les valeurs.
            if args.corpus_command == "import":
                return run_corpus_import(args)
            if args.corpus_command == "search":
                return run_corpus_search(args)
            return run_corpus_discover(args)
        if args.command == "list":
            sujets = {
                "engines": run_list_engines,
                "models": run_list_models,
                "profiles": run_list_profiles,
                "prompts": run_list_prompts,
            }
            return sujets[args.topic](args)
        if args.command == "compare":
            return _compare_command(args.run_a, args.run_b, args.output)
        if args.command == "serve":
            return _serve_command(args.host, args.port, args.reports_dir)
    except (CinocError, OSError) as exc:
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1
    return 1  # pragma: no cover (sous-commande requise)


__all__ = ["demo_to_html", "main"]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

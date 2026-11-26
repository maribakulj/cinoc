"""``JobRunner`` — exécute un run **en arrière-plan**, annulable (couche 6).

Le lanceur de fond : on lance ``orchestrator.run`` dans un
thread *daemon*, on suit son état dans le ``JobStore`` (couche 5), et on câble
l'**annulation coopérative** via ``RunControl`` (couche 4) — un ``cancel`` HTTP
déclenche le signal que l'exécuteur sonde entre deux étapes.

Le corpus est matérialisé par un *builder* dans un workspace temporaire **propre
au job**, vivant le temps du run puis nettoyé : le run lit ses fichiers avant la
fin. Le ``RunResult`` est écrit en JSON dans ``reports_dir`` → il apparaît
aussitôt dans la vitrine read-only existante (preuve de bout en bout).

La progression fine est diffusée via le journal du ``JobStore`` (SSE côté web).

**Archive** : avec un ``archive_dir`` (le web le place dans ``app/data_dir``),
chaque job écrit ses sorties dans ``<archive_dir>/<job_id>`` — le cache de
reprise du run, donc son archive : sidecars natifs, issues, binaires
(``RunManifest.artifacts_dir``). Un dossier **par job**, pas un cache partagé
entre runs : un corpus re-déposé sous les mêmes images mais d'autres sorties
pré-calculées se verrait resservir les anciennes (la clé hache l'image, pas les
fichiers qu'un module ``precomputed`` lit à côté), et deux visiteurs d'une
instance publique partageraient leurs sorties. L'archive d'un run web se
re-note sur le serveur par ``cinoc run --resume-dir <archive> --offline``.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Mapping
from pathlib import Path
from tempfile import TemporaryDirectory

from cinoc.adapters.storage.history_store import HistoryStore
from cinoc.adapters.storage.job_store import JobState, JobStore
from cinoc.adapters.storage.publisher import NoopPublisher, ResultPublisher
from cinoc.app.alto_store import AltoStore
from cinoc.app.history import record_run
from cinoc.app.modules.registry import ModuleRegistry
from cinoc.app.orchestrator import PipelineOutputs
from cinoc.app.orchestrator import run as run_orchestrator
from cinoc.app.results import dump_run_result
from cinoc.app.resume import ResumeStore
from cinoc.app.segmentation import SegmentationStore
from cinoc.domain.artifacts import Artifact, ArtifactType, latest_by_type
from cinoc.domain.errors import CinocError, RunCancelledError
from cinoc.domain.layout import CanonicalLayout
from cinoc.domain.pipeline import INITIAL_STEP_ID
from cinoc.domain.run import RunManifest
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult
from cinoc.pipeline.run_control import RunControl

logger = logging.getLogger(__name__)

#: Construit le ``RunSpec`` d'un job en matérialisant son corpus dans le
#: workspace fourni (vivant le temps du run).
SpecBuilder = Callable[[Path], RunSpec]


class JobRunner:
    """Lance et suit des runs asynchrones, écrivant leurs ``RunResult``."""

    def __init__(
        self,
        *,
        store: JobStore,
        registry: ModuleRegistry,
        reports_dir: Path,
        code_version: str,
        publisher: ResultPublisher | None = None,
        history_store: HistoryStore | None = None,
        segmentation_store: SegmentationStore | None = None,
        alto_store: AltoStore | None = None,
        archive_dir: Path | None = None,
        paths_root: Path | None = None,
    ) -> None:
        self._store = store
        self._registry = registry
        self._reports_dir = reports_dir
        self._code_version = code_version
        #: Persistance : pousse le RunResult vers un dépôt distant. Inactif
        #: par défaut (``NoopPublisher``) → aucun effet réseau sans secret.
        self._publisher = publisher if publisher is not None else NoopPublisher()
        #: Historique longitudinal : enregistre les agrégats de chaque run
        #: terminé. ``None`` → pas de suivi (collaborateur facultatif).
        self._history = history_store
        #: Segmentation : persiste les ``LAYOUT`` produits (aperçu du lanceur).
        #: ``None`` → pas de persistance de mise en page (facultatif).
        self._segmentation = segmentation_store
        #: Export ALTO : persiste les ``ALTO_XML`` produits (téléchargeables par
        #: run). ``None`` → pas d'export ALTO (facultatif).
        self._alto = alto_store
        #: Archive par job (cache de reprise du run). ``None`` → les sorties
        #: meurent avec le workspace, sidecars compris.
        self._archive_dir = archive_dir
        #: Racine des corpus déposés : le ``RunResult`` publié y rapporte ses
        #: chemins au lieu de citer ceux du serveur (``app.portable_paths``).
        self._paths_root = paths_root
        self._controls: dict[str, RunControl] = {}
        self._threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    @property
    def store(self) -> JobStore:
        """Le ``JobStore`` lu par le web pour restituer l'état des jobs."""
        return self._store

    def launch(self, build_spec: SpecBuilder) -> str:
        """Crée un job, démarre son thread, renvoie son identifiant."""
        job = self._store.create()
        control = RunControl()
        thread = threading.Thread(
            target=self._execute,
            args=(job.id, build_spec, control),
            name=f"cinoc-job-{job.id[:8]}",
            daemon=True,
        )
        with self._lock:
            self._controls[job.id] = control
            self._threads[job.id] = thread
        thread.start()
        return job.id

    def cancel(self, job_id: str) -> bool:
        """Demande l'annulation coopérative du job. ``False`` si inconnu/fini."""
        with self._lock:
            control = self._controls.get(job_id)
        job = self._store.get(job_id)
        if control is None or job is None or job.state.is_terminal:
            return False
        control.trigger_cancel()
        return True

    def join(self, job_id: str, timeout: float = 10.0) -> bool:
        """Attend la fin du thread du job (usage tests). ``True`` si terminé."""
        with self._lock:
            thread = self._threads.get(job_id)
        if thread is None:
            return False
        thread.join(timeout)
        return not thread.is_alive()

    def _execute(
        self, job_id: str, build_spec: SpecBuilder, control: RunControl
    ) -> None:
        self._store.update(job_id, state=JobState.RUNNING)
        try:
            with TemporaryDirectory(prefix="cinoc-job-") as workspace:
                spec = build_spec(Path(workspace))

                def _on_progress(done: int, total: int) -> None:
                    self._store.progress(job_id, done, total)

                result = run_orchestrator(
                    spec,
                    registry=self._registry,
                    code_version=self._code_version,
                    control=control,
                    artifact_sink=self._persist_artifacts,
                    on_progress=_on_progress,
                    resume_store=(
                        ResumeStore(self._archive_dir / job_id)
                        if self._archive_dir is not None
                        else None
                    ),
                    paths_root=self._paths_root,
                )
                self._reports_dir.mkdir(parents=True, exist_ok=True)
                run_id = result.manifest.run_id
                result_path = self._reports_dir / f"{run_id}.json"
                dump_run_result(result, result_path)
                published_url = self._publish_safe(run_id, result_path)
                self._record_safe(result)
        except RunCancelledError:
            self._store.update(job_id, state=JobState.CANCELLED)
        except CinocError as exc:
            logger.warning("[jobs] run %s échoué : %s", job_id, exc)
            self._store.update(job_id, state=JobState.FAILED, error=str(exc))
        except Exception as exc:
            # Catch-all **intentionnel** (vérifié Lot G) : un thread worker ne doit
            # jamais mourir en silence — toute erreur inattendue du run est tracée
            # et le job passe FAILED (jamais bloqué en RUNNING).
            logger.warning("[jobs] run %s erreur inattendue : %s", job_id, exc)
            self._store.update(job_id, state=JobState.FAILED, error=str(exc))
        else:
            self._store.update(
                job_id,
                state=JobState.DONE,
                report_name=run_id,
                published_url=published_url,
            )

    def _persist_artifacts(
        self, outputs: PipelineOutputs, manifest: RunManifest
    ) -> None:
        """Sink des artefacts durables (best-effort) : ``LAYOUT`` (→ segmentation)
        et ``ALTO_XML`` (→ export téléchargeable). Un seul exécuteur : ces artefacts
        sont produits par le run et le workspace temporaire les détruit — on les
        capte ici avant nettoyage. Sans store dédié, ou run sans l'artefact → no-op.
        Un échec n'abat pas le run (son ``RunResult`` est l'output)."""
        for pipeline_name, per_document in outputs.items():
            for document_id, by_step in per_document.items():
                artifacts = latest_by_type(by_step)
                page = by_step.get(INITIAL_STEP_ID, {}).get(ArtifactType.IMAGE)
                self._persist_layout(pipeline_name, document_id, artifacts, page)
                self._persist_alto(
                    manifest.run_id, pipeline_name, document_id, artifacts
                )

    def _persist_layout(
        self,
        pipeline_name: str,
        document_id: str,
        artifacts: Mapping[ArtifactType, Artifact],
        page: Artifact | None = None,
    ) -> None:
        """Persiste un ``LAYOUT`` produit dans le ``SegmentationStore`` (viz),
        avec l'image de la page — l'aperçu la dessine sous les régions, et
        sans elle son SVG pointait vers une image absente (404)."""
        if self._segmentation is None:
            return
        layout_art = artifacts.get(ArtifactType.LAYOUT)
        if layout_art is None or layout_art.uri is None:
            return
        try:
            layout = CanonicalLayout.model_validate_json(
                Path(layout_art.uri).read_bytes()
            )
            if page is not None and page.uri is not None:
                source = Path(page.uri)
                self._segmentation.save(
                    layout,
                    image_ext=source.suffix.lower() or None,
                    image_bytes=source.read_bytes(),
                )
            else:
                self._segmentation.save(layout)
        except (OSError, ValueError) as exc:
            logger.warning(
                "[jobs] persistance LAYOUT (%s/%s) échouée : %s",
                pipeline_name, document_id, exc,
            )

    def _persist_alto(
        self,
        run_id: str,
        pipeline_name: str,
        document_id: str,
        artifacts: Mapping[ArtifactType, Artifact],
    ) -> None:
        """Persiste un ``ALTO_XML`` produit dans l'``AltoStore`` (export par run)."""
        if self._alto is None:
            return
        alto_art = artifacts.get(ArtifactType.ALTO_XML)
        if alto_art is None or alto_art.uri is None:
            return
        try:
            self._alto.save(
                run_id, document_id, pipeline_name, Path(alto_art.uri).read_bytes()
            )
        except OSError as exc:
            logger.warning(
                "[jobs] persistance ALTO (%s/%s) échouée : %s",
                pipeline_name, document_id, exc,
            )

    def _record_safe(self, result: RunResult) -> None:
        """Enregistre le run dans l'historique (best-effort) : un échec d'écriture
        ne fait **pas** échouer le run — son résultat est déjà écrit et publié."""
        if self._history is None:
            return
        try:
            record_run(self._history, result)
        except Exception as exc:
            # Catch-all **intentionnel** (vérifié Lot G) : l'historique est un
            # effet secondaire. Le narrower laisserait une erreur inattendue
            # remonter au catch-all worker et marquer FAILED un run pourtant
            # **réussi** (RunResult déjà écrit + publié). On trace, on n'échoue pas.
            logger.warning(
                "[jobs] historique de %s échoué : %s", result.manifest.run_id, exc
            )

    def _publish_safe(self, run_id: str, result_path: Path) -> str | None:
        """Publie le résultat (best-effort) : un échec réseau ne fait PAS échouer
        le run — le résultat local est déjà écrit."""
        try:
            return self._publisher.publish(run_id, result_path)
        except Exception as exc:
            # Catch-all **intentionnel** (vérifié Lot G) : `publish` est un effet
            # secondaire au comportement variable (réseau, dépôt distant, impls
            # tierces). Une publication ratée ne doit jamais faire échouer un run
            # réussi (résultat local déjà écrit). On trace, on renvoie None.
            logger.warning("[jobs] publication de %s échouée : %s", run_id, exc)
            return None


__all__ = ["JobRunner", "SpecBuilder"]

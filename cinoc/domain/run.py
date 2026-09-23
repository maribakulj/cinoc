"""``RunManifest`` — empreinte immuable d'un run de benchmark.

Source de vérité d'un run : quoi (corpus + pipelines + vues), avec quelle
version du code, quand, et avec quelles dépendances. Sérialisé en
``run_manifest.json`` ; combiné aux JSONL de résultats, il permet de
reconstituer un run sans objets Python live.

Garantie de reproductibilité : à ``code_version`` + ``pipeline_specs`` +
``view_specs`` + ``dependencies_lock`` + ``system_binaries_lock``
identiques, ré-exécuter donne les mêmes résultats (au déterminisme près
des adapters externes).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.pipeline import PipelineSpec


class RunManifest(BaseModel):
    """Empreinte immuable d'un run de benchmark.

    ``started_at`` / ``completed_at`` capturent le wall-clock du run mais
    n'entrent pas dans les comparaisons de reproductibilité.

    Attributs
    ---------
    run_id:
        Identifiant unique, filesystem-safe.
    corpus_name / n_documents:
        Corpus traité.
    pipeline_specs:
        Specs complètes des pipelines (steps, params, inputs_from…),
        incluses intégralement pour reproductibilité.
    adapter_kwargs:
        ``{adapter_name: kwargs}`` capturés. Les valeurs sensibles
        (api_key) n'y figurent pas — elles viennent de l'environnement.
    view_specs:
        Vues d'évaluation appliquées.
    code_version:
        Version du code.
    dependencies_lock / system_binaries_lock:
        Snapshots ``{paquet: version}`` et ``{binaire: version}`` —
        indispensables à la reproductibilité.
    artifacts_dir:
        Dossier où les artefacts produits ont été **conservés** — le cache de
        reprise, quand un a été demandé. ``None`` sinon : le workspace d'un run
        est un dossier temporaire **effacé à la sortie**, et sans cette trace un
        ``RunResult`` ne peut pas retrouver ce qu'il a lui-même produit.

        Ce n'est pas qu'une commodité de reprise : c'est la seule façon de
        relire ce qu'un moteur a écrit sur une page une fois le run fini, et le
        préalable à toute analyse recalculée après coup.
    module_versions:
        ``{adapter_name: module.version}`` — version déclarée de chaque
        module exécuté (R-2). La version *binaire* d'un moteur externe
        (tesseract…) relève de ``system_binaries_lock`` (capture live).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    run_id: str = Field(min_length=1, max_length=256)
    corpus_name: str = Field(min_length=1, max_length=128)
    n_documents: int = Field(ge=0)
    pipeline_specs: tuple[PipelineSpec, ...] = Field(default_factory=tuple)
    adapter_kwargs: dict[str, dict[str, Any]] = Field(default_factory=dict)
    view_specs: tuple[EvaluationView, ...] = Field(default_factory=tuple)
    code_version: str = Field(min_length=1, max_length=128)
    started_at: datetime
    completed_at: datetime
    dependencies_lock: dict[str, str] = Field(default_factory=dict)
    system_binaries_lock: dict[str, str] = Field(default_factory=dict)
    module_versions: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)
    artifacts_dir: str | None = Field(default=None, max_length=4096)

    @property
    def duration_seconds(self) -> float:
        """Durée wall-clock du run en secondes."""
        return (self.completed_at - self.started_at).total_seconds()


def utcnow() -> datetime:
    """Timestamp UTC (utile pour les fixtures)."""
    return datetime.now(tz=UTC)


__all__ = ["RunManifest", "utcnow"]

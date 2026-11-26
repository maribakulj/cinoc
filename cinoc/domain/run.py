"""``RunManifest`` — empreinte immuable d'un run de benchmark.

Source de vérité d'un run : quoi (corpus + pipelines + vues), avec quelle
version du code, quand, et avec quelles dépendances. Sérialisé en
``run_manifest.json`` ; combiné aux JSONL de résultats, il permet de
reconstituer un run sans objets Python live.

Garantie de reproductibilité : à ``pipeline_specs`` + ``adapter_kwargs``
(réglages effectifs) + ``module_versions`` + ``system_binaries_lock``
identiques, ré-exécuter donne les mêmes sorties (au déterminisme près des
moteurs externes, et au modèle servi près — ``served_models`` dit lequel) ;
à ``code_version`` + ``dependencies_lock`` + ``unicode_version`` identiques en
plus, les mêmes métriques.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.evaluation import EvaluationView, FailurePolicy
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
        ``{adapter_name: réglages effectifs}`` — les kwargs saisis complétés de
        ce que le module déclare appliquer (``effective_settings()`` : modèle
        demandé, prompt, défauts, endpoint lu dans l'environnement). C'est
        exactement ce que hache l'empreinte de l'étape. Les valeurs secrètes
        n'y figurent pas (``<secret>``).
    view_specs:
        Vues d'évaluation appliquées.
    failure_policy:
        Ce qu'une unité en échec devient dans les agrégats (``exclude`` :
        hors de la moyenne ; ``max_error`` : notée à l'erreur maximale). Un
        agrégat ne se relit pas sans elle.
    code_version:
        Version du code.
    dependencies_lock / system_binaries_lock:
        Snapshots ``{distribution: version}`` (``cinoc`` et ses dépendances
        installées, SDK des moteurs compris) et ``{binaire: version}`` (ceux
        que les modules du run enveloppent ; ceux de l'archive pour un run
        ``--offline``, qui n'exécute rien) — indispensables à la
        reproductibilité.
    unicode_version:
        Version de la base Unicode de l'interpréteur
        (``unicodedata.unidata_version``) : la normalisation NFC/NFD, la
        casse et les catégories de caractères en dépendent, donc les métriques.
    served_models:
        ``{adapter_name: (modèle servi, …)}`` — ce que les fournisseurs disent
        avoir servi (``response.model``), triés, sur toutes les unités ; absent
        pour un module dont la réponse ne le dit pas. Distinct du modèle
        **demandé** (``adapter_kwargs``) : un alias change de cible sans
        prévenir. Une observation, pas un réglage : hors de l'empreinte.
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
    failure_policy: FailurePolicy = "exclude"
    code_version: str = Field(min_length=1, max_length=128)
    started_at: datetime
    completed_at: datetime
    dependencies_lock: dict[str, str] = Field(default_factory=dict)
    system_binaries_lock: dict[str, str] = Field(default_factory=dict)
    unicode_version: str | None = Field(default=None, max_length=32)
    module_versions: dict[str, str] = Field(default_factory=dict)
    served_models: dict[str, tuple[str, ...]] = Field(default_factory=dict)
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

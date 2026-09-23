"""``EvaluationSpec.analyses`` : déclarer ce qu'on veut, ne payer que ça.

Les analyses sont bien plus chères que les métriques — elles observent chaque
couple (pipeline, document), une fois par vue. Une spec qui déclare six
métriques ne doit pas en payer trente-quatre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation._view_collectors import COLLECTEURS, ViewCollectors
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import ANALYSES_CONNUES, evaluate_run

FIXED = datetime(2026, 1, 1, tzinfo=UTC)


def _run(tmp_path: Path, analyses: tuple[str, ...] | str | None):
    gt = tmp_path / "d.gt.txt"
    gt.write_text("alpha beta gamma", encoding="utf-8")
    hyp = tmp_path / "d.raw.txt"
    hyp.write_text("alpha beta gamna", encoding="utf-8")
    corpus = CorpusSpec(
        name="c",
        documents=(
            DocumentRef(
                id="d",
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),
                ),
            ),
        ),
    )
    view = EvaluationView(
        name="texte",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    outputs = {
        "eng": {
            "d": {
                ArtifactType.RAW_TEXT: Artifact(
                    id="d:p:raw_text",
                    document_id="d",
                    type=ArtifactType.RAW_TEXT,
                    uri=str(hyp),
                )
            }
        }
    }
    registry = MetricRegistry()
    register_default_metrics(registry)
    return evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,), analyses=analyses),
        pipeline_outputs=outputs,
        registry=registry,
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            pipeline_specs=(
                PipelineSpec(name="eng", initial_inputs=(ArtifactType.IMAGE,)),
            ),
            code_version="1.0",
            started_at=FIXED,
            completed_at=FIXED,
        ),
    )


def test_le_defaut_est_le_mode_rapide(tmp_path: Path) -> None:
    """Ne rien dire ne coûte que les métriques déclarées.

    Ce test affirmait l'inverse — le défaut produisait **toutes** les analyses.
    Mesuré sur trente unités déjà exécutées : 13 secondes de métriques contre
    15 minutes d'analyses que personne n'avait demandées, et un rapport de
    plusieurs dizaines de méga-octets devenu illisible.
    """
    resultat = _run(tmp_path, None)
    assert resultat.analyses == ()
    assert resultat.pipelines[0].aggregate[0].metric == "cer"


def test_le_mode_detaille_se_reclame(tmp_path: Path) -> None:
    """Et il reste **entier** : c'est un choix, pas une version dégradée."""
    assert len(_run(tmp_path, "toutes").analyses) > 0


def test_tuple_vide_ne_produit_aucune_analyse(tmp_path: Path) -> None:
    resultat = _run(tmp_path, ())
    assert resultat.analyses == ()
    # …mais les métriques déclarées, elles, sont bien là.
    assert resultat.pipelines[0].aggregate[0].metric == "cer"


def test_selection_ne_garde_que_ce_qui_est_demande(tmp_path: Path) -> None:
    resultat = _run(tmp_path, ("diagnostics",))
    assert {a.payload.kind for a in resultat.analyses} <= {"diagnostics"}


def test_analyse_inconnue_refusee_avec_la_liste(tmp_path: Path) -> None:
    with pytest.raises(EvaluationError) as capture:
        _run(tmp_path, ("diagnostik",))
    message = str(capture.value)
    assert "diagnostik" in message
    assert "diagnostics" in message  # la liste des connues est donnée


def test_un_collecteur_eteint_n_observe_rien() -> None:
    """Le gain est à l'**observation**, pas au rendu : un collecteur éteint ne
    doit pas voir passer les documents."""
    view = EvaluationView(
        name="texte",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    collecteurs = ViewCollectors(view, frozenset())
    vus: list[str] = []

    class _Sonde:
        def observe(self, *args: object, **kwargs: object) -> None:
            vus.append("observé")

    collecteurs.diagnostics = _Sonde()  # type: ignore[assignment]
    collecteurs.observe("eng", "d", (), None, None)
    assert vus == []


def test_la_table_des_collecteurs_ne_derive_pas() -> None:
    """Chaque attribut de la table existe, et chaque ``kind`` est connu."""
    view = EvaluationView(
        name="texte",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    collecteurs = ViewCollectors(view)
    for attribut, kind in COLLECTEURS.items():
        assert hasattr(collecteurs, attribut), attribut
        assert kind in ANALYSES_CONNUES, kind


def test_toutes_les_analyses_produites_sont_extinguibles(tmp_path: Path) -> None:
    """Une analyse que la table ignore serait impossible à éteindre."""
    produites = {a.payload.kind for a in _run(tmp_path, None).analyses}
    assert produites <= ANALYSES_CONNUES, produites - ANALYSES_CONNUES

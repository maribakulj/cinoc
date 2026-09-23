"""Réclamer le mode détaillé au lancement, sans éditer la spec.

Le **mode rapide est le défaut** : une spec qui ne dit rien ne paie que ses
métriques. Mesuré sur trente unités déjà exécutées : 29 s en rapide contre
616 s en détaillé.
"""

from __future__ import annotations

import pytest

from cinoc.app.analyses_demandees import AUCUNE, TOUTES, appliquer_analyses
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.run_spec import RunSpec


def _spec(analyses: object = None) -> RunSpec:
    vue = EvaluationView(
        name="texte",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    return RunSpec(
        run_id="r",
        corpus=CorpusSpec(name="c"),
        pipelines=(
            PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,)),
        ),
        evaluation=EvaluationSpec(views=(vue,), analyses=analyses),  # type: ignore[arg-type]
    )


def test_sans_demande_la_spec_decide() -> None:
    assert appliquer_analyses(_spec(), None).evaluation.analyses is None
    assert appliquer_analyses(_spec(TOUTES), None).evaluation.analyses == TOUTES


def test_toutes_reclame_le_mode_detaille() -> None:
    assert appliquer_analyses(_spec(), TOUTES).evaluation.analyses == TOUTES


def test_aucune_contredit_une_spec_bavarde() -> None:
    """L'intérêt d'une option de lancement : répondre à une question ponctuelle
    sans modifier un fichier qu'on partage."""
    assert appliquer_analyses(_spec(TOUTES), AUCUNE).evaluation.analyses == ()


def test_une_liste_est_acceptee_et_nettoyee() -> None:
    resultat = appliquer_analyses(_spec(), " diagnostics , word_errors ,")
    assert resultat.evaluation.analyses == ("diagnostics", "word_errors")


def test_la_spec_n_est_pas_mutee() -> None:
    """Une spec est une donnée : l'option produit une copie, jamais un effet de
    bord sur l'objet chargé."""
    origine = _spec()
    appliquer_analyses(origine, TOUTES)
    assert origine.evaluation.analyses is None


@pytest.mark.parametrize("demande", [TOUTES, AUCUNE, "diagnostics"])
def test_les_vues_sont_conservees(demande: str) -> None:
    resultat = appliquer_analyses(_spec(), demande)
    assert [v.name for v in resultat.evaluation.views] == ["texte"]

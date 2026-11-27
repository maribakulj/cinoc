"""Accès aux API qu'exige le contrat révisé (``CONTRATS.md``, révision n° 6).

Les tranches 1a et 1b remplacent ``Observation(value, weight)`` par une
statistique suffisante et donnent à chaque non-mesure ses axes. Ces API
n'existent pas encore : les tests rouges qui en ont besoin passent par les
fonctions de ce module, qui **lisent** l'API attendue et, si elle manque,
lèvent ``ContratNonImplemente`` (une ``NotImplementedError``) en nommant le
champ et le paragraphe du contrat. Le test est collecté, rouge, et dit ce qui
manque ; aucune erreur d'import ne casse la collecte, rien n'est sauté.

Ce module ne calcule rien et ne reconstruit rien depuis l'ancienne API : une
fonction qui « devinerait » un champ absent rendrait vert un test que le code
ne satisfait pas. Les noms ci-dessous sont la **forme attendue** ; la session
qui implémente une tranche peut en renommer un ici, en un seul endroit, sans
toucher aux attendus des tests.

Forme attendue (anglais, comme le reste de ``RunResult``) :

Observation par document — un ``MetricScore`` de ``RunDocumentResult.scores``
(§ 2.1 a-b) :
    ``applicability`` ∈ {applicable, no_ground_truth, not_transcribed, not_in_view}
    ``availability``  ∈ {available, gt_unreadable, output_missing,
                         output_unreadable, step_failed, step_cancelled,
                         step_not_reached}
    ``validity``      ∈ {valid, partial_output, truncated_output, <motif propre>}
    ``stat``          statistique suffisante (composantes nommées) ou ``None``
    ``value``         le scalaire, ``finalize(stat)`` ; ``scalar_reason`` dit
                      pourquoi il est indéfini (``zero_denominator``…)

Composantes de ``stat`` (§ 2.1 a) :
    taux d'édition, MER : ``substitutions``, ``deletions``, ``insertions``,
                          ``reference_length``
    exactitudes         : ``errors``, ``reference_length``
    appariement P/R/F   : ``tp``, ``fp``, ``fn``

Agrégat d'un pipeline — un ``MetricScore`` de ``PipelineResult.aggregate``
(§ 2.1 a, c) :
    ``value`` = micro, finalisation de la combinaison ; ``stat`` = combinaison
    ``macro`` ; ``micro_support`` = |D^μ_P| ; ``macro_support`` = |D^M_P| ;
    ``expected`` = |attendus| ; ``coverage`` = {motif : nombre d'attendus non
    mesurés} ; ``untruncated_error_rate`` (exactitudes, B1)
    ``PipelineResult.target_population``, ``PipelineResult.cluster_weighting`` (B3)

Supports apparié et global (§ 2.1 c, A4, A6) — une analyse
``kind="comparison"`` par (vue, métrique) :
    ``pairs`` : ``a``, ``b``, ``micro_documents`` (D^μ_AB), ``macro_documents``
    (D^M_AB), ``micro`` et ``macro`` ({pipeline : valeur sur ce support})
    ``global_support`` : ``micro_documents``, ``macro_documents``, ``micro``,
    ``ranking`` (le seul tri multi-pipelines, B7)

Invention hors référence (§ 2.1 c, N3, C5) — une analyse
``kind="invention_outside_reference"`` par (vue, métrique) :
    ``unit`` (``None`` = « non définie ») ; ``pairs`` : ``a``, ``b``,
    ``documents``, ``invented`` ({pipeline : unités}) ; ``coverage`` :
    {pipeline : (mesurées, attendues)} sur les pages sans référence

Déclarations (§ 2.1 b, c, e) :
    ``FailurePolicy`` ∋ ``empty_page`` ; ``UnitOutcome`` ∋ ``partial`` ;
    ``GroundTruthRef.status`` ∈ {transcribed, not_transcribed} (l'importeur) ;
    ``DocumentRef.cluster`` ; ``CorpusSpec.target_population``,
    ``CorpusSpec.cluster_weighting`` ∈ {document, cluster}
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, get_args

from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import FailurePolicy
from cinoc.evaluation.result import PipelineResult, RunResult


class ContratNonImplemente(NotImplementedError):
    """L'API qu'exige ``CONTRATS.md`` n'existe pas encore : test rouge, pas cassé."""


def exige(objet: object, attribut: str, paragraphe: str) -> Any:
    """``objet.attribut``, ou ``ContratNonImplemente`` qui le nomme."""
    if not hasattr(objet, attribut):
        raise ContratNonImplemente(
            f"{type(objet).__name__}.{attribut} absent (CONTRATS.md {paragraphe})"
        )
    return getattr(objet, attribut)


# --- Observation ------------------------------------------------------------


def axes(score: object) -> tuple[str, str, str]:
    """``(applicability, availability, validity)`` d'une observation (§ 2.1 b)."""
    return (
        exige(score, "applicability", "§ 2.1 b, axe 1"),
        exige(score, "availability", "§ 2.1 b, axe 2"),
        exige(score, "validity", "§ 2.1 b, axe 3"),
    )


def statistique(score: object) -> Any:
    """Statistique suffisante d'une observation ou d'un agrégat (§ 2.1 a)."""
    return exige(score, "stat", "§ 2.1 a, statistique suffisante")


def composante(score: object, nom: str) -> Any:
    """Composante ``nom`` de la statistique de ``score`` (§ 2.1 a)."""
    stat = statistique(score)
    if stat is None:
        raise AssertionError(f"statistique absente, composante {nom!r} attendue")
    if isinstance(stat, Mapping):
        if nom not in stat:
            raise ContratNonImplemente(
                f"composante {nom!r} absente de la statistique (CONTRATS.md § 2.1 a)"
            )
        return stat[nom]
    return exige(stat, nom, "§ 2.1 a, composantes de la statistique")


def composantes(score: object, *noms: str) -> tuple[Any, ...]:
    return tuple(composante(score, nom) for nom in noms)


def motif_scalaire(score: object) -> Any:
    """Pourquoi le scalaire est indéfini (``zero_denominator``…), axe 4."""
    return exige(score, "scalar_reason", "§ 2.1 b, axe 4")


# --- Agrégat ----------------------------------------------------------------


def macro(agregat: object) -> Any:
    return exige(agregat, "macro", "§ 2.1 c, estimande macro")


def support_micro(agregat: object) -> Any:
    return exige(agregat, "micro_support", "§ 2.1 c, D^μ_P")


def support_macro(agregat: object) -> Any:
    return exige(agregat, "macro_support", "§ 2.1 c, D^M_P")


def couverture(agregat: object) -> Mapping[str, int]:
    """{motif : nombre d'attendus non mesurés}, ventilée par axe (A1)."""
    valeur: Mapping[str, int] = exige(agregat, "coverage", "§ 2.1 c, A1")
    return valeur


def taux_non_tronque(agregat: object) -> Any:
    return exige(agregat, "untruncated_error_rate", "§ 2.1 a, B1, M2")


def publication_grappes(entree: PipelineResult) -> tuple[Any, Any]:
    """``(population cible, pondération des grappes)`` d'un agrégat (B3)."""
    return (
        exige(entree, "target_population", "§ 2.1 c, B3"),
        exige(entree, "cluster_weighting", "§ 2.1 c, B3"),
    )


# --- Analyses ---------------------------------------------------------------


def _analyse(result: RunResult, kind: str, view: str, metric: str, ou: str) -> Any:
    found = [
        a.payload
        for a in result.analyses
        if a.view == view
        and getattr(a.payload, "kind", None) == kind
        and getattr(a.payload, "metric", None) == metric
    ]
    if not found:
        raise ContratNonImplemente(
            f"aucune analyse kind={kind!r} pour ({view!r}, {metric!r}) "
            f"(CONTRATS.md {ou})"
        )
    (payload,) = found
    return payload


def comparaison(result: RunResult, view: str, metric: str) -> Any:
    """Supports apparié et global d'une (vue, métrique) (§ 2.1 c, A6)."""
    return _analyse(result, "comparison", view, metric, "§ 2.1 c, A6")


def paire(payload: object, a: str, b: str) -> Any:
    for entree in exige(payload, "pairs", "§ 2.1 c, support apparié"):
        if {exige(entree, "a", "§ 2.1 c"), exige(entree, "b", "§ 2.1 c")} == {a, b}:
            return entree
    raise AssertionError(f"paire ({a}, {b}) absente de l'analyse")


def support_global(payload: object) -> Any:
    return exige(payload, "global_support", "§ 2.1 c, support global (B7)")


def invention(result: RunResult, view: str, metric: str) -> Any:
    """Analyse « invention hors référence » (§ 2.1 c, N3, C5)."""
    return _analyse(result, "invention_outside_reference", view, metric, "§ 2.1 c, A4")


# --- Déclarations ------------------------------------------------------------


def politique_empty_page() -> str:
    """``"empty_page"``, si ``FailurePolicy`` le déclare (§ 2.1 e)."""
    if "empty_page" not in get_args(FailurePolicy):
        raise ContratNonImplemente(
            f"FailurePolicy = {get_args(FailurePolicy)} sans 'empty_page' "
            "(CONTRATS.md § 2.1 e)"
        )
    return "empty_page"


def _champ(modele: type, champ: str, ou: str) -> None:
    if champ not in modele.model_fields:  # type: ignore[attr-defined]
        raise ContratNonImplemente(
            f"{modele.__name__}.{champ} absent (CONTRATS.md {ou})"
        )


def reference_non_transcrite(truth: GroundTruthRef) -> GroundTruthRef:
    """La même référence, déclarée ``not_transcribed`` par l'importeur (P7)."""
    _champ(GroundTruthRef, "status", "§ 2.1 b, P7")
    return GroundTruthRef(**{**truth.model_dump(), "status": "not_transcribed"})


def document_en_grappe(document: DocumentRef, cluster: str) -> DocumentRef:
    """Le même document, rattaché à la grappe ``cluster`` (B3)."""
    _champ(DocumentRef, "cluster", "§ 2.1 c, B3")
    return DocumentRef(**{**document.model_dump(), "cluster": cluster})


def corpus_declare(
    corpus: CorpusSpec, *, target_population: str, cluster_weighting: str
) -> CorpusSpec:
    """Le même corpus, avec sa population cible et sa pondération (B3)."""
    _champ(CorpusSpec, "target_population", "§ 2.1 c, B3")
    _champ(CorpusSpec, "cluster_weighting", "§ 2.1 c, B3")
    return CorpusSpec(
        **{
            **corpus.model_dump(),
            "target_population": target_population,
            "cluster_weighting": cluster_weighting,
        }
    )

"""Analyse inter-moteurs : complémentarité (oracle) + divergence taxonomique.

Deux questions complémentaires sur un corpus multi-moteurs (scope corpus) :

- **Complémentarité** — *que rattraperait un ensemble ?* ``oracle_recall`` =
  rappel multiset **bag-of-words** de l'union des moteurs : pour chaque token
  GT (multiplicité comprise), le meilleur moteur **sur ce token** est retenu.
  C'est une **borne supérieure optimiste** — l'ordre des tokens est ignoré ;
  un vote séquentiel réel ferait au mieux autant, en général moins. Comparée
  au meilleur moteur seul, elle chiffre le plafond de gain d'un pipeline
  d'ensemble (``absolute_gap``/``relative_gap``).
- **Divergence taxonomique** — *les moteurs font-ils des erreurs de même
  nature ?* Jensen-Shannon en **bits** (``log2``, bornée [0,1]) entre les
  distributions de classes d'erreurs **déjà comptées** par la taxonomie de la
  même vue : post-passe **cross-payload** (pattern ``conformity``), zéro
  re-classification.

Conventions : GT sans token → document **exclu** du dénominateur, jamais un
rappel 1.0 (R10) ; < 2 pipelines → bloc absent ; tokenisation =
``textual_fidelity.tokenize`` (minuscules, mots Unicode — une seule définition
de token dans la couche). Pur stdlib (``math`` + ``Counter``).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from scipy.spatial.distance import jensenshannon  # type: ignore[import-untyped]

from cinoc.evaluation.analysis import (
    Analysis,
    ComplementarityDocument,
    EngineTokenRecall,
    InterEngineComplementarity,
    InterEngineDivergence,
    InterEnginePayload,
    TaxonomyDivergencePair,
    TaxonomyPayload,
)
from cinoc.evaluation.textual_fidelity import tokenize

#: Lissage des classes absentes d'une distribution (évite ``log(0)``) — assez
#: petit pour ne pas peser sur le résultat ; sert aussi de plancher au
#: dénominateur de ``relative_gap`` (``1 − best`` peut être nul).
_EPSILON = 1e-12

#: Documents embarqués dans le payload (plus forts écarts oracle − meilleur).
#: La source en gardait 50 ; 20 suffit au diagnostic et borne le payload
#: (aligné sur les caps de ``textual_fidelity``/``diagnostics``).
_MAX_DOCUMENTS = 20


def _smoothed(
    distribution: Mapping[str, float], keys: Sequence[str]
) -> list[float]:
    """Aligne ``distribution`` sur ``keys``, lisse les zéros, renormalise."""
    smoothed = [max(distribution.get(key, 0.0), _EPSILON) for key in keys]
    total = sum(smoothed)
    return [value / total for value in smoothed]


def jensen_shannon_divergence(
    p: Mapping[str, float], q: Mapping[str, float]
) -> float:
    """JS-divergence symétrique en **bits**, clampée ``[0, 1]``.

    ``JS(P, Q) = ½·KL(P‖M) + ½·KL(Q‖M)`` avec ``M = (P + Q) / 2`` et un
    logarithme **base 2** (la borne haute vaut alors exactement 1, atteinte
    pour des distributions disjointes). Les clés manquantes d'un côté sont
    lissées à ``ε = 1e-12`` puis renormalisées ; le clamp final absorbe les
    arrondis flottants. Calcul délégué à scipy (P5g 6, D-303) :
    ``jensenshannon`` rend la **distance**, racine de la divergence.
    """
    keys = sorted(set(p) | set(q))
    if not keys:
        return 0.0
    distance = jensenshannon(_smoothed(p, keys), _smoothed(q, keys), base=2)
    return max(0.0, min(1.0, float(distance) ** 2))


def _taxonomy_divergence(
    taxonomy: Analysis | None,
) -> InterEngineDivergence | None:
    """Matrice JS depuis le payload ``taxonomy`` déjà construit (même vue)."""
    payload = taxonomy.payload if taxonomy is not None else None
    if not isinstance(payload, TaxonomyPayload):
        return None
    distributions = {
        row.pipeline: {
            count.label: count.count / row.total_errors for count in row.counts
        }
        for row in payload.pipelines
    }
    names = sorted(distributions)
    if len(names) < 2:
        return None
    pairs: list[TaxonomyDivergencePair] = []
    max_pair: TaxonomyDivergencePair | None = None
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            pair = TaxonomyDivergencePair(
                a=a,
                b=b,
                divergence=jensen_shannon_divergence(
                    distributions[a], distributions[b]
                ),
            )
            pairs.append(pair)
            # Strictement supérieur : à égalité, la première paire (a, b) gagne ;
            # toutes nulles → pas de « paire la plus divergente » (max_pair=None).
            if pair.divergence > 0 and (
                max_pair is None or pair.divergence > max_pair.divergence
            ):
                max_pair = pair
    return InterEngineDivergence(pairs=tuple(pairs), max_pair=max_pair)


class InterEngineCollector:
    """Multisets de tokens (pipeline × document) au scoring ; ``build`` croise.

    ``observe`` ne retient que des ``Counter`` de tokens (jamais les textes) ;
    ``build`` reçoit l'analyse ``taxonomy`` de la **même vue** et n'en lit que
    les comptages (post-passe cross-payload). ``None`` si aucune des deux
    lectures n'est applicable.
    """

    def __init__(self) -> None:
        self._references: dict[str, Counter[str]] = {}
        self._hypotheses: dict[str, dict[str, Counter[str]]] = {}
        self._documents: list[str] = []

    def observe(
        self, pipeline: str, document_id: str, reference: str, hypothesis: str
    ) -> None:
        if document_id not in self._references:
            self._references[document_id] = Counter(tokenize(reference))
            self._documents.append(document_id)
        bucket = self._hypotheses.setdefault(pipeline, {})
        bucket[document_id] = Counter(tokenize(hypothesis))

    def build(self, view: str, taxonomy: Analysis | None) -> Analysis | None:
        complementarity = self._complementarity()
        divergence = _taxonomy_divergence(taxonomy)
        if complementarity is None and divergence is None:
            return None
        return Analysis(
            scope="corpus",
            view=view,
            payload=InterEnginePayload(
                complementarity=complementarity,
                taxonomy_divergence=divergence,
            ),
        )

    def _complementarity(self) -> InterEngineComplementarity | None:
        pipelines = sorted(self._hypotheses)
        if len(pipelines) < 2:
            return None
        total_tokens = 0
        oracle_preserved = 0
        per_engine: dict[str, int] = {name: 0 for name in pipelines}
        documents: list[ComplementarityDocument] = []
        for document_id in self._documents:
            reference = self._references[document_id]
            document_total = sum(reference.values())
            if document_total == 0:
                continue  # R10 : GT sans token = non applicable, jamais 1.0.
            total_tokens += document_total
            preserved = {name: 0 for name in pipelines}
            document_oracle = 0
            for token, count in reference.items():
                best = 0
                for name in pipelines:
                    hypothesis = self._hypotheses[name].get(document_id)
                    # Pipeline sans sortie sur ce document → 0 préservé (l'échec
                    # coûte du rappel, il n'est pas neutralisé en silence).
                    kept = (
                        min(count, hypothesis.get(token, 0))
                        if hypothesis is not None
                        else 0
                    )
                    preserved[name] += kept
                    if kept > best:
                        best = kept
                document_oracle += best
            oracle_preserved += document_oracle
            document_best = 0
            for name in pipelines:
                per_engine[name] += preserved[name]
                if preserved[name] > document_best:
                    document_best = preserved[name]
            documents.append(
                ComplementarityDocument(
                    document_id=document_id,
                    oracle_recall=document_oracle / document_total,
                    best_single_recall=document_best / document_total,
                    absolute_gap=(document_oracle - document_best)
                    / document_total,
                )
            )
        if total_tokens == 0:
            return None  # R10 : corpus entier sans token GT.
        recalls = {name: per_engine[name] / total_tokens for name in pipelines}
        # ``max`` garde le premier maximum : noms triés → à égalité, le plus
        # petit lexicographiquement gagne (déterministe).
        best_engine = max(pipelines, key=lambda name: recalls[name])
        best_recall = recalls[best_engine]
        oracle_recall = oracle_preserved / total_tokens
        absolute_gap = max(0.0, oracle_recall - best_recall)
        relative_gap = min(1.0, absolute_gap / max(1.0 - best_recall, _EPSILON))
        documents.sort(key=lambda d: (-d.absolute_gap, d.document_id))
        return InterEngineComplementarity(
            n_documents=len(documents),
            n_reference_tokens=total_tokens,
            oracle_recall=oracle_recall,
            best_single_recall=best_recall,
            best_engine=best_engine,
            absolute_gap=absolute_gap,
            relative_gap=relative_gap,
            per_engine_recall=tuple(
                EngineTokenRecall(pipeline=name, recall=recalls[name])
                for name in pipelines
            ),
            per_document=tuple(documents[:_MAX_DOCUMENTS]),
        )


__all__ = ["InterEngineCollector", "jensen_shannon_divergence"]

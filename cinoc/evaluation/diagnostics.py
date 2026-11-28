"""Assemblage du diagnostic d'erreurs : confusions, pires lignes, difficulté.

Collecte au fil du scoring (les représentations normalisées sont déjà
chargées — aucun re-calcul, aucune relecture de fichier), puis assemble le
payload ``diagnostics`` (``evaluation.analysis``). Heuristiques **maison**
(règle D-068 : valeurs de test dérivées à la main).

- **Confusions** : les substitutions de l'alignement caractère du CER
  (``Levenshtein.editops``, ``evaluation._alignment``) — top par pipeline ;
  leur somme est le S du CER.
- **Pires lignes** : lignes appariées par l'alignement de lignes F15 (celui de
  la distribution par ligne, ``lines``), notées par ``lines.line_cer`` — top
  corpus, extraits verbatim tronqués. Absentes d'une vue dont le profil écrase
  les sauts de ligne : un document à plat n'a qu'une « ligne », la montrer
  serait trompeur.
- **Documents difficiles** : CER moyen par document sur les pipelines scorés.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from cinoc.evaluation._alignment import (
    aligned_to_reference,
    char_substitutions,
    matches_canonical,
)
from cinoc.evaluation.analysis import (
    Analysis,
    CharConfusion,
    DiagnosticsPayload,
    HardDocument,
    PipelineConfusions,
    WorstLine,
)
from cinoc.evaluation.lines import line_cer
from cinoc.evaluation.result import MetricScore

#: Bornes de rendu : assez pour diagnostiquer, pas un dump du corpus.
_TOP_CONFUSIONS = 10
_TOP_LINES = 5
_TOP_DOCUMENTS = 5
_EXCERPT = 160


def char_confusions(reference: str, hypothesis: str) -> Counter[tuple[str, str]]:
    """Paires (attendu → produit) des substitutions de l'alignement caractère.

    Exactement les S du CER du document (D-286) : la somme des comptes vaut
    ``_alignment.char_counts(...)[0]``. L'alignement ``difflib`` à deux niveaux
    (mots puis caractères des seuls empans substitués) qu'il remplace en
    manquait — « France » lu « Franee » n'y donnait aucune paire — et écartait
    les empans de plus de 2 000 caractères : un texte réordonné y perdait ses
    paires, que le CER compte pourtant. ``rapidfuzz`` aligne une page entière
    en mémoire linéaire (~0,1 s pour 50 000 caractères).
    """
    return Counter(char_substitutions(reference, hypothesis))


def line_cers(
    reference: str, hypothesis: str
) -> list[tuple[int, float, str, str]]:
    """``(index, cer, ligne_ref, ligne_hyp)`` par ligne de référence non vide.

    Lignes appariées par l'alignement de lignes F15 — celui de la
    distribution par ligne (``lines.aligned_line_cers``) : une ligne insérée
    ne décale plus toutes les suivantes, une ligne de référence sans
    correspondance est notée face à une hypothèse vide (CER 1.0). Notée par
    :func:`lines.line_cer` (D-285). Les lignes de référence vides sont
    ignorées (CER indéfini) ; les lignes excédentaires de l'hypothèse
    relèvent du scalaire ``unanchored_trigrams``.
    """
    ref_lines = reference.splitlines()
    mapped = aligned_to_reference(ref_lines, hypothesis.splitlines())
    pairs = zip(ref_lines, mapped, strict=True)
    return [
        (index, line_cer(ref_line, hyp_line or ""), ref_line, hyp_line or "")
        for index, (ref_line, hyp_line) in enumerate(pairs)
        if ref_line
    ]


def _excerpt(text: str) -> str:
    return text if len(text) <= _EXCERPT else text[: _EXCERPT - 1] + "…"


class DiagnosticsCollector:
    """Accumule confusions et lignes au fil du scoring d'une vue."""

    def __init__(self, *, lines: bool = True) -> None:
        #: ``False`` : la vue écrase les sauts de ligne, pas de « pire ligne ».
        self._with_lines = lines
        #: Les confusions suivent l'alignement RapidFuzz : concordent-elles, sur
        #: tous les documents, avec les comptes canoniques du CER ?
        self._concordant = True
        self._confusions: dict[str, Counter[tuple[str, str]]] = {}
        self._lines: list[tuple[float, str, str, int, str, str]] = []

    def observe(
        self, pipeline: str, document_id: str, reference: str, hypothesis: str
    ) -> None:
        bucket = self._confusions.setdefault(pipeline, Counter())
        bucket.update(char_confusions(reference, hypothesis))
        self._concordant = self._concordant and matches_canonical(
            reference, hypothesis
        )
        if not self._with_lines:
            return
        for index, cer, ref_line, hyp_line in line_cers(reference, hypothesis):
            if cer > 0:
                self._lines.append(
                    (cer, pipeline, document_id, index, ref_line, hyp_line)
                )

    def build(
        self,
        view: str,
        metric: str,
        document_ids: Sequence[str],
        per_pipeline_scores: Mapping[str, Sequence[MetricScore]],
    ) -> Analysis | None:
        """Assemble le payload ; ``None`` si rien d'observé (vue non texte)."""
        confusions = tuple(
            PipelineConfusions(
                pipeline=pipeline,
                pairs=tuple(
                    CharConfusion(expected=e, observed=o, count=count)
                    for (e, o), count in sorted(
                        bucket.items(), key=lambda kv: (-kv[1], kv[0])
                    )[:_TOP_CONFUSIONS]
                ),
                n_pairs=len(bucket),
                n_substitutions=sum(bucket.values()),
            )
            for pipeline, bucket in sorted(self._confusions.items())
            if bucket
        )
        worst = tuple(
            WorstLine(
                pipeline=pipeline,
                document_id=document_id,
                line_index=index,
                cer=cer,
                reference=_excerpt(ref_line),
                hypothesis=_excerpt(hyp_line),
            )
            for cer, pipeline, document_id, index, ref_line, hyp_line in sorted(
                self._lines, key=lambda row: (-row[0], row[1], row[2], row[3])
            )[:_TOP_LINES]
        )
        hardest = _hardest_documents(document_ids, per_pipeline_scores)
        if not confusions and not worst and not hardest:
            return None
        payload = DiagnosticsPayload(
            metric=metric,
            matches_canonical_counts=self._concordant,
            confusions=confusions,
            worst_lines=worst,
            hardest_documents=hardest,
        )
        return Analysis(scope="corpus", view=view, payload=payload)


def _hardest_documents(
    document_ids: Sequence[str],
    per_pipeline_scores: Mapping[str, Sequence[MetricScore]],
) -> tuple[HardDocument, ...]:
    """Top des documents par CER moyen (pipelines ayant une valeur)."""
    rows: list[HardDocument] = []
    for index, document_id in enumerate(document_ids):
        values = [
            scores[index].value
            for scores in per_pipeline_scores.values()
            if index < len(scores) and scores[index].value is not None
        ]
        if values:
            rows.append(
                HardDocument(
                    document_id=document_id,
                    mean_cer=sum(v for v in values if v is not None)
                    / len(values),
                    n_pipelines=len(values),
                )
            )
    rows.sort(key=lambda r: (-r.mean_cer, r.document_id))
    return tuple(rows[:_TOP_DOCUMENTS])


__all__ = ["DiagnosticsCollector", "char_confusions", "line_cers"]

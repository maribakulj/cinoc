"""Assemblage du diagnostic d'erreurs : confusions, pires lignes, difficulté.

Collecte au fil du scoring (les représentations normalisées sont déjà
chargées — aucun re-calcul, aucune relecture de fichier), puis assemble le
payload ``diagnostics`` (``evaluation.analysis``). Heuristiques **maison**
(PLAN_PARITE §5.8b : valeurs de test dérivées à la main).

- **Confusions** : caractères substitués appariés positionnellement dans les
  segments ``replace`` d'un alignement ``difflib`` **à deux niveaux** (mots
  puis caractères — cf. ``char_confusions``) — top par pipeline.
- **Pires lignes** : lignes appariées par index, CER par ligne
  (Levenshtein/longueur de référence) — top corpus, extraits verbatim tronqués.
- **Documents difficiles** : CER moyen par document sur les pipelines scorés.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from difflib import SequenceMatcher

from rapidfuzz.distance import Levenshtein

from cinoc.evaluation.analysis import (
    Analysis,
    CharConfusion,
    DiagnosticsPayload,
    HardDocument,
    PipelineConfusions,
    WorstLine,
)
from cinoc.evaluation.result import MetricScore

#: Bornes de rendu : assez pour diagnostiquer, pas un dump du corpus.
_TOP_CONFUSIONS = 10
_TOP_LINES = 5
_TOP_DOCUMENTS = 5
_EXCERPT = 160
#: Empan maximal, en caractères, où l'appariement caractère à
#: caractère garde un sens (cf. ``char_confusions``).
_EMPAN_MAX = 2000

#: Découpe en mots — le blanc est séparateur, pas jeton : inclure les
#: blancs remettrait un élément ultra-répétitif dans l'alignement.
_MOTS = re.compile(r"\S+")


def char_confusions(reference: str, hypothesis: str) -> Counter[tuple[str, str]]:
    """Paires (attendu → produit) des segments substitués, appariées par position.

    L'alignement se fait **en deux temps** : sur les mots, puis sur les
    caractères à l'intérieur des seuls empans substitués. Aligner directement
    les caractères d'une page entière dégénère en quadratique — une page de
    presse a ~40 000 caractères pour moins de 100 symboles distincts, donc
    ``SequenceMatcher`` compare chaque « e » à tous les autres (mesuré : 32 s
    contre 0,13 s, paires de tête inchangées). Les mots, eux, sont assez variés
    pour que les blocs communs se trouvent vite.

    ``autojunk`` reste désactivé aux deux niveaux : il écarte les éléments
    présents dans plus de 1 % d'une séquence longue, ce qui sur des caractères
    revient à tous les écarter — et produit des paires identitaires (``e``→``e``)
    dénuées de sens.
    """
    pairs: Counter[tuple[str, str]] = Counter()
    ref_mots = _MOTS.findall(reference)
    hyp_mots = _MOTS.findall(hypothesis)
    mots = SequenceMatcher(a=ref_mots, b=hyp_mots, autojunk=False)
    for op, a0, a1, b0, b1 in mots.get_opcodes():
        if op != "replace":
            continue
        attendu = " ".join(ref_mots[a0:a1])
        produit = " ".join(hyp_mots[b0:b1])
        # Au-delà de cet empan, les deux côtés ne se correspondent plus (texte
        # réordonné, pas texte mal lu) : apparier leurs caractères n'aurait
        # aucun sens, et ferait réapparaître le coût quadratique.
        if max(len(attendu), len(produit)) > _EMPAN_MAX:
            continue
        for sous_op, x0, x1, y0, y1 in SequenceMatcher(
            a=attendu, b=produit, autojunk=False
        ).get_opcodes():
            if sous_op != "replace":
                continue
            for expected, observed in zip(
                attendu[x0:x1], produit[y0:y1], strict=False
            ):
                pairs[(expected, observed)] += 1
    return pairs


def line_cers(
    reference: str, hypothesis: str
) -> list[tuple[int, float, str, str]]:
    """``(index, cer, ligne_ref, ligne_hyp)`` par paire de lignes (même index).

    Les lignes de référence vides sont ignorées (CER indéfini) ; les lignes
    excédentaires de l'hypothèse relèvent du scalaire ``hallucination``.
    """
    out: list[tuple[int, float, str, str]] = []
    hyp_lines = hypothesis.splitlines()
    for index, ref_line in enumerate(reference.splitlines()):
        if not ref_line:
            continue
        hyp_line = hyp_lines[index] if index < len(hyp_lines) else ""
        cer = Levenshtein.distance(ref_line, hyp_line) / len(ref_line)
        out.append((index, cer, ref_line, hyp_line))
    return out


def _excerpt(text: str) -> str:
    return text if len(text) <= _EXCERPT else text[: _EXCERPT - 1] + "…"


class DiagnosticsCollector:
    """Accumule confusions et lignes au fil du scoring d'une vue."""

    def __init__(self) -> None:
        self._confusions: dict[str, Counter[tuple[str, str]]] = {}
        self._lines: list[tuple[float, str, str, int, str, str]] = []

    def observe(
        self, pipeline: str, document_id: str, reference: str, hypothesis: str
    ) -> None:
        bucket = self._confusions.setdefault(pipeline, Counter())
        bucket.update(char_confusions(reference, hypothesis))
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

"""Distribution du CER par ligne (couche 3).

Le CER document noie la **répartition** des erreurs : 5 % d'erreurs uniformes
(correction rapide partout) et 5 % concentrées en lignes détruites (re-saisie
locale) ne se relisent pas pareil. Par pipeline, sur les lignes GT du corpus
**poolées** (micro — pas une moyenne de statistiques par document) :

- **CER par ligne** — lignes GT appariées aux lignes hypothèse par un
  alignement Levenshtein **sur les listes de lignes** avant tout calcul
  (audit source F15) : une ligne insérée/supprimée ne décale plus toutes les
  suivantes. Ligne GT sans correspondance → CER 1.0 (ligne perdue) ; lignes
  hypothèse en trop ignorées (la distribution est indexée sur la GT). Limite
  résiduelle assumée : une fusion/scission de lignes est approximée par une
  substitution + une délétion. CER de ligne plafonné à 1.0.
- **Percentiles** p50→p99 (interpolation linéaire) · **Gini** (0 = erreurs
  uniformes, 1 = concentrées) · **taux catastrophiques** (part des lignes au
  CER **≥ seuil** — seuils 0.30/0.50/1.00 portés par le payload ; le ``>``
  strict de la source laissait le seuil 1.0 à zéro pour toujours, le CER
  étant plafonné à 1.0) · **heatmap** positionnelle (CER moyen par tranche
  de position relative dans le document, tranche vide → ``None``).

**Applicabilité** : la distribution n'a de sens que si la normalisation de la
vue **préserve les sauts de ligne** — sur un profil « à plat » (``flat_text``,
le défaut ; ``hipe``…), l'analyse est absente (jamais un chiffre trompeur) ;
la vue par défaut « texte (lignes) » (``keep_line_breaks``) la porte. Sonde
comportementale ``newline_preserved(view)`` : la survie de ``\\n`` à
``prepare_text`` (couvre profils **et** ``char_exclude``).
"""

from __future__ import annotations

from collections.abc import Sequence

from rapidfuzz.distance import Levenshtein

from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation._alignment import aligned_to_reference
from cinoc.evaluation.analysis import (
    Analysis,
    CatastrophicRate,
    LinePercentiles,
    LinesPayload,
    PipelineLines,
)
from cinoc.evaluation.representations import prepare_text

#: Seuils de ligne « catastrophique » (CER ≥ seuil) — conventions éditoriales
#: de la source : 0.30 = relecture lourde, 0.50 = re-saisie probable,
#: 1.00 = ligne totalement perdue (cap).
_CATASTROPHIC_THRESHOLDS = (0.30, 0.50, 1.00)

#: Tranches de position de la heatmap (dixièmes de document).
_HEATMAP_BINS = 10

#: Percentiles rapportés (p50 = médiane … p99 = queue extrême).
_PERCENTILES = (50, 75, 90, 95, 99)


def newline_preserved(view: EvaluationView) -> bool:
    """``True`` si la préparation de la vue laisse vivre les sauts de ligne.

    Sonde comportementale (pas une lecture de champs) : on prépare un témoin
    ``"a\\nb"`` exactement comme au scoring — un profil « à plat », un levier
    ``\\W → espace`` ou un ``char_exclude`` contenant ``\\n`` le détectent tous.
    """
    return "\n" in prepare_text("a\nb", view)


def line_cer(reference: str, hypothesis: str) -> float:
    """CER d'une paire de lignes **déjà préparées par la vue**, plafonné à 1.0.

    La formule de la métrique ``cer`` — distance d'édition / longueur de la
    ligne de référence —, sans normalisation propre : la ligne a reçu celle de
    la vue (``prepare_text``), comme le document. Elle appliquait autrefois
    un NFC et un ``strip`` à elle, si bien que le CER d'une ligne et celui du
    document ne suivaient pas la même convention (D-285). Sous le profil de la
    vue « texte (lignes) », les blancs de bord sont déjà retirés.

    Ligne GT vide → 0.0 si l'hypothèse l'est aussi, 1.0 sinon (contenu
    halluciné sur une ligne blanche) — convention de la source, au niveau
    ligne seulement (un *document* sans ligne ne produit rien).
    """
    if not reference:
        return 0.0 if not hypothesis else 1.0
    return min(Levenshtein.distance(reference, hypothesis) / len(reference), 1.0)


def aligned_line_cers(reference: str, hypothesis: str) -> list[float]:
    """CER par ligne GT, lignes appariées par alignement Levenshtein (F15).

    L'alignement opère sur les **listes de lignes**
    (``_alignment.aligned_to_reference``, partagé avec les pires lignes des
    diagnostics) : seuls les blocs ``equal``/``replace`` apparient ; une ligne
    GT supprimée reste sans correspondance (CER 1.0 via l'hypothèse vide) ;
    les lignes hypothèse insérées n'entrent pas dans la distribution.
    """
    ref_lines = reference.splitlines()
    mapped = aligned_to_reference(ref_lines, hypothesis.splitlines())
    return [
        line_cer(ref_line, mapped[i] or "")
        for i, ref_line in enumerate(ref_lines)
    ]


def percentile(sorted_values: Sequence[float], p: float) -> float:
    """p-ième percentile (0 ≤ p ≤ 100) d'une liste **triée non vide**.

    Interpolation linéaire entre les deux rangs encadrants (la convention de
    ``numpy`` par défaut, portée de la source en pur stdlib).
    """
    n = len(sorted_values)
    index = p / 100 * (n - 1)
    lo = int(index)
    hi = min(lo + 1, n - 1)
    frac = index - lo
    return sorted_values[lo] + frac * (sorted_values[hi] - sorted_values[lo])


def gini(values: Sequence[float]) -> float:
    """Coefficient de Gini de la concentration des erreurs, clampé ``[0, 1]``.

    ``G = (2·Σ (i+1)·xᵢ) / (n·Σ xᵢ) − (n+1)/n`` sur les valeurs triées
    croissantes. 0 = erreurs uniformément réparties (ou aucune erreur :
    somme nulle → 0.0, l'uniformité parfaite) ; 1 = tout le volume d'erreur
    concentré sur une ligne. Le clamp absorbe les arrondis flottants.
    """
    xs = sorted(max(value, 0.0) for value in values)
    n = len(xs)
    total = sum(xs)
    if n == 0 or total == 0.0:
        return 0.0
    weighted = sum((i + 1) * x for i, x in enumerate(xs))
    return max(0.0, min(1.0, (2.0 * weighted) / (n * total) - (n + 1) / n))


class LinesCollector:
    """Accumule ``(CER, position relative)`` par ligne GT au fil du scoring.

    ``enabled=False`` (vue dont la normalisation écrase ``\\n``) → no-op :
    l'analyse est non applicable, le payload absent. La position relative
    (``index / nombre de lignes du document``) permet de pooler la heatmap
    entre documents de tailles différentes.
    """

    def __init__(
        self, *, enabled: bool = True, heatmap_bins: int = _HEATMAP_BINS
    ) -> None:
        self._enabled = enabled
        self._bins = heatmap_bins
        self._lines: dict[str, list[tuple[float, float]]] = {}

    def observe(self, pipeline: str, reference: str, hypothesis: str) -> None:
        if not self._enabled:
            return
        cers = aligned_line_cers(reference, hypothesis)
        if not cers:
            return
        bucket = self._lines.setdefault(pipeline, [])
        count = len(cers)
        bucket.extend((cer, i / count) for i, cer in enumerate(cers))

    def build(self, view: str) -> Analysis | None:
        rows = [self._row(pipeline) for pipeline in sorted(self._lines)]
        if not rows:
            return None
        return Analysis(
            scope="corpus",
            view=view,
            payload=LinesPayload(heatmap_bins=self._bins, pipelines=tuple(rows)),
        )

    def _row(self, pipeline: str) -> PipelineLines:
        lines = self._lines[pipeline]
        cers = [cer for cer, _ in lines]
        ordered = sorted(cers)
        count = len(cers)
        catastrophic: list[CatastrophicRate] = []
        for threshold in _CATASTROPHIC_THRESHOLDS:
            n_over = sum(1 for cer in cers if cer >= threshold)
            catastrophic.append(
                CatastrophicRate(
                    threshold=threshold, count=n_over, rate=n_over / count
                )
            )
        bins: list[list[float]] = [[] for _ in range(self._bins)]
        for cer, fraction in lines:
            bins[min(int(fraction * self._bins), self._bins - 1)].append(cer)
        p50, p75, p90, p95, p99 = (percentile(ordered, p) for p in _PERCENTILES)
        return PipelineLines(
            pipeline=pipeline,
            line_count=count,
            mean_cer=sum(cers) / count,
            gini=gini(cers),
            percentiles=LinePercentiles(p50=p50, p75=p75, p90=p90, p95=p95, p99=p99),
            catastrophic=tuple(catastrophic),
            heatmap=tuple(
                sum(values) / len(values) if values else None for values in bins
            ),
        )


__all__ = [
    "LinesCollector",
    "aligned_line_cers",
    "gini",
    "line_cer",
    "newline_preserved",
    "percentile",
]

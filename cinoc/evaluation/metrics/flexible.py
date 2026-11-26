"""Flexible Character Accuracy (FCA) — exactitude caractère indépendante de
l'ordre de lecture.

Capture le cœur de Clausner et al. (ICDAR 2019) : un texte transcrit dans un
**ordre de lecture différent** (colonnes interverties, blocs réordonnés) ne doit
pas être pénalisé comme une erreur de caractère. Méthode ici : **appariement
optimal de lignes** (algorithme hongrois sur les distances d'édition
ligne-à-ligne), donc :

- chaque ligne de référence est appariée à **au plus une** ligne d'hypothèse de
  façon à **minimiser la distance d'édition totale**, sans tenir compte de
  l'ordre des lignes ;
- une ligne de référence non appariée coûte toute sa longueur (suppression) ;
- une ligne d'hypothèse non appariée coûte toute sa longueur (insertion) ;
- FCA = 1 − erreurs / nombre de caractères de référence, bornée [0, 1].

⚠️ On ne fait **pas** l'appariement *sous-ligne* récursif de l'algorithme
original (une ligne de réf. coupée puis appariée à plusieurs lignes
d'hypothèse) ni sa recherche de coefficients — variante plus lourde et **non
déterministe**, différée. La méthode retenue est entièrement **déterministe et
auditable** (invariant §12), ce qui prime sur la fidélité bit-à-bit à une
implémentation de référence.

⚠️ **Métrique limitée** (déclarée en D-288, glossaire et radar) : appariant des
lignes **entières**, elle vaut **0** dès que la sortie fusionne les lignes de
la référence — le cas typique d'un VLM qui rend un paragraphe —, quelle que
soit la qualité du texte. Et sous un profil qui aplatit les blancs (le défaut
``flat_text``), la vue lui donne une seule ligne de chaque côté : elle vaut
alors 1 − CER, sans sa tolérance à l'ordre.
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric


def _flexible_errors(gt_lines: list[str], ocr_lines: list[str]) -> int:
    """Coût d'édition total sous appariement optimal de lignes (ordre libre)."""
    import numpy as np
    from rapidfuzz.distance import Levenshtein
    from rapidfuzz.process import cdist
    from scipy.optimize import linear_sum_assignment  # type: ignore[import-untyped]

    n, m = len(gt_lines), len(ocr_lines)
    # Coût d'un appariement « interdit » : strictement pire que tout (suppression
    # + insertion de toutes les lignes) → jamais choisi par l'optimiseur.
    forbidden = sum(map(len, gt_lines)) + sum(map(len, ocr_lines)) + 1
    # Matrice carrée (n+m) : lignes réelles + nœuds « non apparié » (dummies).
    cost = np.zeros((n + m, n + m), dtype=np.int64)
    if n and m:
        cost[:n, :m] = cdist(
            gt_lines, ocr_lines, scorer=Levenshtein.distance, dtype=np.int64
        )
    # Bloc « réf. non appariée » : diagonale = longueur (suppression), reste interdit.
    cost[:n, m:] = forbidden
    for i in range(n):
        cost[i, m + i] = len(gt_lines[i])
    # Bloc « hyp. non appariée » : diagonale = longueur (insertion), reste interdit.
    cost[n:, :m] = forbidden
    for j in range(m):
        cost[n + j, j] = len(ocr_lines[j])
    rows, cols = linear_sum_assignment(cost)
    return int(cost[rows, cols].sum())


@document_metric(
    name="fca",
    input_types=(ArtifactType.RAW_TEXT, ArtifactType.RAW_TEXT),
    description=(
        "Flexible Character Accuracy : exactitude caractère par appariement "
        "optimal de lignes entières (ordre libre) ; 0 si la sortie fusionne "
        "les lignes."
    ),
    higher_is_better=True,
    tags=frozenset({"text", "accuracy", "reading_order"}),
)
def flexible_character_accuracy(ctx: DocContext) -> Observation:
    if not isinstance(ctx.reference, str) or not isinstance(ctx.hypothesis, str):
        raise EvaluationError("fca : reference et hypothesis doivent être du texte.")
    gt_lines = [ln for ln in ctx.reference.splitlines() if ln.strip()]
    ocr_lines = [ln for ln in ctx.hypothesis.splitlines() if ln.strip()]
    total = sum(len(ln) for ln in gt_lines)
    if total == 0:
        # Réf. vide : exact ssi l'hypothèse l'est aussi ; poids 0 → exclue du micro.
        return Observation(value=1.0 if not ocr_lines else 0.0, weight=0)
    errors = _flexible_errors(gt_lines, ocr_lines)
    return Observation(value=max(0.0, 1.0 - errors / total), weight=total)


#: Socle « ordre de lecture libre », collecté explicitement par le registre.
FLEXIBLE_METRICS: tuple[DocumentMetric, ...] = (flexible_character_accuracy,)

__all__ = ["FLEXIBLE_METRICS", "flexible_character_accuracy"]

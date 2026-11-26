"""Alignement optimal partagé (couche 3) — une seule source.

Le runner distribue à chaque collecteur le **même** ``(référence, hypothèse)``
normalisé. Tout ce qui, en couche 3, aligne deux séquences pour dire *quelles*
erreurs (taxonomie, hallucinations, confusions, mots manqués, modernisation,
pires lignes, WER) passe par ici, si bien qu'une analyse voit exactement les
éditions que compte la métrique affichée à côté (D-286). Le diff surligné
du rapport (couche 7, ``reports/text_diff``) lit :func:`opcodes` aussi : il
surligne les éditions du CER (D-287).

**Alignement de Levenshtein de coût minimal** (``rapidfuzz``, déjà dépendance
de la couche). ``difflib.SequenceMatcher``, utilisé auparavant par cinq
analyses, cherche le plus long bloc commun d'abord : ce n'est pas un
alignement de coût minimal, et sur un article bégayé il voyait deux lacunes et
trois insertions là où le WER voit une insertion.

**Égalités de coût.** Plusieurs alignements optimaux peuvent exister ;
``rapidfuzz`` en choisit un qui ne dépend que de l'égalité des éléments,
aveugle à leur ressemblance. Pour qu'il ne dépende pas non plus de ``hash()``
(une séquence de mots y est hachée élément par élément), les éléments sont
codés en entiers par ordre d'apparition : même résultat sous toute graine
``PYTHONHASHSEED``. C'est aussi le codage de jiwer, d'où les mêmes S, D et I.
Deux départages en découlent, chacun pour ses consommateurs :

- :func:`alignment` (taxonomie, hallucinations, mots manqués, modernisation —
  des analyses qui **nomment** des mots) réapparie par ressemblance les blocs
  d'éditions aux côtés inégaux, sans changer un seul compte ;
- :func:`aligned_to_reference` (lignes de F15, mots de la correction) garde le
  départage de ``rapidfuzz``, celui de la distribution par ligne (D-125).

Les confusions de caractères lisent l'alignement caractère du CER
(:func:`char_substitutions`) : au caractère, rien n'est réapparié.

La forme du char-MER (comptes S/D/I, dénominateur ``H+S+D+I`` borné) est figée
par ``tests/evaluation/test_char_mer_anchor``.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterator, Sequence

from rapidfuzz.distance import Levenshtein, Opcode

#: Au-delà de ce produit ``n × m`` des deux côtés d'un bloc d'éditions, le
#: départage par ressemblance (:func:`alignment`) est sauté : un tel bloc est
#: un texte méconnaissable, pas des mots mal lus, et le calcul y est
#: quadratique. Le départage de ``rapidfuzz`` reste alors.
_MAX_BLOCK_CELLS = 200_000


def _codes(
    reference: Sequence[Hashable], hypothesis: Sequence[Hashable]
) -> tuple[list[int], list[int]]:
    """Éléments codés en entiers par ordre d'apparition (indépendant de ``hash``)."""
    table: dict[Hashable, int] = {}
    ref = [table.setdefault(item, len(table)) for item in reference]
    hyp = [table.setdefault(item, len(table)) for item in hypothesis]
    return ref, hyp


def opcodes(
    reference: Sequence[Hashable], hypothesis: Sequence[Hashable]
) -> list[Opcode]:
    """Blocs ``equal``/``replace``/``delete``/``insert`` d'un alignement optimal.

    Une chaîne s'aligne au caractère, une liste à l'élément (mots, lignes). Un
    bloc ``replace`` a autant d'éléments des deux côtés : il s'apparie un à un.
    C'est l'alignement du WER ; ses comptes S/D/I sont ceux de jiwer.
    """
    if isinstance(reference, str) and isinstance(hypothesis, str):
        return list(Levenshtein.opcodes(reference, hypothesis))
    return list(Levenshtein.opcodes(*_codes(reference, hypothesis)))


#: Une case d'alignement : ``(i, j)`` apparie ``reference[i]`` et
#: ``hypothesis[j]`` (égaux ou substitués), ``(i, None)`` est une suppression,
#: ``(None, j)`` une insertion.
Pair = tuple[int | None, int | None]


def alignment(reference: Sequence[str], hypothesis: Sequence[str]) -> list[Pair]:
    """Alignement optimal élément par élément, dans l'ordre des deux séquences.

    Mêmes blocs et mêmes comptes S/D/I que :func:`opcodes` — donc que le WER.
    Seul change, dans un bloc d'éditions aux deux côtés inégaux, **quels**
    éléments restent sans vis-à-vis : ``rapidfuzz`` (coût unitaire, aveugle au
    contenu) les place selon l'ordre de son calcul, si bien que « ville » lu
    « vile » suivi de quatre mots ajoutés donnait « vile » pour inséré et
    « ville » ↔ « inondation » pour substitution. Ici, parmi ces
    appariements de même coût, on garde celui dont les paires se ressemblent le
    plus (somme des distances de Levenshtein normalisées, minimale) ; à
    ressemblance égale, celui de ``rapidfuzz`` — donc de jiwer.
    """
    pairs: list[Pair] = []
    for op in opcodes(reference, hypothesis):
        i0, i1, j0, j1 = op.src_start, op.src_end, op.dest_start, op.dest_end
        if op.tag in ("equal", "replace"):
            pairs.extend((i0 + k, j0 + k) for k in range(i1 - i0))
        elif op.tag == "delete":
            pairs.extend((i, None) for i in range(i0, i1))
        else:
            pairs.extend((None, j) for j in range(j0, j1))
    return _rematch_blocks(reference, hypothesis, pairs)


def _rematch_blocks(
    reference: Sequence[str], hypothesis: Sequence[str], pairs: list[Pair]
) -> list[Pair]:
    """Réapparie chaque bloc d'éditions (entre deux égalités) par ressemblance."""
    out: list[Pair] = []
    block: list[Pair] = []
    for pair in [*pairs, (None, None)]:
        i, j = pair
        is_equal = (
            i is not None and j is not None and reference[i] == hypothesis[j]
        )
        if pair != (None, None) and not is_equal:
            block.append(pair)
            continue
        if block:
            out.extend(_rematch(reference, hypothesis, block))
            block = []
        if pair != (None, None):
            out.append(pair)
    return out


def _rematch(
    reference: Sequence[str], hypothesis: Sequence[str], block: list[Pair]
) -> list[Pair]:
    """Le bloc réapparié : autant de paires, au moindre écart de contenu."""
    refs = [i for i, _ in block if i is not None]
    hyps = [j for _, j in block if j is not None]
    if (
        len(refs) == len(hyps)
        or not refs
        or not hyps
        or len(refs) * len(hyps) > _MAX_BLOCK_CELLS
    ):
        return block
    swap = len(refs) < len(hyps)
    long_, short = (hyps, refs) if swap else (refs, hyps)
    long_items = [hypothesis[k] if swap else reference[k] for k in long_]
    short_items = [reference[k] if swap else hypothesis[k] for k in short]
    original = {p for p in block if None not in p}
    n, m = len(long_), len(short)
    # cost[a][b] : long_[:a] aligné sur short[:b], tout short[:b] apparié
    # (b ≤ a) — (somme des distances, paires absentes de l'appariement de
    # ``rapidfuzz``) ; paired_here[a][b] : long_[a-1] y est apparié à short[b-1].

    def as_pair(a: int, b: int | None) -> Pair:
        """``(i, j)`` de l'élément ``long_[a]`` apparié à ``short[b]`` (ou seul)."""
        other = None if b is None else short[b]
        return (other, long_[a]) if swap else (long_[a], other)

    cost = [[(0.0, 0)] * (m + 1) for _ in range(n + 1)]
    paired_here = [[False] * (m + 1) for _ in range(n + 1)]
    for a in range(1, n + 1):
        for b in range(1, min(a, m) + 1):
            before = cost[a - 1][b - 1]
            distance = Levenshtein.normalized_distance(
                long_items[a - 1], short_items[b - 1]
            )
            paired = (
                before[0] + distance,
                before[1] + (as_pair(a - 1, b - 1) not in original),
            )
            # À égalité, apparier l'emporte (départage fixe, déterministe).
            if b == a or paired <= cost[a - 1][b]:
                cost[a][b], paired_here[a][b] = paired, True
            else:
                cost[a][b] = cost[a - 1][b]
    rematched: list[Pair] = []
    a, b = n, m
    while a > 0:
        if b > 0 and paired_here[a][b]:
            rematched.append(as_pair(a - 1, b - 1))
            b -= 1
        else:
            rematched.append(as_pair(a - 1, None))
        a -= 1
    rematched.reverse()
    return rematched


def aligned_to_reference(
    reference: Sequence[str], hypothesis: Sequence[str]
) -> list[str | None]:
    """Élément de l'hypothèse aligné sur chaque élément de la référence.

    ``None`` = élément de référence supprimé ; les éléments insérés de
    l'hypothèse ne figurent pas (la liste est indexée sur la référence). C'est
    l'appariement des lignes de F15 (distribution par ligne **et** pires
    lignes) et des mots de la correction : les blocs de :func:`opcodes`, tels
    que ``rapidfuzz`` les départage — sans le réappariement par ressemblance
    de :func:`alignment`, qui changerait la distribution par ligne (D-125)
    au-delà de cette tranche (D-286).
    """
    aligned: list[str | None] = [None] * len(reference)
    for op in opcodes(reference, hypothesis):
        if op.tag in ("equal", "replace"):
            for offset in range(op.src_end - op.src_start):
                aligned[op.src_start + offset] = hypothesis[op.dest_start + offset]
    return aligned


def char_substitutions(reference: str, hypothesis: str) -> Iterator[tuple[str, str]]:
    """``(attendu, produit)`` de chaque substitution de l'alignement caractère.

    Ce sont exactement les S du CER : le compte de :func:`char_counts`.
    """
    for op in Levenshtein.editops(reference, hypothesis):
        if op.tag == "replace":
            yield reference[op.src_pos], hypothesis[op.dest_pos]


def char_counts(reference: str, hypothesis: str) -> tuple[int, int, int]:
    """``(substitutions, suppressions, insertions)`` de l'alignement caractère."""
    substitutions = deletions = insertions = 0
    for op in Levenshtein.editops(reference, hypothesis):
        if op.tag == "replace":
            substitutions += 1
        elif op.tag == "delete":
            deletions += 1
        else:
            insertions += 1
    return substitutions, deletions, insertions


def char_mer(reference: str, hypothesis: str) -> tuple[float, int, int]:
    """``(cmer, edits, dénominateur)`` — Match Error Rate caractère (SPEC_HIPE §4.1).

    ``cmer = (S+D+I) / (H+S+D+I)``, borné ``[0, 1]`` ; dénominateur
    ``H+S+D+I = len(reference) + insertions`` (l'alignement complet de la
    référence donne ``H+S+D = len(reference)``). Deux textes vides → ``(0.0, 0, 0)``.
    """
    substitutions, deletions, insertions = char_counts(reference, hypothesis)
    total = len(reference) + insertions
    edits = substitutions + deletions + insertions
    return (edits / total if total else 0.0), edits, total


__all__ = [
    "Pair",
    "aligned_to_reference",
    "alignment",
    "char_counts",
    "char_mer",
    "char_substitutions",
    "opcodes",
]

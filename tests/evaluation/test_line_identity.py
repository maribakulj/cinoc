"""Apparier les lignes par **identité**, et non par devinette.

Sur du texte plat, le banc apparie les lignes par un alignement de Levenshtein
sur des *listes de lignes* : une devinette, nécessaire faute de mieux. Quand les
deux côtés portent des identifiants, l'appariement est **connu**.

Ce que la devinette coûte, mesuré sur ``corpus/37-GT-BNL`` (522 lignes) : elle
diverge de l'identité sur **57 lignes**, presque toujours dans le même sens —
51 sur-notées contre 6 sous-notées — et pour **14** d'entre elles elle conclut
« aucune correspondance » (CER 1,0) alors qu'un jumeau existe sous le même
identifiant.
"""

from __future__ import annotations

from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.lines import aligned_line_cers
from cinoc.evaluation.metrics.layout import line_identity_cer, line_identity_coverage


def _layout(*paires: tuple[str, str]) -> CanonicalLayout:
    return CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(
                        id="R1",
                        lines=tuple(
                            Line(id=lid, text=texte) for lid, texte in paires
                        ),
                    ),
                ),
            ),
        )
    )


def _ctx(reference: CanonicalLayout, hypothesis: CanonicalLayout) -> DocContext:
    return DocContext(
        document_id="doc1", reference=reference, hypothesis=hypothesis
    )


def test_a_perfect_hypothesis_scores_zero() -> None:
    layout = _layout(("L1", "alpha"), ("L2", "beta"))
    assert line_identity_cer.fn(_ctx(layout, layout)).value == 0.0


def test_a_near_perfect_line_is_not_declared_unmatched() -> None:
    """**Le cas qui motive la métrique**, réduit à quatre lignes.

    ``gamma`` a un jumeau quasi parfait sous le même identifiant (``gamna``,
    une lettre de différence). Mais la ligne vide qui le précède disparaît du
    texte aplati, les blocs d'opcodes se décalent, et l'alignement conclut
    « aucune correspondance » : CER 1,0 pour une ligne à 0,2.

    Sur le corpus BNL, ce cas se produit 14 fois.
    """
    ids = ("L1", "L2", "L3", "L4")
    gt_textes = ("alpha", "beta", "gamma", "delta")
    hyp_textes = ("alpha", "", "gamna", "delta")
    reference = _layout(*zip(ids, gt_textes, strict=True))
    hypothese = _layout(*zip(ids, hyp_textes, strict=True))

    devine = aligned_line_cers(
        "\n".join(t for t in gt_textes if t), "\n".join(t for t in hyp_textes if t)
    )
    assert devine[2] == 1.0  # « gamma » déclarée sans correspondance…

    # …alors que par identité elle est à une lettre près.
    par_identite = line_identity_cer.fn(_ctx(reference, hypothese)).value
    tout_faux = line_identity_cer.fn(
        _ctx(reference, _layout(*zip(ids, ("alpha", "", "", "delta"), strict=True)))
    ).value
    assert par_identite < tout_faux


def test_a_missing_line_counts_as_entirely_wrong() -> None:
    """Une ligne perdue est une ligne perdue, pas une ligne à ignorer."""
    reference = _layout(("L1", "alpha"), ("L2", "beta"))
    hypothese = _layout(("L1", "alpha"))
    assert line_identity_cer.fn(_ctx(reference, hypothese)).value == 4 / 9


def test_lines_without_an_id_are_ignored() -> None:
    """Sans identité, une ligne n'a rien à quoi être appariée."""
    reference = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(
                        id="R1",
                        lines=(Line(text="anonyme"), Line(id="L2", text="ok")),
                    ),
                ),
            ),
        )
    )
    assert line_identity_cer.fn(_ctx(reference, reference)).value == 0.0
    stat = line_identity_cer.fn(_ctx(reference, reference)).stat
    assert stat.reference_length == 2  # "ok"


def test_a_layout_without_lines_is_not_applicable() -> None:
    """Niveau absent → métrique non applicable, jamais un zéro flatteur."""
    vide = CanonicalLayout(pages=(LayoutPage(regions=(Region(id="R1"),)),))
    assert line_identity_cer.fn(_ctx(vide, vide)) is None
    assert line_identity_coverage.fn(_ctx(vide, vide)) is None


def test_coverage_sees_what_a_cer_cannot() -> None:
    """Un CER n'a aucun moyen de dire qu'une ligne a **disparu** plutôt que
    d'avoir été mal transcrite. La couverture, si."""
    reference = _layout(("L1", "a"), ("L2", "b"), ("L3", "c"), ("L4", "d"))
    hypothese = _layout(("L1", "a"), ("L3", "c"))
    assert line_identity_coverage.fn(_ctx(reference, hypothese)).value == 0.5


def test_a_renamed_line_is_a_lost_line() -> None:
    """Réattribuer un identifiant casse l'identité aussi sûrement que perdre
    la ligne — et c'est exactement ce qu'on veut voir signalé."""
    reference = _layout(("L1", "alpha"))
    renommee = _layout(("AUTRE", "alpha"))
    assert line_identity_coverage.fn(_ctx(reference, renommee)).value == 0.0

"""Helpers tabulaires partagés : data-bar, en-tête de métrique (def + tri)."""

from __future__ import annotations

from cinoc.evaluation.result import MetricScore
from cinoc.evaluation.statistics import EditCounts, ErrorCounts
from cinoc.reports.sections._tables import (
    bar_cell,
    group_header_row,
    metric_th,
    nonempty_metric_indices,
)


def _s(value: float | None, metric: str = "cer") -> MetricScore:
    return MetricScore(metric=metric, value=value, support=1)


def test_group_header_row_merges_consecutive_same_group() -> None:
    # cer, cer_diplo = « caractère » (colspan 2) ; mer = « mot » ; diacritic = « philo »
    row = group_header_row(["cer", "cer_diplo", "mer", "diacritic_err"], "fr", lead=1)
    assert '<th colspan="1"></th>' in row  # cadrage colonne pipeline
    assert 'colspan="2">Erreur · caractère' in row
    assert 'colspan="1">Erreur · mot' in row
    assert "Philologique" in row


def test_group_header_row_unknown_metric_is_blank_cell() -> None:
    row = group_header_row(["mystery"], "fr")
    assert "<th></th>" in row  # métrique hors groupe → cellule vide, pas d'erreur


def test_group_header_row_localized() -> None:
    assert "Character error" in group_header_row(["cer"], "en")


def test_nonempty_metric_indices_hides_all_none_keeps_zero() -> None:
    rows = [(_s(0.0, "cer"), _s(None, "air")), (_s(0.1, "cer"), _s(None, "air"))]
    # cer a des valeurs (dont 0.0 = vraie valeur) → gardé ; air tout None → masqué
    assert nonempty_metric_indices(rows) == [0]


def test_bar_cell_sortable_adds_data_sort() -> None:
    assert 'data-sort="0.250000"' in bar_cell(_s(0.25), 0.5, lang="fr", sortable=True)
    assert "data-sort" not in bar_cell(_s(0.25), 0.5, lang="fr")  # pas de clé de tri
    assert "data-sort" not in bar_cell(
        _s(None), 0.5, lang="fr", sortable=True
    )  # None non triable


def test_metric_th_has_definition_and_sort_affordance() -> None:
    th = metric_th("cer", "fr", sortable=True)
    assert 'class="num-cell has-def sortable"' in th
    assert "title=" in th and "CER" in th  # définition au survol (glossaire)
    assert 'aria-sort="none"' in th and 'class="th-sort"' in th  # affordance de tri


def test_metric_th_non_sortable_keeps_definition_only() -> None:
    th = metric_th("cer", "fr")
    assert "has-def" in th and "title=" in th
    assert "sortable" not in th and "aria-sort" not in th


def test_metric_th_unknown_metric_has_no_definition() -> None:
    th = metric_th("unknown_metric", "fr", sortable=True)
    assert "has-def" not in th and "title=" not in th
    assert "sortable" in th  # triable même sans définition


def test_metric_th_localized_definition() -> None:
    assert "word error rate" in metric_th("wer", "en")  # def EN au survol


def test_nonempty_metric_indices_masks_hidden_metrics() -> None:
    # ``mer`` est calculé mais masqué de l'affichage (redondant avec WER) :
    # il ne figure pas dans les indices de colonnes, contrairement à cer/wer.
    from cinoc.evaluation.result import MetricScore
    from cinoc.reports.sections._tables import nonempty_metric_indices

    rows = [
        (
            MetricScore(metric="cer", value=0.1, support=1),
            MetricScore(metric="mer", value=0.2, support=1),
            MetricScore(metric="wer", value=0.3, support=1),
        )
    ]
    keep = nonempty_metric_indices(rows)
    kept_metrics = {rows[0][i].metric for i in keep}
    assert kept_metrics == {"cer", "wer"}  # mer retiré, cer/wer gardés


def test_an_undefined_scalar_is_not_a_dash() -> None:
    """K1 : une page à référence vide a des comptes (ses insertions entrent au
    corpus) et un scalaire indéfini — lu « indéfini », pas « — » (non mesuré)."""
    blank = MetricScore(
        metric="cer",
        stat=EditCounts(
            substitutions=0, deletions=0, insertions=3, reference_length=0
        ),
        scalar_reason="zero_denominator",
    )
    assert ">indéfini</span>" in bar_cell(blank, 1.0, lang="fr")
    assert ">undefined</span>" in bar_cell(blank, 1.0, lang="en")
    assert "—" in bar_cell(MetricScore(metric="cer"), 1.0, lang="fr")


def test_a_floored_accuracy_shows_its_untruncated_rate_and_counts() -> None:
    """B1 : au plancher, 0 ne distingue plus un taux de 1,2 d'un taux de 4,4 —
    le taux non tronqué et les comptes sont écrits à côté ; sous le plancher,
    la valeur vaut 1 − e/n et rien n'est ajouté."""
    floored = MetricScore(
        metric="char_accuracy",
        value=0.0,
        stat=ErrorCounts(errors=44, reference_length=10),
        untruncated_error_rate=4.4,
    )
    fr = bar_cell(floored, 1.0, lang="fr")
    assert "(erreurs 4,4000 · 44/10)" in fr
    assert "(errors 4.4000 · 44/10)" in bar_cell(floored, 1.0, lang="en")
    plain = MetricScore(
        metric="char_accuracy",
        value=0.5,
        stat=ErrorCounts(errors=6, reference_length=12),
        untruncated_error_rate=0.5,
    )
    assert "untruncated" not in bar_cell(plain, 1.0, lang="fr")

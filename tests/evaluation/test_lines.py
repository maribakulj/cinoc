"""Distribution par ligne : alignement F15, percentiles, Gini, seuils, sonde.

Toutes les valeurs attendues sont **dérivées à la main** (règle D-068) :
fixture canonique = 5 lignes de 5 caractères aux CER [0.0, 0.2, 0.4, 0.6, 1.0]
(0, 1, 2, 3, 5 substitutions) — percentiles interpolés posés, Gini = 24/55.
"""

from __future__ import annotations

import pytest

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.analysis import LinesPayload
from cinoc.evaluation.lines import (
    LinesCollector,
    aligned_line_cers,
    gini,
    line_cer,
    newline_preserved,
    percentile,
)
from cinoc.evaluation.representations import prepare_text

#: Réf 5 lignes (5 caractères chacune) ; hyp à 0, 1, 2, 3 et 5 substitutions
#: → CER par ligne [0.0, 0.2, 0.4, 0.6, 1.0] (dérivé à la main).
_REF_FIVE = "linea\nlineb\nlinec\nlined\nlinee"
_HYP_FIVE = "linea\nlineX\nliXYc\nlWXYd\nVWXYZ"


def _view(
    profile: str | None = None, char_exclude: str | None = None
) -> EvaluationView:
    return EvaluationView(
        name="text",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
        normalization_profile=profile,
        char_exclude=char_exclude,
    )


class TestLineCer:
    def test_substitution_ratio(self) -> None:
        assert line_cer("abcd", "abcf") == 0.25  # 1 édition / 4 caractères

    def test_empty_reference_conventions(self) -> None:
        assert line_cer("", "") == 0.0
        assert line_cer("", "halluciné") == 1.0  # contenu sur ligne blanche

    def test_capped_at_one(self) -> None:
        assert line_cer("ab", "abcdef") == 1.0  # 4 insertions / 2 → plafonné

    def test_no_normalisation_of_its_own(self) -> None:
        """D-285 : une seule définition du CER. La ligne arrive préparée par la
        vue ; ``line_cer`` n'ajoute ni NFC ni ``strip`` — il les ajoutait, et
        le CER d'une ligne ne suivait pas la convention du document."""
        assert line_cer("caf\u00e9", "cafe\u0301") == 0.5  # 2 éditions / 4
        assert line_cer("  abc  ", "abc") == pytest.approx(4 / 7)

    def test_the_view_profile_is_what_prepares_the_line(self) -> None:
        # Sous ``keep_line_breaks`` (vue « texte (lignes) »), NFC et bords sont
        # traités par le profil, des deux côtés, comme pour le document.
        view = _view("keep_line_breaks")
        ref = prepare_text("caf\u00e9\n  abc  ", view)
        hyp = prepare_text("cafe\u0301\nabc", view)
        assert aligned_line_cers(ref, hyp) == [0.0, 0.0]


class TestAlignedLineCers:
    def test_identical_lines(self) -> None:
        text = "le roi\ndort bien\nce soir"
        assert aligned_line_cers(text, text) == [0.0, 0.0, 0.0]

    def test_deleted_gt_line_does_not_shift_the_rest(self) -> None:
        # F15 : la ligne du milieu manque côté hypothèse — l'alignement la
        # marque perdue (1.0) sans décaler la suivante (un appariement
        # positionnel donnerait [0, cer('dort bien','ce soir'), 1.0]).
        cers = aligned_line_cers("le roi\ndort bien\nce soir", "le roi\nce soir")
        assert cers == [0.0, 1.0, 0.0]

    def test_inserted_hyp_line_is_ignored(self) -> None:
        # La distribution est indexée sur la GT : la ligne insérée n'y entre pas.
        cers = aligned_line_cers("le roi\nce soir", "le roi\nparasite\nce soir")
        assert cers == [0.0, 0.0]

    def test_replace_pairs_positionally(self) -> None:
        assert aligned_line_cers("le roi\nabcd", "le roi\nabcf") == [0.0, 0.25]

    def test_empty_reference_yields_no_lines(self) -> None:
        assert aligned_line_cers("", "du texte") == []


class TestPercentile:
    def test_linear_interpolation_hand_derived(self) -> None:
        ordered = [0.0, 0.1, 0.2, 0.3, 0.4]
        assert percentile(ordered, 50) == pytest.approx(0.2)  # index 2
        assert percentile(ordered, 75) == pytest.approx(0.3)  # index 3
        assert percentile(ordered, 90) == pytest.approx(0.36)  # 0.3 + 0.6×0.1
        assert percentile(ordered, 95) == pytest.approx(0.38)
        assert percentile(ordered, 99) == pytest.approx(0.396)

    def test_single_value(self) -> None:
        assert percentile([0.5], 99) == 0.5


class TestGini:
    def test_concentrated_hand_derived(self) -> None:
        # tri [0, 0, 1] : Σ(i+1)x = 3 ; G = 6/(3·1) − 4/3 = 2/3.
        assert gini([0.0, 1.0, 0.0]) == pytest.approx(2 / 3)

    def test_uniform_is_zero(self) -> None:
        assert gini([0.3, 0.3, 0.3]) == pytest.approx(0.0, abs=1e-12)

    def test_no_error_is_zero(self) -> None:
        assert gini([0.0, 0.0]) == 0.0  # somme nulle = uniformité parfaite

    def test_single_line_is_zero(self) -> None:
        assert gini([1.0]) == 0.0  # 2/(1·1) − 2/1


class TestNewlinePreserved:
    def test_no_profile_keeps_newlines(self) -> None:
        assert newline_preserved(_view()) is True

    def test_diplomatic_profile_keeps_newlines(self) -> None:
        assert newline_preserved(_view("medieval_french")) is True

    def test_flat_profiles_destroy_newlines(self) -> None:
        assert newline_preserved(_view("flat_text")) is False
        assert newline_preserved(_view("hipe")) is False

    def test_char_exclude_containing_newline_is_detected(self) -> None:
        assert newline_preserved(_view(char_exclude="\n")) is False


class TestLinesCollector:
    def test_distribution_hand_derived(self) -> None:
        collector = LinesCollector()
        collector.observe("alpha", _REF_FIVE, _HYP_FIVE)
        analysis = collector.build("text")
        assert analysis is not None
        assert analysis.scope == "corpus" and analysis.view == "text"
        payload = analysis.payload
        assert isinstance(payload, LinesPayload)
        assert payload.heatmap_bins == 10
        (row,) = payload.pipelines
        assert row.pipeline == "alpha"
        assert row.line_count == 5
        assert row.mean_cer == pytest.approx(0.44)  # (0+0.2+0.4+0.6+1.0)/5
        # tri [0, .2, .4, .6, 1] : Σ(i+1)x = 9 ; G = 18/(5·2.2) − 6/5 = 24/55.
        assert row.gini == pytest.approx(24 / 55)
        assert row.percentiles.p50 == pytest.approx(0.4)
        assert row.percentiles.p75 == pytest.approx(0.6)
        assert row.percentiles.p90 == pytest.approx(0.84)  # 0.6 + 0.6×0.4
        assert row.percentiles.p95 == pytest.approx(0.92)
        assert row.percentiles.p99 == pytest.approx(0.984)
        rates = {item.threshold: item.rate for item in row.catastrophic}
        counts = {item.threshold: item.count for item in row.catastrophic}
        assert rates == {
            0.30: pytest.approx(0.6),
            0.50: pytest.approx(0.4),
            1.00: pytest.approx(0.2),
        }
        # Seuil inclusif : la ligne au CER plafonné 1.0 compte à ≥ 1.00 (le
        # « > » strict de la source laissait ce seuil à zéro pour toujours).
        assert counts[1.00] == 1
        # Positions relatives 0/5…4/5 → tranches 0, 2, 4, 6, 8 ; vides → None.
        assert row.heatmap == (0.0, None, 0.2, None, 0.4, None, 0.6, None, 1.0, None)

    def test_pools_lines_across_documents(self) -> None:
        collector = LinesCollector()
        collector.observe("alpha", "aaaa\nbbbb", "XXXX\nbbbb")  # [1.0, 0.0]
        collector.observe("alpha", "cccc", "cccc")  # [0.0]
        analysis = collector.build("text")
        assert analysis is not None
        (row,) = analysis.payload.pipelines
        assert row.line_count == 3
        assert row.mean_cer == pytest.approx(1 / 3)
        assert row.gini == pytest.approx(2 / 3)
        # Tranche 0 : 1ʳᵉ ligne des deux docs (1.0 et 0.0) → moyenne 0.5 ;
        # tranche 5 : 2ᵉ ligne du doc de 2 (fraction 0.5) → 0.0.
        assert row.heatmap[0] == pytest.approx(0.5)
        assert row.heatmap[5] == 0.0
        assert all(v is None for i, v in enumerate(row.heatmap) if i not in (0, 5))

    def test_pipelines_sorted_and_independent(self) -> None:
        collector = LinesCollector()
        collector.observe("beta", "abcd", "abcd")
        collector.observe("alpha", "abcd", "abcf")
        analysis = collector.build("text")
        assert analysis is not None
        rows = analysis.payload.pipelines
        assert [r.pipeline for r in rows] == ["alpha", "beta"]
        assert rows[0].mean_cer == 0.25 and rows[1].mean_cer == 0.0

    def test_disabled_collector_is_a_no_op(self) -> None:
        # Vue « à plat » : l'analyse est non applicable — payload absent,
        # jamais une distribution trompeuse calculée sur un texte aplati.
        collector = LinesCollector(enabled=newline_preserved(_view("flat_text")))
        collector.observe("alpha", _REF_FIVE, _HYP_FIVE)
        assert collector.build("text") is None

    def test_no_observation_yields_none(self) -> None:
        assert LinesCollector().build("text") is None

    def test_document_without_gt_lines_contributes_nothing(self) -> None:
        collector = LinesCollector()
        collector.observe("alpha", "", "du texte produit")
        assert collector.build("text") is None

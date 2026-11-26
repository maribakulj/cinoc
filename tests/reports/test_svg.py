"""Helpers SVG déterministes : convention d'arrondi + graphes serveur."""

from __future__ import annotations

from cinoc.reports.svg import (
    bar_series,
    box_plot,
    calibration_curve,
    composition_bar,
    donut_chart,
    dumbbell_rows,
    num,
    word_engine_heatmap,
    word_overlap_venn,
)


def test_donut_chart_empty_full_and_segments() -> None:
    assert donut_chart([]) == ""
    assert donut_chart([(0.0, "x")]) == ""  # tout à zéro
    full = donut_chart([(5.0, "oklch(0.55 0.11 40)")])
    assert "<circle" in full and "donut-hole" in full  # 100 % → cercle + trou
    multi = donut_chart([(3.0, "a"), (1.0, "b"), (1.0, "c")])
    assert multi.count('class="donut-seg"') == 3
    assert "donut-hole" in multi
    assert multi == donut_chart([(3.0, "a"), (1.0, "b"), (1.0, "c")])  # octet-stable


def test_dumbbell_rows_empty_and_links() -> None:
    assert dumbbell_rows([], scale_max=1.0) == ""
    rows = [("d1", [(0.1, "a"), (0.3, "b")]), ("d2", [(0.2, "a"), (0.2, "b")])]
    svg = dumbbell_rows(rows, scale_max=0.4)
    assert svg.count('class="dumb-dot"') == 4  # 2 points × 2 lignes
    assert svg.count('class="dumb-link"') == 2  # une liaison par ligne (≥2 points)
    assert "d1" in svg and "d2" in svg
    assert svg == dumbbell_rows(rows, scale_max=0.4)  # octet-stable


def test_box_plot_parts_and_deterministic() -> None:
    svg = box_plot(0.0, 0.1, 0.2, 0.3, 0.5, 0.22, 0.5, accent="var(--fern)")
    for cls in ("box-whisker", "box-cap", "box-box", "box-med", "box-mean"):
        assert cls in svg
    assert svg.startswith("<svg") and 'aria-hidden="true"' in svg
    assert svg == box_plot(0.0, 0.1, 0.2, 0.3, 0.5, 0.22, 0.5, accent="var(--fern)")


def test_word_overlap_venn_two_engines_regions_and_counts() -> None:
    svg = word_overlap_venn(
        ["A", "B"],
        {frozenset({0}): 5, frozenset({1}): 3, frozenset({0, 1}): 44},
        accents=["var(--fern)", "var(--slate)"],
    )
    assert svg.startswith("<svg") and 'class="venn-svg"' in svg
    assert svg.count("<circle") == 2
    assert ">5<" in svg and ">3<" in svg and ">44<" in svg
    assert ">A<" in svg and ">B<" in svg
    assert "var(--fern)" in svg and "var(--slate)" in svg


def test_word_overlap_venn_three_engines_has_three_circles() -> None:
    svg = word_overlap_venn(
        ["A", "B", "C"], {frozenset({0, 1, 2}): 7}, accents=["#a", "#b", "#c"]
    )
    assert svg.count("<circle") == 3 and ">7<" in svg


def test_word_overlap_venn_skips_zero_regions() -> None:
    svg = word_overlap_venn(
        ["A", "B"], {frozenset({0}): 0, frozenset({0, 1}): 9}, accents=["#a", "#b"]
    )
    assert ">9<" in svg and ">0<" not in svg


def test_word_overlap_venn_beyond_three_is_empty() -> None:
    assert word_overlap_venn(["A", "B", "C", "D"], {}, accents=["#a"] * 4) == ""


def test_word_overlap_venn_is_deterministic() -> None:
    a = word_overlap_venn(["A", "B"], {frozenset({0}): 2}, accents=["#a", "#b"])
    b = word_overlap_venn(["A", "B"], {frozenset({0}): 2}, accents=["#a", "#b"])
    assert a == b


def test_bar_series_one_rect_per_value_scaled_to_max() -> None:
    svg = bar_series([0.1, 0.2, 0.4], accent="#abc", width=100.0, height=100.0, gap=0.0)
    assert 'class="bars-svg"' in svg and "#abc" in svg
    assert svg.count("<rect") == 3
    # max (0.4) → barre pleine hauteur (y=0, height=100)
    assert 'y="0.00"' in svg and 'height="100.00"' in svg


def test_bar_series_empty_is_valid_svg() -> None:
    assert "<svg" in bar_series([], accent="#000")  # série vide → SVG vide valide


def test_composition_bar_segments_normalized_and_stacked() -> None:
    svg = composition_bar([(3.0, "#aaa"), (1.0, "#bbb")], width=100.0)
    assert 'class="comp-bar"' in svg
    assert "#aaa" in svg and "#bbb" in svg
    # parts normalisées (3:1) → 75 puis 25, empilées (x = 0 puis 75)
    assert 'x="0.00" y="0" width="75.00"' in svg
    assert 'x="75.00" y="0" width="25.00"' in svg


def test_composition_bar_handles_zero_total() -> None:
    assert "<svg" in composition_bar([], width=100.0)  # somme nulle → pas de /0


def test_num_is_fixed_precision_deterministic() -> None:
    assert num(1 / 3) == "0.33"  # précision fixe (2 décimales)
    assert num(10.0) == "10.00"
    assert num(0.0) == "0.00"
    # même entrée → mêmes octets (pas de flottant à précision variable)
    assert num(0.1 + 0.2) == num(0.3)


def test_calibration_curve_diagonal_polyline_and_inverted_y() -> None:
    svg = calibration_curve([(0.5, 0.5), (0.8, 0.6)], accent="#f0f", size=100.0)
    assert 'class="calib-diag"' in svg  # diagonale = calibration parfaite
    assert 'class="calib-line"' in svg and 'points="' in svg
    assert "#f0f" in svg
    # y inversé : exactitude 0.5 sur 100 → y = 50 ; conf 0.5 → x = 50
    assert "50.00,50.00" in svg


def test_calibration_curve_empty_keeps_diagonal_only() -> None:
    svg = calibration_curve([], accent="#000")
    assert 'class="calib-diag"' in svg
    assert 'class="calib-line"' not in svg  # aucun point → pas de polyligne


def test_calibration_curve_is_deterministic() -> None:
    pts = [(0.2, 0.3), (0.9, 0.85)]
    a = calibration_curve(pts, accent="#abc")
    b = calibration_curve(pts, accent="#abc")
    assert a == b


def test_word_engine_heatmap_words_headers_counts_and_teint() -> None:
    svg = word_engine_heatmap(
        ["A", "B"],
        [("prologve", [3, 0]), ("roi", [1, 2])],
        accent="var(--fern)",
    )
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert 'class="wmap-svg"' in svg and 'aria-hidden="true"' in svg
    # taille **intrinsèque** posée (width/height) → pas d'étirement à 100 % du
    # conteneur (2 colonnes : 156 + 30×2 = 216 de large, 18 + 22×2 = 62 de haut).
    assert 'width="216.00"' in svg and 'height="62.00"' in svg
    assert "prologve" in svg and "roi" in svg  # mots verbatim (lignes)
    assert ">A<" in svg and ">B<" in svg  # en-têtes moteur
    assert ">3<" in svg and ">2<" in svg  # comptes inscrits
    assert "var(--fern)" in svg  # teinte unique (intensité = compte)
    # case vide (compte 0) = pas de fond teinté
    assert 'style="fill:none"' in svg


def test_word_engine_heatmap_escapes_words_anti_xss() -> None:
    svg = word_engine_heatmap(["A"], [("<x>", [1])], accent="#abc")
    assert "&lt;x&gt;" in svg  # mot échappé
    assert "<x>" not in svg  # jamais injecté brut (pas de fausse balise)


def test_word_engine_heatmap_empty_is_valid_svg() -> None:
    assert "<svg" in word_engine_heatmap([], [], accent="#000")  # ne lève pas


def test_word_engine_heatmap_is_deterministic() -> None:
    a = word_engine_heatmap(["A", "B"], [("roi", [1, 2])], accent="#abc")
    b = word_engine_heatmap(["A", "B"], [("roi", [1, 2])], accent="#abc")
    assert a == b

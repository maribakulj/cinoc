"""Glossaire : loader YAML (FR/EN) + panneau dialog contextuel (chrome)."""

from __future__ import annotations

from cinoc.reports.glossary import load_glossary
from cinoc.reports.glossary_panel import glossary_chrome_link, glossary_dialog

#: Métriques réellement calculées par le moteur → chacune doit avoir une entrée.
REAL_METRICS = (
    "cer",
    "cer_diplo",
    "wer",
    "mer",
    "del_rate",
    "ins_rate",
    "diacritic_err",
    "mufi_err",
    "hcpr",
    "air",
    "unanchored_trigrams",
    "searchability",
    "region_cer",
    "region_detection",
    "ner_f1",
    "ner_f1_exact",
    "fca",
    "significance_p",
    "ece",
    "mce",
)


def test_load_fr_and_en_cover_every_real_metric() -> None:
    for lang in ("fr", "en"):
        gloss = load_glossary(lang)
        for metric in REAL_METRICS:
            assert metric in gloss, f"{metric} absent du glossaire {lang}"
            entry = gloss[metric]
            assert entry.get("title")
            assert entry.get("definition")


def test_unknown_lang_falls_back_to_fr() -> None:
    assert load_glossary("zz") == load_glossary("fr")


def test_cache_returns_same_object() -> None:
    assert load_glossary("fr") is load_glossary("fr")


def test_dialog_renders_only_present_metrics() -> None:
    html = glossary_dialog({"cer"}, "fr")
    assert '<dialog id="glossary-dialog"' in html  # périphérie, pas dans le flux
    assert "Glossaire" in html
    assert "CER — taux d" in html  # titre de l'entrée cer (apostrophe échappée)
    assert "erreur caractère" in html
    assert 'class="gl-item"' in html and "<details" in html  # disclosure natif
    # une métrique absente du run n'apparaît pas
    assert "erreur mot" not in html  # le titre WER est absent


def test_dialog_english_lang() -> None:
    html = glossary_dialog({"wer"}, "en")
    assert "Glossary" in html
    assert "WER — word error rate" in html
    assert "What it measures" in html  # libellé de champ EN


def test_dialog_empty_when_metric_has_no_entry() -> None:
    assert glossary_dialog({"unknown_metric"}, "fr") == ""


def test_dialog_empty_when_no_metrics() -> None:
    assert glossary_dialog(set(), "fr") == ""


def test_dialog_is_deterministic() -> None:
    # Ordre stable (clés triées) : même sortie quel que soit l'ordre d'itération.
    a = glossary_dialog({"cer", "wer"}, "fr")
    b = glossary_dialog({"wer", "cer"}, "fr")
    assert a == b


def test_chrome_link_targets_dialog() -> None:
    fr = glossary_chrome_link("fr")
    assert 'href="#glossary-dialog"' in fr and "Glossaire" in fr
    assert "Glossary" in glossary_chrome_link("en")


def test_card_shows_declared_category_and_unit_and_oracle() -> None:
    """D-289 : la fiche affiche la catégorie et l'unité **du registre** (pas une
    copie dans le YAML) et l'oracle du calcul."""
    fr = glossary_dialog({"cer", "unanchored_trigrams"}, "fr")
    assert "Catégorie</dt><dd class=\"gl-v\">établie" in fr
    assert "Catégorie</dt><dd class=\"gl-v\">exploratoire" in fr
    assert "Unité</dt><dd class=\"gl-v\">caractère" in fr
    assert "Unité</dt><dd class=\"gl-v\">trigramme" in fr
    assert "Oracle</dt>" in fr and "jiwer 4.0.0" in fr
    en = glossary_dialog({"wer"}, "en")
    assert "Category</dt><dd class=\"gl-v\">established" in en
    assert "Unit</dt><dd class=\"gl-v\">word" in en


def test_a_term_outside_the_registry_has_no_declared_category() -> None:
    # ``significance_p`` est un test, pas une métrique notée : pas de catégorie.
    html = glossary_dialog({"significance_p"}, "fr")
    assert "Catégorie" not in html and "Oracle</dt>" in html

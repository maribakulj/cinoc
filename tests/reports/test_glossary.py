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

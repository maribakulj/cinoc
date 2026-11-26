"""Des noms qui ne promettent pas plus qu'ils ne mesurent (T4a D-194, puis P5e 8
D-288).

T4a avait renommé l'**affichage** des métriques aux noms « chargés » en gardant
leurs clés. P5e 8 renomme la **clé** de ``hallucination`` — le calcul est la
part des trigrammes de l'hypothèse absents de la GT, rien de plus : il ne voit
pas une page recopiée deux fois — et dit les limites de ``fca``,
``searchability``, ``ner_f1`` et ``region_cer`` là où le lecteur les lit."""

from __future__ import annotations

from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.reports.glossary import load_glossary
from cinoc.reports.sections._tables import _METRIC_SHORT, metric_short_label


def _registry() -> MetricRegistry:
    registry = MetricRegistry()
    register_default_metrics(registry)
    return registry


def test_the_key_says_what_is_computed() -> None:
    registry = _registry()
    assert registry.document_metric("unanchored_trigrams") is not None
    # Zéro shim : l'ancienne clé n'est ni enregistrée ni aliasée.
    assert registry.document_metric("hallucination") is None
    for lang in ("fr", "en"):
        gloss = load_glossary(lang)
        assert "hallucination" not in gloss
        assert "unanchored_trigrams" in gloss


def test_glossary_titles_are_descriptive_and_carry_the_criterion() -> None:
    cases = (("fr", "trigramme", "page dupliquée"), ("en", "trigram", "duplicated"))
    for lang, anchor_kw, blind_kw in cases:
        gloss = load_glossary(lang)
        h, s = gloss["unanchored_trigrams"], gloss["searchability"]
        assert "ancr" in h["title"].lower() or "anchor" in h["title"].lower()
        assert "rappel" in s["title"].lower() or "recall" in s["title"].lower()
        assert anchor_kw in h["definition"].lower()
        # La limite mesurée est dite : une page recopiée deux fois vaut 0,021.
        assert blind_kw in h["limits"].lower()
        # Le seuil n'est plus un « ≤ 2 » absolu.
        assert "≤ 2" not in s["title"] and "AUTO" in s["definition"]


def test_fca_is_declared_limited() -> None:
    for lang, kw in (("fr", "fusionn"), ("en", "merge")):
        entry = load_glossary(lang)["fca"]
        assert kw in entry["limits"].lower()
        assert kw in entry["title"].lower() or "limit" in entry["title"].lower()


def test_ner_carries_no_borrowed_convention() -> None:
    for lang in ("fr", "en"):
        gloss = load_glossary(lang)
        for key in ("ner_f1", "ner_f1_exact"):
            text = " ".join(str(v) for v in gloss[key].values())
            assert "CoNLL" not in text and "HIPE" not in text


def test_region_cer_says_phantom_regions_count() -> None:
    for lang, kw in (("fr", "fantôme"), ("en", "phantom")):
        assert kw in load_glossary(lang)["region_cer"]["definition"].lower()


def test_short_labels() -> None:
    assert _METRIC_SHORT["unanchored_trigrams"] == "non-ancré"
    assert _METRIC_SHORT["searchability"] == "rappel·ft"
    assert metric_short_label("unanchored_trigrams") == "non-ancré"
    assert "hallucination" not in _METRIC_SHORT

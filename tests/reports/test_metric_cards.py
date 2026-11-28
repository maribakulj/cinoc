"""Une fiche par métrique, trois niveaux (D-289) — le critère de sortie de P5e 9.

Toute métrique enregistrée déclare sa **catégorie** et son **unité** au
registre (``MetricSpec``, une seule déclaration) ; le glossaire porte sa
**fiche** en français et en anglais (définition, ce qu'elle mesure, limites,
oracle) ; la définition nomme l'unité déclarée ; et cette unité est **celle du
calcul** — ce que compte la statistique de l'``Observation`` (son dénominateur
de référence, K1), vérifié ici sur des échantillons dont chaque compte a été
fait à la main.
"""

from __future__ import annotations

import pytest

from cinoc.domain.evaluation import MetricCategory, MetricSpec, MetricUnit
from cinoc.domain.layout import (
    BBox,
    CanonicalLayout,
    Geometry,
    LayoutPage,
    Line,
    Region,
)
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.metric import DocumentMetric
from cinoc.evaluation.ner import Entity, EntitySet
from cinoc.evaluation.registry import (
    MetricRegistry,
    metric_specs,
    register_default_metrics,
)
from cinoc.evaluation.statistics import EditCounts, ErrorCounts, MatchCounts
from cinoc.reports.glossary import load_glossary
from cinoc.reports.metric_categories import UNIT_LABELS

E, A, X = (
    MetricCategory.ESTABLISHED,
    MetricCategory.ADAPTED,
    MetricCategory.EXPLORATORY,
)

#: La table de D-289, figée : changer une catégorie est une décision, pas une
#: retouche. Établie = conforme à une référence nommée dont un oracle vérifie
#: le calcul ; dans le doute, adaptée.
CATEGORIES: dict[str, MetricCategory] = {
    "cer": E, "wer": E, "mer": E, "cmer": E,
    "cer_diplo": A, "char_accuracy": A, "word_accuracy": A, "fca": A,
    "del_rate": A, "ins_rate": A,
    "bow_precision": A, "bow_recall": A, "bow_f1": A, "searchability": A,
    "region_cer": A, "region_detection": A, "line_identity_cer": A,
    "reading_order_tau": A, "ner_f1": A, "ner_f1_exact": A,
    "diacritic_err": X, "mufi_err": X, "air": X, "hcpr": X,
    "unanchored_trigrams": X, "numseq_strict": X, "numseq_value": X,
    "line_identity_coverage": X, "reading_order_coverage": X,
}

_FIELDS = ("title", "definition", "measures", "limits", "oracle")


def test_the_catalogue_is_the_registry_plus_the_bound_hcpr() -> None:
    registry = MetricRegistry()
    register_default_metrics(registry)
    assert set(metric_specs()) == {*registry.names(), "hcpr"}


@pytest.mark.parametrize("name", sorted(metric_specs()))
def test_every_registered_metric_declares_category_and_unit(name: str) -> None:
    spec = metric_specs()[name]
    assert isinstance(spec, MetricSpec)
    assert isinstance(spec.category, MetricCategory)
    assert isinstance(spec.unit, MetricUnit)
    assert spec.category is CATEGORIES[name], name


def test_the_categorisation_table_covers_every_metric() -> None:
    assert set(CATEGORIES) == set(metric_specs())


def test_only_four_metrics_are_established() -> None:
    established = {n for n, s in metric_specs().items() if s.category is E}
    assert established == {"cer", "wer", "mer", "cmer"}


def _stems(label: str) -> list[str]:
    # « entity » → « entit » (entities) ; les pluriels français ajoutent un s.
    return [word.removesuffix("y") for word in label.split()]


@pytest.mark.parametrize("lang", ["fr", "en"])
@pytest.mark.parametrize("name", sorted(metric_specs()))
def test_every_metric_has_a_full_card_naming_its_unit(name: str, lang: str) -> None:
    card = load_glossary(lang).get(name)
    assert card is not None, f"{name} sans fiche ({lang})"
    for field in _FIELDS:
        assert card.get(field), f"{name} : champ « {field} » vide ({lang})"
    label = UNIT_LABELS[metric_specs()[name].unit][1 if lang == "en" else 0]
    definition = card["definition"].lower()
    for stem in _stems(label):
        assert stem in definition, f"{name} ({lang}) : unité « {label} » non dite"


_TEXT = "le chat noir dort"
#: Comptes faits à la main sur ``_TEXT`` : 17 caractères (espaces comprises),
#: 4 mots, 15 trigrammes de caractères.
_TEXT_COUNTS = {
    MetricUnit.CHARACTER: 17,
    MetricUnit.WORD: 4,
    MetricUnit.CHARACTER_TRIGRAM: 15,
}
_NUMBERS = "en 1515 et 1789, fol. 12r"
_NUMBER_COUNTS = {
    MetricUnit.CHARACTER: 25,
    MetricUnit.WORD: 6,
    MetricUnit.NUMERIC_SEQUENCE: 3,  # 1515, 1789, fol. 12r
}


def _region(rid: str, x: int, *lines: tuple[str, str]) -> Region:
    return Region(
        id=rid,
        geometry=Geometry(bbox=BBox(x=x, y=0, width=40, height=40)),
        lines=tuple(Line(id=lid, text=text) for lid, text in lines),
    )


#: Trois régions, quatre lignes. Les lignes d'une région sont jointes par un
#: saut de ligne pour le CER par région (« ij\nklmn » : 7 caractères).
_LAYOUT = CanonicalLayout(
    pages=(
        LayoutPage(
            width=200,
            height=100,
            regions=(
                _region("R1", 0, ("L1", "abc")),
                _region("R2", 50, ("L2", "defgh")),
                _region("R3", 100, ("L3", "ij"), ("L4", "klmn")),
            ),
            reading_order=("R1", "R2", "R3"),
        ),
    )
)
_LAYOUT_COUNTS = {MetricUnit.REGION: 3, MetricUnit.LINE: 4}
_ENTITIES = EntitySet(
    text="Jean à Paris",
    entities=(Entity("PER", 0, 4, "Jean"), Entity("LOC", 7, 12, "Paris")),
)

#: (métrique, référence, hypothèse, comptes à la main par unité candidate).
SAMPLES: list[tuple[str, object, object, dict[MetricUnit, int]]] = [
    *(
        (name, _TEXT, _TEXT, _TEXT_COUNTS)
        for name in (
            "cer", "cer_diplo", "char_accuracy", "cmer", "fca", "wer", "mer",
            "del_rate", "ins_rate", "word_accuracy", "bow_precision",
            "bow_recall", "bow_f1", "searchability", "unanchored_trigrams",
        )
    ),
    # Les métriques restreintes à une classe de caractères : un texte qui
    # n'en contient que d'eux (4 caractères, 1 mot, 2 trigrammes).
    ("diacritic_err", "éàüç", "éàüç", {MetricUnit.CHARACTER: 4, MetricUnit.WORD: 1}),
    ("mufi_err", "ſþꝑ", "ſþꝑ", {MetricUnit.CHARACTER: 3, MetricUnit.WORD: 1}),
    ("air", "ſſſ", "ſſſ", {MetricUnit.CHARACTER: 3, MetricUnit.WORD: 1}),
    ("hcpr", "ſſſ", "ſſſ", {MetricUnit.CHARACTER: 3, MetricUnit.WORD: 1}),
    ("numseq_strict", _NUMBERS, _NUMBERS, _NUMBER_COUNTS),
    ("numseq_value", _NUMBERS, _NUMBERS, _NUMBER_COUNTS),
    # 3 + 5 + 7 caractères de région ; 3 + 5 + 2 + 4 caractères de ligne.
    ("region_cer", _LAYOUT, _LAYOUT, {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 15}),
    ("line_identity_cer", _LAYOUT, _LAYOUT,
     {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 14}),
    ("line_identity_coverage", _LAYOUT, _LAYOUT,
     {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 14}),
    ("region_detection", _LAYOUT, _LAYOUT,
     {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 15}),
    ("reading_order_tau", _LAYOUT, _LAYOUT,
     {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 15}),
    ("reading_order_coverage", _LAYOUT, _LAYOUT,
     {**_LAYOUT_COUNTS, MetricUnit.CHARACTER: 15}),
    # 2 entités, 3 mots, 12 caractères.
    ("ner_f1", _ENTITIES, _ENTITIES,
     {MetricUnit.ENTITY: 2, MetricUnit.WORD: 3, MetricUnit.CHARACTER: 12}),
    ("ner_f1_exact", _ENTITIES, _ENTITIES,
     {MetricUnit.ENTITY: 2, MetricUnit.WORD: 3, MetricUnit.CHARACTER: 12}),
]


def _metric(name: str) -> DocumentMetric:
    from cinoc.evaluation.archaic import DEFAULT_ARCHAIC_LIST, resolve_archaic_list
    from cinoc.evaluation.metrics.archaic import make_hcpr_metric

    registry = MetricRegistry()
    register_default_metrics(registry)
    registry.register_document_metric(
        make_hcpr_metric(resolve_archaic_list(DEFAULT_ARCHAIC_LIST).chars)
    )
    metric = registry.document_metric(name)
    assert metric is not None
    return metric


def test_every_metric_has_a_sample() -> None:
    assert {name for name, *_ in SAMPLES} == set(metric_specs())


def _counted(stat: object) -> int:
    """Les unités que compte la statistique : son dénominateur de référence
    (|réf| pour un taux, tp + fn pour un appariement, n pour une proportion).
    Sur ces échantillons, hypothèse = référence : tous les dénominateurs
    d'une famille (précision, MER…) coïncident."""
    if isinstance(stat, EditCounts | ErrorCounts):
        return stat.reference_length
    if isinstance(stat, MatchCounts):
        return stat.tp + stat.fn
    return int(stat.total)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("name", "reference", "hypothesis", "counts"),
    SAMPLES,
    ids=[s[0] for s in SAMPLES],
)
def test_the_declared_unit_is_what_the_statistic_counts(
    name: str,
    reference: object,
    hypothesis: object,
    counts: dict[MetricUnit, int],
) -> None:
    unit = metric_specs()[name].unit
    assert unit in counts, f"{name} : aucun compte à la main pour {unit}"
    # L'échantillon départage : le compte de l'unité déclarée n'est celui
    # d'aucune autre unité candidate — une unité mal déclarée échouerait.
    others = [n for u, n in counts.items() if u is not unit]
    assert counts[unit] not in others
    observation = _metric(name).fn(
        DocContext(document_id="d", reference=reference, hypothesis=hypothesis)
    )
    assert observation is not None
    assert _counted(observation.stat) == counts[unit]

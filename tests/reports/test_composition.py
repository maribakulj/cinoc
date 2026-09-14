"""La section composition : **ce qu'il y a dans chaque chaîne**, pas son nom.

Le rapport disait quelle chaîne gagne, jamais de quoi elle est faite. Un nom
comme ``T_saknussemm_vision_bert`` porte une intention, pas un contenu : ni le
segmenteur, ni le modèle, ni les réglages. Comparer deux chiffres sans pouvoir
lire les deux montages, c'est comparer deux boîtes noires.

Ce qui est vérifié ici est que la section **lit le manifeste** et n'invente
rien : la donnée existait déjà (``pipeline_specs``, ``adapter_kwargs``), seule
la façon de la montrer manquait.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from cinoc.evaluation.result import RunManifest, RunResult
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.composition import CompositionSection


def _spec(nom: str, steps: list[dict[str, Any]]) -> dict[str, Any]:
    return {"name": nom, "initial_inputs": ["image"], "steps": steps}


def _etape(
    ident: str,
    adapter: str,
    entrees: list[str],
    sorties: list[str],
    **extra: Any,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": ident,
        "kind": "x",
        "adapter_name": adapter,
        "params": {},
        "input_types": entrees,
        "output_types": sorties,
        "inputs_from": {},
        "fanout": False,
        "crop": False,
        "merge_from": [],
    }
    base.update(extra)
    return base


def _result(
    specs: list[dict[str, Any]], kwargs: dict[str, Any] | None = None
) -> RunResult:
    return RunResult(
        manifest=_manifest(specs, kwargs), pipelines=(), documents=()
    )


def _manifest(
    specs: list[dict[str, Any]], kwargs: dict[str, Any] | None = None
) -> RunManifest:
    instant = datetime(2026, 9, 14, tzinfo=UTC)
    return RunManifest(
        run_id="r",
        corpus_name="c",
        code_version="1.0",
        n_documents=1,
        started_at=instant,
        completed_at=instant,
        pipeline_specs=specs,
        adapter_kwargs=kwargs or {},
    )


def _rendu(specs: list[dict[str, Any]], kwargs: dict[str, Any] | None = None) -> str:
    html = CompositionSection().render(
        _result(specs, kwargs), SectionContext(lang="fr")
    )
    assert html is not None
    return str(html)


def _tableaux(specs: list[dict[str, Any]]) -> str:
    """Les seuls tableaux : le chapeau **explique** la notation ``←``/``⊕``, donc
    le chercher dans le HTML entier le trouverait toujours."""
    return "<table" + _rendu(specs).split("<table", 1)[1]


def test_a_run_without_specs_renders_nothing() -> None:
    """Pas de spec, pas de section : mieux vaut rien qu'un cadre vide."""
    assert CompositionSection().render(_result([]), SectionContext()) is None


def test_each_step_names_its_module_and_its_types() -> None:
    html = _rendu(
        [_spec("P", [_etape("s", "tesseract_layout", ["image"], ["layout"])])]
    )
    assert "tesseract_layout" in html
    assert "image" in html and "layout" in html


def test_the_real_settings_are_shown() -> None:
    """**Deux chaînes au nom voisin peuvent ne différer que par un nombre**, et
    c'est alors ce nombre, seul, que le banc mesure. Le cacher rend la
    comparaison illisible."""
    html = _rendu(
        [_spec("P", [_etape("s", "tesseract:x", ["image"], ["raw_text"])])],
        {"tesseract:x": {"label": "x", "lang": "fra", "psm": 6}},
    )
    assert "psm=6" in html
    assert "lang=fra" in html
    assert "label=x" not in html, (
        "le label ne nomme que des fichiers de workspace : il n'apprend rien."
    )


def test_a_fanout_step_is_marked() -> None:
    """Une étape ``par région`` s'exécute **une fois par bloc** : c'est la
    différence entre lire une page et lire trente morceaux."""
    html = _rendu(
        [
            _spec(
                "P",
                [
                    _etape("seg", "yolo", ["image"], ["layout"]),
                    _etape(
                        "reco",
                        "tesseract:b",
                        ["layout", "image"],
                        ["layout"],
                        fanout=True,
                        crop=True,
                        inputs_from={"layout": "seg"},
                    ),
                ],
            )
        ]
    )
    assert "par région" in html
    assert "découpe" in html


def test_a_merge_names_its_sources() -> None:
    """Une fusion n'est pas une chaîne linéaire, et le nom du pipeline ne le
    dit pas."""
    html = _rendu(
        [
            _spec(
                "P",
                [
                    _etape("a", "m1", ["image"], ["layout"]),
                    _etape("b", "m2", ["image"], ["layout"]),
                    _etape(
                        "f",
                        "gap_fill:g",
                        ["layout"],
                        ["layout"],
                        merge_from=["a", "b"],
                    ),
                ],
            )
        ]
    )
    assert "⊕" in html
    assert "a + b" in html


def test_a_step_that_simply_follows_says_nothing() -> None:
    """Le bruit tue la lecture : on ne signale que ce qui **s'écarte** de
    l'évidence. Une étape qui suit la précédente n'a rien à déclarer."""
    tableaux = _tableaux(
        [
            _spec(
                "P",
                [
                    _etape("a", "m1", ["image"], ["layout"]),
                    _etape(
                        "b", "m2", ["layout"], ["raw_text"],
                        inputs_from={"layout": "a"},
                    ),
                ],
            )
        ]
    )
    assert "←" not in tableaux


def test_a_step_reaching_further_back_is_flagged() -> None:
    """Le pendant : remonter plus haut change la forme du graphe, et doit se
    voir. Sans ce signal, deux DAG différents se liraient pareil."""
    html = _rendu(
        [
            _spec(
                "P",
                [
                    _etape("a", "m1", ["image"], ["layout"]),
                    _etape(
                        "b", "m2", ["layout"], ["layout"],
                        inputs_from={"layout": "a"},
                    ),
                    _etape(
                        "c", "m3", ["layout"], ["raw_text"],
                        inputs_from={"layout": "a"},
                    ),
                ],
            )
        ]
    )
    assert "← a" in html


def test_pipelines_are_ordered_like_everywhere_else() -> None:
    """Le badge « A » doit désigner la même chaîne d'une section à l'autre :
    l'ordre vient de ``result.pipelines``, jamais d'un tri local."""
    from cinoc.evaluation.result import PipelineResult

    result = RunResult(
        manifest=_manifest([_spec("second", []), _spec("premier", [])]),
        pipelines=(
            PipelineResult(pipeline="premier", view="v", aggregate=()),
            PipelineResult(pipeline="second", view="v", aggregate=()),
        ),
        documents=(),
    )
    html = CompositionSection().render(result, SectionContext(lang="fr"))
    assert html is not None
    texte = str(html)
    assert texte.index("premier") < texte.index("second")


def test_the_section_is_declared_wide() -> None:
    """**Elle doit prendre toute la largeur.**

    C'est un tableau de cinq colonnes par pipeline, dont une de réglages qui
    peut être longue (``psm_by_class=plain text:6,title:6,…``). Dans une colonne
    étroite, chaque cellule se replie sur trois lignes et le montage devient
    illisible — la section rate alors exactement ce pour quoi elle existe, et
    le défaut ne se voit qu'à l'œil, jamais dans un test de contenu.
    """
    from cinoc.reports.renderer import _WIDE_SECTIONS

    assert "composition" in _WIDE_SECTIONS

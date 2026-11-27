"""Tranche 1b — non-mesure et supports (K2 ; A1, A2, A4, A6, A7).

Tests écrits pour la refonte (``CONTRATS.md`` § 4.1, « 1b · À écrire ») : les
contre-exemples de la revue (``rapports/revue_contre_exemples/`` de la
contre-expertise) portés en tests, les cas A2 (troncature aval, repli total de
``saknussemm``, ``not_transcribed``), les grappes (B3) et les propriétés « P »
de A1 et A2 (Hypothesis, profil déterministe).

Deux bancs : ``Bench`` (``evaluate_run``, couche 3) quand l'exécution n'est pas
en jeu, et le kit des briques tierces (``cinoc.app.run``) quand elle l'est. Les
champs que la tranche ajoute sont lus par ``tests/adversarial/_contrat.py``.
"""

from __future__ import annotations

import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cinoc.adapters.extension import (
    AdapterStepError,
    Artifact,
    ArtifactType,
    CanonicalLayout,
    RunContext,
    RunControl,
    StepOutput,
    compute_content_hash,
    layout_step_output,
    workspace_artifact_path,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.layout import LayoutPage, Line, Region
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import (
    axes,
    comparaison,
    composante,
    corpus_declare,
    couverture,
    document_en_grappe,
    invention,
    macro,
    paire,
    politique_empty_page,
    publication_grappes,
    reference_non_transcrite,
    statistique,
    support_global,
    support_macro,
    support_micro,
)
from tests.adversarial._hypothese import DETERMINISTE
from tests.adversarial.metriques_stats.ms_support import (
    Bench,
    entities_json,
    letters,
    observation,
    prf_f1,
    substitute,
    view,
)
from tests.adversarial.metriques_stats.ms_support import aggregate as bench_aggregate

from ._kit import (
    T,
    TextBrick,
    aggregate,
    corpus,
    execute,
    fixed,
    levenshtein,
    per_document,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)

pytestmark = pytest.mark.tranche("1b")

REF = "abcdefghij"


# --------------------------------------------------------------------------
# A1, A2, A7 : part manquante (``partial``, ``truncated``), jamais imputée.
# --------------------------------------------------------------------------


class _Segmenter:
    """Deux régions sans texte, ``r1`` et ``r2``, sur chaque page."""

    name = "ce_seg2"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.LAYOUT})

    def execute(
        self, inputs: object, params: object, context: RunContext, control: RunControl
    ) -> StepOutput:
        layout = CanonicalLayout(
            pages=(
                LayoutPage(
                    regions=(Region(id="r1"), Region(id="r2")),
                    reading_order=("r1", "r2"),
                ),
            )
        )
        return layout_step_output(layout, context, self.name)


class _RegionReco:
    """Reconnaisseur de région : rend le texte exact, sauf sur ``pannes``
    (``(document, région)``), où il lève comme une API tombée."""

    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(
        self,
        name: str,
        texts: Mapping[tuple[str, str], str],
        pannes: set[tuple[str, str]],
    ) -> None:
        self.name = name
        self._texts = texts
        self._pannes = pannes

    def execute(
        self,
        inputs: Mapping[ArtifactType, Artifact],
        params: object,
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        region = inputs[ArtifactType.IMAGE].region_id or ""
        key = (context.document_id, region)
        if key in self._pannes:
            raise AdapterStepError("503 Service Unavailable")
        assert context.workspace_uri is not None
        payload = self._texts[key].encode("utf-8")
        path = workspace_artifact_path(
            context.workspace_uri, context.document_id, f"{self.name}_{region}", "txt"
        )
        path.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:{region}",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(payload),
                )
            }
        )


PAGES = {"p1": ("abcdefghij", "klmnopqrst"), "p2": ("uvwxyzabcd", "efghijklmn")}


def _partial_run(tmp_path: Path, **evaluation: Any) -> RunResult:
    """``P`` perd une région sur deux de ``p2`` ; ``Q`` perd les deux."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    texts = {
        (page, f"r{i + 1}"): text
        for page, pair in PAGES.items()
        for i, text in enumerate(pair)
    }
    documents = []
    for page, (first, second) in PAGES.items():
        (tmp_path / f"{page}.png").write_bytes(b"\x89PNG stub")
        gt = tmp_path / f"{page}.gt.layout.json"
        truth = CanonicalLayout(
            pages=(
                LayoutPage(
                    regions=(
                        Region(id="r1", lines=(Line(text=first),)),
                        Region(id="r2", lines=(Line(text=second),)),
                    ),
                ),
            )
        )
        gt.write_bytes(truth.model_dump_json().encode("utf-8"))
        documents.append(
            DocumentRef(
                id=page,
                image_uri=str(tmp_path / f"{page}.png"),
                ground_truths=(GroundTruthRef(type=T.LAYOUT, uri=str(gt)),),
            )
        )

    def hybrid(name: str, reco: str) -> PipelineSpec:
        return PipelineSpec(
            name=name,
            initial_inputs=(T.IMAGE,),
            steps=(
                PipelineStep(
                    id="segment",
                    kind="segmentation",
                    adapter_name="ce_seg2",
                    input_types=(T.IMAGE,),
                    output_types=(T.LAYOUT,),
                ),
                PipelineStep(
                    id="recognize",
                    kind="recognition",
                    adapter_name=reco,
                    input_types=(T.LAYOUT, T.IMAGE),
                    output_types=(T.LAYOUT,),
                    inputs_from={T.LAYOUT: "segment"},
                    fanout=True,
                ),
            ),
        )

    structure = EvaluationView(
        name="structure",
        candidate_types=frozenset({T.LAYOUT}),
        metric_names=("region_cer",),
    )
    return execute(
        spec(
            CorpusSpec(name="ce", documents=tuple(documents)),
            [hybrid("P", "ce_reco_p"), hybrid("Q", "ce_reco_q")],
            [structure],
            **evaluation,
        ),
        registry_with(
            _Segmenter(),
            _RegionReco("ce_reco_p", texts, {("p2", "r2")}),
            _RegionReco("ce_reco_q", texts, {("p2", "r1"), ("p2", "r2")}),
        ),
    )


def test_k2_partial_impute_en_silence__part_manquante_exclue_par_defaut(
    tmp_path: Path,
) -> None:
    """``k2_partial_impute_en_silence.py`` (A1, A2, A7) : sur ``p2``, ``P`` perd
    une région et ``Q`` les deux. Aujourd'hui la région perdue de ``P`` est
    notée vide en silence (``region_cer`` 0,5 sur ``p2``) tandis que ``Q`` est
    écarté : plus d'échecs, meilleur agrégat. Contrat : les deux ``p2`` portent
    ``partial_output`` (axe 3), ne sont pas notés par défaut, et la couverture
    le dit (1 mesuré sur 2 attendus). Sous ``empty_page`` seulement, la part
    manquante est notée vide : P = 10/40, Q = 20/40 — l'ordre suit les échecs."""
    result = _partial_run(tmp_path / "defaut")
    for name in ("P", "Q"):
        p2 = per_document(result, name, "p2", "region_cer", view="structure")
        assert p2.value is None, f"{name} : région perdue notée en silence, {p2.value}"
        assert axes(p2)[2] == "partial_output"
        agg = aggregate(result, name, "region_cer", view="structure")
        assert (agg.value, support_micro(agg), agg.expected) == (0.0, 1, 2)
        assert couverture(agg) == {"partial_output": 1}
    sensible = _partial_run(
        tmp_path / "sensible", failure_policy=politique_empty_page()
    )
    values = {
        name: aggregate(sensible, name, "region_cer", view="structure").value
        for name in ("P", "Q")
    }
    assert values == pytest.approx({"P": 10 / 40, "Q": 20 / 40})


def test_a2_troncature_aval__la_vue_amont_reste_complete(tmp_path: Path) -> None:
    """A2 : l'OCR lit ``b`` en entier, la correction aval est coupée par
    ``max_tokens``. La vue « lecture » (``target_step: ocr``) est complète :
    ``b`` y est valide et noté (CER 0). La vue « texte » (sortie corrigée)
    porte ``truncated_output`` sur ``b`` et ne la note pas par défaut."""
    bricks = (
        TextBrick("ce_ocr", fixed({"a": REF, "b": REF})),
        TextBrick(
            "ce_corr",
            fixed({"a": REF, "b": "abcde"}),
            in_type=T.RAW_TEXT,
            out_type=T.CORRECTED_TEXT,
            truncate=frozenset({"b"}),
        ),
    )
    result = execute(
        spec(
            corpus(tmp_path, {"a": REF, "b": REF}),
            [
                pipeline(
                    "p",
                    step("ocr", "ce_ocr"),
                    step(
                        "corr", "ce_corr", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT
                    ),
                )
            ],
            [
                text_view("lecture", target_step="ocr"),
                text_view("texte", candidates=(T.CORRECTED_TEXT,)),
            ],
        ),
        registry_with(*bricks),
    )
    lecture = per_document(result, "p", "b", view="lecture")
    texte = per_document(result, "p", "b", view="texte")
    assert lecture.value == 0.0
    assert texte.value is None, f"sortie corrigée tronquée notée : CER {texte.value}"
    assert axes(lecture) == ("applicable", "available", "valid")
    assert axes(texte)[2] == "truncated_output"


class _Lines:
    """Segmenteur qui rend une ligne à corriger (``ſ`` long) et une ligne propre."""

    name = "ce_lines"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.LAYOUT})

    def execute(
        self, inputs: object, params: object, context: RunContext, control: RunControl
    ) -> StepOutput:
        layout = CanonicalLayout(
            pages=(
                LayoutPage(
                    regions=(
                        Region(
                            id="r1",
                            lines=(
                                Line(id="l1", text="le ſoleil"),
                                Line(id="l2", text="rien ici"),
                            ),
                        ),
                    )
                ),
            )
        )
        return layout_step_output(layout, context, self.name)


def test_a2_saknussemm_repli_total__unite_partielle(tmp_path: Path) -> None:
    """A2 (§ 1.3, R6) : ``saknussemm`` interroge un serveur qui ne répond sur
    aucune ligne (port fermé de la boucle locale) ; il retombe sur le texte
    source de chaque ligne. Aujourd'hui l'unité est ``ok``, sans message, et la
    sortie non corrigée est notée comme une correction. Contrat : l'unité est
    ``partial`` et l'observation de la sortie corrigée porte
    ``partial_output``, non notée par défaut."""
    (tmp_path / "d.png").write_bytes(b"\x89PNG stub")
    (tmp_path / "d.gt.txt").write_text("le soleil\nrien ici", encoding="utf-8")
    documents = (
        DocumentRef(
            id="d",
            image_uri=str(tmp_path / "d.png"),
            ground_truths=(
                GroundTruthRef(type=T.RAW_TEXT, uri=str(tmp_path / "d.gt.txt")),
            ),
        ),
    )
    chain = PipelineSpec(
        name="p",
        initial_inputs=(T.IMAGE,),
        steps=(
            PipelineStep(
                id="seg",
                kind="segmentation",
                adapter_name="ce_lines",
                input_types=(T.IMAGE,),
                output_types=(T.LAYOUT,),
            ),
            PipelineStep(
                id="corr",
                kind="post_correction",
                adapter_name="saknussemm:llm",
                input_types=(T.LAYOUT,),
                output_types=(T.LAYOUT, T.CORRECTED_TEXT),
            ),
        ),
    )
    run_spec = spec(
        CorpusSpec(name="ce", documents=documents),
        [chain],
        [text_view(candidates=(T.CORRECTED_TEXT,))],
    ).model_copy(
        update={
            "adapter_kwargs": {
                "saknussemm:llm": {
                    "label": "llm",
                    "producer": "ollama",
                    "model": "m",
                    "host": "http://127.0.0.1:9",
                }
            }
        }
    )
    result = execute(run_spec, registry_with(_Lines()))
    (unit,) = result.usage
    assert str(unit.outcome) == "partial", (
        f"repli total : issue {unit.outcome!r}, message {unit.message!r}, "
        f"CER noté {per_document(result, 'p', 'd').value}"
    )
    d = per_document(result, "p", "d")
    assert axes(d)[2] == "partial_output"
    assert d.value is None


def test_a2_not_transcribed__distinct_dune_reference_vide(tmp_path: Path) -> None:
    """A2, M1 (P7) : une page **non transcrite** (VT vide parce que personne ne
    l'a saisie, déclarée ``not_transcribed`` par l'importeur) et une page
    **blanche** (VT vide parce qu'il n'y a rien à lire) ont aujourd'hui la même
    représentation. Contrat : la première est hors des attendus, sans
    statistique ; la seconde est applicable, et ses 5 caractères inventés
    entrent au micro. Attendus : 2 ; micro = 5/10."""
    base = corpus(tmp_path, {"a": REF, "blank": "", "nt": ""})
    nt = base.documents[2]
    documents = (
        *base.documents[:2],
        nt.model_copy(
            update={"ground_truths": (reference_non_transcrite(nt.ground_truths[0]),)}
        ),
    )
    result = execute(
        spec(
            CorpusSpec(name="ce", documents=documents),
            [pipeline("p", step("ocr", "ce_ocr"))],
            [text_view()],
        ),
        registry_with(
            TextBrick("ce_ocr", fixed({"a": REF, "blank": "hello", "nt": "hello"}))
        ),
    )
    unread = per_document(result, "p", "nt")
    assert axes(unread)[0] == "not_transcribed"
    assert statistique(unread) is None
    blank = per_document(result, "p", "blank")
    assert axes(blank) == ("applicable", "available", "valid")
    assert composante(blank, "insertions") == 5
    agg = aggregate(result, "p")
    assert (agg.value, agg.expected) == pytest.approx((0.5, 2))


# --------------------------------------------------------------------------
# A4 : macro sur D^M fixé par la référence ; invention hors référence.
# --------------------------------------------------------------------------


def _hallucination_bench(tmp_path: Path) -> Bench:
    """d1 : 5 entités, A et B parfaits ; d2 : aucune entité de référence, A en
    invente 5, B se tait (comptes (tp, fp, fn) de la revue)."""
    bench = Bench(tmp_path, gt_type=ArtifactType.ENTITIES)
    t1 = "Anne Paul Marc Jean Lise"
    spans = [("PER", 5 * i, 5 * i + 4) for i in range(5)]
    bench.document("d1", entities_json(t1, spans))
    t2 = "a b c d e f g h i j"
    bench.document("d2", entities_json(t2, []))
    for name in ("A", "B"):
        bench.output(name, "d1", entities_json(t1, spans))
    bench.output(
        "A", "d2", entities_json(t2, [("PER", 2 * i, 2 * i + 1) for i in range(5)])
    )
    bench.output("B", "d2", entities_json(t2, []))
    return bench


def test_k2_support_macro_depend_du_pipeline__fixe_par_la_reference(
    tmp_path: Path,
) -> None:
    """``k2_support_macro_depend_du_pipeline.py`` (A4, R5) : si D^M dépendait du
    scalaire de chaque pipeline, le document sans référence serait « défini »
    (F1 = 0) pour A qui invente et « indéfini » pour B qui se tait, et
    l'intersection retirerait exactement le document où ils diffèrent. Contrat :
    D^M = {d : tp + fn > 0} = {d1}, le même pour A et B."""
    result = _hallucination_bench(tmp_path).run(view(["ner_f1"], ArtifactType.ENTITIES))
    supports = {
        name: support_macro(bench_aggregate(result, name, "ner_f1"))
        for name in ("A", "B")
    }
    assert supports == {"A": 1, "B": 1}
    ab = paire(comparaison(result, "v", "ner_f1"), "A", "B")
    assert tuple(ab.macro_documents) == ("d1",)


def test_r2_r5_support_reference__le_macro_ne_voit_pas_linvention_le_micro_si(
    tmp_path: Path,
) -> None:
    """``r2_r5_support_reference.py`` (A4, N3) : sur D^M = {d1}, le macro de A
    et celui de B valent 1 — le macro ne voit pas l'invention d'un document
    sans référence, et le contrat le dit. Le micro la voit : A = F1(5, 5, 0) =
    2/3, B = 1."""
    result = _hallucination_bench(tmp_path).run(view(["ner_f1"], ArtifactType.ENTITIES))
    a, b = (bench_aggregate(result, name, "ner_f1") for name in ("A", "B"))
    assert (a.value, b.value) == pytest.approx((prf_f1(5, 5, 0), 1.0)), (
        f"micro A = {a.value}, B = {b.value}"
    )
    assert (macro(a), macro(b)) == (pytest.approx(1.0), pytest.approx(1.0))


def _blank_pages_bench(tmp_path: Path) -> Bench:
    """Une page de texte, lue parfaitement par A et B ; quatre pages blanches :
    A échoue sur b1-b3 et rend b4 vide ; B lit les quatre, invente « yy » sur b1."""
    bench = Bench(tmp_path)
    bench.document("t", REF)
    for name in ("A", "B"):
        bench.output(name, "t", REF)
    for page in ("b1", "b2", "b3", "b4"):
        bench.document(page, "")
        bench.output("B", page, "yy" if page == "b1" else "")
    for page in ("b1", "b2", "b3"):
        bench.fail("A", page)
    bench.output("A", "b4", "")
    return bench


def test_r3_invention_hors_reference__support_apparie_et_couverture(
    tmp_path: Path,
) -> None:
    """``r3_invention_hors_reference.py`` (A4, C5) : publiée par pipeline sur son
    support conditionnel, l'analyse ferait paraître A (qui échoue sur 3 pages
    blanches sur 4) plus propre que B. Contrat : elle est calculée sur le
    support apparié (b4 seule), où A et B ont la même valeur (0 caractère
    inventé), avec la couverture des pages sans référence par pipeline (A 1/4,
    B 4/4). Son unité est déclarée par famille : définie pour le CER (les
    insertions), « non définie » (``None``) pour ``searchability``, dont la
    statistique ne compte aucune unité de l'hypothèse."""
    bench = _blank_pages_bench(tmp_path)
    payload = invention(bench.run(view(["cer"])), "v", "cer")
    assert payload.unit is not None
    pair = paire(payload, "A", "B")
    assert (tuple(pair.documents), dict(pair.invented)) == (("b4",), {"A": 0, "B": 0})
    assert {k: tuple(v) for k, v in payload.coverage.items()} == {
        "A": (1, 4),
        "B": (4, 4),
    }
    proportion = invention(bench.run(view(["searchability"])), "v", "searchability")
    assert proportion.unit is None


# --------------------------------------------------------------------------
# A6 : classement sur le support apparié, tri sur le support global.
# --------------------------------------------------------------------------


ERRORS: dict[str, dict[str, int | None]] = {
    "A": {"d1": 1, "d2": 5, "d3": None, "d4": 3},
    "B": {"d1": None, "d2": 2, "d3": 6, "d4": 3},
    "C": {"d1": 4, "d2": None, "d3": 1, "d4": 3},
}


def test_k2_ordres_apparies_intransitifs__seul_le_support_global_trie(
    tmp_path: Path,
) -> None:
    """``k2_ordres_apparies_intransitifs.py`` (A6, B7) : chaque paire, sur son
    propre support, donne B < A (d2, d4), C < B (d3, d4) et A < C (d1, d4) — un
    cycle. Aucun classement ne se compose de ces ordres ; le seul tri
    multi-pipelines est celui du support global (d4), où les trois valent 0,03."""
    bench = Bench(tmp_path)
    for document in ("d1", "d2", "d3", "d4"):
        bench.document(document, letters(100, seed=int(document[1])))
    for name, by_doc in ERRORS.items():
        for document, errors in by_doc.items():
            if errors is None:
                bench.fail(name, document)
            else:
                bench.output(
                    name,
                    document,
                    substitute(letters(100, seed=int(document[1])), errors),
                )
    payload = comparaison(bench.run(view(["cer"])), "v", "cer")
    expected = {
        ("A", "B"): (("d2", "d4"), {"A": 0.04, "B": 0.025}),
        ("B", "C"): (("d3", "d4"), {"B": 0.045, "C": 0.02}),
        ("A", "C"): (("d1", "d4"), {"A": 0.02, "C": 0.035}),
    }
    for (a, b), (documents, values) in expected.items():
        pair = paire(payload, a, b)
        assert tuple(pair.micro_documents) == documents
        assert dict(pair.micro) == pytest.approx(values)
    family = support_global(payload)
    assert tuple(family.micro_documents) == ("d4",)
    assert dict(family.micro) == pytest.approx({"A": 0.03, "B": 0.03, "C": 0.03})
    ranked = [family.micro[name] for name in family.ranking]
    assert set(family.ranking) == {"A", "B", "C"} and ranked == sorted(ranked)


# --------------------------------------------------------------------------
# B3 : grappes, population cible et pondération déclarées.
# --------------------------------------------------------------------------


def _clustered_run(tmp_path: Path, weighting: str) -> RunResult:
    """Manuscrit m1 : trois pages à CER 0,1 ; manuscrit m2 : une page à 0,5."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    pages = {"m1a": "m1", "m1b": "m1", "m1c": "m1", "m2a": "m2"}
    base = corpus(tmp_path, dict.fromkeys(pages, REF))
    declared = corpus_declare(
        CorpusSpec(
            name="ce",
            documents=tuple(document_en_grappe(d, pages[d.id]) for d in base.documents),
        ),
        target_population="pages de deux manuscrits",
        cluster_weighting=weighting,
    )
    outputs = {d: substitute(REF, 5 if d == "m2a" else 1) for d in pages}
    return execute(
        spec(declared, [pipeline("p", step("ocr", "ce_ocr"))], [text_view()]),
        registry_with(TextBrick("ce_ocr", fixed(outputs))),
    )


def test_b3_grappes__population_et_ponderation_publiees(tmp_path: Path) -> None:
    """B3 (§ 2.1 c) : les grappes sont déclarées par le corpus, avec la
    population cible et la pondération des grappes, publiées avec l'agrégat.
    Le micro (8/40 = 0,2) ne dépend pas de la pondération ; le macro si :
    par grappe (0,1 + 0,5)/2 = 0,3, par document (3 × 0,1 + 0,5)/4 = 0,2."""
    by_cluster = _clustered_run(tmp_path / "grappe", "cluster")
    by_document = _clustered_run(tmp_path / "document", "document")
    for result, weighting, expected_macro in (
        (by_cluster, "cluster", 0.3),
        (by_document, "document", 0.2),
    ):
        (entry,) = result.pipelines
        assert publication_grappes(entry) == ("pages de deux manuscrits", weighting)
        agg = aggregate(result, "p")
        assert agg.value == pytest.approx(0.2)
        assert macro(agg) == pytest.approx(expected_macro)


# --------------------------------------------------------------------------
# Propriétés P de A1 et A2.
# --------------------------------------------------------------------------


@st.composite
def corpus_states(
    draw: st.DrawFn, states: tuple[str, ...]
) -> list[tuple[str, int, int]]:
    """Documents (état, longueur de référence, erreurs) ; références non vides
    sauf pour l'état ``blank``."""
    return [
        (
            draw(st.sampled_from(states)),
            draw(st.integers(4, 12)),
            draw(st.integers(0, 3)),
        )
        for _ in range(draw(st.integers(1, 5)))
    ]


def _texts(i: int, state: str, length: int, errors: int) -> tuple[str, str]:
    """(référence, sortie) du document ``d{i}`` : la sortie tronquée est la
    première moitié de la sortie complète ; une page blanche reçoit « xy »."""
    ref = letters(length, seed=i)
    hyp = substitute(ref, errors)
    if state == "blank":
        return "", "xy"
    if state == "truncated":
        return ref, hyp[: length // 2]
    return ref, hyp


def _bench_from_states(root: Path, documents: list[tuple[str, int, int]]) -> Bench:
    bench = Bench(root)
    for i, (state, length, errors) in enumerate(documents):
        doc = f"d{i}"
        ref, hyp = _texts(i, state, length, errors)
        if state == "no_gt":
            bench.documents.append(DocumentRef(id=doc))
            bench.output("p", doc, hyp)
            continue
        bench.document(doc, ref)
        if state == "failed":
            bench.fail("p", doc)
        elif state == "truncated":
            bench.truncate("p", doc, hyp)
        else:
            bench.output("p", doc, hyp)
    return bench


@DETERMINISTE
@given(corpus_states(("ok", "failed", "truncated")))
def test_propriete_a1__agregat_conditionnel_et_couverture(
    documents: list[tuple[str, int, int]],
) -> None:
    """P (A1, A7) : pour tout corpus, l'agrégat conditionnel par défaut est le
    micro des seules observations complètes ; aucune part manquante (échec,
    troncature) n'y est notée ; la couverture compte chaque attendu non mesuré
    sous son motif. Sous ``empty_page``, l'échec vaut une page vide (toute la
    référence en suppressions) et la sortie tronquée est notée telle quelle."""
    with tempfile.TemporaryDirectory() as tmp:
        bench = _bench_from_states(Path(tmp), documents)
        result = bench.run(view(["cer"]))
        _assert_conditional(result, documents)
        sensible = bench.run(view(["cer"]), failure_policy=politique_empty_page())
    texts = [_texts(i, *doc) for i, doc in enumerate(documents)]
    # empty_page : un échec est une hypothèse vide ; une sortie tronquée est
    # notée telle quelle (sa fin manquante compte en suppressions).
    expected_sensible = sum(
        levenshtein(ref, "" if state == "failed" else hyp)
        for (state, _, _), (ref, hyp) in zip(documents, texts, strict=True)
    ) / sum(len(ref) for ref, _ in texts)
    assert bench_aggregate(sensible, "p", "cer").value == pytest.approx(
        expected_sensible
    )


def _assert_conditional(
    result: RunResult, documents: list[tuple[str, int, int]]
) -> None:
    """Défaut (A1) : micro des observations complètes, couverture par motif."""
    texts = [_texts(i, *doc) for i, doc in enumerate(documents)]
    complete = [
        (ref, hyp)
        for (state, _, _), (ref, hyp) in zip(documents, texts, strict=True)
        if state == "ok"
    ]
    oracle = (
        sum(levenshtein(r, h) for r, h in complete) / sum(len(r) for r, _ in complete)
        if complete
        else None
    )
    agg = bench_aggregate(result, "p", "cer")
    assert agg.value == (pytest.approx(oracle) if oracle is not None else None), (
        f"agrégat par défaut {agg.value}, micro des observations complètes {oracle}"
    )
    counts = {
        motif: n
        for motif, n in (
            ("step_failed", sum(s == "failed" for s, _, _ in documents)),
            ("truncated_output", sum(s == "truncated" for s, _, _ in documents)),
        )
        if n
    }
    assert (support_micro(agg), agg.expected) == (len(complete), len(documents))
    assert couverture(agg) == counts


@DETERMINISTE
@given(corpus_states(("ok", "failed", "truncated", "no_gt", "blank")))
def test_propriete_a2__quatre_axes(documents: list[tuple[str, int, int]]) -> None:
    """P (A2) : pour tout corpus, attendus = applicables ; une référence absente
    est ``no_ground_truth`` ; un échec est ``step_failed`` ; une troncature est
    ``truncated_output`` ; une page blanche est applicable, disponible, valide,
    de scalaire indéfini ; et la statistique est présente si et seulement si
    les axes 1 à 3 sont au vert."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _bench_from_states(Path(tmp), documents).run(view(["cer"]))
    applicable = sum(state != "no_gt" for state, _, _ in documents)
    assert bench_aggregate(result, "p", "cer").expected == applicable
    green = ("applicable", "available", "valid")
    for i, (state, _, _) in enumerate(documents):
        score = observation(result, "p", f"d{i}", "cer")
        applicability, availability, validity = axes(score)
        expected = {
            "ok": green,
            "blank": green,
            "no_gt": ("no_ground_truth", applicability, validity),
            "failed": ("applicable", "step_failed", validity),
            "truncated": ("applicable", "available", "truncated_output"),
        }[state]
        assert (applicability, availability, validity) == expected, (state, score)
        assert (statistique(score) is not None) == (
            (applicability, availability, validity) == green
        )
        if state == "blank":
            assert score.value is None

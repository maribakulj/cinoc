"""Affirmation 2 — applicabilité : chaque « non-mesure » est-elle distinguée,
et « n attendus » résiste-t-il à une unité **réussie** qui ne fournit pas ce que
la vue exige ?

Contre-exemples construits par l'API publique (briques tierces branchées par
``discover_plugins``, run par ``cinoc.app.run``). Références indépendantes :
distance d'édition écrite à la main, ``scipy.stats.wilcoxon``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from scipy import stats

from cinoc.adapters.extension import (
    AdapterStepError,
    ArtifactType,
    CanonicalLayout,
    RunContext,
    RunControl,
    StepOutput,
    layout_step_output,
)
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.layout import LayoutPage, Line, Region
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.evaluation.analysis import InferencePayload

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

REF = "abcdefghij"


def _inference(result, view: str = "texte", metric: str = "cer") -> InferencePayload:  # type: ignore[no-untyped-def]
    (payload,) = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, InferencePayload)
        and a.view == view
        and a.payload.metric == metric
    ]
    return payload


# --------------------------------------------------------------------------
# Repères : ce qui est déjà bien distingué (doivent rester verts).
# --------------------------------------------------------------------------


def test_gt_absente__ni_notee_ni_attendue(tmp_path: Path) -> None:
    """Un document sans vérité terrain, moteur réussi : ``None``, hors de « n
    notés » **et** de « n attendus » (la métrique ne le couvre pas)."""
    brick = TextBrick("ce_ocr", fixed({"a": REF, "b": "xyz"}))
    result = execute(
        spec(corpus(tmp_path, {"a": REF, "b": None}), [pipeline("p", step("ocr", "ce_ocr"))],
             [text_view()]),
        registry_with(brick),
    )
    assert per_document(result, "p", "b").value is None
    agg = aggregate(result, "p")
    assert (agg.value, agg.support, agg.expected) == (0.0, 1, 1)


def test_troncature__notee_attendue_et_signalee(tmp_path: Path) -> None:
    """Une sortie coupée par ``max_tokens`` reste une sortie : elle est notée
    (CER calculé à la main), comptée dans « n attendus », et l'unité dit
    ``truncated``."""
    brick = TextBrick(
        "ce_llm", fixed({"a": REF, "b": "abcde"}), truncate=frozenset({"b"})
    )
    result = execute(
        spec(corpus(tmp_path, {"a": REF, "b": REF}), [pipeline("p", step("ocr", "ce_llm"))],
             [text_view()]),
        registry_with(brick),
    )
    outcomes = {u.document_id: u.outcome for u in result.usage}
    assert outcomes == {"a": "ok", "b": "truncated"}
    assert per_document(result, "p", "b").value == pytest.approx(
        levenshtein(REF, "abcde") / len(REF)
    )
    agg = aggregate(result, "p")
    assert (agg.support, agg.expected) == (2, 2)


# --------------------------------------------------------------------------
# Unité réussie qui ne fournit pas l'information : « n attendus » doit tenir.
# --------------------------------------------------------------------------


@pytest.mark.valide
def test_applicabilite__artefact_sans_contenu_dune_unite_reussie_reste_attendu(
    tmp_path: Path,
) -> None:
    """Moteur réussi dont l'artefact déclaré arrive sans contenu (``uri=None``)
    sur ``b`` : le document a une GT, il doit rester dans « n attendus » (ou
    l'unité ne pas être « ok »), sinon la moyenne perd ``b`` sans le dire."""
    brick = TextBrick(
        "ce_ocr", fixed({"a": REF, "b": "zzzz", "c": REF}), inline=frozenset({"b"})
    )
    result = execute(
        spec(corpus(tmp_path, {"a": REF, "b": REF, "c": REF}),
             [pipeline("p", step("ocr", "ce_ocr"))], [text_view()]),
        registry_with(brick),
    )
    agg = aggregate(result, "p")
    outcome_b = next(u.outcome for u in result.usage if u.document_id == "b")
    assert agg.expected == 3 or outcome_b != "ok", (
        f"n notés/n attendus = {agg.support}/{agg.expected}, issue de b = "
        f"{outcome_b!r}, CER affiché = {agg.value}"
    )


@pytest.mark.valide
def test_applicabilite__artefact_reference_mais_absent_du_disque_nabat_que_son_unite(
    tmp_path: Path,
) -> None:
    """Le moteur ``p`` rend pour ``b`` une URI vers un fichier jamais écrit : seule
    cette unité doit en pâtir ; le run et le pipeline ``q`` doivent être notés."""
    bad = TextBrick("ce_bad", fixed({"a": REF, "b": REF}), dangling=frozenset({"b"}))
    good = TextBrick("ce_good", fixed({"a": REF, "b": REF}))
    run_spec = spec(
        corpus(tmp_path, {"a": REF, "b": REF}),
        [pipeline("p", step("ocr", "ce_bad")), pipeline("q", step("ocr", "ce_good"))],
        [text_view()],
    )
    try:
        result = execute(run_spec, registry_with(bad, good))
    except CinocError as exc:
        pytest.fail(
            f"tout le run est perdu (moteurs déjà exécutés : {bad.calls + good.calls})"
            f" : {type(exc).__name__}: {exc}"
        )
    assert aggregate(result, "q").support == 2
    assert aggregate(result, "p").expected == 2


@pytest.mark.discutable("C13-non-mesure-typee")
def test_applicabilite__gt_referencee_mais_absente_refusee_avant_de_payer(
    tmp_path: Path,
) -> None:
    """La GT de ``b`` est déclarée mais le fichier n'existe pas : le run doit
    soit le refuser **avant** d'exécuter un moteur, soit noter le reste ; jamais
    exécuter (et facturer) tout le corpus puis s'effondrer à l'évaluation."""
    brick = TextBrick("ce_ocr", fixed({"a": REF, "b": REF}))
    base = corpus(tmp_path, {"a": REF, "b": REF})
    documents = (
        base.documents[0],
        base.documents[1].model_copy(
            update={
                "ground_truths": (
                    GroundTruthRef(type=T.RAW_TEXT, uri=str(tmp_path / "absente.gt.txt")),
                )
            }
        ),
    )
    run_spec = spec(
        CorpusSpec(name="ce", documents=documents),
        [pipeline("p", step("ocr", "ce_ocr"))],
        [text_view()],
    )
    try:
        result = execute(run_spec, registry_with(brick))
    except CinocError as exc:
        assert brick.calls == [], (
            f"refus **après** exécution de {brick.calls} : {type(exc).__name__}: {exc}"
        )
        return
    assert aggregate(result, "p").support == 1


# --------------------------------------------------------------------------
# Fan-out : toutes les régions en échec, unité « ok ».
# --------------------------------------------------------------------------


class _Segmenter:
    """Segmenteur tiers : deux régions sans texte (``IMAGE → LAYOUT``)."""

    name = "ce_seg"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.LAYOUT})

    def execute(
        self,
        inputs: object,
        params: object,
        context: RunContext,
        control: RunControl,
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


def _fanout_run(tmp_path: Path):  # type: ignore[no-untyped-def]
    """``ok`` : la reconnaissance rend du texte faux ; ``panne`` : elle lève sur
    chaque région (API tombée). GT : deux régions de texte sur chaque page."""
    gt_layout = CanonicalLayout(
        pages=(
            LayoutPage(
                regions=(
                    Region(id="r1", lines=(Line(text="hello world"),)),
                    Region(id="r2", lines=(Line(text="second block"),)),
                ),
            ),
        )
    )
    documents = []
    for document_id in ("ok", "panne"):
        (tmp_path / f"{document_id}.png").write_bytes(b"\x89PNG stub")
        gt = tmp_path / f"{document_id}.gt.layout.json"
        gt.write_bytes(gt_layout.model_dump_json().encode("utf-8"))
        documents.append(
            DocumentRef(
                id=document_id,
                image_uri=str(tmp_path / f"{document_id}.png"),
                ground_truths=(GroundTruthRef(type=T.LAYOUT, uri=str(gt)),),
            )
        )

    def recognize(document_id: str) -> str | AdapterStepError:
        if document_id == "panne":
            return AdapterStepError("503 Service Unavailable")
        return "xx"

    recognizer = TextBrick("ce_reco", recognize)
    seg_pipeline = PipelineSpec(
        name="hybride",
        initial_inputs=(T.IMAGE,),
        steps=(
            PipelineStep(
                id="segment", kind="segmentation", adapter_name="ce_seg",
                input_types=(T.IMAGE,), output_types=(T.LAYOUT,),
            ),
            PipelineStep(
                id="recognize", kind="recognition", adapter_name="ce_reco",
                input_types=(T.LAYOUT, T.IMAGE), output_types=(T.LAYOUT,),
                inputs_from={T.LAYOUT: "segment"}, fanout=True,
            ),
        ),
    )
    view = EvaluationView(
        name="structure",
        candidate_types=frozenset({T.LAYOUT}),
        metric_names=("region_cer",),
    )
    return execute(
        spec(CorpusSpec(name="ce", documents=tuple(documents)), [seg_pipeline], [view]),
        registry_with(_Segmenter(), recognizer),
    )


@pytest.mark.discutable("C13-non-mesure-typee")
def test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu(
    tmp_path: Path,
) -> None:
    """Toutes les régions de ``panne`` échouent : la page n'a aucun texte alors
    que sa GT en a. ``region_cer`` doit compter la page (CER 1, ou « n attendus »
    = 2), pas la déclarer non applicable — sinon perdre tout le texte améliore
    le score par rapport à en rendre un mauvais."""
    result = _fanout_run(tmp_path)
    agg = aggregate(result, "hybride", "region_cer", view="structure")
    panne = per_document(result, "hybride", "panne", "region_cer", view="structure")
    assert agg.expected == 2, (
        f"region_cer panne = {panne.value}, agrégat {agg.value} sur "
        f"{agg.support}/{agg.expected}"
    )


@pytest.mark.valide
def test_applicabilite__fanout_entierement_en_echec_nest_pas_une_unite_ok(
    tmp_path: Path,
) -> None:
    """Le reconnaisseur a levé sur **toutes** les régions de ``panne`` : l'issue
    de l'unité doit le dire (``failed`` ou au moins un message), pas ``ok``."""
    result = _fanout_run(tmp_path)
    unit = next(u for u in result.usage if u.document_id == "panne")
    assert unit.outcome != "ok" or unit.message, (
        f"issue {unit.outcome!r}, message {unit.message!r}"
    )


# --------------------------------------------------------------------------
# Pipeline non applicable et tests statistiques.
# --------------------------------------------------------------------------


def _paired_corpus(tmp_path: Path, n: int = 8) -> tuple[dict[str, str | None], dict[str, str], dict[str, str]]:
    """``A`` : 1 erreur par page ; ``B`` : 2..n+1 erreurs (écarts tous distincts)."""
    refs: dict[str, str | None] = {}
    a: dict[str, str] = {}
    b: dict[str, str] = {}
    for i in range(n):
        doc = f"d{i}"
        reference = "abcdefghijklmnopqrst"  # 20 caractères
        refs[doc] = reference
        a[doc] = "X" + reference[1:]
        b[doc] = "X" * (i + 2) + reference[i + 2 :]
    return refs, a, b


@pytest.mark.valide
def test_applicabilite__pipeline_non_applicable_nannule_pas_le_test_des_autres(
    tmp_path: Path,
) -> None:
    """``A`` et ``B`` notés sur 8 pages, ``C`` ne produit que du texte corrigé
    (aucun type candidat de la vue texte). Le test apparié A/B doit être celui
    de ``scipy.stats.wilcoxon`` sur leurs 8 CER ; ``C`` ne doit pas le supprimer."""
    refs, a, b = _paired_corpus(tmp_path)
    bricks = (
        TextBrick("ce_a", fixed(a)),
        TextBrick("ce_b", fixed(b)),
        TextBrick("ce_c", fixed(a), out_type=T.CORRECTED_TEXT),
    )
    result = execute(
        spec(
            corpus(tmp_path, refs),
            [
                pipeline("A", step("ocr", "ce_a")),
                pipeline("B", step("ocr", "ce_b")),
                pipeline("C", step("ocr", "ce_c", out_type=T.CORRECTED_TEXT)),
            ],
            [text_view()],
        ),
        registry_with(*bricks),
    )
    assert aggregate(result, "C").support == 0  # C est bien non applicable
    cer_a = [levenshtein(refs[d] or "", a[d]) / 20 for d in sorted(a)]
    cer_b = [levenshtein(refs[d] or "", b[d]) / 20 for d in sorted(b)]
    oracle = stats.wilcoxon(cer_a, cer_b).pvalue
    payload = _inference(result)
    assert (payload.test, payload.p_value) == ("wilcoxon", pytest.approx(oracle)), (
        f"test={payload.test!r}, motif={payload.not_computed!r}, "
        f"n cas complets={payload.n_documents}, p oracle={oracle:.4f}"
    )


def _blank_pages_run(tmp_path: Path):  # type: ignore[no-untyped-def]
    """6 pages de texte où ``A`` fait moins d'erreurs que ``B`` ; 6 pages
    blanches (GT vide) où ``A`` rend un bruit d'un caractère et ``B`` rien."""
    refs: dict[str, str | None] = {}
    a: dict[str, str] = {}
    b: dict[str, str] = {}
    reference = "abcdefghijklmnopqrst"
    for i in range(6):
        doc = f"t{i}"
        refs[doc] = reference
        a[doc] = "X" + reference[1:]
        b[doc] = "X" * (i + 2) + reference[i + 2 :]
    for i in range(6):
        doc = f"v{i}"
        refs[doc] = ""
        a[doc] = "."
        b[doc] = ""
    result = execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view()],
        ),
        registry_with(TextBrick("ce_a", fixed(a)), TextBrick("ce_b", fixed(b))),
    )
    cer_a = [levenshtein(reference, a[f"t{i}"]) / 20 for i in range(6)]
    cer_b = [levenshtein(reference, b[f"t{i}"]) / 20 for i in range(6)]
    return result, cer_a, cer_b


@pytest.mark.valide
def test_applicabilite__reference_vide_nest_pas_comptee_notee(tmp_path: Path) -> None:
    """Une page blanche (GT vide) ne pèse rien dans l'agrégat micro ; elle ne
    doit donc pas gonfler « n notés » : 6 pages notées, pas 12."""
    result, cer_a, _ = _blank_pages_run(tmp_path)
    agg = aggregate(result, "A")
    assert agg.value == pytest.approx(sum(cer_a) / 6)  # l'agrégat ignore les blanches
    assert agg.support == 6, f"n notés = {agg.support} pour un agrégat sur 6 pages"


@pytest.mark.discutable("C01-reference-vide")
def test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie(
    tmp_path: Path,
) -> None:
    """Le CER d'une GT vide est indéfini (0/0 ou x/0) ; le Wilcoxon A/B doit être
    celui de ``scipy`` sur les 6 pages de texte, pas sur 12 valeurs dont 6
    fabriquées (1,0 contre 0,0)."""
    result, cer_a, cer_b = _blank_pages_run(tmp_path)
    oracle = stats.wilcoxon(cer_a, cer_b).pvalue
    payload = _inference(result)
    assert payload.n_documents == 6 and payload.p_value == pytest.approx(oracle), (
        f"n cas complets={payload.n_documents}, p={payload.p_value}, "
        f"p oracle (6 pages)={oracle:.4f}"
    )


@pytest.mark.valide
def test_applicabilite__sortie_incompatible_refusee_ou_attendue(tmp_path: Path) -> None:
    """La vue accepte ``raw_text`` **et** ``layout`` mais note un CER texte sans
    projection ``layout → raw_text`` : le pipeline ``seg`` (réussi, sortie
    ``layout``) ne peut pas être noté. Cela doit être refusé au chargement, ou
    compté dans « n attendus » — pas rendu 0/0 comme un pipeline hors sujet."""
    view = text_view(candidates=(T.RAW_TEXT, T.LAYOUT))
    documents = corpus(tmp_path, {"a": REF, "b": REF})
    pipelines = [
        pipeline("ocr", step("ocr", "ce_ocr")),
        PipelineSpec(
            name="seg",
            initial_inputs=(T.IMAGE,),
            steps=(
                PipelineStep(
                    id="segment", kind="segmentation", adapter_name="ce_seg",
                    input_types=(T.IMAGE,), output_types=(T.LAYOUT,),
                ),
            ),
        ),
    ]
    try:
        run_spec = spec(documents, pipelines, [view])
    except CinocError:
        return  # refus au chargement : comportement attendu
    result = execute(
        run_spec,
        registry_with(TextBrick("ce_ocr", fixed({"a": REF, "b": REF})), _Segmenter()),
    )
    agg = aggregate(result, "seg")
    assert agg.expected == 2, (
        f"pipeline seg : {agg.value} sur {agg.support}/{agg.expected}, "
        f"issues {[u.outcome for u in result.usage if u.pipeline == 'seg']}"
    )

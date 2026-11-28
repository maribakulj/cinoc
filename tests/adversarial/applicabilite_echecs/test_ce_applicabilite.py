"""Affirmation 2 — applicabilité : chaque « non-mesure » est-elle distinguée,
et « n attendus » résiste-t-il à une unité **réussie** qui ne fournit pas ce que
la vue exige ?

Importé de la contre-expertise (``applicabilite_echecs/test_ce_applicabilite.py``,
commit ``04a1c17b``) : seuls les tests que ``CONTRATS.md`` § 4.1 range en
tranche 1b. Les valides sont tels quels, deux sont reformulés (supports), les
discutables suivent les arbitrages ; la troncature, verte à ``04a1c17b``, est
inversée (R6 : exclue par défaut, notée sous ``empty_page``).

Contre-exemples construits par l'API publique (briques tierces branchées par
``discover_plugins``, run par ``cinoc.app.run``). Référence indépendante :
distance d'édition écrite à la main.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

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
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import (
    axes,
    comparaison,
    paire,
    politique_empty_page,
    support_macro,
    support_micro,
)

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


def _inference(
    result: RunResult, view: str = "texte", metric: str = "cer"
) -> InferencePayload:
    (payload,) = [
        a.payload
        for a in result.analyses
        if isinstance(a.payload, InferencePayload)
        and a.view == view
        and a.payload.metric == metric
    ]
    return payload


# --------------------------------------------------------------------------
# Troncature (R6) : inversée.
# --------------------------------------------------------------------------


def _truncated_run(tmp_path: Path, **evaluation: object) -> RunResult:
    tmp_path.mkdir(parents=True, exist_ok=True)
    brick = TextBrick(
        "ce_llm", fixed({"a": REF, "b": "abcde"}), truncate=frozenset({"b"})
    )
    return execute(
        spec(
            corpus(tmp_path, {"a": REF, "b": REF}),
            [pipeline("p", step("ocr", "ce_llm"))],
            [text_view()],
            **evaluation,
        ),
        registry_with(brick),
    )


def test_troncature__exclue_par_defaut_notee_sous_empty_page(tmp_path: Path) -> None:
    """Inverse ``test_troncature__notee_attendue_et_signalee`` (vert à
    ``04a1c17b``, qui figeait R6). Une sortie coupée par ``max_tokens`` porte
    ``truncated_output`` à l'axe 3 : par défaut elle n'est **pas** notée (1
    mesuré sur 2 attendus), sa fin manquante n'est pas imputée en silence. Sous
    la sensibilité ``empty_page``, la fin manquante est notée vide : CER de
    ``b`` = 5/10 (calculé à la main), sous ce nom."""
    result = _truncated_run(tmp_path / "defaut")
    outcomes = {u.document_id: u.outcome for u in result.usage}
    assert outcomes == {"a": "ok", "b": "truncated"}
    b = per_document(result, "p", "b")
    assert b.value is None, f"fin tronquée notée par défaut : CER {b.value}"
    assert axes(b)[2] == "truncated_output"
    agg = aggregate(result, "p")
    assert (support_micro(agg), agg.expected) == (1, 2)
    sensible = _truncated_run(
        tmp_path / "sensible", failure_policy=politique_empty_page()
    )
    assert per_document(sensible, "p", "b").value == pytest.approx(
        levenshtein(REF, "abcde") / len(REF)
    )
    assert str(sensible.manifest.failure_policy) == "empty_page"


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
        spec(
            corpus(tmp_path, {"a": REF, "b": REF, "c": REF}),
            [pipeline("p", step("ocr", "ce_ocr"))],
            [text_view()],
        ),
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
    """La GT de ``b`` est déclarée mais le fichier n'existe pas. Reformulé (F8,
    § 2.1 e : validation avant exécution) : le run est **refusé**, par une
    erreur typée, **avant** le premier appel de moteur — jamais exécuté et
    facturé sur tout le corpus pour s'effondrer à l'évaluation."""
    brick = TextBrick("ce_ocr", fixed({"a": REF, "b": REF}))
    base = corpus(tmp_path, {"a": REF, "b": REF})
    documents = (
        base.documents[0],
        base.documents[1].model_copy(
            update={
                "ground_truths": (
                    GroundTruthRef(
                        type=T.RAW_TEXT, uri=str(tmp_path / "absente.gt.txt")
                    ),
                )
            }
        ),
    )
    run_spec = spec(
        CorpusSpec(name="ce", documents=documents),
        [pipeline("p", step("ocr", "ce_ocr"))],
        [text_view()],
    )
    with pytest.raises(CinocError):
        execute(run_spec, registry_with(brick))
    assert brick.calls == [], f"refus **après** exécution de {brick.calls}"


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


def _fanout_run(tmp_path: Path, **evaluation: Any) -> RunResult:
    """``ok`` : la reconnaissance rend du texte faux ; ``panne`` : elle lève sur
    chaque région (API tombée). GT : deux régions de texte sur chaque page."""
    tmp_path.mkdir(parents=True, exist_ok=True)
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
                id="segment",
                kind="segmentation",
                adapter_name="ce_seg",
                input_types=(T.IMAGE,),
                output_types=(T.LAYOUT,),
            ),
            PipelineStep(
                id="recognize",
                kind="recognition",
                adapter_name="ce_reco",
                input_types=(T.LAYOUT, T.IMAGE),
                output_types=(T.LAYOUT,),
                inputs_from={T.LAYOUT: "segment"},
                fanout=True,
            ),
        ),
    )
    view = EvaluationView(
        name="structure",
        candidate_types=frozenset({T.LAYOUT}),
        metric_names=("region_cer",),
    )
    return execute(
        spec(
            CorpusSpec(name="ce", documents=tuple(documents)),
            [seg_pipeline],
            [view],
            **evaluation,
        ),
        registry_with(_Segmenter(), recognizer),
    )


@pytest.mark.discutable("C13-non-mesure-typee")
def test_applicabilite__fanout_sans_aucune_region_reconnue_reste_attendu(
    tmp_path: Path,
) -> None:
    """Toutes les régions de ``panne`` échouent : la page n'a aucun texte alors
    que sa GT en a. Reformulé (R6, A2, A7) : la page reste attendue (2
    attendus) ; elle porte ``partial_output`` à l'axe 3 et n'est pas notée par
    défaut ; sous ``empty_page`` elle vaut 1,0 (toute la référence en
    suppressions), sous ce nom."""
    result = _fanout_run(tmp_path / "defaut")
    agg = aggregate(result, "hybride", "region_cer", view="structure")
    panne = per_document(result, "hybride", "panne", "region_cer", view="structure")
    assert agg.expected == 2, (
        f"region_cer panne = {panne.value}, agrégat {agg.value} sur "
        f"{agg.support}/{agg.expected}"
    )
    assert axes(panne)[2] == "partial_output"
    assert panne.value is None
    sensible = _fanout_run(tmp_path / "sensible", failure_policy=politique_empty_page())
    assert per_document(
        sensible, "hybride", "panne", "region_cer", view="structure"
    ).value == pytest.approx(1.0)


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
# Pipeline non applicable et supports.
# --------------------------------------------------------------------------


def _paired_corpus(
    n: int = 8,
) -> tuple[dict[str, str | None], dict[str, str], dict[str, str]]:
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
    (aucun type candidat de la vue texte). Reformulé (support, A6) : ``C`` est
    non applicable (``not_in_view``) et ne change pas le support apparié de
    (A, B), qui compte les 8 documents. La p du test (0,0078 par scipy) relève
    de la tranche I."""
    refs, a, b = _paired_corpus()
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
    # C est non applicable (D1) : « hors vue » est une propriété du pipeline, et
    # un pipeline hors vue n'a aucune entrée d'agrégat dans cette vue.
    assert "C" not in {entry.pipeline for entry in result.pipelines}
    ab = paire(comparaison(result, "texte", "cer"), "A", "B")
    assert tuple(ab.micro_documents) == tuple(sorted(refs))
    assert axes(per_document(result, "C", "d0"))[0] == "not_in_view"


def _blank_pages_run(tmp_path: Path) -> tuple[RunResult, list[float], list[float]]:
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
    """Reformulé (T1, A1, A4) : une page blanche est applicable, disponible et
    valide, de scalaire indéfini ; elle contribue au micro. Micro de A =
    (6 substitutions + 6 insertions) / 120 = 0,100 ; 12 documents au support
    micro, 6 au support macro (les pages blanches sont hors de D^M)."""
    result, _, _ = _blank_pages_run(tmp_path)
    agg = aggregate(result, "A")
    assert agg.value == pytest.approx(12 / 120), f"micro de A = {agg.value}"
    assert (support_micro(agg), support_macro(agg)) == (12, 6)


@pytest.mark.discutable("C01-reference-vide")
def test_applicabilite__reference_vide_nentre_pas_dans_le_test_apparie(
    tmp_path: Path,
) -> None:
    """Partie support (1b) : le CER d'une GT vide est indéfini (x/0) ; les 6
    pages blanches sont hors de D^M, donc hors de toute analyse par document —
    l'analyse de rangs comprise (6 documents, pas 12 dont 6 valeurs fabriquées
    1,0 contre 0,0). La p (0,031 par scipy) relève de la tranche I."""
    result, _, _ = _blank_pages_run(tmp_path)
    texte = tuple(f"t{i}" for i in range(6))
    payload = _inference(result)
    assert payload.n_documents == 6, (
        f"analyse par document sur {payload.n_documents} documents, "
        "pages blanches comprises"
    )
    ab = paire(comparaison(result, "texte", "cer"), "A", "B")
    assert tuple(ab.macro_documents) == texte


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
                    id="segment",
                    kind="segmentation",
                    adapter_name="ce_seg",
                    input_types=(T.IMAGE,),
                    output_types=(T.LAYOUT,),
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

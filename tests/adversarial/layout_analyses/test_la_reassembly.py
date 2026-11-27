"""Contre-expertise — réassemblage par ordre de lecture (couches 3, 4, 5).

Le fan-out (couche 4) remplit les régions **sur place** et laisse
``reading_order`` intact ; le réassemblage effectif a lieu à la projection
``LAYOUT → texte``. Il en existe **deux** : ``evaluation/projectors.layout_to_text``
(couche 3, appliquée à la VT et aux candidats projetés par une vue) et
``adapters/layout/to_text.LayoutToTextExtractor`` (couche 5, étape ``projection``
des recettes). Contrat du domaine (``LayoutPage.reading_order``) : liste **plate**
d'identifiants, parcours profondeur d'abord côté PAGE — des régions imbriquées
peuvent donc y figurer.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.layout.to_text import LayoutToTextExtractor
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.layout import BBox, CanonicalLayout, Geometry, LayoutPage, Line, Region
from cinoc.evaluation.projectors import layout_to_text
from cinoc.pipeline.fanout import run_region_fanout
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.run import RunManifest
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
from cinoc.evaluation.runner import evaluate_run
from datetime import UTC, datetime

_T = datetime(2026, 1, 1, tzinfo=UTC)


def _leaf(rid: str, text: str | None, x: int = 0) -> Region:
    return Region(
        id=rid,
        geometry=Geometry(bbox=BBox(x=x, y=0, width=40, height=40)),
        lines=(Line(id=f"{rid}.l1", text=text),) if text is not None else (),
    )


def _composed_page() -> CanonicalLayout:
    """Bloc composé C {c1 « alpha », c2 « beta »}, ordre de lecture plat c2 → c1."""
    composed = Region(
        id="C", region_type="composed", regions=(_leaf("c1", "alpha"), _leaf("c2", "beta", 50))
    )
    return CanonicalLayout(
        pages=(LayoutPage(width=100, height=100, regions=(composed,), reading_order=("c2", "c1")),)
    )


def _extract(tmp_path: Path, layout: CanonicalLayout) -> str:
    src = tmp_path / "layout.json"
    src.write_text(layout.model_dump_json(), encoding="utf-8")
    out = LayoutToTextExtractor("t").execute(
        {ArtifactType.LAYOUT: Artifact(id="d:l", document_id="d", type=ArtifactType.LAYOUT, uri=str(src))},
        {},
        RunContext(document_id="d", code_version="0", pipeline_name="p", workspace_uri=str(tmp_path)),
        RunControl(),
    )
    return Path(out.artifacts[ArtifactType.RAW_TEXT].uri or "").read_text(encoding="utf-8")


def test_ordre_de_lecture_imbrique__la_projection_d_evaluation_le_respecte() -> None:
    """Ordre plat c2 → c1 sur des régions imbriquées : la projection de couche 3
    (celle qu'on applique à la VT) doit rendre « beta » avant « alpha »."""
    text = str(layout_to_text(_composed_page(), {}))
    assert text.index("beta") < text.index("alpha"), text


def test_deux_projections__meme_layout_meme_texte(tmp_path: Path) -> None:
    """Le même ``CanonicalLayout`` projeté par la couche 3 (VT) et par l'étape
    ``projection`` de couche 5 (candidat) doit donner le même texte — sinon un
    candidat parfait a un CER non nul. Cas : 2 régions de premier niveau."""
    layout = CanonicalLayout(
        pages=(
            LayoutPage(
                width=100,
                height=100,
                regions=(_leaf("a", "alpha"), _leaf("b", "beta", 50)),
                reading_order=("a", "b"),
            ),
        )
    )
    assert str(layout_to_text(layout, {})) == _extract(tmp_path, layout)


def test_deux_projections__ordre_imbrique_identique(tmp_path: Path) -> None:
    """Même comparaison sur le bloc composé à ordre plat c2 → c1."""
    layout = _composed_page()
    assert str(layout_to_text(layout, {})) == _extract(tmp_path, layout)


class _EchoRecognizer:
    """Reconnaisseur factice : rend comme texte l'``id`` de la région reçue."""

    def __init__(self, tmp_path: Path) -> None:
        self._dir = tmp_path
        self.images: list[tuple[str, str]] = []

    name = "echo"
    version = "1"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def execute(self, inputs, params, context, control) -> StepOutput:
        image = inputs[ArtifactType.IMAGE]
        self.images.append((image.region_id or "?", image.uri or "?"))
        path = self._dir / f"{image.region_id}.txt"
        path.write_text(f"T_{image.region_id}", encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"d:echo:{image.region_id}", document_id="d",
                    type=ArtifactType.RAW_TEXT, uri=str(path),
                )
            }
        )


def _ctx(tmp_path: Path) -> RunContext:
    return RunContext(document_id="d", code_version="0", pipeline_name="p", workspace_uri=str(tmp_path))


def test_fanout__ordre_de_lecture_preserve_au_reassemblage(tmp_path: Path) -> None:
    """Régions déclarées b, a mais ordre de lecture a → b : après fan-out, le layout
    garde l'ordre de lecture et la projection rend T_a avant T_b."""
    seg = CanonicalLayout(
        pages=(
            LayoutPage(
                width=100, height=100,
                regions=(_leaf("b", None, 50), _leaf("a", None)),
                reading_order=("a", "b"),
            ),
        )
    )
    image = Artifact(id="d:img", document_id="d", type=ArtifactType.IMAGE, uri=str(tmp_path / "p1.png"))
    filled, _ = run_region_fanout(
        layout=seg, page_image=image, recognizer=_EchoRecognizer(tmp_path),
        context=_ctx(tmp_path), control=RunControl(),
    )
    assert filled.pages[0].reading_order == ("a", "b")
    text = str(layout_to_text(filled, {}))
    assert text.index("T_a") < text.index("T_b")


def test_fanout_multipage__une_page_n_est_pas_lue_dans_l_image_d_une_autre(tmp_path: Path) -> None:
    """Layout de 2 pages, une seule IMAGE de document : le fan-out doit refuser
    (ou recevoir une image par page) plutôt que reconnaître les régions de la
    page 2 dans l'image de la page 1."""
    seg = CanonicalLayout(
        pages=(
            LayoutPage(width=100, height=100, regions=(_leaf("p1a", None),)),
            LayoutPage(width=100, height=100, regions=(_leaf("p2a", None),)),
        )
    )
    image = Artifact(id="d:img", document_id="d", type=ArtifactType.IMAGE, uri=str(tmp_path / "p1.png"))
    reco = _EchoRecognizer(tmp_path)
    try:
        run_region_fanout(
            layout=seg, page_image=image, recognizer=reco,
            context=_ctx(tmp_path), control=RunControl(),
        )
    except CinocError:  # un refus typé satisfait l'attendu
        return
    lus = dict(reco.images)
    assert lus["p2a"] != lus["p1a"], f"page 2 lue dans l'image de la page 1 : {lus}"


def test_deux_projections__candidat_parfait_cer_nul_vue_lignes(tmp_path: Path) -> None:
    """VT = layout (projetée par la vue), candidat = le même layout projeté par
    l'étape ``projection`` des recettes ; vue « garde les sauts de ligne ». Le
    candidat est parfait : CER attendu 0 (via ``evaluate_run``)."""
    blocs = tuple(_leaf(f"r{i}", f"mot{i}", 10 * i) for i in range(5))
    layout = CanonicalLayout(pages=(LayoutPage(width=100, height=100, regions=blocs),))
    gt = tmp_path / "gt.layout.json"
    gt.write_text(layout.model_dump_json(), encoding="utf-8")
    hyp = tmp_path / "hyp.txt"
    hyp.write_text(_extract(tmp_path, layout), encoding="utf-8")
    view = EvaluationView(
        name="lignes",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        projection=ProjectionSpec(
            source_type=ArtifactType.LAYOUT,
            target_type=ArtifactType.RAW_TEXT,
            projector_name="layout_to_text",
        ),
        normalization_profile="keep_line_breaks",
        metric_names=("cer",),
    )
    corpus = CorpusSpec(
        name="c",
        documents=(DocumentRef(id="d", ground_truths=(GroundTruthRef(type=ArtifactType.LAYOUT, uri=str(gt)),)),),
    )
    registry = MetricRegistry()
    register_default_metrics(registry)
    result = evaluate_run(
        corpus=corpus,
        evaluation=EvaluationSpec(views=(view,)),
        pipeline_outputs={"p": {"d": {"texte": {ArtifactType.RAW_TEXT: Artifact(
            id="d:texte:raw", document_id="d", type=ArtifactType.RAW_TEXT, uri=str(hyp))}}}},
        registry=registry,
        manifest=RunManifest(
            run_id="r", corpus_name="c", n_documents=1,
            pipeline_specs=(PipelineSpec(name="p", initial_inputs=(ArtifactType.IMAGE,)),),
            code_version="1", started_at=_T, completed_at=_T,
        ),
    )
    assert result.pipelines[0].aggregate[0].value == pytest.approx(0.0)

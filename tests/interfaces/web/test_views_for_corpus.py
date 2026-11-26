"""``_views_for_corpus`` : la sélection des vues d'évaluation d'après les types
de GT présents dans le corpus (consommateur réel de ``REFERENCE_TEXT``, Lot C).

GT manuelle ``RAW_TEXT`` → vue ``texte`` ; référence ``REFERENCE_TEXT`` (OCR
Gallica) → vue *référence* distincte (étiquetée dans son nom) ; aucune GT → vue
``texte`` par défaut (run OCR-able, non scoré).
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app.run_planning import _views_for_corpus
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef


def _corpus(*gt_types: ArtifactType) -> CorpusSpec:
    gts = tuple(GroundTruthRef(type=t, uri=f"/tmp/{t.value}.txt") for t in gt_types)
    doc = DocumentRef(id="d1", image_uri="/tmp/a.png", ground_truths=gts)
    return CorpusSpec(name="c", documents=(doc,))


def test_manual_gt_yields_text_view_only() -> None:
    views = _views_for_corpus(_corpus(ArtifactType.RAW_TEXT))
    assert [v.name for v in views] == ["texte"]


def test_reference_text_yields_distinct_reference_view() -> None:
    views = _views_for_corpus(_corpus(ArtifactType.REFERENCE_TEXT))
    assert len(views) == 1
    view = views[0]
    # nom auto-documenté (le rapport l'affiche tel quel) + projection opt-in
    assert "vérité-terrain" in view.name
    spec = view.projection_for(ArtifactType.REFERENCE_TEXT)
    assert spec is not None and spec.target_type == ArtifactType.RAW_TEXT


def test_both_gt_types_yield_both_views() -> None:
    views = _views_for_corpus(
        _corpus(ArtifactType.RAW_TEXT, ArtifactType.REFERENCE_TEXT)
    )
    names = [v.name for v in views]
    assert names[0] == "texte"
    assert any("vérité-terrain" in n for n in names)


def test_no_gt_falls_back_to_text_view() -> None:
    views = _views_for_corpus(_corpus())
    assert [v.name for v in views] == ["texte"]


def _corpus_with_gt(tmp_path: Path, text: str) -> CorpusSpec:
    gt = tmp_path / "d1.gt.txt"
    gt.write_text(text, encoding="utf-8")
    doc = DocumentRef(
        id="d1",
        image_uri=str(tmp_path / "a.png"),
        ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),),
    )
    return CorpusSpec(name="c", documents=(doc,))


def test_gt_with_lines_adds_the_lines_view(tmp_path: Path) -> None:
    """D-285 : sous le défaut à plat, la seconde vue garde les sauts de ligne —
    c'est elle qui porte l'analyse par ligne (et le chiffre de dinglehopper)."""
    views = _views_for_corpus(_corpus_with_gt(tmp_path, "le roi\ndort\n"))
    assert [(v.name, v.normalization_profile) for v in views] == [
        ("texte", "flat_text"),
        ("texte (lignes)", "keep_line_breaks"),
    ]
    assert views[1].metric_names == ("cer",)
    # D-289 : la FCA n'est plus d'aucune vue par défaut — 1 − CER à plat, et
    # sous « texte (lignes) » soit 1 − CER encore, soit ~0 pour qui fusionne.
    assert all("fca" not in v.metric_names for v in views)


def test_single_line_gt_keeps_one_view(tmp_path: Path) -> None:
    views = _views_for_corpus(_corpus_with_gt(tmp_path, "une seule ligne\n"))
    assert [v.name for v in views] == ["texte"]


def test_a_chosen_profile_gives_a_single_view(tmp_path: Path) -> None:
    """Un profil choisi remplace le défaut : l'utilisateur a dit sa convention."""
    views = _views_for_corpus(
        _corpus_with_gt(tmp_path, "le roi\ndort"), normalization="nfc"
    )
    assert [(v.name, v.normalization_profile) for v in views] == [("texte", "nfc")]

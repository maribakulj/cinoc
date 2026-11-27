"""La vérité ``LAYOUT`` d'un corpus déposé sur la page (S29a).

Un dépôt ZIP à ``.gt.txt`` + ALTO n'avait **aucune** vérité de mise en page :
la vue ``structure`` n'était jamais déclarée sur un corpus web. La règle que
S28b proposait — tirer la vérité de l'ALTO et exclure la vue ``structure`` du
pipeline dont un ``alto_source`` lit ce même fichier — n'est pas nette : le
``<rad>.xml`` d'un tel corpus est le plus souvent l'ALTO d'un OCR à corriger,
et en faire la vérité noterait **tout autre** pipeline contre l'accord avec un
OCR, sans le dire. Règle retenue : une mise en page n'est une vérité que
**nommée comme telle** (``<rad>.gt.xml``) ; ``alto_source`` lit ``<rad>.xml`` ou
``<rad>.alto.xml``, jamais ``<rad>.gt.xml`` — l'auto-comparaison d'``alto_corrige``
est impossible par construction.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from cinoc.adapters.layout.alto_source import AltoLayoutSource
from cinoc.app.corpus_upload import CorpusUploadError, extract_corpus_zip
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def _alto(*lines: str) -> bytes:
    strings = "".join(
        f'<TextLine ID="l{i}"><String CONTENT="{text}"/></TextLine>'
        for i, text in enumerate(lines, start=1)
    )
    return (
        '<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>'
        '<Page ID="p" WIDTH="100" HEIGHT="100"><PrintSpace>'
        f'<TextBlock ID="b1">{strings}</TextBlock>'
        "</PrintSpace></Page></Layout></alto>"
    ).encode()


#: L'ALTO d'un OCR (à corriger) et la mise en page vraie, à part.
_OCR = _alto("le ſoleil fe leve", "ſur la mer")
_VRAI = _alto("le soleil se leve", "sur la mer")


def _upload(tmp_path: Path, entries: dict[str, bytes]) -> CorpusSpec:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, payload in entries.items():
            archive.writestr(name, payload)
    return extract_corpus_zip(buffer, tmp_path / "c", name="c")


def _views(corpus: CorpusSpec, *recipes: str) -> set[str]:
    spec = plan_recipe_run(
        corpus, tuple(RecipeEntry(recipe=r) for r in recipes), run_id="r"
    )
    return {view.name for view in spec.evaluation.views}


def test_a_named_layout_truth_scores_the_structure(tmp_path: Path) -> None:
    """Rouge avant S29a : ``<rad>.gt.xml`` à côté d'un ``.gt.txt`` était
    ignoré, et la vue ``structure`` absente pour **tous** les pipelines."""
    corpus = _upload(tmp_path, {
        "p1.png": _PNG, "p1.gt.txt": b"le soleil se leve\nsur la mer",
        "p1.xml": _OCR, "p1.gt.xml": _VRAI,
    })
    (document,) = corpus.documents
    assert {gt.type for gt in document.ground_truths} == {
        ArtifactType.RAW_TEXT, ArtifactType.LAYOUT,
    }
    layout = document.gt_for(ArtifactType.LAYOUT)
    assert layout is not None and Path(layout.uri or "").name == "p1.gt.xml"
    # Le texte reste la transcription fournie, pas l'ALTO.
    texte = document.gt_for(ArtifactType.RAW_TEXT)
    assert texte is not None and Path(texte.uri or "").name == "p1.gt.txt"
    # La structure note ``alto_corrige`` **et** un autre pipeline à mise en page.
    assert "structure" in _views(corpus, "alto_corrige")
    assert "structure" in _views(corpus, "alto_corrige", "segmentation_puis_lecture")


def test_alto_corrige_is_never_scored_against_its_own_alto(tmp_path: Path) -> None:
    """La vérité de la vue ``structure`` n'est jamais un fichier que lit
    ``alto_source`` — quel que soit le jeu de fichiers déposé."""
    for entries in (
        {"p1.png": _PNG, "p1.gt.txt": b"x", "p1.xml": _OCR, "p1.gt.xml": _VRAI},
        {"p1.png": _PNG, "p1.xml": _OCR, "p1.gt.xml": _VRAI},
        {"p1.png": _PNG, "p1.gt.txt": b"x", "p1.xml": _OCR},
        {"p1.png": _PNG, "p1.xml": _OCR},
    ):
        dossier = tmp_path / str(len(list(tmp_path.iterdir())))
        (document,) = _upload(dossier, entries).documents
        lus = set(AltoLayoutSource().unit_inputs(document))
        layout = document.gt_for(ArtifactType.LAYOUT)
        assert layout is None or Path(layout.uri or "") not in lus, entries


@pytest.mark.parametrize(
    "entries",
    [
        {"p1.png": _PNG, "p1.gt.txt": b"x", "p1.xml": _OCR},
        {"p1.png": _PNG, "p1.xml": _OCR},
    ],
    ids=["gt-txt-et-alto", "alto-seul"],
)
def test_a_bare_alto_is_not_a_layout_truth(
    tmp_path: Path, entries: dict[str, bytes]
) -> None:
    """``<rad>.xml`` est la source d'``alto_source`` : jamais la vérité de la
    structure (seul ``<rad>.gt.xml`` l'est) — pour aucun pipeline."""
    corpus = _upload(tmp_path, entries)
    (document,) = corpus.documents
    assert document.gt_for(ArtifactType.LAYOUT) is None
    assert "structure" not in _views(corpus, "segmentation_puis_lecture")


def test_an_unreadable_layout_truth_is_refused(tmp_path: Path) -> None:
    with pytest.raises(CorpusUploadError, match="illisible"):
        _upload(tmp_path, {"p1.png": _PNG, "p1.gt.txt": b"x",
                           "p1.gt.xml": b"<alto>pas valable"})


def test_alto_corrige_is_scored_against_the_named_truth(tmp_path: Path) -> None:
    """De bout en bout (producteur ``rules``, hors ligne) : la structure de la
    sortie corrigée est notée contre ``p1.gt.xml``. Contre son propre ALTO, la
    ligne « le ſoleil fe leve » corrigée en « le soleil fe leve » aurait l'air
    juste ; contre la vérité, « fe » reste une erreur (1 caractère sur 28)."""
    pytest.importorskip("saknussemm")
    from cinoc.app import run
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    corpus = _upload(tmp_path, {
        "p1.png": _PNG, "p1.gt.txt": b"le soleil se leve\nsur la mer",
        "p1.xml": _OCR, "p1.gt.xml": _VRAI,
    })
    spec = plan_recipe_run(corpus, (RecipeEntry(recipe="alto_corrige"),), run_id="r")
    registry = ModuleRegistry()
    register_default_modules(registry)
    result = run(spec, registry=registry, code_version="1")
    (structure,) = (d for d in result.documents if d.view == "structure")
    scores = {s.metric: s.value for s in structure.scores}
    assert scores["region_cer"] == pytest.approx(1 / 28)
    assert scores["line_identity_coverage"] == 1.0

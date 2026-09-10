"""Planifier un run de **post-correction structurée** (couche 6).

Le banc savait décrire trois formes de concurrent : un OCR à plat, une chaîne
OCR → LLM, et un pipeline hybride segmenteur → bloc. Aucune ne dit « prendre un
ALTO **déjà là** et le corriger ». La chaîne existait pourtant — source ALTO,
correcteur, projections — mais il fallait écrire le YAML à la main, ce qui n'est
pas une façon d'utiliser un banc.

La spec produite :

    IMAGE ─ alto_source ─→ LAYOUT ─┬─ layout_to_text ──→ RAW_TEXT
                                   └─ saknussemm ──────→ LAYOUT corrigé
                                                       + CORRECTED_TEXT
                                                       + DECISIONS

``layout_to_text`` part du LAYOUT **source**, pas du corrigé : le bilan de
correction du banc compare un ``RAW_TEXT`` à un ``CORRECTED_TEXT``, et lui
donner deux fois le texte d'arrivée n'aurait mesuré que le silence.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.app.corpus_upload import GT_SOURCE_KEY
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import INITIAL_STEP_ID, PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

#: Producteurs câblés dans l'adapter de correction.
_PRODUCERS = ("rules", "ollama")

#: Extensions d'image cherchées à côté d'un ALTO (mêmes que ``transcription``).
_IMAGE_EXT = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2")

#: Métriques de la vue structure. ``line_identity_*`` n'ont de sens que
#: **parce que** cette chaîne préserve l'identité de ligne : elles apparient par
#: identifiant au lieu de deviner par alignement.
_STRUCTURE_METRICS = (
    "region_cer",
    "line_identity_cer",
    "line_identity_coverage",
)


def plan_correction_run(
    corpus: CorpusSpec,
    run_id: str,
    *,
    producer: str = "rules",
    model: str = "",
    label: str = "correction",
    host: str = "http://localhost:11434",
    ocr_sidecar: str = "",
) -> RunSpec:
    """Spec d'un run de correction structurée sur un corpus porteur d'ALTO.

    ``ocr_sidecar`` est **la** option à ne pas oublier sur un corpus à vérité
    terrain : sans elle, la source lit l'ALTO de référence, le correcteur n'a
    rien à corriger, et le CER vaut zéro *par construction*. Un zéro
    tautologique ressemble à un excellent résultat.

    La vue « structure » n'est ajoutée que si le corpus porte une GT ``LAYOUT``
    — sans référence, il n'y a rien à noter, et une vue vide vaut moins que pas
    de vue.
    """
    if producer not in _PRODUCERS:
        raise CinocError(
            f"plan_correction_run : producteur {producer!r} inconnu "
            f"(attendu : {', '.join(_PRODUCERS)})."
        )
    if producer == "ollama" and not model:
        raise CinocError(
            "plan_correction_run : le producteur 'ollama' exige un `model`."
        )
    if not corpus.documents:
        raise CinocError("plan_correction_run : corpus vide.")

    corrector = f"saknussemm:{label}"
    projector = f"layout_to_text:{label}"
    pipeline = PipelineSpec(
        name=f"alto→{model or producer}",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="source",
                kind="layout_source",
                adapter_name="alto_source",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.LAYOUT,),
                inputs_from={ArtifactType.IMAGE: INITIAL_STEP_ID},
            ),
            PipelineStep(
                id="brut",
                kind="projection",
                adapter_name=projector,
                input_types=(ArtifactType.LAYOUT,),
                output_types=(ArtifactType.RAW_TEXT,),
                inputs_from={ArtifactType.LAYOUT: "source"},
            ),
            PipelineStep(
                id="corr",
                kind="post_correction",
                adapter_name=corrector,
                input_types=(ArtifactType.LAYOUT,),
                output_types=(
                    ArtifactType.LAYOUT,
                    ArtifactType.CORRECTED_TEXT,
                    ArtifactType.DECISIONS,
                ),
                # Explicitement la sortie de ``source``. Le pool étant indexé
                # par type, ``LAYOUT`` y désignerait sinon la sortie la plus
                # récente — celle de cette étape même.
                inputs_from={ArtifactType.LAYOUT: "source"},
            ),
        ),
    )
    views = [
        EvaluationView(
            name="texte",
            candidate_types=frozenset(
                {ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT}
            ),
            metric_names=("cer", "wer"),
        )
    ]
    if any(d.gt_for(ArtifactType.LAYOUT) is not None for d in corpus.documents):
        views.append(
            EvaluationView(
                name="structure",
                candidate_types=frozenset({ArtifactType.LAYOUT}),
                metric_names=_STRUCTURE_METRICS,
            )
        )
    source_kwargs: dict[str, str | int | float | bool] = {}
    if ocr_sidecar:
        source_kwargs["ocr_sidecar"] = ocr_sidecar
    corrector_kwargs: dict[str, str | int | float | bool] = {
        "label": label,
        "producer": producer,
        "host": host,
    }
    if model:
        corrector_kwargs["model"] = model
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=tuple(views)),
        adapter_kwargs={
            "alto_source": source_kwargs,
            projector: {"label": label},
            corrector: corrector_kwargs,
        },
        run_id=run_id,
    )


def corpus_from_alto(
    directory: str | Path, *, name: str | None = None, ground_truth: bool = True
) -> CorpusSpec:
    """``CorpusSpec`` d'un dossier ``<stem>.xml`` + ``<stem>.<image>``.

    ``ground_truth`` déclare l'ALTO comme vérité terrain ``LAYOUT``. C'est vrai
    d'un corpus **transcrit à la main** ; c'est faux d'un ALTO d'OCR, où la
    référence n'existe pas — l'y déclarer ferait comparer le texte à lui-même.
    Le paramètre existe pour que ce soit un choix visible et non un défaut muet.
    """
    folder = Path(directory)
    if not folder.is_dir():
        raise CinocError(f"dossier ALTO introuvable : {folder}")
    documents = []
    for xml in sorted(folder.glob("*.xml")):
        image = next(
            (
                candidate
                for suffix in _IMAGE_EXT
                if (candidate := xml.with_suffix(suffix)).is_file()
            ),
            None,
        )
        if image is None:
            continue
        documents.append(
            DocumentRef(
                id=xml.stem,
                image_uri=str(image.resolve()),
                ground_truths=(
                    (
                        GroundTruthRef(
                            type=ArtifactType.LAYOUT, uri=str(xml.resolve())
                        ),
                    )
                    if ground_truth
                    else ()
                ),
            )
        )
    if not documents:
        raise CinocError(
            f"aucune paire ALTO + image dans {folder} "
            f"(un ``<nom>.xml`` avec un ``<nom>{sorted(_IMAGE_EXT)[0]}`` à côté)."
        )
    return CorpusSpec(name=name or folder.name, documents=tuple(documents))


def ground_truth_is_its_own_source(corpus: CorpusSpec) -> bool:
    """La vérité terrain du corpus est-elle **extraite de l'ALTO à corriger** ?

    C'est le piège du banc de correction, et il est silencieux. Un corpus déposé
    sous forme d'images + ALTO, sans transcription à part, voit sa vérité terrain
    **dérivée de cet ALTO** (``corpus_upload``). Or c'est exactement le texte
    dont part le correcteur : le comparer à lui-même donne un CER nul pour la
    sortie brute, et n'attribue au correcteur que ses propres changements. Le
    rapport dirait alors « corriger dégrade », quel que soit le correcteur.

    Vrai dès qu'**un** document est dans ce cas : un corpus à moitié piégé
    produit un classement à moitié faux, ce qui ne vaut pas mieux.
    """
    return any(
        document.metadata.get(GT_SOURCE_KEY) == "layout"
        for document in corpus.documents
    )


__all__ = [
    "corpus_from_alto",
    "ground_truth_is_its_own_source",
    "plan_correction_run",
]

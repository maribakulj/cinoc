"""Mini-corpus de démonstration **déterministe** (couche 6, ``app``).

Le même corpus pré-calculé sert la commande CLI ``demo`` **et** le lanceur web
(walking skeleton) : un run réel, sans moteur externe (``precomputed``),
qui produit un ``RunResult`` reproductible. Construire le ``RunSpec`` est un acte
de **planification de run** → couche ``app`` (les feuilles de transport ``cli`` /
``web`` délèguent ici, jamais l'inverse — cf. ``test_interfaces_thin``).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.archaic import DEFAULT_ARCHAIC_LIST, resolve_archaic_list

DEMO_ENGINES = ("tesseract", "pero")

#: Mini-corpus déterministe : (id, vérité-terrain, {moteur: sortie pré-calculée}).
#: ``(doc_id, strate, vérité-terrain, {moteur: sortie})``. Deux strates pour
#: démontrer la composition / le CER par strate (forme optionnelle, P0/U5′).
_DEMO_DOCS: tuple[tuple[str, str, str, dict[str, str]], ...] = (
    (
        "folio_001",
        "manuscrit médiéval",
        "Icy commence le prologue",
        {
            "tesseract": "Icy commence le prologve",
            "pero": "Icy commence le prologue",
        },
    ),
    (
        "folio_002",
        "manuscrit médiéval",
        "maistre Jehan Froissart",
        {
            "tesseract": "maistre Jehan Froissart",
            "pero": "maistre Jehan Froiſſart",
        },
    ),
    (
        "folio_003",
        "manuscrit médiéval",
        "les croniques de France",
        {
            "tesseract": "les croniques de France",
            "pero": "les croniques de France",
        },
    ),
    (
        "imprime_001",
        "imprimé ancien",
        "DE L'IMPRIMERIE DE PIERRE LE ROUGE",
        {
            "tesseract": "DE L'IMPRIMERIE DE PIERRE LE ROVGE",
            "pero": "DE L'IMPRIMERIE DE PIERRE LE ROUGE",
        },
    ),
    (
        "imprime_002",
        "imprimé ancien",
        "Imprimé à Paris l'an mil cinq cens",
        {
            "tesseract": "Imprime a Paris l'an mil cinq cens",
            "pero": "Imprimé à Paris l'an mil cinq cens",
        },
    ),
)

# ``air`` figure ici car le mini-corpus exerce un vrai cas : ``pero`` rend
# « Froiſſart » (ſ long) là où la GT écrit « Froissart » → archaïsme **inséré**.
_TEXT_VIEW = EvaluationView(
    name="texte",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer", "cer_diplo", "wer", "mer", "air"),
)

#: Même corpus, sous équivalence orthographique du français médiéval (ſ=s, u=v,
#: i=j…) appliquée des deux côtés : les « erreurs » purement graphiques tombent.
_DIPLOMATIC_VIEW = EvaluationView(
    name="francais_medieval",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer", "wer", "mer"),
    normalization_profile="medieval_french",
)


def write_demo_corpus(root: Path) -> CorpusSpec:
    """Matérialise le mini-corpus dans ``root`` et renvoie sa ``CorpusSpec``."""
    documents: list[DocumentRef] = []
    for doc_id, stratum, ground_truth, engine_texts in _DEMO_DOCS:
        (root / f"{doc_id}.gt.txt").write_text(ground_truth, encoding="utf-8")
        for label, text in engine_texts.items():
            (root / f"{doc_id}.{label}.txt").write_text(text, encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc_id,
                image_uri=str(root / f"{doc_id}.png"),
                ground_truths=(
                    GroundTruthRef(
                        type=ArtifactType.RAW_TEXT,
                        uri=str(root / f"{doc_id}.gt.txt"),
                    ),
                ),
                metadata={"stratum": stratum},
            )
        )
    return CorpusSpec(name="demo", documents=tuple(documents))


def demo_run_spec(corpus: CorpusSpec, *, run_id: str = "demo") -> RunSpec:
    """``RunSpec`` de démonstration : un pipeline ``precomputed`` par moteur."""
    pipelines = tuple(
        PipelineSpec(
            name=label,
            initial_inputs=(ArtifactType.IMAGE,),
            steps=(
                PipelineStep(
                    id="ocr",
                    kind="ocr",
                    adapter_name=f"precomputed:{label}",
                    input_types=(ArtifactType.IMAGE,),
                    output_types=(ArtifactType.RAW_TEXT,),
                ),
            ),
        )
        for label in DEMO_ENGINES
    )
    adapter_kwargs = {
        f"precomputed:{label}": {"source_label": label} for label in DEMO_ENGINES
    }
    archaic = resolve_archaic_list(DEFAULT_ARCHAIC_LIST)
    return RunSpec(
        corpus=corpus,
        pipelines=pipelines,
        evaluation=EvaluationSpec(views=(_TEXT_VIEW, _DIPLOMATIC_VIEW)),
        adapter_kwargs=adapter_kwargs,
        run_id=run_id,
        metadata={
            "archaic_list": archaic.name,
            "archaic_list_hash": archaic.list_hash,
        },
    )


def demo_spec_builder(run_id: str = "demo") -> Callable[[Path], RunSpec]:
    """Builder de spec de la **démonstration** : matérialise le mini-corpus dans
    le workspace fourni, puis construit le ``RunSpec`` précalculé (``precomputed``).
    """

    def build(workspace: Path) -> RunSpec:
        return demo_run_spec(write_demo_corpus(workspace), run_id=run_id)

    return build


__all__ = [
    "DEMO_ENGINES",
    "demo_run_spec",
    "demo_spec_builder",
    "write_demo_corpus",
]

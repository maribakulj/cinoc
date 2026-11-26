"""Un corpus d'**ALTO déjà là**, à corriger (couche 6).

La correction structurée est une recette (``alto_corrige`` : source ALTO,
projection du texte de départ, correcteur), construite par la file comme toute
autre (D-298) — il n'y a plus de planificateur à part. Restent ici les deux
choses propres à ce corpus : le **lire** depuis un dossier (``cinoc correct``)
et **reconnaître le piège** d'une vérité terrain extraite de l'ALTO même qu'on
corrige, que la file refuse pour toute entrée.

La recette :

    IMAGE ─ alto_source ─→ LAYOUT ─┬─ layout_to_text ──→ RAW_TEXT
                                   └─ saknussemm ──────→ LAYOUT corrigé
                                                       + CORRECTED_TEXT
                                                       + DECISIONS

``layout_to_text`` part du LAYOUT **source**, pas du corrigé : le bilan de
correction du banc compare un ``RAW_TEXT`` à un ``CORRECTED_TEXT``, et lui
donner deux fois le texte d'arrivée n'aurait mesuré que le silence.
"""

from __future__ import annotations

import re
from pathlib import Path

from cinoc.adapters.layout.alto_source import (
    alto_candidates,
    alto_file_name,
    file_component,
)
from cinoc.adapters.layout.saknussemm_correct import (
    #: Producteurs câblés dans l'adapter — **lus là-bas, jamais recopiés**.
    #:
    #: C'en était une copie, et elle aurait dérivé dès que l'adapter a gagné
    #: ``mistral`` : la CLI et le web auraient continué d'offrir deux
    #: producteurs sur quatre. Le garde-fou des listes recopiées ne l'aurait pas
    #: vue — elle ne contenait qu'un seul nom de fournisseur, et son seuil est
    #: deux.
    PRODUCERS,
)
from cinoc.app.corpus_upload import GT_SOURCE_KEY, truths_beside
from cinoc.app.spec_coherence import SpecCoherenceError
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec
from cinoc.formats.images import IMAGE_SUFFIXES


def corpus_from_alto(
    directory: str | Path,
    *,
    name: str | None = None,
    pipeline: str = "",
    ocr_sidecar: str = "",
    ground_truth: bool = True,
) -> CorpusSpec:
    """``CorpusSpec`` d'un dossier d'images, chacune avec l'ALTO à corriger.

    **Appariement** — celui d'``alto_source``, qui lira l'ALTO au run : à côté
    de ``<nom>.png``, ``<nom>.xml`` puis ``<nom>.alto.xml`` (un ALTO d'un autre
    outil) ; avec ``pipeline``, ``<nom>.<pipeline>.alto.xml`` **seul** (l'ALTO
    qu'un run Cinoc a écrit, ``alto_file_name``). Un dossier qui ne porte que
    des ALTO écrits par Cinoc, sans ``pipeline``, est refusé en nommant les
    pipelines qu'il contient.

    **Vérité terrain — la règle de D-307.** Aucun chiffre ne doit pouvoir se
    lire comme une exactitude quand il mesure la fidélité à l'entrée :

    - la transcription déposée à côté (``<nom>.gt.txt``, ``<nom>.txt``) et la
      mise en page nommée ``<nom>.gt.xml`` — la règle du dépôt ZIP
      (``truths_beside``) ;
    - l'ALTO à corriger **n'est une vérité que sous** ``ocr_sidecar`` : alors
      c'est une transcription, et le texte de départ vient de l'OCR. Sans
      sidecar, le déclarer ferait comparer la sortie à sa propre entrée — le
      ``F1 1,0 · CER 0,0`` qu'un testeur a lu sur un ALTO d'OCR ; avec
      ``pipeline``, c'est la sortie d'un moteur, jamais une vérité ;
    - ``ground_truth`` faux : aucune vérité, le run n'est pas noté.
    """
    folder = Path(directory)
    if not folder.is_dir():
        raise CinocError(f"dossier ALTO introuvable : {folder}")
    if pipeline and file_component(pipeline) != pipeline:
        raise CinocError(
            f"--pipeline {pipeline!r} : le nom tel qu'il figure dans le fichier "
            f"({file_component(pipeline)!r} ?)."
        )
    files = {p.name: p.resolve() for p in folder.iterdir() if p.is_file()}
    alto_is_truth = ground_truth and bool(ocr_sidecar) and not pipeline
    documents = []
    # Une image par radical, dans l'ordre de préférence de la table (un PNG
    # avant un JPEG de même nom) : le radical est l'identifiant du document.
    images: dict[str, Path] = {}
    for suffix in IMAGE_SUFFIXES:
        for chemin in sorted(files.values()):
            if chemin.suffix.lower() == suffix:
                images.setdefault(chemin.stem, chemin)
    for image in (images[stem] for stem in sorted(images)):
        stem = image.stem
        candidats = (
            (image.with_name(alto_file_name(stem, pipeline)),)
            if pipeline
            else alto_candidates(image)
        )
        alto = next((c for c in candidats if c.name in files), None)
        if alto is None:
            continue
        truths, source = truths_beside(stem, files) if ground_truth else ((), "")
        if alto_is_truth and not any(t.type is ArtifactType.LAYOUT for t in truths):
            truths = (*truths, GroundTruthRef(type=ArtifactType.LAYOUT, uri=str(alto)))
        documents.append(
            DocumentRef(
                id=stem,
                image_uri=str(image),
                ground_truths=truths,
                metadata={GT_SOURCE_KEY: source} if source else {},
            )
        )
    if not documents:
        raise CinocError(_no_pair(folder, files, pipeline))
    return CorpusSpec(name=name or folder.name, documents=tuple(documents))


def _no_pair(folder: Path, files: dict[str, Path], pipeline: str) -> str:
    """Pourquoi rien n'est apparié — et, si le dossier porte des ALTO écrits par
    Cinoc, les pipelines à nommer."""
    stems = {p.stem for p in files.values() if p.suffix.lower() in IMAGE_SUFFIXES}
    motifs = [re.compile(re.escape(s) + r"\.([\w-]+)\.alto\.xml", re.A) for s in stems]
    trouves = sorted(
        {m.group(1) for nom in files for motif in motifs if (m := motif.fullmatch(nom))}
    )
    image = f"<nom>{IMAGE_SUFFIXES[0]}"
    if pipeline:
        attendu = f"'<nom>.{pipeline}.alto.xml' à côté de '{image}'"
    else:
        attendu = f"'<nom>.xml' ou '<nom>.alto.xml' à côté de '{image}'"
    message = f"aucune paire ALTO + image dans {folder} ({attendu})."
    if trouves:
        message += (
            " Ce dossier porte des ALTO écrits par Cinoc : nommez leur pipeline "
            f"avec --pipeline ({', '.join(trouves)})."
        )
    return message


def truth_summary(corpus: CorpusSpec) -> str:
    """Ce que mesureront les chiffres d'une correction sur ``corpus`` — dit
    **avant** le run, en clair, pour qu'aucun ne se lise comme ce qu'il n'est
    pas."""
    total = len(corpus.documents)
    texte = sum(
        any(t.type is ArtifactType.RAW_TEXT for t in d.ground_truths)
        for d in corpus.documents
    )
    page = sum(
        any(t.type is ArtifactType.LAYOUT for t in d.ground_truths)
        for d in corpus.documents
    )
    if not texte and not page:
        return (
            "Aucune vérité terrain : rien n'est noté. Le rapport montre ce que le "
            "correcteur a changé et refusé — pas une exactitude. Une "
            "transcription <nom>.gt.txt à côté de chaque image donne un CER."
        )
    lignes = []
    if texte:
        lignes.append(
            f"Vérité terrain texte : {texte}/{total} document(s) (<nom>.gt.txt) — "
            "CER et WER du texte corrigé contre elle."
        )
    if page:
        lignes.append(
            f"Vérité de mise en page : {page}/{total} document(s) — vue structure."
        )
    return "\n".join(lignes)


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


def refuse_self_reference(spec: RunSpec) -> None:
    """Refuse de lire un ALTO **dont la vérité terrain est extraite**.

    Un corpus déposé en images + ALTO, sans transcription à part, voit sa vérité
    terrain dérivée de cet ALTO : une étape ``alto_source`` partirait du texte
    auquel on la compare, et le CER vaudrait zéro par construction — un verdict
    qui ressemble à un excellent résultat. Seule issue : lire l'OCR d'ailleurs
    (``ocr_sidecar``). Vaut pour **toute** spec — recette de la page, ``cinoc
    run --recipe``, spec écrite à la main (CLI comme web), D-307.
    """
    if not ground_truth_is_its_own_source(spec.corpus):
        return
    for pipeline in spec.pipelines:
        for etape in pipeline.steps:
            if etape.adapter_name.split(":", 1)[0] != "alto_source":
                continue
            if not spec.adapter_kwargs.get(etape.adapter_name, {}).get("ocr_sidecar"):
                raise SpecCoherenceError(
                    "la vérité terrain de ce corpus est extraite de son propre "
                    "ALTO : le correcteur partirait du texte auquel on le "
                    "compare, et le CER vaudrait zéro par construction. Dépose "
                    "une transcription à part (<nom>.gt.txt) à côté de chaque "
                    "ALTO."
                )


__all__ = [
    # Ré-exportés pour les transports : une interface lit la capacité en couche
    # `app`, jamais en couche `adapters` — et surtout jamais en la recopiant.
    "PRODUCERS",
    "corpus_from_alto",
    "ground_truth_is_its_own_source",
    "refuse_self_reference",
    "truth_summary",
]

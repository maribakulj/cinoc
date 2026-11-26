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

from pathlib import Path

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
from cinoc.app.corpus_upload import GT_SOURCE_KEY
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.formats.images import IMAGE_SUFFIXES

#: Extensions d'image cherchées à côté d'un ALTO (mêmes que ``transcription``).


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
                for suffix in IMAGE_SUFFIXES
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
            f"(un ``<nom>.xml`` avec un ``<nom>{IMAGE_SUFFIXES[0]}`` à côté)."
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
    # Ré-exportés pour les transports : une interface lit la capacité en couche
    # `app`, jamais en couche `adapters` — et surtout jamais en la recopiant.
    "PRODUCERS",
    "corpus_from_alto",
    "ground_truth_is_its_own_source",
]

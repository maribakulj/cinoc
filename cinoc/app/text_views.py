"""Vues texte par défaut d'un run planifié (couche 6) — D-285.

Les planificateurs (benchmark web, recettes, correction structurée) notent du
texte sous **deux** vues quand la vérité terrain a des lignes :

- ``texte`` — le profil par défaut (``flat_text`` : NFC, invisibles retirés,
  tout blanc réduit à une espace). Une vue texte compare une transcription, pas
  une segmentation en lignes : un moteur qui déroule ses lignes n'y paie pas une
  substitution par ligne.
- ``texte (lignes)`` — le même texte, sauts de ligne **comptés**
  (``keep_line_breaks``). Elle porte l'analyse par ligne, qu'une vue à plat ne
  peut pas calculer, et donne le chiffre qu'on rapproche de dinglehopper (qui
  joint les lignes par ``\\n`` et le compte).

Un profil **choisi** par l'utilisateur remplace le défaut et ne donne qu'une
vue : il a dit quelle convention il voulait.
"""

from __future__ import annotations

import logging
from pathlib import Path

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.evaluation import EvaluationView
from cinoc.formats.text import read_plaintext

logger = logging.getLogger(__name__)

#: Nom machine de la vue texte principale (libellé localisé au rapport).
TEXT_VIEW = "texte"
#: Nom machine de la seconde vue, sauts de ligne comptés.
LINES_VIEW = "texte (lignes)"
#: Profil de la seconde vue.
LINES_NORMALIZATION_PROFILE = "keep_line_breaks"


def ground_truth_has_lines(corpus: CorpusSpec) -> bool:
    """Vrai si au moins une GT ``RAW_TEXT`` lisible tient sur plusieurs lignes.

    Une GT illisible ici ne décide rien : le run la signalera là où elle est
    lue pour noter ; on ne fabrique pas une seconde vue sur une supposition.
    """
    for document in corpus.documents:
        truth = document.gt_for(ArtifactType.RAW_TEXT)
        if truth is None or truth.uri is None:
            continue
        try:
            text = read_plaintext(Path(truth.uri).read_bytes())
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("[text_views] GT illisible ignorée : %s", exc)
            continue
        if "\n" in text.strip():
            return True
    return False


def text_views(
    corpus: CorpusSpec,
    *,
    candidate_types: frozenset[ArtifactType],
    metric_names: tuple[str, ...],
    normalization: str | None = None,
    char_exclude: str | None = None,
) -> tuple[EvaluationView, ...]:
    """``texte`` (+ ``texte (lignes)`` si le défaut s'applique et que la GT a
    des lignes). ``normalization`` nommé → une seule vue, sous ce profil."""
    if normalization is not None:
        return (
            EvaluationView(
                name=TEXT_VIEW,
                candidate_types=candidate_types,
                metric_names=metric_names,
                normalization_profile=normalization,
                char_exclude=char_exclude,
            ),
        )
    main = EvaluationView(
        name=TEXT_VIEW,
        candidate_types=candidate_types,
        metric_names=metric_names,
        char_exclude=char_exclude,
    )
    if not ground_truth_has_lines(corpus):
        return (main,)
    # Le CER seul : c'est le chiffre que le saut de ligne change (le WER
    # découpe sur tout blanc), et chaque métrique ajoutée grossit la famille
    # de Holm du run.
    lines = EvaluationView(
        name=LINES_VIEW,
        candidate_types=candidate_types,
        metric_names=("cer",),
        normalization_profile=LINES_NORMALIZATION_PROFILE,
        char_exclude=char_exclude,
    )
    return (main, lines)


__all__ = [
    "LINES_NORMALIZATION_PROFILE",
    "LINES_VIEW",
    "TEXT_VIEW",
    "ground_truth_has_lines",
    "text_views",
]

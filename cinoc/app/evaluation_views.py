"""**Une seule politique de vues** (couche 6) — D-285, D-297.

Qui décide comment un run est noté ? Avant D-297, chaque entrée le décidait
pour elle-même : le composeur notait le texte sous le profil ``standard`` et
lisait les types de GT du corpus ; les recettes ne notaient que ``cer, wer`` et
lisaient les sorties du pipeline ; la correction avait sa propre liste. Trois
rapports pour un même pipeline, des noms de vue que ``cinoc compare`` ne
rapprochait pas, et des options de notation que la page offrait sans les
appliquer aux recettes.

:func:`plan_evaluation` est désormais **la** décision, appelée par les trois
entrées (``run_planning``, ``recipes``, ``correction_planning``) et donc par
leurs deux transports. Elle ne lit que trois choses :

- ce que les pipelines **produisent** (types de sortie de leurs étapes) ;
- ce que le corpus **porte** (types de GT, et si le texte a des lignes) ;
- les **options** de notation choisies (:class:`EvaluationOptions`).

Une vue n'est déclarée que si elle peut noter quelque chose : un candidat
produit **et** une vérité terrain qui le juge. Une vue vide vaut moins que pas
de vue. Seule exception, la vue texte d'un corpus sans aucune GT : le run reste
exécutable, simplement non noté.

Les vues texte (D-285) :

- ``texte`` — le profil par défaut (``flat_text`` : NFC, invisibles retirés,
  tout blanc réduit à une espace). Une vue texte compare une transcription, pas
  une segmentation en lignes : un moteur qui déroule ses lignes n'y paie pas une
  substitution par ligne.
- ``texte (lignes)`` — le même texte, sauts de ligne **comptés**
  (``keep_line_breaks``), CER seul, ajoutée quand la GT a des lignes. Elle porte
  l'analyse par ligne, qu'une vue à plat ne peut pas calculer, et donne le
  chiffre qu'on rapproche de dinglehopper (qui joint les lignes par ``\\n``).

Un profil **choisi** remplace le défaut et ne donne qu'une vue : l'utilisateur a
dit quelle convention il voulait.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import (
    DEFAULT_NORMALIZATION_PROFILE,
    EvaluationSpec,
    EvaluationView,
)
from cinoc.domain.pipeline import PipelineSpec
from cinoc.domain.projection import ProjectionSpec
from cinoc.evaluation.archaic import resolve_archaic_list
from cinoc.formats.text import NORMALIZATION_PROFILES, read_plaintext

logger = logging.getLogger(__name__)

#: Nom machine de la vue texte principale (libellé localisé au rapport).
TEXT_VIEW = "texte"
#: Nom machine de la seconde vue, sauts de ligne comptés.
LINES_VIEW = "texte (lignes)"
#: Profil de la seconde vue.
LINES_NORMALIZATION_PROFILE = "keep_line_breaks"
#: Vue de la mise en page (sorties ``LAYOUT`` contre une GT ``LAYOUT``).
STRUCTURE_VIEW = "structure"
#: Vue des entités nommées (sorties ``ENTITIES`` contre une GT ``ENTITIES``).
ENTITIES_VIEW = "entites"
#: Vue contre une référence OCR. **Le nom porte l'avertissement** : ce n'est
#: pas une vérité terrain manuelle, le score mesure l'accord avec un autre OCR.
REFERENCE_VIEW = "référence OCR (pas une vérité-terrain manuelle)"

#: Types notés par toute vue texte : ``RAW_TEXT`` (OCR, zero-shot) **et**
#: ``CORRECTED_TEXT`` (chaîne corrigée) — le runner note la sortie la plus
#: aboutie de chaque pipeline.
_TEXT = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})

#: **Profils de métriques** : colonnes scalaires de la vue ``texte``. Chaque
#: nom ne référence que des métriques **enregistrées** pour ``(RAW_TEXT,
#: RAW_TEXT)`` (verrouillé par test). Changer de profil n'allège **que** les
#: colonnes de classement : les collecteurs (taxonomie, données structurées…)
#: n'en dépendent pas. ``standard``, le défaut, n'a **aucune métrique
#: exploratoire** (D-289) ni ``fca`` (1 − CER à plat). ``numseq_*`` restent hors
#: des profils (D-130) : adaptatifs, ils donneraient des colonnes vides sur tout
#: corpus sans dates ni folios ; la section des données structurées reste.
DEFAULT_METRIC_PROFILE = "standard"
METRIC_PROFILES: dict[str, tuple[str, ...]] = {
    # ``cmer`` = MER caractère **borné [0,1]** (robuste aux modèles génératifs
    # qui font dépasser le CER), calculé sur RAW_TEXT comme le CER.
    "standard": (
        "cer", "cmer", "char_accuracy", "word_accuracy", "wer", "mer",
        "bow_precision", "bow_recall", "bow_f1", "searchability",
    ),
    "essentiel": ("cer", "wer", "mer"),
    "philologie": ("cer", "cer_diplo", "mer", "diacritic_err", "mufi_err", "air"),
}

#: Métriques de la vue structure : détection, texte par région, lignes par
#: **identité** (exact là où l'alignement devine : mesuré sur 37-GT-BNL, la
#: devinette diverge sur 57 lignes de 522), ordre de lecture et sa couverture —
#: chaque mesure avec son compagnon obligatoire (D-289). Un niveau absent des
#: deux côtés donne « non applicable », pas un zéro.
_STRUCTURE_METRICS = (
    "region_detection",
    "region_cer",
    "line_identity_cer",
    "line_identity_coverage",
    "reading_order_tau",
    "reading_order_coverage",
)


class EvaluationOptionsError(CinocError):
    """Option de notation inconnue (profil, liste archaïque)."""


class EvaluationOptions(BaseModel):
    """Ce que l'utilisateur choisit de la notation — le même objet, quelle que
    soit l'entrée (composeur, recette, correction) et le transport.

    ``archaic_list`` relie ``air`` à une liste curée et active ``hcpr`` ;
    ``detailed_analyses`` demande le mode détaillé (le défaut est le mode
    rapide, ici comme en ligne de commande, D-224).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    normalization: str | None = Field(default=None, max_length=128)
    char_exclude: str | None = Field(default=None, max_length=512)
    metric_profile: str | None = Field(default=None, max_length=64)
    archaic_list: str | None = Field(default=None, max_length=64)
    detailed_analyses: bool = False


@dataclass(frozen=True)
class EvaluationPlan:
    """Les vues d'un run et ce que le manifeste doit dire de leur notation."""

    evaluation: EvaluationSpec
    #: Liste archaïque effective (nom + empreinte) : ``air`` l'utilise même sans
    #: choix, le manifeste la nomme donc toujours (reproductibilité).
    metadata: dict[str, str] = field(default_factory=dict)


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
            logger.warning("[evaluation_views] GT illisible ignorée : %s", exc)
            continue
        if "\n" in text.strip():
            return True
    return False


def _text_views(
    corpus: CorpusSpec, options: EvaluationOptions, metric_names: tuple[str, ...]
) -> tuple[EvaluationView, ...]:
    """``texte`` (+ ``texte (lignes)`` sous le défaut, GT à lignes)."""
    if options.normalization is not None:
        return (
            EvaluationView(
                name=TEXT_VIEW,
                candidate_types=_TEXT,
                metric_names=metric_names,
                normalization_profile=options.normalization,
                char_exclude=options.char_exclude,
            ),
        )
    main = EvaluationView(
        name=TEXT_VIEW,
        candidate_types=_TEXT,
        metric_names=metric_names,
        char_exclude=options.char_exclude,
    )
    if not ground_truth_has_lines(corpus):
        return (main,)
    # Le CER seul : c'est le chiffre que le saut de ligne change (le WER
    # découpe sur tout blanc), et chaque métrique ajoutée grossit la famille
    # de Holm du run.
    lines = EvaluationView(
        name=LINES_VIEW,
        candidate_types=_TEXT,
        metric_names=("cer",),
        normalization_profile=LINES_NORMALIZATION_PROFILE,
        char_exclude=options.char_exclude,
    )
    return (main, lines)


def _reference_view(options: EvaluationOptions) -> EvaluationView:
    """Le candidat contre une ``REFERENCE_TEXT`` (ex. OCR Gallica), par une
    projection identité ; même convention que la vue ``texte``."""
    return EvaluationView(
        name=REFERENCE_VIEW,
        candidate_types=_TEXT,
        projections_by_source_type={
            ArtifactType.REFERENCE_TEXT: ProjectionSpec(
                source_type=ArtifactType.REFERENCE_TEXT,
                target_type=ArtifactType.RAW_TEXT,
                projector_name="identity_text",
            )
        },
        metric_names=("cer", "wer", "mer"),
        ignored_dimensions=("exactitude (la référence est elle-même un OCR)",),
        # Non choisi → le défaut (D-285), pas la comparaison brute (``None``).
        normalization_profile=options.normalization or DEFAULT_NORMALIZATION_PROFILE,
        char_exclude=options.char_exclude,
    )


def _metric_names(options: EvaluationOptions) -> tuple[str, ...]:
    """Colonnes de la vue ``texte`` : le profil, plus ``air`` et ``hcpr``
    quand une liste archaïque est **choisie** — sinon ``hcpr`` doublonnerait
    ``mufi_err`` sur tout corpus médiéval."""
    profil = options.metric_profile or DEFAULT_METRIC_PROFILE
    if profil not in METRIC_PROFILES:
        raise EvaluationOptionsError(f"profil de métriques inconnu : {profil!r}.")
    noms = METRIC_PROFILES[profil]
    if options.archaic_list is not None:
        noms = (*noms, *(m for m in ("air", "hcpr") if m not in noms))
    return noms


def plan_evaluation(
    pipelines: Sequence[PipelineSpec],
    corpus: CorpusSpec,
    options: EvaluationOptions | None = None,
) -> EvaluationPlan:
    """Les vues qui notent ``pipelines`` sur ``corpus`` — la seule règle.

    Lève :class:`EvaluationOptionsError` sur un profil de normalisation, un
    profil de métriques ou une liste archaïque inconnus : jamais un défaut muet.
    """
    options = options or EvaluationOptions()
    if (
        options.normalization is not None
        and options.normalization not in NORMALIZATION_PROFILES
    ):
        raise EvaluationOptionsError(
            f"profil de normalisation inconnu : {options.normalization!r}."
        )
    try:
        archaic = resolve_archaic_list(options.archaic_list)
    except CinocError as exc:
        raise EvaluationOptionsError(str(exc)) from exc
    produits = {
        t for pipeline in pipelines for step in pipeline.steps
        for t in step.output_types
    }
    gts = {gt.type for doc in corpus.documents for gt in doc.ground_truths}
    texte = bool(produits & _TEXT)
    vues: list[EvaluationView] = []
    if texte and ArtifactType.RAW_TEXT in gts:
        vues.extend(_text_views(corpus, options, _metric_names(options)))
    if texte and ArtifactType.REFERENCE_TEXT in gts:
        vues.append(_reference_view(options))
    if ArtifactType.LAYOUT in produits & gts:
        vues.append(
            EvaluationView(
                name=STRUCTURE_VIEW,
                candidate_types=frozenset({ArtifactType.LAYOUT}),
                metric_names=_STRUCTURE_METRICS,
            )
        )
    if ArtifactType.ENTITIES in produits & gts:
        vues.append(
            EvaluationView(
                name=ENTITIES_VIEW,
                candidate_types=frozenset({ArtifactType.ENTITIES}),
                metric_names=("ner_f1", "ner_f1_exact"),
            )
        )
    if not vues and texte:
        vues.extend(_text_views(corpus, options, _metric_names(options)))
    return EvaluationPlan(
        evaluation=EvaluationSpec(
            views=tuple(vues),
            analyses="toutes" if options.detailed_analyses else None,
        ),
        metadata={
            "archaic_list": archaic.name,
            "archaic_list_hash": archaic.list_hash,
        },
    )


def metric_profile_catalog() -> tuple[dict[str, object], ...]:
    """Profils de métriques proposables — **source unique** du sélecteur de la
    page : ``standard`` (défaut) d'abord, puis les autres triés, chacun avec la
    liste **ordonnée** de ses métriques."""
    autres = sorted(n for n in METRIC_PROFILES if n != DEFAULT_METRIC_PROFILE)
    return tuple(
        {"name": nom, "metrics": list(METRIC_PROFILES[nom])}
        for nom in (DEFAULT_METRIC_PROFILE, *autres)
    )


__all__ = [
    "DEFAULT_METRIC_PROFILE",
    "ENTITIES_VIEW",
    "LINES_NORMALIZATION_PROFILE",
    "LINES_VIEW",
    "METRIC_PROFILES",
    "REFERENCE_VIEW",
    "STRUCTURE_VIEW",
    "TEXT_VIEW",
    "EvaluationOptions",
    "EvaluationOptionsError",
    "EvaluationPlan",
    "ground_truth_has_lines",
    "metric_profile_catalog",
    "plan_evaluation",
]

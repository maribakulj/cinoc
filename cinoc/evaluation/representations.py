"""Chargement d'un artefact vers sa représentation comparable.

Le runner compare des **représentations** (``str`` pour le texte), pas des
artefacts bruts. Charge aujourd'hui le texte (``RAW_TEXT``/``CORRECTED_TEXT``) via
la couche 2 ; les autres types (``LAYOUT``…) arrivent avec leur tranche.
"""

from __future__ import annotations

from pathlib import Path

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import FormatError
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.layout import CanonicalLayout
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.ner import EntitySet, parse_entities
from cinoc.formats.layout_xml import layout_xml_kind, parse_layout_xml
from cinoc.formats.text import (
    NormalizationProfile,
    get_builtin_profile,
    read_plaintext,
)

_TEXT_TYPES = frozenset(
    {
        ArtifactType.RAW_TEXT,
        ArtifactType.CORRECTED_TEXT,
        ArtifactType.REFERENCE_TEXT,
    }
)


def load_representation(uri: str, artifact_type: ArtifactType) -> object:
    """Charge le contenu pointé par ``uri`` dans sa représentation comparable."""
    try:
        data = Path(uri).read_bytes()
    except OSError as exc:
        raise EvaluationError(
            f"représentation illisible ({artifact_type.value}) : "
            f"{uri!r} ({exc})."
        ) from exc
    if artifact_type in _TEXT_TYPES:
        try:
            return read_plaintext(data)
        except UnicodeDecodeError as exc:
            # Un octet non UTF-8 rend la sortie (ou la vérité terrain)
            # illisible : un fait de l'unité, jamais la perte du run (D9).
            raise EvaluationError(
                f"texte non UTF-8 ({artifact_type.value}) : {uri!r} ({exc})."
            ) from exc
    if artifact_type is ArtifactType.LAYOUT:
        return _load_layout(uri, data)
    if artifact_type is ArtifactType.ENTITIES:
        return _load_entities(uri, data)
    raise EvaluationError(
        f"représentation non chargeable pour le type {artifact_type.value!r}."
    )


def _load_layout(uri: str, data: bytes) -> CanonicalLayout:
    """Charge un ``CanonicalLayout`` depuis du JSON natif, de l'ALTO ou du PAGE.

    XML (premier octet non-blanc ``<``) → ALTO ou PAGE selon le marqueur de
    racine (``PcGts``/``pagecontent`` = PAGE, sinon ALTO) ; autrement JSON
    sérialisé d'un ``CanonicalLayout``.
    """
    if data.lstrip()[:1] == b"<":
        try:
            return parse_layout_xml(data)
        except (ValueError, FormatError) as exc:
            raise EvaluationError(
                f"{layout_xml_kind(data)} illisible en layout ({uri!r}) : {exc}"
            ) from exc
    try:
        return CanonicalLayout.model_validate_json(data)
    except ValueError as exc:
        raise EvaluationError(f"CanonicalLayout invalide ({uri!r}) : {exc}") from exc


def _load_entities(uri: str, data: bytes) -> EntitySet:
    """Charge un ``EntitySet`` depuis un sidecar ``{"text", "entities"}``."""
    try:
        return parse_entities(data)
    except EvaluationError as exc:
        raise EvaluationError(f"entités illisibles ({uri!r}) : {exc}") from exc


def view_profile(view: EvaluationView) -> NormalizationProfile | None:
    """Le profil que la vue applique ; ``None`` = comparaison brute.

    Un nom inconnu lève ``EvaluationError`` : il n'y a pas de repli silencieux
    sur un autre profil. Le rapport le lit ici pour **dire** la convention
    (D-285) — la même résolution que celle qui a préparé les textes.
    """
    if view.normalization_profile is None:
        return None
    try:
        return get_builtin_profile(view.normalization_profile)
    except KeyError as exc:
        raise EvaluationError(str(exc)) from exc


def prepare_text(text: str, view: EvaluationView) -> str:
    """Applique la normalisation de la vue (profil + ``char_exclude``) à un texte.

    **La** définition de « préparé comme au scoring » : le runner et les
    analyses qui chargent leurs propres textes (bilan de correction) passent
    par ici — une seule implémentation, symétrique GT/hypothèse.
    """
    profile = view_profile(view)
    if profile is not None:
        text = profile.normalize(text)
    if view.char_exclude:
        excluded = set(view.char_exclude)
        text = "".join(char for char in text if char not in excluded)
    return text


__all__ = ["load_representation", "prepare_text", "view_profile"]

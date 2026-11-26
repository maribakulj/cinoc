"""Caractères archaïques : listes nommées, empreinte, ``air``/``hcpr`` (couche 3).

Deux mesures **bidirectionnelles** sur une **liste configurable de caractères
archaïques** (formes historiques : ``ſ`` s long, abréviations rotunda, thorn…) :

- **``hcpr``** (*Historical Character Preservation Rate*, Levchenko 2025) — taux
  de **préservation** : parmi les caractères de la liste présents dans la GT,
  combien survivent dans la sortie. Généralisation paramétrable de
  ``diacritic_err``/``mufi_err`` (même moteur :mod:`preservation` — parité
  bit-à-bit), mais **côté préservation** et sur une liste **choisie**, pas une
  plage figée.
- **``air``** (*Archaism Insertion Rate*, Levchenko 2025) — **l'apport net** :
  parmi les caractères de la liste présents dans la **sortie**, combien sont
  *ajoutés* (à une position non fidèle à la GT). Détecte la **sur-historicisation**
  — un VLM/LLM qui « archaïse » un texte que la GT écrit en clair. C'est la mesure
  que ``mufi_err`` ne porte pas : elle regarde la sortie, pas la référence.

**Dénominateur d'``air``** (décision de build, bornée [0,1]) : nombre
d'occurrences de la liste **dans la sortie** ; numérateur = celles tombant sur une
position **non couverte par un opcode ``equal``** (donc insérée ou substituée —
non recopiée fidèlement de la GT). ``air = ajoutées / total_sortie`` ∈ [0,1].
``None`` si la sortie ne porte **aucun** caractère de la liste (rien à juger).

**Liste par défaut ``archaic_core``** (Q4, trans-langue, sans ambiguïté de langue
moderne) : ``ſ ꝛ ⁊ ꝑ ꝓ ꝗ ꝙ ꝯ ꝝ ꝫ ꝭ þ ð ȝ`` + la **marque combinante** ``U+0364``
(``◌ͤ`` e suscrit) qui forme ``aͤ oͤ uͤ`` — la marque **est** le trait archaïque,
captée quel que soit le caractère de base (les séquences ``aͤ/oͤ/uͤ`` n'ont pas de
forme pré-composée, elles restent décomposées : matcher la marque suffit et reste
au niveau codepoint, comme le moteur de préservation). ``œ æ ß ç`` et les accents
modernes sont **exclus** du défaut (relatifs à une langue : « cœur » moderne →
faux positif ``air`` ; leur perte relève déjà de ``diacritic_err``).

Reproductibilité : chaque liste a un **nom** et une **empreinte** SHA-256 de ses
codepoints, inscrits au ``RunManifest`` et au rapport (deux runs même liste → même
empreinte ; listes différentes → empreintes différentes).
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from dataclasses import dataclass

from rapidfuzz.distance import Levenshtein

from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import Observation
from cinoc.evaluation.preservation import preservation_counts

#: ``◌ͤ`` (U+0364, combining latin small letter e) — marque suscrite des formes
#: ``aͤ oͤ uͤ`` ; représente la famille à elle seule (pas de pré-composé).
_E_ABOVE = "ͤ"

#: Listes nommées, **données** de package (≠ surface exécutable, comme les profils
#: de normalisation). ``archaic_core`` est le seul socle livré (Q4) ; l'enveloppe
#: porte plusieurs listes nommées, la surface n'en remplit qu'une (axe 2). Ajouter
#: une liste curée = une entrée ici (aucune dette spéculative — on ne livre pas de
#: liste sans consommateur).
ARCHAIC_LISTS: dict[str, tuple[str, ...]] = {
    "archaic_core": (
        "ſ",  # U+017F long s
        "ꝛ",  # U+A75B r rotunda
        "⁊",  # U+204A tironian et
        "ꝑ",  # U+A751 p with stroke through descender (per/par)
        "ꝓ",  # U+A753 p with flourish (pro)
        "ꝗ",  # U+A757 q with stroke through descender (qui)
        "ꝙ",  # U+A759 q with diagonal stroke (quia)
        "ꝯ",  # U+A76F con/us abbreviation
        "ꝝ",  # U+A75D rum rotunda
        "ꝫ",  # U+A76B et abbreviation
        "ꝭ",  # U+A76D is abbreviation
        "þ",  # U+00FE thorn
        "ð",  # U+00F0 eth
        "ȝ",  # U+021D yogh
        _E_ABOVE,  # aͤ oͤ uͤ via la marque suscrite
    ),
}

#: Liste active par défaut : ``air`` la mesure d'office (Q4) ; ``hcpr`` n'apparaît
#: que sur une liste **explicitement** configurée (anti-colonne-jumelle de
#: ``mufi_err`` — cf. :mod:`cinoc.app.evaluation_views`).
DEFAULT_ARCHAIC_LIST = "archaic_core"


def archaic_list_hash(chars: Iterable[str]) -> str:
    """Empreinte SHA-256 **déterministe** d'un jeu de caractères archaïques.

    Sur les codepoints **uniques triés** : indépendante de l'ordre/des doublons de
    déclaration (même contenu → même empreinte), sensible au moindre ajout/retrait.
    """
    payload = "".join(sorted(set(chars)))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResolvedArchaicList:
    """Liste archaïque résolue : nom curé + caractères + empreinte (manifeste)."""

    name: str
    chars: frozenset[str]
    list_hash: str


def resolve_archaic_list(name: str | None = None) -> ResolvedArchaicList:
    """Résout une liste **nommée** (défaut ``archaic_core``). Fail-closed.

    Un nom inconnu lève ``EvaluationError`` (jamais un repli silencieux sur le
    défaut : une liste mal nommée fausserait ``air``/``hcpr`` sans le dire).
    """
    effective = name or DEFAULT_ARCHAIC_LIST
    if effective not in ARCHAIC_LISTS:
        known = ", ".join(sorted(ARCHAIC_LISTS))
        raise EvaluationError(
            f"liste archaïque inconnue : {effective!r} (connues : {known})."
        )
    chars = frozenset(ARCHAIC_LISTS[effective])
    return ResolvedArchaicList(
        name=effective, chars=chars, list_hash=archaic_list_hash(chars)
    )


def hcpr_observation(
    reference: str, hypothesis: str, chars: frozenset[str]
) -> Observation | None:
    """Taux de **préservation** des caractères de la liste présents dans la GT.

    ``(n_total − n_wrong) / n_total`` sur les comptes du moteur partagé (parité
    ``diacritic_err``/``mufi_err``). ``None`` si la GT n'en porte aucun.
    """
    counts = preservation_counts(reference, hypothesis, lambda ch: ch in chars)
    if counts is None:
        return None
    n_total, n_wrong = counts
    return Observation(value=(n_total - n_wrong) / n_total, weight=n_total)


def air_observation(
    reference: str, hypothesis: str, chars: frozenset[str]
) -> Observation | None:
    """**Apport net** d'archaïsmes : part des caractères de la liste **insérés**.

    Dénominateur = occurrences de la liste dans la **sortie** ; numérateur = celles
    à une position **non** couverte par un opcode ``equal`` (insérée ou substituée,
    donc non recopiée fidèlement de la GT). Borné [0,1]. ``None`` si la sortie n'en
    porte aucun.
    """
    targets = [j for j, char in enumerate(hypothesis) if char in chars]
    if not targets:
        return None
    faithful: set[int] = set()
    for op in Levenshtein.opcodes(reference, hypothesis):
        if op.tag == "equal":
            faithful.update(range(op.dest_start, op.dest_end))
    added = sum(1 for j in targets if j not in faithful)
    return Observation(value=added / len(targets), weight=len(targets))


__all__ = [
    "ARCHAIC_LISTS",
    "DEFAULT_ARCHAIC_LIST",
    "ResolvedArchaicList",
    "air_observation",
    "archaic_list_hash",
    "hcpr_observation",
    "resolve_archaic_list",
]

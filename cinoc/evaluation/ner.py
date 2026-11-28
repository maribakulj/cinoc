"""Précision sur entités nommées : appariement IoU + reprojection R14 (couche 3).

Pour un médiéviste ou un archiviste, l'utilité aval d'un OCR ne se mesure pas
qu'au CER : ce qui compte est la **survie des entités nommées** (personnes,
lieux, dates). Un CER de 5 % qui rate 80 % des noms propres est inutilisable en
indexation prosopographique.

**Réparation R14 (bug C9 de la source).** Les entités GT portent des offsets
sur le **texte GT** ; les entités hypothèse, des offsets sur le **texte OCR**.
Comparer leurs spans par IoU sans rien faire revient à comparer deux systèmes
de coordonnées : toute insertion/délétion amont décale les offsets aval, et une
entité **parfaitement transcrite** est comptée « manquée + hallucinée » dès que
le drift dépasse sa longueur — le F1 mesure alors le profil ins/del de l'OCR,
pas la préservation des entités. Avant l'IoU, on **reprojette** les spans
hypothèse en coordonnées GT via un alignement caractère ``rapidfuzz`` (la
mécanique des marqueurs positionnels), puis on apparie.

Le format d'entités embarque donc **le texte de référence des offsets** :
``{"text": str, "entities": [{"label", "start", "end", "text"?}]}``. La GT et la
sortie le portent toutes deux — c'est ce qui rend la reprojection auto-suffisante
(≠ source : la tolérance « liste nue sans texte » est abandonnée, R14 l'exige).

Limite assumée : la métrique mesure **conjointement** OCR + modèle NER (un
extracteur hallucine aussi) — documenté dans la section.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz.distance import Levenshtein

from cinoc.evaluation.analysis import (
    Analysis,
    EntityCategoryScore,
    EntityMention,
    NerPayload,
    PipelineNer,
)
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.statistics import MatchCounts, f1, precision, recall

#: Seuil d'IoU pour qu'un appariement compte. Convention **de Cinoc** — ni
#: celle de CoNLL (empans exacts), ni celles de HIPE (strict : empans exacts ;
#: fuzzy : tout recouvrement) : la mention « CoNLL/HIPE » qu'elle portait était
#: inexacte (D-288).
DEFAULT_IOU_THRESHOLD = 0.5

#: Échantillons d'entités embarqués dans le payload (bornent la sortie).
_MAX_MISSED = 20
_MAX_HALLUCINATED = 20


@dataclass(frozen=True)
class Entity:
    """Entité nommée : label + span caractère ``[start, end)`` + forme de surface.

    ``text`` est **informatif** — jamais utilisé pour l'appariement (deux
    entités matchent par recouvrement de spans, pas par égalité de surface).
    """

    label: str
    start: int
    end: int
    text: str = ""

    def __post_init__(self) -> None:
        if self.start < 0 or self.start > self.end:
            raise EvaluationError(
                f"span d'entité invalide : start={self.start}, end={self.end}."
            )

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class EntitySet:
    """Un texte + les entités dont les offsets s'y rapportent.

    Bundler le texte rend la reprojection R14 auto-suffisante : chaque côté
    sait à quoi ses offsets réfèrent.
    """

    text: str
    entities: tuple[Entity, ...]


def parse_entities(data: bytes) -> EntitySet:
    """Parse un sidecar entités ``{"text", "entities"}`` ; lève si malformé.

    Anti-silence : un format invalide est une **erreur typée**, jamais un skip
    muet (le défaut de la source qui renvoyait ``[]`` → rappel 0 sans message).
    """
    try:
        payload = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EvaluationError(f"entités illisibles (JSON) : {exc}") from exc
    if not isinstance(payload, dict) or "text" not in payload:
        raise EvaluationError(
            "entités : objet {\"text\", \"entities\"} attendu "
            "(la liste nue sans texte n'est pas acceptée — R14 exige le texte)."
        )
    text = payload["text"]
    raw_entities = payload.get("entities", [])
    if not isinstance(text, str) or not isinstance(raw_entities, list):
        raise EvaluationError("entités : 'text' (str) et 'entities' (list) requis.")
    entities: list[Entity] = []
    for item in raw_entities:
        if not isinstance(item, dict):
            raise EvaluationError(f"entité : objet attendu, reçu {type(item)}.")
        try:
            entities.append(
                Entity(
                    label=str(item["label"]),
                    start=int(item["start"]),
                    end=int(item["end"]),
                    text=str(item.get("text", "")),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise EvaluationError(f"entité invalide ({item!r}) : {exc}") from exc
    return EntitySet(text=text, entities=tuple(entities))


def build_position_map(reference: str, hypothesis: str) -> list[int]:
    """``hyp_index → ref_index`` (longueur ``len(hypothesis) + 1``) — cœur de R14.

    Aligne ``reference`` (a) et ``hypothesis`` (b) au caractère ; chaque position
    de l'hypothèse reçoit la position GT correspondante. ``equal`` → 1:1 ;
    ``replace`` → linéaire clampé ; ``insert`` (caractère OCR sans contrepartie
    GT) → effondré sur la frontière GT ; ``delete`` → aucune position hyp à
    remplir. Le sentinelle final mappe ``len(hyp) → len(ref)`` (borne d'un span
    exclusif).
    """
    pos = [0] * (len(hypothesis) + 1)
    for op in Levenshtein.opcodes(reference, hypothesis):
        i1, i2, j1, j2 = op.src_start, op.src_end, op.dest_start, op.dest_end
        if op.tag == "equal":
            for k in range(j2 - j1):
                pos[j1 + k] = i1 + k
        elif op.tag == "replace":
            for k in range(j2 - j1):
                pos[j1 + k] = min(i1 + k, i2)
        elif op.tag == "insert":
            for k in range(j2 - j1):
                pos[j1 + k] = i1
        # delete : i1<i2, j1==j2 — pas de position hypothèse à remplir.
    pos[len(hypothesis)] = len(reference)
    return pos


def remap_entities(
    entities: tuple[Entity, ...], position_map: list[int]
) -> list[Entity]:
    """Reprojette des spans hypothèse en coordonnées GT via ``position_map``."""
    remapped: list[Entity] = []
    for entity in entities:
        start = position_map[entity.start]
        end = max(start, position_map[entity.end])
        remapped.append(
            Entity(label=entity.label, start=start, end=end, text=entity.text)
        )
    return remapped


def _iou(a: Entity, b: Entity) -> float:
    inter = max(0, min(a.end, b.end) - max(a.start, b.start))
    union = a.length + b.length - inter
    return inter / union if union > 0 else 0.0


def align_entities(
    references: list[Entity], hypotheses: list[Entity], iou_threshold: float
) -> tuple[list[tuple[int, int]], set[int], set[int]]:
    """Appariement glouton par IoU décroissant (chaque entité appariée ≤ 1 fois).

    Renvoie ``(matches, unmatched_refs, unmatched_hyps)`` ; ``matches`` = paires
    ``(ref_idx, hyp_idx)``. Labels comparés **casefold** ; tri déterministe
    ``(−iou, ref_idx, hyp_idx)``.
    """
    candidates: list[tuple[float, int, int]] = []
    for i, ref in enumerate(references):
        for j, hyp in enumerate(hypotheses):
            if ref.label.casefold() != hyp.label.casefold():
                continue
            score = _iou(ref, hyp)
            if score >= iou_threshold:
                candidates.append((score, i, j))
    candidates.sort(key=lambda c: (-c[0], c[1], c[2]))
    matched_refs: set[int] = set()
    matched_hyps: set[int] = set()
    matches: list[tuple[int, int]] = []
    for _score, i, j in candidates:
        if i in matched_refs or j in matched_hyps:
            continue
        matched_refs.add(i)
        matched_hyps.add(j)
        matches.append((i, j))
    unmatched_refs = set(range(len(references))) - matched_refs
    unmatched_hyps = set(range(len(hypotheses))) - matched_hyps
    return matches, unmatched_refs, unmatched_hyps


@dataclass(frozen=True)
class NerCounts:
    """Comptes d'appariement d'un document (accumulables sur un corpus)."""

    tp: int
    fp: int
    fn: int
    cat_tp: Counter[str]
    cat_fp: Counter[str]
    cat_fn: Counter[str]
    missed: list[Entity]
    hallucinated: list[Entity]
    #: Appariés dont la **forme écrite** dans la sortie est celle de la GT,
    #: caractère pour caractère (``ner_f1_exact``) ; ``≤ tp``.
    tp_exact: int = 0


def _surface(entity_set: EntitySet, entity: Entity) -> str:
    """Forme écrite d'une entité, lue à ses offsets dans **son** texte."""
    return entity_set.text[entity.start : entity.end]


def compute_ner(
    reference: EntitySet,
    hypothesis: EntitySet,
    iou_threshold: float = DEFAULT_IOU_THRESHOLD,
) -> NerCounts:
    """Apparie les entités après reprojection R14 ; renvoie les comptes du doc."""
    position_map = build_position_map(reference.text, hypothesis.text)
    hyps = remap_entities(hypothesis.entities, position_map)
    refs = list(reference.entities)
    matches, unmatched_refs, unmatched_hyps = align_entities(
        refs, hyps, iou_threshold
    )
    cat_tp: Counter[str] = Counter(refs[i].label for i, _ in matches)
    cat_fn: Counter[str] = Counter(refs[i].label for i in unmatched_refs)
    cat_fp: Counter[str] = Counter(hyps[j].label for j in unmatched_hyps)
    # La forme se lit aux offsets **d'origine** de la sortie (avant R14) : le
    # span reprojeté est en coordonnées GT, pas dans le texte du moteur.
    tp_exact = sum(
        1
        for i, j in matches
        if _surface(hypothesis, hypothesis.entities[j])
        == _surface(reference, refs[i])
    )
    return NerCounts(
        tp=len(matches),
        fp=len(unmatched_hyps),
        fn=len(unmatched_refs),
        cat_tp=cat_tp,
        cat_fp=cat_fp,
        cat_fn=cat_fn,
        missed=[refs[i] for i in sorted(unmatched_refs)],
        hallucinated=[hyps[j] for j in sorted(unmatched_hyps)],
        tp_exact=tp_exact,
    )


@dataclass
class _PipelineAccumulator:
    """Comptes NER cumulés d'un pipeline sur le corpus."""

    tp: int = 0
    fp: int = 0
    fn: int = 0
    cat_tp: Counter[str] = field(default_factory=Counter)
    cat_fp: Counter[str] = field(default_factory=Counter)
    cat_fn: Counter[str] = field(default_factory=Counter)
    missed: list[Entity] = field(default_factory=list)
    hallucinated: list[Entity] = field(default_factory=list)


class EntitiesCollector:
    """Accumule les appariements NER (avec R14) au fil du scoring d'une vue."""

    def __init__(self, iou_threshold: float = DEFAULT_IOU_THRESHOLD) -> None:
        self._threshold = iou_threshold
        self._pipelines: dict[str, _PipelineAccumulator] = {}

    def observe(
        self, pipeline: str, reference: EntitySet, hypothesis: EntitySet
    ) -> None:
        counts = compute_ner(reference, hypothesis, self._threshold)
        acc = self._pipelines.setdefault(pipeline, _PipelineAccumulator())
        acc.tp += counts.tp
        acc.fp += counts.fp
        acc.fn += counts.fn
        acc.cat_tp.update(counts.cat_tp)
        acc.cat_fp.update(counts.cat_fp)
        acc.cat_fn.update(counts.cat_fn)
        acc.missed.extend(counts.missed[: _MAX_MISSED - len(acc.missed)])
        acc.hallucinated.extend(
            counts.hallucinated[: _MAX_HALLUCINATED - len(acc.hallucinated)]
        )

    def build(self, view: str) -> Analysis | None:
        """Payload ``ner`` de la vue ; ``None`` si aucune entité GT observée."""
        rows = [
            self._row(pipeline)
            for pipeline in sorted(self._pipelines)
            if self._pipelines[pipeline].tp + self._pipelines[pipeline].fn > 0
        ]
        if not rows:
            return None
        return Analysis(
            scope="corpus",
            view=view,
            payload=NerPayload(iou_threshold=self._threshold, pipelines=tuple(rows)),
        )

    def _row(self, pipeline: str) -> PipelineNer:
        acc = self._pipelines[pipeline]
        total = MatchCounts(tp=acc.tp, fp=acc.fp, fn=acc.fn)
        categories = sorted(set(acc.cat_tp) | set(acc.cat_fp) | set(acc.cat_fn))
        per_category: list[EntityCategoryScore] = []
        for label in categories:
            # Une catégorie seulement prédite (support 0) : P = 0, R indéfini —
            # le scalaire indéfini se dit ``None``, jamais un faux 0 ni une
            # erreur (M3).
            counts = MatchCounts(
                tp=acc.cat_tp[label], fp=acc.cat_fp[label], fn=acc.cat_fn[label]
            )
            per_category.append(
                EntityCategoryScore(
                    label=label,
                    precision=precision(counts).value,
                    recall=recall(counts).value,
                    f1=f1(counts).value,
                    support=counts.tp + counts.fn,
                )
            )
        return PipelineNer(
            pipeline=pipeline,
            n_reference=acc.tp + acc.fn,
            true_positives=acc.tp,
            false_positives=acc.fp,
            false_negatives=acc.fn,
            precision=precision(total).value,
            # Une ligne n'existe qu'avec des entités GT (tp + fn ≥ 1) : rappel
            # et F1 y sont toujours définis.
            recall=acc.tp / (acc.tp + acc.fn),
            f1=2 * acc.tp / (2 * acc.tp + acc.fp + acc.fn),
            per_category=tuple(per_category),
            missed=tuple(
                EntityMention(label=e.label, text=e.text[:128]) for e in acc.missed
            ),
            hallucinated=tuple(
                EntityMention(label=e.label, text=e.text[:128])
                for e in acc.hallucinated
            ),
        )


__all__ = [
    "DEFAULT_IOU_THRESHOLD",
    "EntitiesCollector",
    "Entity",
    "EntitySet",
    "NerCounts",
    "align_entities",
    "build_position_map",
    "compute_ner",
    "parse_entities",
    "remap_entities",
]

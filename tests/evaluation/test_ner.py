"""NER : appariement IoU, reprojection R14, PRF (valeurs dérivées à la main).

R14 = la réparation centrale : sans reprojection, une entité parfaitement
transcrite mais décalée par un insert OCR amont est comptée « manquée +
hallucinée » ; avec, elle reste un vrai positif. Le test le prouve dans les deux
sens (le span brut échouerait l'IoU, le span reprojeté réussit).
"""

from __future__ import annotations

import json

import pytest

from cinoc.evaluation.analysis import NerPayload
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.ner import (
    EntitiesCollector,
    Entity,
    EntitySet,
    align_entities,
    build_position_map,
    compute_ner,
    parse_entities,
    prf,
    remap_entities,
)


def _es(text: str, *entities: tuple[str, int, int]) -> EntitySet:
    return EntitySet(
        text=text,
        entities=tuple(
            Entity(label=lab, start=s, end=e, text=text[s:e]) for lab, s, e in entities
        ),
    )


class TestParseEntities:
    def test_parses_text_and_entities(self) -> None:
        data = json.dumps(
            {"text": "Marie", "entities": [{"label": "PER", "start": 0, "end": 5}]}
        ).encode()
        result = parse_entities(data)
        assert result.text == "Marie"
        (entity,) = result.entities
        assert (entity.label, entity.start, entity.end) == ("PER", 0, 5)

    def test_bare_list_without_text_is_rejected(self) -> None:
        # R14 exige le texte : la liste nue de la source n'est pas acceptée.
        with pytest.raises(EvaluationError, match="texte"):
            parse_entities(
                json.dumps([{"label": "PER", "start": 0, "end": 5}]).encode()
            )

    def test_malformed_json_raises(self) -> None:
        with pytest.raises(EvaluationError, match="JSON"):
            parse_entities(b"{not json")

    def test_invalid_entity_raises_not_skips(self) -> None:
        # Anti-silence : une entité invalide lève (≠ source qui renvoyait []).
        data = json.dumps({"text": "x", "entities": [{"label": "PER"}]}).encode()
        with pytest.raises(EvaluationError):
            parse_entities(data)

    def test_negative_span_rejected(self) -> None:
        with pytest.raises(EvaluationError, match="span"):
            Entity(label="PER", start=5, end=2)


class TestPositionMapAndRemap:
    def test_identity_when_texts_equal(self) -> None:
        text = "Marie de Bourgogne"
        pos = build_position_map(text, text)
        assert pos == list(range(len(text) + 1))

    def test_insert_shifts_back_to_gt_coords(self) -> None:
        # OCR a 5 caractères en trop au début ; "Bourgogne" est à [14,23) côté
        # OCR mais [9,18) côté GT → la reprojection le ramène exactement.
        gt = "Marie de Bourgogne"
        ocr = "XXXXXMarie de Bourgogne"
        pos = build_position_map(gt, ocr)
        assert pos[14] == 9 and pos[23] == 18
        (remapped,) = remap_entities(
            (Entity(label="LOC", start=14, end=23, text="Bourgogne"),), pos
        )
        assert (remapped.start, remapped.end) == (9, 18)

    def test_sentinel_maps_to_reference_length(self) -> None:
        pos = build_position_map("abc", "abcdef")
        assert pos[6] == 3  # len(hyp) → len(ref)


class TestAlignAndCompute:
    def test_iou_threshold_and_label_casefold(self) -> None:
        refs = [Entity("PER", 0, 10), Entity("LOC", 20, 30)]
        # hyp 0 overlaps ref0 at IoU 0.8 (label 'per' casefold) ; hyp 1 wrong label.
        hyps = [Entity("per", 1, 9), Entity("ORG", 20, 30)]
        matches, unmatched_refs, unmatched_hyps = align_entities(refs, hyps, 0.5)
        assert matches == [(0, 0)]
        assert unmatched_refs == {1} and unmatched_hyps == {1}

    def test_r14_turns_a_miss_into_a_true_positive(self) -> None:
        # GT entity "Bourgogne" [9,18) ; hyp entity on OCR text [14,23). Raw IoU
        # = 4/14 ≈ 0.29 < 0.5 (would be missed+hallucinated). After R14 → TP.
        gt = _es("Marie de Bourgogne", ("LOC", 9, 18))
        ocr = "XXXXXMarie de Bourgogne"
        hyp = EntitySet(text=ocr, entities=(Entity("LOC", 14, 23, "Bourgogne"),))
        # Raw (no remap) would fail:
        from cinoc.evaluation.ner import _iou

        assert _iou(gt.entities[0], hyp.entities[0]) == pytest.approx(4 / 14)
        # With remap (compute_ner) → TP.
        counts = compute_ner(gt, hyp)
        assert (counts.tp, counts.fp, counts.fn) == (1, 0, 0)

    def test_prf_hand_derived(self) -> None:
        # 3 GT (2 PER, 1 LOC). hyp: PER0 matches, PER1 wrong label, LOC matches,
        # 1 extra ORG hallucinated. TP=2, FP(label-mismatch PER1? no — it's a
        # hyp with PER label at LOC position) → keep it simple, build explicit.
        gt = _es("aaaa bbbb cccc", ("PER", 0, 4), ("PER", 5, 9), ("LOC", 10, 14))
        hyp = EntitySet(
            text="aaaa bbbb cccc",
            entities=(
                Entity("PER", 0, 4),  # TP
                Entity("LOC", 10, 14),  # TP
                Entity("ORG", 5, 9),  # FP (label≠PER) ; PER1 → FN
            ),
        )
        counts = compute_ner(gt, hyp)
        assert (counts.tp, counts.fp, counts.fn) == (2, 1, 1)
        precision, recall, f1 = prf(counts.tp, counts.fp, counts.fn)
        assert precision == pytest.approx(2 / 3)
        assert recall == pytest.approx(2 / 3)
        assert f1 == pytest.approx(2 / 3)

    def test_per_category_counts(self) -> None:
        gt = _es("aaaa bbbb", ("PER", 0, 4), ("LOC", 5, 9))
        hyp = _es("aaaa bbbb", ("PER", 0, 4))  # LOC missed
        counts = compute_ner(gt, hyp)
        assert counts.cat_tp["PER"] == 1
        assert counts.cat_fn["LOC"] == 1
        assert [e.label for e in counts.missed] == ["LOC"]

    def test_empty_gt_has_no_tp_or_fn(self) -> None:
        gt = _es("aaaa")  # no entities
        hyp = _es("aaaa", ("PER", 0, 4))
        counts = compute_ner(gt, hyp)
        assert (counts.tp, counts.fn) == (0, 0)
        assert counts.fp == 1  # the hyp is hallucinated


class TestEntitiesCollector:
    def test_micro_aggregate_and_payload(self) -> None:
        collector = EntitiesCollector()
        # doc1: 1 PER matched, 1 LOC missed. doc2: 1 PER matched.
        collector.observe(
            "alpha",
            _es("aaaa bbbb", ("PER", 0, 4), ("LOC", 5, 9)),
            _es("aaaa bbbb", ("PER", 0, 4)),
        )
        collector.observe(
            "alpha", _es("cccc", ("PER", 0, 4)), _es("cccc", ("PER", 0, 4))
        )
        analysis = collector.build("text")
        assert analysis is not None
        payload = analysis.payload
        assert isinstance(payload, NerPayload)
        assert payload.iou_threshold == 0.5
        (row,) = payload.pipelines
        assert row.pipeline == "alpha"
        assert row.n_reference == 3  # 2 PER + 1 LOC
        assert (
            row.true_positives,
            row.false_positives,
            row.false_negatives,
        ) == (2, 0, 1)
        assert row.precision == pytest.approx(1.0)
        assert row.recall == pytest.approx(2 / 3)
        cats = {c.label: c for c in row.per_category}
        assert cats["PER"].recall == 1.0 and cats["PER"].support == 2
        assert cats["LOC"].recall == 0.0 and cats["LOC"].support == 1
        assert [m.label for m in row.missed] == ["LOC"]

    def test_pipeline_without_gt_entities_excluded(self) -> None:
        collector = EntitiesCollector()
        collector.observe("alpha", _es("aaaa"), _es("aaaa", ("PER", 0, 4)))
        assert collector.build("text") is None

    def test_pipelines_sorted(self) -> None:
        collector = EntitiesCollector()
        per = ("PER", 0, 4)
        collector.observe("beta", _es("aaaa", per), _es("aaaa", per))
        collector.observe("alpha", _es("aaaa", ("PER", 0, 4)), _es("aaaa"))
        analysis = collector.build("text")
        assert analysis is not None
        assert [r.pipeline for r in analysis.payload.pipelines] == ["alpha", "beta"]


class TestExactName:
    """Variante « nom exact » (D-288) : ``ner_f1`` apparie par recouvrement
    d'empans et ne lit pas la forme écrite — « Montfort » lu « Montfert » au
    même endroit compte juste. ``ner_f1_exact`` exige la forme de la GT."""

    def _pair(self, written: str) -> tuple[EntitySet, EntitySet]:
        gt = _es("Jehan de Montfort vint", ("PER", 0, 17))
        hyp = _es(f"Jehan de {written} vint", ("PER", 0, 9 + len(written)))
        return gt, hyp

    def test_misread_name_counts_for_span_f1_not_for_exact(self) -> None:
        from cinoc.evaluation.context import DocContext
        from cinoc.evaluation.metrics.ner import ner_f1, ner_f1_exact

        gt, hyp = self._pair("Montfert")
        ctx = DocContext(document_id="d", reference=gt, hypothesis=hyp)
        span, exact = ner_f1.fn(ctx), ner_f1_exact.fn(ctx)
        assert span is not None and span.value == 1.0
        assert exact is not None and exact.value == 0.0
        assert exact.weight == 1
        counts = compute_ner(gt, hyp)
        assert (counts.tp, counts.tp_exact) == (1, 0)

    def test_exact_name_counts_for_both(self) -> None:
        from cinoc.evaluation.context import DocContext
        from cinoc.evaluation.metrics.ner import ner_f1, ner_f1_exact

        # Le nom est exact mais décalé par un insert OCR amont : R14 le
        # reprojette, et sa forme est lue à ses offsets dans **la sortie**.
        gt = _es("Jehan de Montfort vint", ("PER", 0, 17))
        hyp = _es("XX Jehan de Montfort vint", ("PER", 3, 20))
        ctx = DocContext(document_id="d", reference=gt, hypothesis=hyp)
        assert ner_f1.fn(ctx).value == 1.0  # type: ignore[union-attr]
        assert ner_f1_exact.fn(ctx).value == 1.0  # type: ignore[union-attr]

    def test_misread_name_is_both_missed_and_spurious(self) -> None:
        # Deux entités, une seule exacte : TP 1, FP 1, FN 1 → F1 = 0,5.
        from cinoc.evaluation.context import DocContext
        from cinoc.evaluation.metrics.ner import ner_f1_exact

        gt = _es("Jehan de Montfort et Marie", ("PER", 0, 17), ("PER", 21, 26))
        hyp = _es("Jehan de Montfert et Marie", ("PER", 0, 17), ("PER", 21, 26))
        ctx = DocContext(document_id="d", reference=gt, hypothesis=hyp)
        assert ner_f1_exact.fn(ctx).value == pytest.approx(0.5)  # type: ignore[union-attr]

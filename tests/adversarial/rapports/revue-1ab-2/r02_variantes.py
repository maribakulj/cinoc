"""R02 — Variantes non couvertes par les tests rouges.
V1 (D1) : pipeline multi-étapes seg(LAYOUT) → ocr(RAW_TEXT), une seule étape
    déclare le type de la vue ; la seg échoue sur d1. Plus un pipeline S « seg
    seule » (hors vue), qui échoue sur d0 et d2.
V2 (D1, target_step) : vue qui cible l'étape seg (LAYOUT, non candidat texte).
V3 (D2) : unité partielle ET illisible.
V4 (D10) : trois pipelines, un en échec partiel (une partielle + un échec)."""
import sys, json, tempfile
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (T, corpus, registry_with, step,
    pipeline, text_view, spec, execute, per_document)
from tests.adversarial.applicabilite_echecs._kit_revue import (BriqueOctets, layout_octets,
    LAYOUT_ILLISIBLE, vue_layout, verifie_agregat)
from cinoc.adapters.extension import AdapterStepError

def ana(r, kind):
    return [a.payload for a in r.analyses if a.payload.kind == kind]

def show(r, tag):
    pol = r.manifest.failure_policy
    print(f"[{tag}/{pol}] entrées :", [(p.pipeline, p.view) for p in r.pipelines])
    for p in r.pipelines:
        c, o = p.conditional_aggregate[0], p.operational_aggregate[0]
        print(f"   {p.pipeline}/{p.view}: cond={c.value} {c.support}/{c.expected} cov={c.coverage} | op={o.value} {o.support}/{o.expected}")
    for c in ana(r, "comparison"):
        print("   comparison", c.metric if hasattr(c, 'metric') else '', [(pp.a, pp.b, pp.micro_documents) for pp in c.pairs], "global", c.global_support.micro_documents, c.global_support.ranking)
    for i in ana(r, "inference"):
        print("   inference", i.view if hasattr(i,'view') else '', i.test, getattr(i, 'n_documents', None), i.status, getattr(i, 'pipelines', None))
    for s in r.cross_engine:
        print("   cross", s.metric, s.value, s.support, s.status)

REF = {f"d{i}": "abcdefghijklmnopqrst" for i in range(8)}
for pol in ("exclude", "empty_page"):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF)
        seg = BriqueOctets("seg", {d: (AdapterStepError("seg") if d == "d1" else layout_octets("")) for d in REF}, out_type=T.LAYOUT)
        ocr = BriqueOctets("ocr", {d: b"abcdefghijklmnopqrs#" for d in REF}, in_type=T.LAYOUT)
        segS = BriqueOctets("segS", {d: (AdapterStepError("x") if d in ("d0", "d2") else layout_octets("")) for d in REF}, out_type=T.LAYOUT)
        other = BriqueOctets("oth", {d: b"abcdefghijklmnopq###" for d in REF})
        s = spec(c, [pipeline("M", step("seg", "seg", out_type=T.LAYOUT), step("ocr", "ocr", in_type=T.LAYOUT)),
                     pipeline("S", step("seg", "segS", out_type=T.LAYOUT)),
                     pipeline("O", step("ocr", "oth"))],
                 [text_view(metrics=("cer", "wer"))], failure_policy=pol)
        r = execute(s, registry_with(seg, ocr, segS, other))
    show(r, "V1")
    print("   M d1 axes:", [(x.applicability, x.availability, x.validity, x.stat_vide) for x in [per_document(r, "M", "d1")]])
    print("   S d0 axes:", [(x.applicability, x.availability, x.validity, x.stat_vide) for x in [per_document(r, "S", "d0")]])

# V2
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    seg = BriqueOctets("seg", {d: layout_octets("") for d in REF}, out_type=T.LAYOUT)
    ocr = BriqueOctets("ocr", {d: b"abcdefghijklmnopqrs#" for d in REF}, in_type=T.LAYOUT)
    other = BriqueOctets("oth", {d: b"abcdefghijklmnopq###" for d in REF})
    try:
        s = spec(c, [pipeline("M", step("seg", "seg", out_type=T.LAYOUT), step("ocr", "ocr", in_type=T.LAYOUT)),
                     pipeline("O", step("seg", "oth"))],
                 [text_view(target_step="seg")])
        r = execute(s, registry_with(seg, ocr, other)); show(r, "V2 target_step=seg")
    except Exception as e:
        print("[V2]", type(e).__name__, str(e)[:200])

# V3 partielle + illisible (et tronquée + illisible)
REF3 = {"d1": "abcdefghij", "d2": "klmnopqrst", "d3": "uvwxyz0123"}
for pol in ("exclude", "empty_page"):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF3)
        a = BriqueOctets("a", {"d1": layout_octets(REF3["d1"]), "d2": LAYOUT_ILLISIBLE, "d3": LAYOUT_ILLISIBLE},
                         partial=frozenset({"d2"}), truncate=frozenset({"d3"}), out_type=T.LAYOUT)
        b = BriqueOctets("b", {d: layout_octets(v) for d, v in REF3.items()}, out_type=T.LAYOUT)
        r = execute(spec(c, [pipeline("A", step("ocr", "a", out_type=T.LAYOUT)), pipeline("B", step("ocr", "b", out_type=T.LAYOUT))],
                         [vue_layout()], failure_policy=pol), registry_with(a, b))
    show(r, "V3")
    for d in ("d2", "d3"):
        x = per_document(r, "A", d)
        print(f"   A {d}: axes=({x.applicability},{x.availability},{x.validity}) stat={x.stat} part={x.stat_partielle} vide={x.stat_vide} value={x.value}")
    u = {(u.pipeline, u.document_id): (u.outcome, u.step_issues) for u in r.usage}
    print("   usage A:", {k: v for k, v in u.items() if k[0] == "A"})
    data = json.loads(r.model_dump_json())
    for q in ("conditionnelle", "operationnelle"):
        try: verifie_agregat(data, "A", "texte", REF3, q, "document"); print("   recalcul", q, "OK")
        except AssertionError as e: print("   recalcul", q, "ÉCHEC", e)

# V4 trois pipelines, un en échec partiel
REF4 = {f"d{i}": "abcdefghijklmnopqrst" for i in range(9)}
for pol in ("exclude", "empty_page"):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF4)
        def out(k): return {d: ("abcdefghijklmnopqrst"[:20 - k - (i % 3)] + "#" * (k + (i % 3))).encode() for i, d in enumerate(REF4)}
        oa = out(0); oa["d0"] = AdapterStepError("x"); oa["d1"] = b"abcdefghij"
        A = BriqueOctets("A", oa, partial=frozenset({"d1"}))
        B = BriqueOctets("B", out(2)); C = BriqueOctets("C", out(5))
        r = execute(spec(c, [pipeline(n, step("ocr", n)) for n in "ABC"], [text_view()], failure_policy=pol, analyses=("comparison", "inference", "paired") if False else None) if False else
                    spec(c, [pipeline(n, step("ocr", n)) for n in "ABC"], [text_view()], failure_policy=pol), registry_with(A, B, C))
    show(r, "V4")

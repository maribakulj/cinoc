"""C20 — Rév. 7 : « le résultat ne prétend pas décomposer exactement les comptes
canoniques quand ils divergent ». Corpus à ex æquo (« ab » → « ba » au caractère,
« un deux » → « deux un » au mot) : payloads diagnostics/taxonomy à
matches_canonical_counts = False ; que dit le rapport ?"""
import sys, tempfile, re, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.reports import default_report_renderer
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute, per_document)
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), {"d1": "ab un deux", "d2": "abc trois"})
    r = execute(spec(c, [pipeline("A", step("ocr", "ba")), pipeline("B", step("ocr", "bb"))],
                     [text_view(metrics=("cer", "wer", "del_rate", "ins_rate"))], analyses="toutes"),
                registry_with(RawBrick("ba", {"d1": b"ba deux un", "d2": b"abc trois"}), RawBrick("bb", {"d1": b"ab un deux", "d2": b"abd trois"})))
for kind in ("diagnostics", "taxonomy", "document_texts"):
    p = next(a.payload for a in r.analyses if a.payload.kind == kind)
    print(kind, "matches_canonical_counts =", p.matches_canonical_counts)
cer = per_document(r, "A", "d1", "cer").stat; wer = per_document(r, "A", "d1", "wer").stat
print("CER A/d1 (S,D,I) =", (cer.substitutions, cer.deletions, cer.insertions), "; WER A/d1 (S,D,I) =", (wer.substitutions, wer.deletions, wer.insertions))
tax = next(a.payload for a in r.analyses if a.payload.kind == "taxonomy")
print("taxonomie A :", [(x.label, x.count) for pl in tax.pipelines if pl.pipeline == "A" for x in pl.counts])
diag = next(a.payload for a in r.analyses if a.payload.kind == "diagnostics")
print("confusions A :", [(x.expected, x.observed, x.count) for pl in diag.confusions if pl.pipeline == "A" for x in pl.pairs])
for lang in ("fr", "en"):
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", H.unescape(default_report_renderer().render(r, lang=lang))))
    for needle in ("substitutions que compte le CER, ni plus ni moins", "exactly the substitutions the CER counts",
                   "les omissions sont ses suppressions", "omissions are its deletions"):
        if needle in txt: print(f"[{lang}] le rapport affiche : « {needle} »")
print("--- autres analyses qui nomment des éditions (sans alignment_path) ---")
for a in r.analyses:
    fields = type(a.payload).model_fields
    if a.payload.kind in ("word_errors", "textual_fidelity", "lines", "document_lines", "document_taxonomy", "document_hallucination", "correction"):
        print(a.payload.kind, "porte alignment_path :", "alignment_path" in fields)
we = next((a.payload for a in r.analyses if a.payload.kind == "word_errors"), None)
if we: print("word_errors :", [(w.word, [(e.pipeline, e.count, e.variant) for e in w.per_engine]) for w in we.words])

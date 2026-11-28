"""R03 — Rapport FR/EN du scénario V4 (3 pipelines, A partielle d1 + échec d0) :
texte visible des sections overview, paired_comparison, cross_engine, key_measures,
engine table ; recherche de « verdict », « significa* » ; cohérence avec le JSON."""
import sys, json, re, tempfile, html as H
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (T, corpus, registry_with, step, pipeline, text_view, spec, execute)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets, texte_visible
from cinoc.adapters.extension import AdapterStepError
from cinoc.reports.renderer import default_report_renderer
pol = sys.argv[1]; out = Path(sys.argv[2])
REF4 = {f"d{i}": "abcdefghijklmnopqrst" for i in range(9)}
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF4)
    def o(k): return {d: ("abcdefghijklmnopqrst"[:20 - k - (i % 3)] + "#" * (k + (i % 3))).encode() for i, d in enumerate(REF4)}
    oa = o(0); oa["d0"] = AdapterStepError("x"); oa["d1"] = b"abcdefghij"
    r = execute(spec(c, [pipeline(n, step("ocr", n)) for n in "ABC"], [text_view(metrics=("cer", "wer"))], failure_policy=pol, analyses="toutes" if len(sys.argv) > 3 else None),
                registry_with(BriqueOctets("A", oa, partial=frozenset({"d1"})), BriqueOctets("B", o(2)), BriqueOctets("C", o(5))))
out.mkdir(parents=True, exist_ok=True)
(out / f"v4_{pol}.json").write_text(r.model_dump_json(indent=1))
for lang in ("fr", "en"):
    doc = default_report_renderer().render(r, lang=lang)
    (out / f"v4_{pol}_{lang}.html").write_text(doc)
    txt = texte_visible(doc)
    (out / f"v4_{pol}_{lang}.txt").write_text(txt)
    for pat in (r".{0,80}\bverdicts?\b.{0,80}", r".{0,80}significa\w*.{0,80}", r".{0,60}\bsignifican\w*.{0,60}"):
        for m in sorted(set(x.group(0) for x in re.finditer(pat, txt, re.I))):
            print(f"[{lang}] {m}")

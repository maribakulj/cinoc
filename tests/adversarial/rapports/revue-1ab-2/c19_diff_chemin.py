"""C19 — Rév. 7 / § 2.1 f « Diff surligné » : le payload ``document_texts`` porte
``alignment_path`` et « le rendu l'affiche ». Sur « ab » → « ba » (ex æquo),
le diff surligne-t-il « exactement les éditions que compte le CER » (docstring de
reports/text_diff.py) et le rapport dit-il le chemin employé ?"""
import sys, tempfile, re, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.reports.text_diff import char_diff
from cinoc.evaluation.statistics import canonical_edit_counts
from cinoc.reports import default_report_renderer
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
ref_html, hyp_html = char_diff("ab", "ba")
print("diff GT :", ref_html, "| diff hyp :", hyp_html)
e = canonical_edit_counts("ab", "ba"); print("comptes du CER (canoniques) S, D, I =", e.substitutions, e.deletions, e.insertions)
print("caractères GT surlignés :", len(re.findall(r"<del[^>]*>(.*?)</del>", ref_html)), "attendu S + D =", e.substitutions + e.deletions)
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), {"d1": "ab", "d2": "abc"})
    r = execute(spec(c, [pipeline("A", step("ocr", "ba")), pipeline("B", step("ocr", "bb"))], [text_view()], analyses="toutes"),
                registry_with(RawBrick("ba", {"d1": b"ba", "d2": b"abc"}), RawBrick("bb", {"d1": b"ab", "d2": b"abd"})))
p = next(a.payload for a in r.analyses if a.payload.kind == "document_texts")
print("payload document_texts : alignment_path =", p.alignment_path, "matches_canonical_counts =", p.matches_canonical_counts)
for lang in ("fr", "en"):
    doc = H.unescape(default_report_renderer().render(r, lang=lang))
    print(lang, "le rapport mentionne rapidfuzz / chemin / canonical :", any(w in doc.lower() for w in ("rapidfuzz", "alignment_path", "canonique", "canonical")))
doc = H.unescape(default_report_renderer().render(r, lang="fr"))
txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", doc))
for w in ("rapidfuzz", "canonique", "alignment_path"):
    for m in list(re.finditer(w, txt, re.I))[:3]:
        print(f"[{w}] … {txt[max(0, m.start()-150): m.end()+100]} …")

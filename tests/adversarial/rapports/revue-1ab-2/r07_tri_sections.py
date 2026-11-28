"""R07 — D7 (tri global) dans TOUTES les sections qui ordonnent des moteurs.
c08 : A échoue sur 4 pages difficiles ; support global (6 pages) : B meilleur ;
sur son propre support A paraît meilleur. Ordre des moteurs dans chaque tableau."""
import re, tempfile
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets
from cinoc.adapters.extension import AdapterStepError
from cinoc.reports.renderer import default_report_renderer
REF = {f"d{i}": "abcdefghijklmnopqrst" for i in range(10)}
with tempfile.TemporaryDirectory() as tmp:
    c = corpus(Path(tmp), REF)
    a = BriqueOctets("ZA", {d: (AdapterStepError("x") if i < 4 else b"abcdefghijklmnopqr##") for i, d in enumerate(REF)})
    b = BriqueOctets("ZB", {d: (b"##########klmnopqrst" if i < 4 else b"abcdefghijklmnopqrs#") for i, d in enumerate(REF)})
    r = execute(spec(c, [pipeline("AAA", step("ocr", "ZA")), pipeline("BBB", step("ocr", "ZB"))], [text_view(metrics=("cer", "wer"))]), registry_with(a, b))
comp = next(x.payload for x in r.analyses if x.payload.kind == "comparison" and x.payload.metric == "cer")
print("tri global publié :", comp.global_support.ranking)
html = default_report_renderer().render(r, lang="fr")
# ordre d'apparition des moteurs dans chaque <table>, avec le titre de section le plus proche
for m in re.finditer(r'<section[^>]*id="([^"]+)"(.*?)</section>', html, re.S):
    sid, body = m.group(1), m.group(2)
    for t in re.finditer(r"<table.*?</table>", body, re.S):
        names = [n for n in re.findall(r"\b(AAA|BBB)\b", re.sub(r'title="[^"]*"', "", t.group(0)))]
        seq = []
        for n in names:
            if not seq or seq[-1] != n: seq.append(n)
        if len(set(seq)) == 2 and len(seq) <= 3:
            print(f"  section {sid:28s} ordre {seq}")

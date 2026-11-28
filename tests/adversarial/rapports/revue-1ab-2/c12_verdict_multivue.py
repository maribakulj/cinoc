"""C12 — Rév. 7 (« Wording des sections ») : à deux vues, la section « Mesures clés »
qualifie-t-elle un résultat de test de « verdict » ?"""
import sys, tempfile, re, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.reports.sections.key_measures import KeyMeasuresSection
from cinoc.reports.section import SectionContext
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
REF = {f"d{i:02d}": "abcdefghijklmnopqrst" for i in range(8)}
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    mk = lambda n, k: RawBrick(n, {d: ("abcdefghijklmnopqrst"[:20-k-(i%3)] + "#"*(k+(i%3))).encode() for i, d in enumerate(REF)})
    s = spec(c, [pipeline("A", step("ocr", "ba")), pipeline("B", step("ocr", "bb"))],
             [text_view("texte"), text_view("texte_brut")])
    r = execute(s, registry_with(mk("ba", 0), mk("bb", 4)))
for lang in ("fr", "en"):
    txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", H.unescape(str(KeyMeasuresSection().render(r, SectionContext(lang=lang))))))
    for m in re.finditer(r"[^.]{0,60}\bverdict\b[^.]{0,60}", txt, re.I):
        print(f"[{lang}] {m.group(0).strip()}")

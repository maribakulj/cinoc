"""C11 — Rév. 7 : aucun texte du rapport n'emploie « verdict » ni « significatif »
comme verdict d'un résultat de test. Run à 3 pipelines nettement différents
(Friedman rejeté, post-hoc), rapport complet FR et EN ; on cherche dans le texte
visible et dans les infobulles (title=, glossaire embarqué)."""
import sys, tempfile, re, html as H
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.reports import default_report_renderer
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
REF = {f"d{i:02d}": "abcdefghijklmnopqrst" for i in range(14)}
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    mk = lambda n, k: RawBrick(n, {d: ("abcdefghijklmnopqrst"[:20-k-(i%3)] + "#"*(k+(i%3))).encode() for i, d in enumerate(REF)})
    bricks = [mk("ba", 0), mk("bb", 3), mk("bc", 7)]
    s = spec(c, [pipeline(x.upper(), step("ocr", x)) for x in ("ba", "bb", "bc")], [text_view()], analyses="toutes")
    r = execute(s, registry_with(*bricks))
inf = next(a.payload for a in r.analyses if a.payload.kind == "inference")
print("test :", inf.test, "p_holm :", inf.p_holm, "status :", inf.status, "pairwise significant :", [(p.a, p.b) for p in inf.pairwise])
for lang in ("fr", "en"):
    doc = default_report_renderer().render(r, lang=lang)
    texte = H.unescape(doc)
    for pat in (r"[^.<>\"]{0,90}\bverdicts?\b[^.<>\"]{0,90}", r"[^.<>\"]{0,80}significa(?:nt|tif|tive|tivement)\w*[^.<>\"]{0,80}"):
        hits = sorted(set(m.group(0).strip() for m in re.finditer(pat, texte, re.I)))
        hits = [h for h in hits if "class=" not in h and "verdict sig" not in h]
        for h in hits[:8]:
            print(f"[{lang}] … {h} …")
for lang in ("fr", "en"):
    doc = H.unescape(default_report_renderer().render(r, lang=lang))
    for needle in ("verdict lit la p-valeur", "verdict reads the p-value", "un verdict ne vaut", "a verdict holds", "significance_p"):
        print(lang, repr(needle), "présent dans le HTML :", needle in doc)

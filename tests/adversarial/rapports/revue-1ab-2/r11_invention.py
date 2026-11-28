"""R11 — D7 : l'invention hors référence et la comparaison appariée affichées
(FR/EN) égalent le JSON ; scénario c14 (page blanche, échec, partielle, tronquée)."""
import json, re, sys, tempfile
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (T, corpus, registry_with, step, pipeline, text_view, spec, execute)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets, texte_visible, affiche, entier_affiche
from cinoc.adapters.extension import AdapterStepError
from cinoc.reports.renderer import default_report_renderer
REF = {f"d{i}": ("le soleil luit sur la seine " * 2) for i in range(6)} | {"blanc": ""}
pol = sys.argv[1]
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    def outs(k):
        return {d: (AdapterStepError("x") if (k == 1 and d == "d0") else ("le ſoleil luit sur la ſeine "[: 28 - k] + "zz " * (k + (d == "blanc") * 3)).encode()) for d in REF}
    bricks = [BriqueOctets(f"b{k}", outs(k), partial=frozenset({"d1"}) if k == 1 else frozenset(), truncate=frozenset({"d2"}) if k == 2 else frozenset()) for k in range(3)]
    r = execute(spec(c, [pipeline(f"P{k}", step("ocr", f"b{k}")) for k in range(3)], [text_view("texte", metrics=("cer", "wer"))], failure_policy=pol), registry_with(*bricks))
inv = [a.payload for a in r.analyses if a.payload.kind == "invention_outside_reference"]
comp = [a.payload for a in r.analyses if a.payload.kind == "comparison"]
for lang in ("fr", "en"):
    txt = texte_visible(default_report_renderer().render(r, lang=lang))
    miss = []
    for p in inv:
        for pr in p.pairs:
            for k, v in pr.model_dump().items():
                if isinstance(v, int) and not isinstance(v, bool) and v > 3 and not entier_affiche(txt, v): miss.append((p.metric, k, v))
                if isinstance(v, float) and not affiche(txt, v): miss.append((p.metric, k, v))
        for q, (a, b) in p.coverage.items():
            if not re.search(rf"{a}\s*/\s*{b}", txt): miss.append((p.metric, "coverage", q, a, b))
    for p in inv:
        for pr in p.pairs:
            for q, v in pr.invented.items():
                if not entier_affiche(txt, v): miss.append((p.metric, "invented", q, v))
    i = txt.find("hors référence") if lang == "fr" else txt.find("outside the reference")
    print(txt[i-50:i+500]) if lang == "fr" and pol == "exclude" else None
    for c_ in comp:
        for pr in c_.pairs:
            for q in (pr.a, pr.b):
                if pr.micro.get(q) is not None and not affiche(txt, pr.micro[q]): miss.append((c_.metric, "micro", q, pr.micro[q]))
    print(pol, lang, "invention:", [pr.model_dump() for p in inv for pr in p.pairs][:3], "cov", [p.coverage for p in inv][:1], "| manquants :", miss[:6])

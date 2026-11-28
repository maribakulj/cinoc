"""C07 — Sous ``empty_page`` : le test apparié (Wilcoxon exploratoire), la
p ``significance_p`` et le support apparié publié (``comparison``) portent-ils sur
les mêmes documents ? § 2.1 c : « Apparié, par paire : D^μ_AB … ; Wilcoxon de la paire »."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
REF = {f"d{i}": f"texte de la page {i:02d} " * 3 for i in range(10)}
def bruit(t, k): return t[:-k] + "#" * k
policy = sys.argv[1]
with tempfile.TemporaryDirectory() as tmp:
    c = corpus(Path(tmp), REF)
    a = RawBrick("brick_a", {d: (AdapterStepError("x") if i < 4 else bruit(t, 1).encode()) for i, (d, t) in enumerate(REF.items())},
                 partial=frozenset({"d4"}))
    b = RawBrick("brick_b", {d: bruit(t, 3).encode() for d, t in REF.items()})
    s = spec(c, [pipeline("A", step("ocr", "brick_a")), pipeline("B", step("ocr", "brick_b"))], [text_view()], failure_policy=policy)
    r = execute(s, registry_with(a, b))
for an in r.analyses:
    k = an.payload.kind
    if k == "comparison":
        pr = an.payload.pairs[0]
        print(f"{policy}: comparison D^μ_AB = {len(pr.micro_documents)} docs {pr.micro_documents} ; micro {pr.micro}")
    if k == "inference":
        p = an.payload
        print(f"{policy}: inference status={p.status} test={p.test} n_documents={p.n_documents} p={p.p_value}")
for s in r.cross_engine:
    print(f"{policy}: cross_engine {s.metric} value={s.value} support={s.support}")
for p in r.pipelines:
    print(f"{policy}: {p.pipeline} principal value={r.principal_aggregate(p)[0].value} support={r.principal_aggregate(p)[0].support}/{r.principal_aggregate(p)[0].expected}")

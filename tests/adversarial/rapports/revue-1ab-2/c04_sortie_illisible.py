"""C04 — Sortie non décodable (octets non UTF-8) : l'unité seule, ou le run ?
Puis VT non décodable."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)

def run_case(tmp, gt_bytes=None, out=b"\xff\xfe\x00garbage"):
    c = corpus(tmp, {"d1": "abcdefghij", "d2": "klmnopqrst"})
    if gt_bytes is not None:
        Path(c.documents[1].ground_truths[0].uri).write_bytes(gt_bytes)
    a = RawBrick("brick_a", {"d1": b"abcdefghij", "d2": out})
    b = RawBrick("brick_b", {"d1": b"abcdefghiX", "d2": b"klmnopqrsX"})
    reg = registry_with(a, b)
    s = spec(c, [pipeline("A", step("ocr", "brick_a")), pipeline("B", step("ocr", "brick_b"))],
             [text_view()])
    return execute(s, reg)

for label, kw in (("sortie non UTF-8", {}), ("VT non UTF-8", {"gt_bytes": b"\xff\xfeabc", "out": b"klmnopqrst"})):
    with tempfile.TemporaryDirectory() as t:
        try:
            r = run_case(Path(t), **kw)
            ag = {p.pipeline: [(s.metric, s.value, s.support, s.expected, s.coverage) for s in r.principal_aggregate(p)] for p in r.pipelines}
            print(label, "→ run noté :", ag)
        except Exception as e:
            print(label, "→ RUN PERDU :", type(e).__name__, str(e)[:160])

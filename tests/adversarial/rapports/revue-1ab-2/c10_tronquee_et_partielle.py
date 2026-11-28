"""C10 — Unité à la fois tronquée et partielle (arbitrage du 28/11, § 2.1 f) :
« partial l'emporte sur l'axe 3, et la troncature reste tracée dans les issues
d'étape ». Une seule étape déclare les deux."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute, per_document)
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), {"d1": "abcdefghij"})
    a = RawBrick("brick_a", {"d1": b"abcde"}, partial=frozenset({"d1"}), truncate=frozenset({"d1"}))
    r = execute(spec(c, [pipeline("A", step("ocr", "brick_a"))], [text_view()]), registry_with(a))
u = r.usage[0]
print("outcome :", u.outcome, "| step_issues :", u.step_issues, "| message :", u.message)
s = per_document(r, "A", "d1")
print("axe 3 :", s.validity)

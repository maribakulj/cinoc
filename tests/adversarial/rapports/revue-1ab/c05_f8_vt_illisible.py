"""C05 — F8 « refus avant de payer » : une VT présente mais non décodable (UTF-8
invalide) est-elle refusée avant le premier appel de moteur ?"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
calls = []
class Counting(RawBrick):
    def execute(self, inputs, params, context, control):
        calls.append(context.document_id)
        return super().execute(inputs, params, context, control)
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), {"d1": "abc", "d2": "def"})
    Path(c.documents[1].ground_truths[0].uri).write_bytes(b"\xff\xfedef")
    a = Counting("brick_a", {"d1": b"abc", "d2": b"def"})
    s = spec(c, [pipeline("A", step("ocr", "brick_a"))], [text_view()])
    try:
        execute(s, registry_with(a)); print("run noté")
    except Exception as e:
        print("erreur :", type(e).__name__, "| appels de moteur payés avant :", calls)

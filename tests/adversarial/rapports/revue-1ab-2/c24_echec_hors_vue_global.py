"""C24 — Suite de C23 : A et B sont vus par la vue « corrigé » ; C (OCR seul) ne l'est
pas, mais échoue sur une page. Le support global de la famille et son tri (B7)
survivent-ils ? (cf. test « pipeline non applicable n'annule pas le test des autres »)."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError, ArtifactType as T
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
REF = {f"d{i}": "abcdefghij" for i in range(4)}
def chain(name, ocr_out, corr_out):
    return (RawBrick(f"o{name}", ocr_out), RawBrick(f"c{name}", corr_out, in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT),
            pipeline(name, step("ocr", f"o{name}"), step("corr", f"c{name}", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT)))
for c_fails in (False, True):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF)
        oa, ca, pa = chain("A", {d: b"x" for d in REF}, {d: b"abcdefghiX" for d in REF})
        ob, cb, pb = chain("B", {d: b"x" for d in REF}, {d: b"abcdefghXX" for d in REF})
        oc = RawBrick("oC", {d: (AdapterStepError("x") if (c_fails and d == "d0") else b"abcdefghij") for d in REF})
        r = execute(spec(c, [pa, pb, pipeline("C", step("ocr", "oC"))], [text_view("corrige", candidates=(T.CORRECTED_TEXT,))]),
                    registry_with(oa, ca, ob, cb, oc))
    comp = next(a.payload for a in r.analyses if a.payload.kind == "comparison")
    print(f"C échoue sur d0 : {c_fails} → pipelines comparés : {sorted({x for pp in comp.pairs for x in (pp.a, pp.b)})} ; "
          f"support global : {comp.global_support.micro_documents} ; tri : {comp.global_support.ranking}")

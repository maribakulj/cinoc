"""C23 — Axe 1 : un pipeline que la vue ne voit pas (il ne produit aucun type
candidat de la vue) devient-il « attendu » par ses seuls échecs ?
Vue « corrigé » (candidat CORRECTED_TEXT). P = OCR seul (RAW_TEXT), échoue sur d1.
Q = OCR → correction (CORRECTED_TEXT), complet."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError, ArtifactType as T
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
REF = {"d1": "abcdefghij", "d2": "abcdefghij", "d3": "abcdefghij"}
for policy in ("exclude", "empty_page"):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF)
        p = RawBrick("ocr_p", {"d1": AdapterStepError("x"), "d2": b"abcdefghij", "d3": b"abcdefghij"})
        q1 = RawBrick("ocr_q", {d: b"abcdefghiX" for d in REF})
        q2 = RawBrick("corr_q", {d: b"abcdefghij" for d in REF}, in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT)
        s = spec(c, [pipeline("P", step("ocr", "ocr_p")),
                     pipeline("Q", step("ocr", "ocr_q"), step("corr", "corr_q", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT))],
                 [text_view("corrige", candidates=(T.CORRECTED_TEXT,))], failure_policy=policy)
        r = execute(s, registry_with(p, q1, q2))
    for d in r.documents:
        if d.pipeline == "P": print(policy, "P", d.document_id, "axes :", d.scores[0].applicability, d.scores[0].availability, "valeur :", d.scores[0].value)
    for pr in r.pipelines:
        a = pr.aggregate[0]; o = pr.operational_aggregate[0]
        print(policy, pr.pipeline, f"principal={a.value} {a.support}/{a.expected} cov={a.coverage} | opérationnel={o.value} {o.support}/{o.expected}")
    comp = [a.payload for a in r.analyses if a.payload.kind == "comparison"]
    print(policy, "comparison :", [(pp.a, pp.b, pp.micro_documents) for c_ in comp for pp in c_.pairs], "| tri global :", [c_.global_support.ranking for c_ in comp])

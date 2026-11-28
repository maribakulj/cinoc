"""R08 — B3/D4 : « un document sans grappe forme la sienne ». Le runner clé la
grappe par ``document.cluster or document.id`` : un document sans grappe dont
l'identifiant égale le nom d'une grappe déclarée y est fusionné. Comparaison au
recalcul depuis le JSON (singleton pour cluster = null)."""
import json, tempfile
from fractions import Fraction
from pathlib import Path
from cinoc.domain.corpus import CorpusSpec
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets
from tests.adversarial._contrat import document_en_grappe, corpus_declare
REF = {"g": "abcdefghij", "x1": "abcdefghij", "x2": "abcdefghij"}
GR = {"x1": "g", "x2": "g"}  # « g » est aussi l'id d'un document sans grappe
with tempfile.TemporaryDirectory() as t:
    base = corpus(Path(t), REF)
    docs = tuple(document_en_grappe(d, GR[d.id]) if d.id in GR else d for d in base.documents)
    try:
        cs = corpus_declare(CorpusSpec(name="ce", documents=docs), target_population="p", cluster_weighting="cluster")
    except Exception as e:
        print("refusé à la déclaration :", type(e).__name__, e); raise SystemExit
    out = {"g": b"##########", "x1": b"abcdefghij", "x2": b"abcdefghij"}
    r = execute(spec(cs, [pipeline("A", step("ocr", "a"))], [text_view()]), registry_with(BriqueOctets("a", out)))
d = json.loads(r.model_dump_json())
print("grappes du JSON :", {x["document_id"]: x["cluster"] for x in d["documents"]})
pub = d["pipelines"][0]["conditional_aggregate"][0]["macro"]
print("macro publié :", pub, "| oracle (g singleton) :", float((Fraction(1) + Fraction(0)) / 2), "| si g fusionné dans « g » :", float(Fraction(1, 3)))

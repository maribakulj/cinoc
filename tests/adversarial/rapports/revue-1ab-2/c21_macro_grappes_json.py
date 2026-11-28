"""C21 — B3 : macro par grappe. Le JSON du RunResult permet-il de recalculer le macro
publié (grappes de chaque document) ? Et le macro est-il calculé sur D^M_P ?"""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.domain.corpus import CorpusSpec
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute)
REF = {"a1": "abcdefghij", "a2": "abcdefghij", "a3": "abcdefghij", "b1": "abcdefghij"}
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    docs = tuple(d.model_copy(update={"cluster": d.id[0]}) for d in c.documents)
    c = CorpusSpec(name="ce", documents=docs, cluster_weighting="cluster", target_population="volumes A et B")
    out = {"a1": b"abcdefghij", "a2": b"abcdefghij", "a3": b"abcdefghij", "b1": b"abcde#####"}
    r = execute(spec(c, [pipeline("A", step("ocr", "ba"))], [text_view()]), registry_with(RawBrick("ba", out)))
ag = r.principal_aggregate(r.pipelines[0])[0]
print("macro publié :", ag.macro, "| pondération :", r.pipelines[0].cluster_weighting, "| population :", r.pipelines[0].target_population)
raw = r.model_dump_json()
d = json.loads(raw)
print("champ « cluster » dans les documents du JSON :", any("cluster" in doc for doc in d["documents"]))
print("grappes ('a', 'b') présentes quelque part dans le JSON :", '"cluster"' in raw.replace('"cluster_weighting"', ""))
vals = [doc["scores"][0]["value"] for doc in d["documents"]]
print("macro recalculable sans grappes (par document) :", sum(vals) / len(vals), "≠ publié" if sum(vals)/len(vals) != ag.macro else "")
import re
for m in re.finditer(r'"cluster"', raw):
    print("contexte :", raw[max(0, m.start()-120): m.end()+30])
    break
print("clés du manifeste :", sorted(d["manifest"]))

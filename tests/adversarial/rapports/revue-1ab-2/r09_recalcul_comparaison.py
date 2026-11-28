"""R09 — D3/D10 : les payloads ``comparison`` (supports apparié et global, micro,
macro, tri) se recalculent-ils depuis les observations du JSON, sous la politique
principale (exclude : complètes ; empty_page : opérationnelles) ?"""
import json, sys, collections
from fractions import Fraction
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from r01_recalcul_v7 import F, ref_defines, add, reg
for path in sys.argv[1:]:
    d = json.load(open(path)); pol = d["manifest"]["failure_policy"]
    obs = collections.defaultdict(dict)
    for doc in d["documents"]:
        for s in doc["scores"]:
            if s["applicability"] != "applicable": continue
            if pol == "exclude":
                st = s["stat"] if (s["availability"] == "available" and s["validity"] == "valid") else None
            else:
                if s["availability"] == "gt_unreadable": st = None
                elif s["availability"] == "available": st = s["stat"] if s["validity"] == "valid" else s["stat_partielle"]
                else: st = s["stat_vide"]
            obs[(doc["view"], s["metric"], doc["pipeline"])][doc["document_id"]] = st
    bad = n = 0
    for a in d["analyses"]:
        p = a["payload"]
        if p["kind"] != "comparison": continue
        m = p["metric"]; dm = reg.document_metric(m); fin = dm.finalize.__name__
        def sup(pipes, docs_pub, micro_pub, macro_pub, macro_docs_pub):
            global bad, n
            series = [obs[(a["view"], m, q)] for q in pipes]
            common = sorted(set.intersection(*[{k for k, v in s.items() if v is not None} for s in series]))
            ok = list(docs_pub) == [x for x in common] or sorted(docs_pub) == common
            for q, s in zip(pipes, series):
                tot = None
                for k in common: tot = add(tot, s[k])
                v = None if tot is None else F(tot, fin)[0]
                if (None if v is None else float(v)) != micro_pub.get(q): ok = False; print("   micro", q, micro_pub.get(q), v)
            n += 1; bad += (not ok)
            if not ok: print("   écart", a["view"], m, pipes, docs_pub[:3], common[:3])
        for pr in p["pairs"]:
            sup([pr["a"], pr["b"]], pr["micro_documents"], pr["micro"], pr["macro"], pr["macro_documents"])
        g = p["global_support"]
        pipes = sorted(g["micro"]) if g["micro"] else []
        if pipes: sup(pipes, g["micro_documents"], g["micro"], g["macro"], g["macro_documents"])
    print(f"{path.split('/')[-1]} ({pol}) : supports comparés {n}, écarts {bad}")

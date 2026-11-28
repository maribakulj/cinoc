"""C16 — Valeurs publiées : réévaluation 1a (abee7b5) contre 1b (HEAD), même archive.
Compare agrégat principal (value, stat, support, expected), valeurs par document,
inférence (p) ; et vérifie que chaque agrégat publié par HEAD se recalcule depuis
les observations par document du même JSON (conditionnel et opérationnel)."""
import json, sys
from collections import Counter
A, B = (json.load(open(p)) for p in sys.argv[1:3])
def aggs(R):
    return {(p["pipeline"], p["view"], s["metric"]): s for p in R["pipelines"] for s in p["aggregate"]}
a, b = aggs(A), aggs(B)
diff = Counter(); ex = []
for k in a:
    x, y = a[k], b.get(k)
    if y is None: diff["absent"] += 1; continue
    for f in ("value", "stat", "support", "expected", "untruncated_error_rate"):
        if x.get(f) != y.get(f):
            diff[f] += 1
            if len(ex) < 8: ex.append((k, f, x.get(f), y.get(f)))
print("agrégats comparés :", len(a), "écarts par champ :", dict(diff))
for e in ex: print("  ", e)
def docs(R):
    return {(d["pipeline"], d["view"], d["document_id"], s["metric"]): s for d in R["documents"] for s in d["scores"]}
da, db = docs(A), docs(B)
dd = Counter(); dex = []
for k in da:
    for f in ("value", "stat", "scalar_reason"):
        if da[k].get(f) != db[k].get(f):
            dd[f] += 1
            if len(dex) < 5: dex.append((k, f, da[k].get(f), db[k].get(f), db[k].get("validity"), db[k].get("availability")))
print("observations par document :", len(da), "écarts :", dict(dd))
for e in dex: print("  ", e)
inf = lambda R: {(x["view"], x["payload"]["metric"]): x["payload"] for x in R["analyses"] if x["payload"]["kind"] == "inference"}
ia, ib = inf(A), inf(B)
for k in ia:
    if (ia[k].get("p_value"), ia[k].get("p_holm"), ia[k].get("family_size")) != (ib[k].get("p_value"), ib[k].get("p_holm"), ib[k].get("family_size")):
        print("  inférence", k, "p", ia[k].get("p_value"), "→", ib[k].get("p_value"), "| holm", ia[k].get("p_holm"), "→", ib[k].get("p_holm"), "| m", ia[k].get("family_size"), "→", ib[k].get("family_size"), "| status", ib[k].get("status"))
# recalcul depuis le JSON (HEAD)
from fractions import Fraction
FIELDS = {"edit_counts": ("substitutions", "deletions", "insertions", "reference_length"), "error_counts": ("errors", "reference_length"),
          "match_counts": ("tp", "fp", "fn"), "proportion": ("count", "total")}
def comb(stats):
    if not stats: return None
    fam = stats[0]["family"]
    return {"family": fam, **{f: sum(s[f] for s in stats) for f in FIELDS[fam]}}
bad = Counter(); bex = []
for p in B["pipelines"]:
    for kind in ("conditional_aggregate", "operational_aggregate"):
        for s in p[kind]:
            obs = [sc for d in B["documents"] if (d["pipeline"], d["view"]) == (p["pipeline"], p["view"]) for sc in d["scores"] if sc["metric"] == s["metric"]]
            if kind == "conditional_aggregate":
                st = [o["stat"] for o in obs if o["stat"] and o["applicability"] == "applicable" and o["availability"] == "available" and o["validity"] == "valid"]
            else:
                st = [o["stat"] or o["stat_partielle"] for o in obs if (o["stat"] or o["stat_partielle"])]
            got = comb(st)
            if got != s["stat"]:
                bad[kind] += 1
                if len(bex) < 6: bex.append((p["pipeline"], p["view"], s["metric"], kind, got, s["stat"], s["support"], s["expected"], s["coverage"]))
print("agrégats HEAD non recalculables depuis les observations du JSON :", dict(bad))
for e in bex: print("  ", e)

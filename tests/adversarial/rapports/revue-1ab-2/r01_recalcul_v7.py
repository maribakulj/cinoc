"""R01 — D3/D4/D5 : recalcule TOUS les agrégats (conditionnel, opérationnel ;
value, stat, support, expected, coverage, macro, macro_support,
untruncated_error_rate, scalar_reason) d'un RunResult v7 depuis les seules
observations du JSON, oracle indépendant en Fraction (aucun import de
cinoc.evaluation.aggregation ; seuls les noms de finalisation et le drapeau macro
sont lus dans le registre).
Usage : python r01_recalcul_v7.py <run_result.json> [...]"""
import json, sys, collections
from fractions import Fraction
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics

reg = MetricRegistry(); register_default_metrics(reg)

def F(stat, fin):
    f = stat["family"]
    if f == "edit_counts":
        S, D, I, n = stat["substitutions"], stat["deletions"], stat["insertions"], stat["reference_length"]
        num, den = {"edit_rate": (S+D+I, n), "match_error_rate": (S+D+I, n+I),
                    "insertion_rate": (I, n), "deletion_rate": (D, n)}[fin]
    elif f == "error_counts":
        e, n = stat["errors"], stat["reference_length"]
        if n == 0: return None, None
        if fin == "accuracy":
            return max(Fraction(0), 1 - Fraction(e, n)), Fraction(e, n)
        num, den = e, n
    elif f == "match_counts":
        tp, fp, fn = stat["tp"], stat["fp"], stat["fn"]
        num, den = {"f1": (2*tp, 2*tp+fp+fn), "precision": (tp, tp+fp), "recall": (tp, tp+fn)}[fin]
    else:
        num, den = stat["count"], stat["total"]
    if den == 0: return None, None
    return Fraction(num, den), None

def ref_defines(stat):
    f = stat["family"]
    if f in ("edit_counts", "error_counts"): return stat["reference_length"] > 0
    if f == "match_counts": return stat["tp"] + stat["fn"] > 0
    return stat["total"] > 0

def add(a, b):
    if a is None: return dict(b)
    return {k: (a[k] + b[k] if k != "family" else a[k]) for k in a}

def recompute(d, path):
    weighting_by = {}
    clusters = {doc["document_id"]: doc.get("cluster") for doc in d["documents"]}
    obs = collections.defaultdict(list)
    for doc in d["documents"]:
        for s in doc["scores"]:
            obs[(doc["pipeline"], doc["view"], s["metric"])].append((doc["document_id"], s))
    n_checked = 0; bad = []
    for p in d["pipelines"]:
        w = p.get("cluster_weighting", "document")
        for quality in ("conditional_aggregate", "operational_aggregate"):
            for agg in p[quality]:
                m = agg["metric"]
                base = m.split(":")[0]
                dm = reg.document_metric(m)
                if dm is None:
                    bad.append((path, p["pipeline"], p["view"], m, "métrique inconnue")); continue
                fin = dm.finalize.__name__
                contrib = []; expected = 0; cov = collections.Counter()
                for did, s in obs[(p["pipeline"], p["view"], m)]:
                    if s["applicability"] != "applicable": continue
                    expected += 1
                    av, va = s["availability"], s["validity"]
                    complete = av == "available" and va == "valid" and s["stat"] is not None
                    if not complete:
                        cov[av if av not in (None, "available") else va] += 1
                    if quality == "conditional_aggregate":
                        if complete: contrib.append((did, s["stat"]))
                    else:
                        if av == "gt_unreadable": continue
                        if av == "available":
                            st = s["stat"] if va == "valid" else s["stat_partielle"]
                        else:
                            st = s["stat_vide"]
                        if st is None:
                            bad.append((path, p["pipeline"], p["view"], m, quality, did, "stat manquante", av, va)); continue
                        contrib.append((did, st))
                tot = None
                for _, st in contrib: tot = add(tot, st)
                ex = {"support": len(contrib), "expected": expected, "coverage": dict(sorted(cov.items())), "stat": tot}
                if tot is None:
                    ex["value"] = None
                else:
                    v, unt = F(tot, fin)
                    ex["value"] = None if v is None else float(v)
                    if fin == "accuracy":
                        ex["untruncated_error_rate"] = None if unt is None else float(unt)
                # macro
                if dm.macro:
                    groups = collections.defaultdict(list); cnt = 0
                    for did, st in contrib:
                        if not ref_defines(st): continue
                        v, _ = F(st, fin)
                        if v is None: continue
                        cnt += 1
                        key = (clusters.get(did) or ("doc:" + did)) if w == "cluster" else "all"
                        groups[key].append(v)
                    if cnt == 0:
                        ex["macro"], ex["macro_support"] = None, 0
                    elif w == "cluster":
                        means = [sum(g, Fraction(0)) / len(g) for g in groups.values()]
                        ex["macro"], ex["macro_support"] = float(sum(means, Fraction(0)) / len(means)), cnt
                    else:
                        ex["macro"], ex["macro_support"] = float(sum(groups["all"], Fraction(0)) / cnt), cnt
                else:
                    ex["macro"], ex["macro_support"] = None, None
                for k, v in ex.items():
                    pub = agg.get(k)
                    if k == "stat" and pub is not None and v is not None:
                        pub = {kk: vv for kk, vv in pub.items()}
                    if pub != v:
                        bad.append((path, p["pipeline"], p["view"], m, quality, k, pub, v))
                n_checked += 1
    return n_checked, bad

for path in sys.argv[1:]:
    d = json.load(open(path))
    n, bad = recompute(d, path)
    print(f"{path.split('/')[-2]}/{path.split('/')[-1]} : schéma {d['schema_version']}, politique {d['manifest']['failure_policy']}, agrégats recalculés {n}, écarts {len(bad)}")
    for b in bad[:15]: print("   ", b[1:])

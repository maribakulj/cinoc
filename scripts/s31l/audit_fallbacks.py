"""Unités saknussemm d'une archive : part de lignes en repli, motifs — outil de session.

Usage : python -I audit_fallbacks.py <archive> [--delete-timeouts] [--delete-all-fallback]
"""
import collections, json, shutil, sys
from pathlib import Path

arch = Path(sys.argv[1])
rows = []
for dec in sorted(arch.glob("*/correction.decisions.json")):
    d = json.loads(dec.read_text(encoding="utf-8"))
    lines = d["lines"]
    fb = [l for l in lines if l["status"] == "fallback"]
    timeouts = sum(1 for l in fb if "délai" in (l.get("reason_detail") or ""))
    seps = sum(1 for l in fb if "line separator" in (l.get("reason_detail") or ""))
    idx = json.loads((dec.parent / "index.json").read_text(encoding="utf-8"))
    adapter = next((a["id"].split(":", 1)[1].rsplit(":", 1)[0]
                    for s in idx["steps"] if s["step"] == "correction"
                    for a in s["artifacts"].values()), "?")
    rows.append((dec.parent.name, d["document_id"], adapter, len(lines), len(fb), timeouts, seps,
                 collections.Counter(l["reason_code"] for l in fb)))
for key, doc, ad, n, f, t, s, c in rows:
    flag = "100%-REPLI" if n and f == n else ""
    print(f"{key[:12]} {doc} {ad:22} lignes {n:3} repli {f:3} (délai {t}, séparateur {s}) {flag} {dict(c)}")
for key, doc, ad, n, f, t, s, c in rows:
    if ("--delete-timeouts" in sys.argv and t) or ("--delete-all-fallback" in sys.argv and n and f == n):
        shutil.rmtree(arch / key)
        print(f"supprimée : {key} ({doc}, {ad}, {f}/{n} en repli, délai {t}, séparateur {s})")

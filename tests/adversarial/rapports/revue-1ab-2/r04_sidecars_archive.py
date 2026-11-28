"""R04 — Classes de lignes déclarées dans les sidecars de décision des archives
S30 (statut + reason_code écrits par l'adaptateur de l'époque) : combien d'unités
seraient « partielles » (au moins un repli all_attempts_exhausted /
chunk_error_absorbed), combien entièrement en repli. Usage : r04 <archive>..."""
import json, sys, collections
from pathlib import Path
INCIDENT = {"all_attempts_exhausted", "chunk_error_absorbed"}
for arch in sys.argv[1:]:
    per_doc = collections.defaultdict(collections.Counter)
    files = sorted(Path(arch).rglob("*.decisions.json"))
    for f in files:
        d = json.loads(f.read_text())
        for l in d["lines"]:
            cls = l["status"] if l["status"] != "fallback" else ("repli" if l.get("reason_code") in INCIDENT else "refus")
            per_doc[(f.parent.name[:8], d["document_id"])][cls] += 1
    tot = collections.Counter()
    for c in per_doc.values(): tot.update(c)
    partial = sum(1 for c in per_doc.values() if c["repli"])
    allrep = sum(1 for c in per_doc.values() if c["repli"] and c["repli"] == sum(c.values()))
    print(f"{arch}: sidecars {len(files)}, unités {len(per_doc)}, classes {dict(tot)}, unités avec ≥1 repli {partial}, entièrement en repli {allrep}")

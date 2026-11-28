"""C15 — Compare deux RunResult JSON champ par champ (hors horodatages, durées,
code_version) et résume les écarts par chemin."""
import json, sys
from collections import Counter
VOLATILE = ("started_at", "completed_at", "created_at", "duration", "seconds", "code_version", "pages_per_hour", "cost_eur", "eur_per", "cost_delta")
def walk(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if any(v in k for v in VOLATILE): continue
            if k not in a or k not in b:
                out.append((path + "/" + k, "absent d'un côté", a.get(k, "∅") if k in a else "∅", b.get(k, "∅") if k in b else "∅")); continue
            walk(a[k], b[k], path + "/" + k, out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b): out.append((path, f"longueurs {len(a)}≠{len(b)}", None, None))
        for i, (x, y) in enumerate(zip(a, b)): walk(x, y, path + f"[{i}]", out)
    elif a != b:
        out.append((path, "valeur", a, b))
A, B = (json.load(open(p)) for p in sys.argv[1:3])
out = []; walk(A, B, "", out)
import re
c = Counter(re.sub(r"\[\d+\]", "[]", p) for p, *_ in out)
print("écarts :", len(out))
for k, n in c.most_common(25): print(f"  {n:5d}  {k}")
for p, kind, x, y in out[:int(sys.argv[3]) if len(sys.argv) > 3 else 6]:
    print("  ex.", p, kind, str(x)[:120], "|", str(y)[:120])

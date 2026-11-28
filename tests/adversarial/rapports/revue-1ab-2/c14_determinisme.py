"""C14 — Déterminisme : même spec, même corpus, même code → même JSON octet pour
octet (hors horodatages et durées du manifeste/usage), sous deux PYTHONHASHSEED.
Scénario riche : échec, partielle, tronquée, page blanche, NER absent, 3 pipelines,
mode détaillé (toutes les analyses), puis empty_page."""
import sys, json, hashlib, shutil
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
base = Path(__file__).parent / "det_corpus"; shutil.rmtree(base, ignore_errors=True); base.mkdir()
REF = {f"d{i}": ("le soleil luit sur la seine " * 2) for i in range(6)} | {"blanc": ""}
c = corpus(base, REF)
def outs(k):
    return {d: (AdapterStepError("x") if (k == 1 and d == "d0") else ("le ſoleil luit sur la ſeine "[: 28 - k] + "zz " * k).encode()) for d in REF}
bricks = [RawBrick(f"b{k}", outs(k), partial=frozenset({"d1"}) if k == 1 else frozenset(),
                   truncate=frozenset({"d2"}) if k == 2 else frozenset()) for k in range(3)]
pol = sys.argv[1]
s = spec(c, [pipeline(f"P{k}", step("ocr", f"b{k}")) for k in range(3)],
         [text_view("texte", metrics=("cer", "wer", "mer", "char_accuracy", "ins_rate", "bow_f1", "bow_precision"))],
         analyses="toutes", failure_policy=pol)
r = execute(s, registry_with(*bricks))
d = json.loads(r.model_dump_json())
for k in ("started_at", "completed_at", "created_at", "duration_s", "timestamp"):
    d["manifest"].pop(k, None)
for u in d["usage"]:
    u["usage"].pop("duration_s", None); u["usage"].pop("wall_seconds", None)
def strip(o):
    if isinstance(o, dict):
        return {k: strip(v) for k, v in o.items() if not any(x in k for x in ("duration", "seconds", "_at", "pages_per_hour", "throughput"))}
    if isinstance(o, list): return [strip(x) for x in o]
    return o
d["analyses"] = [a for a in d["analyses"] if a["payload"]["kind"] != "economics"]
blob = json.dumps(strip(d), sort_keys=False, ensure_ascii=False).encode()
Path(sys.argv[2]).write_bytes(json.dumps(strip(d), indent=1, ensure_ascii=False).encode()) if len(sys.argv) > 2 else None
print(pol, hashlib.sha256(blob).hexdigest()[:16], len(blob))

"""Révision 3, rejeu de N4 et N5 contre les règles révisées.

N4 (§ 2.2) : validation = partie calculée de la définition (sources, poids) + environnement,
    chaque module résolu PAR SON NOM (find_spec(nom).origin) puis haché. Rejeu de
    r2_p10 : (a) poids remplacés, (b) module résolu dans un autre venv -> détectés.
N5 (§ 2.3 c) : fermeture d'imports STATIQUE « résolue par find_spec SANS EXÉCUTER ».
    Remarque : `importlib.util.find_spec("pkg.sub")` IMPORTE `pkg` (exécute son
    __init__). « Sans exécuter » n'est vrai que pour les modules de premier niveau.
"""
import hashlib, importlib, importlib.util, sys, tempfile
from pathlib import Path
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
tmp = Path(tempfile.mkdtemp()); v1, v2 = tmp / "venv1", tmp / "venv2"; v1.mkdir(); v2.mkdir()
(v1 / "seg_lib.py").write_text("def run(x): return x\n"); (v2 / "seg_lib.py").write_text("def run(x): return x[::-1]\n")
w = tmp / "fra.traineddata"; w.write_bytes(b"poids v1")
sys.path.insert(0, str(v1)); rec = {"modules": {"seg_lib": sha(importlib.util.find_spec("seg_lib").origin)},
                                    "weights": {"lang=fra": sha(w)}}
sys.path.remove(str(v1)); importlib.invalidate_caches()
def validation(rec, weight_path):
    for name, h in rec["modules"].items():
        spec = importlib.util.find_spec(name)
        if spec is None or spec.origin is None or sha(spec.origin) != h: return False
    return all(sha(weight_path) == h for h in rec["weights"].values())
w.write_bytes(b"poids v2")
print("N4 (a) poids remplacés -> validation =", validation(rec, w)); assert not validation(rec, w)
w.write_bytes(b"poids v1"); sys.path.insert(0, str(v2)); importlib.invalidate_caches()
print("N4 (b) module résolu dans venv2 -> validation =", validation(rec, w)); assert not validation(rec, w)
# N5 : find_spec d'un sous-module exécute le __init__ du paquet parent
pkg = tmp / "plug"; pkg.mkdir(); (pkg / "__init__.py").write_text("import builtins; builtins.EXECUTE = True\n")
(pkg / "sub.py").write_text("X = 1\n"); sys.path.insert(0, str(tmp))
import builtins
importlib.util.find_spec("plug.sub")
print("N5 : find_spec('plug.sub') a exécuté plug/__init__.py :", getattr(builtins, "EXECUTE", False))
assert getattr(builtins, "EXECUTE", False)

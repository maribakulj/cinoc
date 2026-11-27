"""Révision 4, remarque sur N5 : `importlib.util.find_spec("pkg.sub")` importe `pkg`,
donc exécute son `__init__`. Résolution retenue : pour chaque composant du nom, on
interroge les chercheurs de `sys.meta_path` (`finder.find_spec(nom_complet, chemins)`)
avec les `submodule_search_locations` du parent, SANS importer le parent.
Vérifie : (1) un paquet dont l'`__init__` a un effet de bord n'est pas exécuté par cette
résolution, alors qu'il l'est par `find_spec` ; (2) un module de cinoc installé en
éditable (chercheur `__editable__` dans `sys.meta_path`) est résolu sans import."""
import importlib.util, sys, tempfile
from pathlib import Path
def resolve(name):
    path, spec = None, None
    parts = name.split(".")
    for i in range(len(parts)):
        full = ".".join(parts[: i + 1]); spec = None
        for finder in sys.meta_path:
            fs = getattr(finder, "find_spec", None)
            if fs is not None and (spec := fs(full, path)) is not None:
                break
        if spec is None:
            return None
        path = spec.submodule_search_locations
    return spec.origin
root = Path(tempfile.mkdtemp()); pkg = root / "pkgx"; pkg.mkdir()
marker = root / "INIT_EXECUTE"
(pkg / "__init__.py").write_text(f"open({str(marker)!r}, 'w').write('oui')\n")
(pkg / "sub.py").write_text("X = 1\n")
sys.path.insert(0, str(root))
print("résolution sans import :", resolve("pkgx.sub"), "| __init__ exécuté :", marker.exists())
assert resolve("pkgx.sub").endswith("sub.py") and not marker.exists()
importlib.util.find_spec("pkgx.sub")
print("après importlib.util.find_spec :", "__init__ exécuté :", marker.exists())
assert marker.exists()
origin = resolve("cinoc.evaluation.metric")
print("cinoc.evaluation.metric ->", origin, "| cinoc importé :", "cinoc" in sys.modules)
assert origin and origin.endswith("metric.py") and "cinoc" not in sys.modules

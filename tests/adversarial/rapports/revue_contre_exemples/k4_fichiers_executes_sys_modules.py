"""§2.3 c : executed_files = « __file__ / __spec__.origin de chaque module hors
stdlib chargé pour construire puis exécuter le module (différence de
sys.modules) » ; « Une réutilisation exige que tous les fichiers enregistrés se
re-hachent à l'identique » ; I1.

Contre-exemples (modules jetables dans un dossier temporaire) :
 (1) un module DÉJÀ chargé (par Cinoc ou par une étape précédente) n'apparaît
     dans la différence d'aucune étape suivante : le modifier ne change pas
     l'identité de l'étape B qui l'utilise -> relecture périmée ;
 (2) la différence dépend de l'historique du processus : le même module, sur
     deux documents successifs, enregistre deux ensembles différents ;
 (3) circularité : step_key(k) contient l'identité de l'étape, donc
     executed_files, connu seulement APRÈS l'exécution ; la clé de recherche
     ne peut pas le contenir.
"""
import hashlib, importlib, sys, tempfile, textwrap
from pathlib import Path

tmp = Path(tempfile.mkdtemp()); sys.path.insert(0, str(tmp))
(tmp / "shared_norm.py").write_text("def norm(s):\n    return s.lower()\n")
(tmp / "lazy_helper.py").write_text("X = 1\n")
(tmp / "step_a.py").write_text("import shared_norm\ndef execute(t):\n    return shared_norm.norm(t)\n")
(tmp / "step_b.py").write_text(textwrap.dedent("""
    def execute(t):
        import shared_norm, lazy_helper   # import paresseux
        return shared_norm.norm(t) + str(lazy_helper.X)
"""))

def recorded(fn):
    before = set(sys.modules)
    out = fn()
    files = {}
    for name in set(sys.modules) - before:
        origin = getattr(sys.modules[name], "__file__", None)
        if origin and str(tmp) in origin:
            files[Path(origin).name] = hashlib.sha256(Path(origin).read_bytes()).hexdigest()[:8]
    return out, files

_, files_a = recorded(lambda: importlib.import_module("step_a").execute("ABC"))
out_b1, files_b_doc1 = recorded(lambda: importlib.import_module("step_b").execute("ABC"))
out_b2, files_b_doc2 = recorded(lambda: importlib.import_module("step_b").execute("DEF"))
print("étape A, executed_files :", files_a)
print("étape B, document 1    :", files_b_doc1, "  <- shared_norm absent (déjà chargé par A)")
print("étape B, document 2    :", files_b_doc2, "  <- vide : tout est déjà chargé")
assert "shared_norm.py" not in files_b_doc1 and files_b_doc1 != files_b_doc2

# (1) on modifie shared_norm : la vérification « fichiers enregistrés de B » passe
(tmp / "shared_norm.py").write_text("def norm(s):\n    return s.upper()\n")
still_valid = all(hashlib.sha256((tmp / f).read_bytes()).hexdigest()[:8] == h for f, h in files_b_doc1.items())
print("B réutilisable après modification de shared_norm ?", still_valid)
assert still_valid
print("=> enregistrer l'ensemble des modules chargés (hors stdlib) au moment de l'exécution,"
      " par étape et une fois pour le run, pas une différence de sys.modules ;"
      " et séparer clé de recherche (déclarée) et prédicat de réutilisation (fichiers).")

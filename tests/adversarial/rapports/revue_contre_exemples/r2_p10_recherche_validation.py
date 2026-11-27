"""Révision 2, P10 (§ 2.2) :
  lookup_key(k) = H(partie DÉCLARÉE de la définition, artefacts consommés, unit_inputs déclarés, repetition_id)
  validation(record) : chaque fichier de record.environment se re-hache à l'identique, et chaque --version est identique
avec I1 : « modifier … un fichier de poids … interdit la réutilisation » et § 2.3 c :
les poids (P15) et les sources de la brique sont dans StepDefinition, PAS dans StepEnvironment.

(a) Un fichier de poids (traineddata, .pt) remplacé : il n'est ni dans la clé
    (partie déclarée) ni dans la validation (environnement) -> record relu.
(b) La validation re-hache les CHEMINS enregistrés. Si le processus courant
    résout le module ailleurs (autre venv, module homonyme plus tôt dans
    sys.path), l'ancien fichier est intact sur disque -> validation passe alors
    que le code exécuté aujourd'hui a changé.
Implémentation littérale des deux formules.
"""
import hashlib, importlib.util, json, sys, tempfile
from pathlib import Path
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
H = lambda o: hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()[:12]
tmp = Path(tempfile.mkdtemp())
w = tmp / "fra.traineddata"; w.write_bytes(b"poids v1")
v1 = tmp / "venv1"; v2 = tmp / "venv2"; v1.mkdir(); v2.mkdir()
(v1 / "seg_lib.py").write_text("def run(x): return x\n")
(v2 / "seg_lib.py").write_text("def run(x): return x[::-1]\n")   # code différent

declared = {"brick": "tesseract", "version": "1", "settings_sent": {"lang": "fra"}, "model": "fra"}
def lookup_key(): return H([declared, [("IMAGE", "sha-img")], [], 0])
# Run 1 (sys.path = venv1) : on enregistre définition et environnement
sys.path.insert(0, str(v1)); spec1 = importlib.util.find_spec("seg_lib")
record = {"key": lookup_key(),
          "definition": {"weights": {str(w): sha(w)}},
          "environment": {spec1.origin: sha(spec1.origin)}, "versions": {"tesseract": "5.3.4"}}
sys.path.remove(str(v1))
def validation(rec, versions_now):
    return all(sha(p) == h for p, h in rec["environment"].items()) and rec["versions"] == versions_now

# (a) poids remplacés
w.write_bytes(b"poids v2 (autre modele)")
print("(a) poids remplacés : clé identique =", lookup_key() == record["key"],
      "| validation =", validation(record, {"tesseract": "5.3.4"}))
assert lookup_key() == record["key"] and validation(record, {"tesseract": "5.3.4"})
# (b) run 2 dans venv2 : le module résolu aujourd'hui n'est pas celui enregistré
sys.path.insert(0, str(v2)); now = importlib.util.find_spec("seg_lib").origin
print("(b) module enregistré :", Path(spec1.origin).parent.name, "| module résolu aujourd'hui :", Path(now).parent.name,
      "| validation =", validation(record, {"tesseract": "5.3.4"}))
assert now != spec1.origin and validation(record, {"tesseract": "5.3.4"})
print("=> valider aussi la partie calculée de la définition (poids, sources) ; valider par NOM de module"
      " résolu dans le processus courant (find_spec), pas en re-hachant les chemins enregistrés.")

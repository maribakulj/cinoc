"""§2.3 e « Archive = sac BagIt scellé : objects/<sha>, ground_truth/<sha>,
spec.json, run_result.json, observations ; lecture = bagit.Bag.validate() + ... »
I6 « une archive altérée (octet ... de la spec) est refusée avant toute note » ;
§2.3 a 2 « empreinte racine = empreinte du tagmanifest ».

bagit-python ne vérifie que ce que les manifestes listent. Un fichier de
tag (hors `data/`) non listé dans `tagmanifest-*` peut être ajouté ou modifié
sans que `validate()` ni l'empreinte racine ne bougent. La disposition décrite
(spec.json, run_result.json à la racine ?) n'est pas assez précise.
"""
import hashlib, os, shutil, stat, tempfile
from pathlib import Path
import bagit

root = Path(tempfile.mkdtemp())
d = root / "bag"; d.mkdir()
(d / "objects").mkdir(); (d / "objects" / "ab12").write_bytes(b"sortie OCR")
bag = bagit.make_bag(str(d), checksums=["sha256"])
# Cinoc écrit spec.json / run_result.json APRÈS make_bag, hors data/ (lecture littérale du § 2.3 e)
(d / "spec.json").write_text('{"metric": "cer"}')
(d / "run_result.json").write_text('{"cer": 0.10}')
bag = bagit.Bag(str(d)); bag.save()          # re-scelle : tagmanifest régénéré
anchor = hashlib.sha256((d / "tagmanifest-sha256.txt").read_bytes()).hexdigest()
print("tagmanifest liste :", sorted(bag.tagfile_entries() if hasattr(bag, "tagfile_entries") else []))
print((d / "tagmanifest-sha256.txt").read_text())

# 1) altération d'un fichier de tag LISTÉ : détectée (bagit tient)
txt = (d / "run_result.json").read_text()
(d / "run_result.json").write_text('{"cer": 0.01}')
try:
    bagit.Bag(str(d)).validate(fast=False); print("tag listé altéré : accepté ?!")
except bagit.BagValidationError:
    print("tag listé altéré : refusé (tient)")
(d / "run_result.json").write_text(txt)
# 2) AJOUT de fichiers de tag non listés (ex. un second jeu d'observations, une spec « corrigée »)
(d / "observations.json").write_text('[{"doc": "d1", "cer": 0.0}]')
(d / "overrides").mkdir(); (d / "overrides" / "spec.json").write_text('{"metric": "wer"}')
bagit.Bag(str(d)).validate(fast=False)
print("validate() après AJOUT de observations.json et overrides/spec.json hors manifeste : OK (aucune erreur)")
same = anchor == hashlib.sha256((d / "tagmanifest-sha256.txt").read_bytes()).hexdigest()
print("empreinte racine inchangée :", same)
assert same

# Témoin : sous data/, l'altération est bien refusée
(d / "data" / "objects" / "ab12").write_bytes(b"sortie OCR alteree")
try:
    bagit.Bag(str(d)).validate(fast=False); print("data/ altéré : accepté ?!")
except bagit.BagValidationError as e:
    print("témoin data/ altéré : refusé —", str(e).splitlines()[0][:90])

# Liens physiques : lstat ne les voit pas comme « liens »
f = d / "data" / "objects" / "ab12"; other = root / "blob"; os.link(f, other)
st = os.lstat(f)
print("lien dur : S_ISLNK =", stat.S_ISLNK(st.st_mode), " st_nlink =", st.st_nlink)
# 0444 n'empêche pas root d'écrire en place
os.chmod(other, 0o444)
with open(other, "r+b") as fh:
    fh.write(b"X")
print("uid =", os.getuid(), "; écriture en place sur un blob 0444 réussie :", f.read_bytes()[:12])

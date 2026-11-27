"""§2.3 d : ProtocolIdentity = H(..., empreintes des VT) ; ObservationId = H(sortie,
VT du document, ProtocolIdentity) ; I3 « changer ... de VT ... change chaque
ObservationId » ; I5.

L'empreinte de la VT du document est déjà dans ObservationId. Mettre AUSSI
toutes les VT du corpus dans ProtocolIdentity rend l'identité d'une
observation dépendante des AUTRES documents : corriger une coquille dans la VT
de d2 change l'identité de d1 (inchangé), et re-noter un sous-ensemble de
l'archive ne reproduit jamais aucune identité. Formules littérales.
"""
import hashlib, json
H = lambda *x: hashlib.sha256(json.dumps(x).encode()).hexdigest()[:12]
view, metric = "texte", "cer:S,D,I,n_ref"
def protocol(gts): return H(view, metric, sorted(gts.values()))
def obs_id(out, gt, gts): return H(out, gt, protocol(gts))
gts = {"d1": "sha-gt1", "d2": "sha-gt2"}
before = obs_id("sha-out1", gts["d1"], gts)
after_fix = obs_id("sha-out1", gts["d1"], {**gts, "d2": "sha-gt2-corrige"})
subset = obs_id("sha-out1", gts["d1"], {"d1": gts["d1"]})
print("ObservationId(d1) :", before, "| après correction de la VT de d2 :", after_fix, "| re-notation de d1 seul :", subset)
assert before != after_fix and before != subset

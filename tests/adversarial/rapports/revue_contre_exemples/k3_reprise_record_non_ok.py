"""§2.2 step_key(k) = H(identité, artefacts consommés, unit_inputs, repetition_id) ;
I1 « la version du paquet et les réglages OPÉRATIONNELS n'y entrent pas » ;
§1.3 « saknussemm : délai codé en dur -> réglage opérationnel déclaré (K4) +
issue `partial` ».

Le contrat ne dit pas QUELS records sont réutilisables. Un record `partial`
ou `truncated` produit sous un délai de 5 s a la même clé que sous 60 s
(le délai est opérationnel) : `--resume` relit la sortie dégradée après
qu'on a relevé le délai précisément pour la corriger. Implémentation
littérale de la formule.
"""
import hashlib, json

def H(obj): return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()[:16]

def step_key(identity, consumed, unit_inputs, repetition_id):
    return H([identity, sorted(consumed), sorted(unit_inputs), repetition_id])

identity = {"module": "saknussemm", "version": "1", "settings_sent": {"prompt": "p", "temperature": 0}}
consumed = [("ALTO_XML", "sha-alto")]
cache = {}
# run 1 : timeout opérationnel 5 s -> la moitié des lignes en repli
k1 = step_key(identity, consumed, [], 0)
cache[k1] = {"outcome": "partial", "reason": "lignes en repli (délai 5 s)"}
# run 2 : --resume avec timeout 60 s (hors identité, par I1)
k2 = step_key(identity, consumed, [], 0)
print("clé run 1 = clé run 2 :", k1 == k2, "->", cache.get(k2))
assert k1 == k2
print("=> préciser : seul un record `ok` est réutilisable ; ou les réglages opérationnels"
      " qui ont produit un `partial`/`truncated` entrent dans la clé de ce record.")

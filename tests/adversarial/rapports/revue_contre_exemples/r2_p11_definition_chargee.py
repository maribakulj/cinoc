"""Révision 2, P11 (§ 2.3 d) : ProtocolDefinition ⊃ « sha256 des sources .py de
cinoc.evaluation et cinoc.formats CHARGÉES » ; I3 « ProtocolDefinition est la même
sur deux plateformes aux mêmes sources » ; I5.

« Chargées » réintroduit dans la définition PORTABLE la dépendance à l'historique
du processus que R9 a retirée de l'environnement : deux points d'entrée qui
calculent le même CER (un appel direct, le runner complet ; CLI contre web)
chargent des ensembles différents de modules -> deux définitions pour un même
protocole. Mesuré sur la copie figée, dans deux sous-processus.
"""
import hashlib, json, subprocess, sys
PROBE = r'''
import sys, json, hashlib
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
register_default_metrics(MetricRegistry())          # le socle complet, comme le runner
{imp}
from cinoc.evaluation.metrics.text import cer
from cinoc.evaluation.context import DocContext
cer.fn(DocContext(document_id="d", reference="abc", hypothesis="abd"))
mods = sorted(m for m in sys.modules if m.startswith(("cinoc.evaluation", "cinoc.formats")))
files = [(m, hashlib.sha256(open(sys.modules[m].__file__, "rb").read()).hexdigest()) for m in mods if getattr(sys.modules[m], "__file__", None)]
print(json.dumps(files))
'''
def definition(imp):
    out = subprocess.run([sys.executable, "-c", PROBE.format(imp=imp)], capture_output=True, text=True, check=True).stdout
    files = json.loads(out); return len(files), hashlib.sha256(out.encode()).hexdigest()[:12]
a = definition("")
b = definition("import cinoc.formats.images  # un run qui a aussi validé les images (F8)")
c = definition("import cinoc.evaluation.longitudinal  # le même CER, calculé par un processus qui a aussi lancé une analyse")
print("re-notation seule            : %d modules, empreinte partielle %s" % a)
print("+ validation des images      : %d modules, empreinte partielle %s" % b)
print("+ analyse longitudinale      : %d modules, empreinte partielle %s" % c)
assert a[1] != b[1] and a[1] != c[1]
print("=> hacher toutes les sources des paquets cinoc.evaluation et cinoc.formats (sur disque), pas les modules chargés.")

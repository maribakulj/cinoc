"""§2.3 d « ProtocolIdentity = H(..., identité de chaque métrique (..., executed_files
du code d'évaluation et de formats qui l'a calculée), ...) » ; I5 « sous le
même protocole, une re-notation rend les mêmes ObservationId ».

Les fichiers réellement exécutés pour calculer un CER incluent des extensions C
dont le NOM porte l'étiquette de plateforme (`cpython-313-x86_64-linux-gnu`) :
sur macOS, Windows, ou un autre Python, ProtocolIdentity diffère toujours.
Une « reproduction sous protocole identique » par un tiers est donc
impossible par construction ; toute re-notation hors de la machine d'origine
devient une « réévaluation sous nouveau protocole ».
"""
import sys
before = set(sys.modules)
import cinoc.evaluation.metrics.text as text
from rapidfuzz.distance import Levenshtein
Levenshtein.opcodes("abc", "abd")
loaded = set(sys.modules) - before
so = sorted({getattr(sys.modules[m], "__file__", "") or "" for m in loaded} - {""})
so = [p for p in so if p.endswith((".so", ".pyd", ".dylib"))]
for p in so[:8]:
    print("  ", p.split("site-packages/")[-1])
print(f"   ... {len(so)} extensions C chargées ; étiquette : {sys.implementation.cache_tag}, {sys.platform}")
assert any("linux" in p for p in so)
print("=> séparer l'identité de la DÉFINITION (sources de cinoc/evaluation et formats, profils,"
      " Unicode, VT) de l'identité d'ENVIRONNEMENT (extensions, versions), publiée à part.")

"""K1 §2.1a : « combinaison (associative, commutative, avec un élément neutre) »
et M6 « combiner les histogrammes par document = calculer sur les jetons poolés »,
pour les familles à somme réelle combinées par `math.fsum` (ECE/MCE : Σ conf_b ;
Moyenne de réels : Σx).

Contre-exemple : fsum n'est exact que sur la liste COMPLÈTE de ses termes ;
appliqué à des sommes partielles déjà arrondies (une par document), il n'est
ni égal au calcul poolé ni associatif.
"""
import math
from fractions import Fraction

doc1, doc2 = [0.1, 0.2], [0.3]                      # confiances d'une même classe
pooled = math.fsum(doc1 + doc2)                     # « jetons poolés »
per_doc = math.fsum([math.fsum(doc1), math.fsum(doc2)])  # « combiner les histogrammes »
print("poolé       :", repr(pooled))
print("par document:", repr(per_doc))
assert pooled != per_doc, "M6 au bit près"

# Non-associativité de la combinaison binaire (fsum à deux termes = + arrondi)
a, b, c = 0.1, 0.2, 0.3
left = math.fsum([math.fsum([a, b]), c])
right = math.fsum([a, math.fsum([b, c])])
print("(a+b)+c =", repr(left), " a+(b+c) =", repr(right))
assert left != right

# Conséquence sur l'ECE d'une classe : |Σjustes - Σconf| / N
justes = 0  # 0 jeton juste ; 3 jetons
ece_pool = abs(justes - pooled) / 3
ece_doc = abs(justes - per_doc) / 3
print("ECE poolé", repr(ece_pool), "ECE par histogrammes", repr(ece_doc))
assert ece_pool != ece_doc
# Référence exacte
exact = abs(Fraction(0) - sum(map(Fraction, doc1 + doc2))) / 3
print("exact (Fraction) :", float(exact))
print("=> la statistique réelle n'est pas un monoïde : garder des entiers "
      "(confiances quantifiées) ou les partiels de Shewchuk, ou fsum sur la liste "
      "plate des jetons à la finalisation.")

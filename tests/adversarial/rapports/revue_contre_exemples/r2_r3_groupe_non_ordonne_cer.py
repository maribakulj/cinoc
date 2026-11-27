"""Révision 2, R3 (§ 2.4 b) : « La référence ordonne (a, b) seulement à travers un
groupe ordonné. La projection en texte linéarise un groupe non ordonné dans
l'ordre de déclaration du fichier. » ; M5 (paires d'un groupe non ordonné exclues
du τ) ; M7 (projection unique).

Deux marginalia déclarées NON ordonnées par la VT : le τ ne pénalise plus
l'ordre inverse (R3 levé), mais le CER de la vue texte, calculé sur la
projection linéaire de la VT, le pénalise, et selon l'ordre de déclaration du
fichier. Deux métriques de la même campagne jugent donc différemment la même
liberté laissée par la VT ; réordonner deux éléments du XML change le CER.
"""
from rapidfuzz.distance import Levenshtein as L
m1, m2 = "Nota bene en marge", "Renvoi au folio 12"
gt_file_order_a = "\n".join([m1, m2]); gt_file_order_b = "\n".join([m2, m1])   # même VT, déclarations permutées
hyp = "\n".join([m2, m1])
cer = lambda r, h: L.distance(r, h) / len(r)
print("τ (paires non ordonnées exclues) : aucune paire -> non pénalisé")
print("CER vue texte, VT déclarée (m1, m2) :", round(cer(gt_file_order_a, hyp), 3))
print("CER vue texte, VT déclarée (m2, m1) :", round(cer(gt_file_order_b, hyp), 3))
assert cer(gt_file_order_a, hyp) > 0 == cer(gt_file_order_b, hyp)
print("=> écrire que la vue texte impose l'ordre de déclaration (convention publiée), ou aligner les"
      " membres d'un groupe non ordonné par appariement avant concaténation (comme FCA).")

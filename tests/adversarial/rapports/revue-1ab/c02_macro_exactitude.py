"""C02 — Le macro est-il exact (« Σ x exacte, n » ; une seule conversion flottante) ?

macro_of() arrondit chaque scalaire de document en flottant, les somme par fsum
(somme exacte des flottants **déjà arrondis**, puis arrondie), puis divise : jusqu'à
trois arrondis. On compare à la valeur exacte float(Σ Fraction(e_d, n_d) / N).
Puis : la même moyenne est-elle invariante par ordre/partition des grappes ?"""
import random
from fractions import Fraction
from cinoc.evaluation.aggregation import macro_of
from cinoc.evaluation.metrics.text import cer
from cinoc.evaluation.statistics import EditCounts

rng = random.Random(7)
ecarts_doc = ecarts_grappe = 0
exemple = None
for trial in range(3000):
    n = rng.randint(2, 9)
    stats = []
    for _ in range(n):
        nref = rng.randint(1, 997)
        s = rng.randint(0, nref)
        stats.append(EditCounts(substitutions=s, deletions=0, insertions=rng.randint(0, 50), reference_length=nref))
    items = list(enumerate(stats))
    got, _ = macro_of(cer, items, [str(i) for i in range(n)], "document")
    exact = float(sum(Fraction(st.edits, st.reference_length) for st in stats) / n)
    if got != exact:
        ecarts_doc += 1
        if exemple is None:
            exemple = ([(st.edits, st.reference_length) for st in stats], got, exact)
    # grappes : 2 grappes, moyenne des moyennes
    clusters = ["g1" if i % 2 else "g0" for i in range(n)]
    got_c, _ = macro_of(cer, items, clusters, "cluster")
    groups = {}
    for i, st in items:
        groups.setdefault(clusters[i], []).append(Fraction(st.edits, st.reference_length))
    exact_c = float(sum(sum(g) / len(g) for g in groups.values()) / len(groups))
    if got_c != exact_c:
        ecarts_grappe += 1
print("écarts macro par document :", ecarts_doc, "/ 3000")
print("écarts macro par grappe   :", ecarts_grappe, "/ 3000")
print("premier exemple (e,n), obtenu, exact :", exemple)
# Lecture la plus favorable : x = les scalaires flottants publiés par document.
rng = random.Random(8); ecarts_f = 0
for trial in range(3000):
    n = rng.randint(2, 9)
    stats = [EditCounts(substitutions=(s := rng.randint(0, (m := rng.randint(1, 997)))), deletions=0, insertions=rng.randint(0, 50), reference_length=m) for _ in range(n)]
    got, _ = macro_of(cer, list(enumerate(stats)), [str(i) for i in range(n)], "document")
    floats = [st.edits / st.reference_length for st in stats]
    if got != float(sum(Fraction(x) for x in floats) / n): ecarts_f += 1
print("écarts au macro exact des scalaires flottants publiés (Σ exacte puis une division) :", ecarts_f, "/ 3000")

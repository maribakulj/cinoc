"""A8 « en singletons, l'IC égale l'IC par document » ; §2.1d « avant tout tirage,
les documents sont triés par id ».

Avec une graine fixée, le bootstrap dépend de l'ORDRE des lignes. Si les
grappes singletons sont triées par id de grappe et les documents par id de
document, les deux ordres diffèrent dès que les noms ne se trient pas pareil
(« c10 » < « c2 ») : l'égalité annoncée est fausse au bit près, vraie
seulement « à l'erreur de Monte-Carlo près ».
"""
import numpy as np
from scipy import stats
docs = {"d01": (3, 100), "d02": (9, 120), "d03": (1, 80), "d04": (12, 150), "d05": (0, 90),
        "d06": (5, 110), "d07": (7, 60), "d08": (2, 130), "d09": (4, 70), "d10": (8, 100)}
cluster_of = {d: f"c{int(d[1:])}" for d in docs}            # grappes singletons c1..c10
by_doc = sorted(docs)
by_cluster = sorted(docs, key=lambda d: cluster_of[d])     # c1, c10, c2, ...
def ci(order):
    E = np.array([docs[d][0] for d in order], float); N = np.array([docs[d][1] for d in order], float)
    f = lambda i, axis=-1: E[i].sum(axis) / N[i].sum(axis)
    r = stats.bootstrap((np.arange(len(order)),), f, n_resamples=2000, method="percentile",
                        rng=np.random.default_rng(0), vectorized=True)
    return r.confidence_interval
print("ordre des documents :", by_doc[:3], "... IC =", ci(by_doc))
print("ordre des grappes   :", by_cluster[:3], "... IC =", ci(by_cluster))
assert ci(by_doc) != ci(by_cluster)
print("=> trier les grappes par le plus petit id de document qu'elles contiennent (singletons = documents).")

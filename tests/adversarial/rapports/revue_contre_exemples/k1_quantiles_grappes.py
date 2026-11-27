"""§2.1a « Quantiles (analyses) : données élémentaires ; Les quantiles sont la
seule famille qui rééchantillonne des données élémentaires » (percentiles par
LIGNE).

Si l'élément rééchantillonné est la ligne, les lignes d'une même page
(même main, même moteur, même dégradation) sont traitées comme
indépendantes : l'IC de la médiane des CER par ligne est trop étroit. Simulation :
couverture nominale 95 %.
"""
import numpy as np
rng = np.random.default_rng(3)
n_docs, n_lines, sims, B = 8, 60, 300, 400
def corpus():
    effet = rng.normal(0.10, 0.05, n_docs)                  # difficulté propre à la page
    return [np.clip(e + rng.normal(0, 0.02, n_lines), 0, None) for e in effet]
# vraie médiane de la population (grand corpus)
truth = np.median(np.concatenate(corpus_big := [np.clip(e + rng.normal(0, 0.02, n_lines), 0, None) for e in rng.normal(0.10, 0.05, 20000)]))
cover_line = cover_doc = 0
for _ in range(sims):
    docs = corpus(); flat = np.concatenate(docs)
    m_line = [np.median(rng.choice(flat, flat.size)) for _ in range(B)]
    m_doc = [np.median(np.concatenate([docs[i] for i in rng.integers(0, n_docs, n_docs)])) for _ in range(B)]
    lo, hi = np.percentile(m_line, [2.5, 97.5]); cover_line += lo <= truth <= hi
    lo, hi = np.percentile(m_doc, [2.5, 97.5]); cover_doc += lo <= truth <= hi
print(f"couverture IC 95 % de la médiane par ligne : rééchantillonnage des LIGNES {cover_line/sims:.2f}, des DOCUMENTS {cover_doc/sims:.2f}")
assert cover_line / sims < 0.8 < cover_doc / sims

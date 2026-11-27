"""K1 §2.1a (familles « Taux d'édition » et « MER ») et M1.

1. (S, D, I) n'est PAS une fonction des deux textes : seule S+D+I l'est.
   Plusieurs alignements de coût minimal existent ; `ins_rate`, `del_rate`,
   `mer`, `cmer` dépendent du départage de l'implémentation (rapidfuzz).
2. M1 « égal à jiwer ... pages à référence vide comprises » : jiwer refuse-t-il
   une référence vide ?
"""
import itertools
from rapidfuzz.distance import Levenshtein

def all_optimal_sdi(ref, hyp):
    """Énumère par programmation dynamique tous les triplets (S,D,I) de coût minimal."""
    n, m = len(ref), len(hyp)
    from functools import lru_cache
    @lru_cache(None)
    def go(i, j):
        if i == n and j == m:
            return {(0, 0, 0, 0)}
        out = set()
        if i < n and j < m:
            for (c, s, d, k) in go(i + 1, j + 1):
                out.add((c + (ref[i] != hyp[j]), s + (ref[i] != hyp[j]), d, k))
        if i < n:
            for (c, s, d, k) in go(i + 1, j):
                out.add((c + 1, s, d + 1, k))
        if j < m:
            for (c, s, d, k) in go(i, j + 1):
                out.add((c + 1, s, d, k + 1))
        best = min(c for c, *_ in out)
        return {t for t in out if t[0] == best}
    return sorted({t[1:] for t in go(0, 0)})

ref, hyp = "ab", "ba"
opt = all_optimal_sdi(ref, hyp)
print("triplets (S,D,I) optimaux pour", (ref, hyp), ":", opt)
for s, d, i in opt:
    h = len(ref) - s - d
    print(f"  S={s} D={d} I={i}  CER={(s+d+i)/len(ref):.3f}  ins_rate={i/len(ref):.3f}"
          f"  del_rate={d/len(ref):.3f}  MER={(s+d+i)/(h+s+d+i):.3f}")
ops = Levenshtein.opcodes(ref, hyp)
print("rapidfuzz choisit :", [(o.tag, o.src_start, o.src_end, o.dest_start, o.dest_end) for o in ops])
assert len(opt) > 1, "plusieurs alignements optimaux"
mers = {(s + d + i) / (len(ref) - s - d + s + d + i) for s, d, i in opt}
assert len(mers) > 1, "MER dépend du départage"

import jiwer
print("jiwer", jiwer.__version__ if hasattr(jiwer, "__version__") else "")
print("jiwer.mer('a b', 'b a') =", jiwer.mer("a b", "b a"))
try:
    print("jiwer.cer(['', 'abc'], ['xyz', 'abc']) =", jiwer.cer(["", "abc"], ["xyz", "abc"]))
except Exception as exc:  # oracle indisponible sur référence vide
    print("jiwer refuse la référence vide :", type(exc).__name__, exc)
try:
    print("jiwer.cer([''], ['xyz']) =", jiwer.cer([""], ["xyz"]))
except Exception as exc:
    print("jiwer, corpus entièrement vide :", type(exc).__name__, exc)

# M1 : « corpus entièrement vide : CER/WER micro indéfinis » contre l'oracle déclaré
for refs, hyps in [([""], [""]), ([""], ["xyz"]), (["", ""], ["a b", ""])]:
    print("jiwer corpus vide", refs, hyps, "cer =", jiwer.cer(refs, hyps), "wer =", jiwer.wer(refs, hyps))
print("=> jiwer donne un nombre là où M1 exige « indéfini » : l'oracle et l'invariant se contredisent"
      " sur le corpus entièrement vide (il faut exclure ce cas de l'égalité à jiwer).")

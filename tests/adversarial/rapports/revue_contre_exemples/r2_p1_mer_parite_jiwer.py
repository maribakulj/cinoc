"""Révision 2, P1 (« parmi les alignements optimaux, maximiser S ») contre M1
(« égal à jiwer … S+D+I seulement ») et § 4.2 (tests qui figent un défaut).

Les tests existants `tests/evaluation/test_metrics_parity.py::test_mer_matches_jiwer`
et `test_metrics_conformity.py` (cmer, parité jiwer) comparent MER/cMER à jiwer.
Avec les comptes canoniques (max S), MER = (S+D+I)/(n_réf+I) s'écarte de jiwer
dès qu'il existe des alignements ex æquo, et ces tests ne sont pas listés au § 4.2.
On évalue la règle canonique (formule de l'auteur) sur leurs paires et sur un cas minimal.
"""
from rapidfuzz.distance import Levenshtein as L
import jiwer

def canon(r, h):
    d = L.distance(r, h); K = len(r) + len(h) + 1
    W = L.distance(r, h, weights=(K, K, K - 1))
    S = K * d - W; D = (d - S - (len(h) - len(r))) // 2
    return S, D, d - S - D

def mer_canon(r, h):
    S, D, I = canon(r, h); return (S + D + I) / (len(r) + I) if len(r) + I else None

def words(s): return s.split()
pairs = [("le chat noir", "le chien noir"), ("Icy commence le prologue", "Icy commence le prologve"),
         ("maistre Jehan Froissart", "maistre Jehan Froiart"), ("hello world here", "world here"),
         ("transcription test case", "transcryption test case")]
print("paires de test_metrics_parity (MER mot) :")
for r, h in pairs:
    print(f"  {r!r:30s} canon={mer_canon(words(r), words(h)):.4f} jiwer={jiwer.mer(r, h):.4f}")
print("cMER (caractères), paires de test_metrics_conformity :")
diff = []
for r, h in [("abc", "abd"), ("ab", "abxy"), ("chat", "chien"), ("", "xy")]:
    o = jiwer.process_characters(r, h) if r else None
    jm = (o.substitutions + o.deletions + o.insertions) / (o.hits + o.substitutions + o.deletions + o.insertions) if o else None
    c = mer_canon(r, h)
    print(f"  {r!r:8s}{h!r:8s} canon={c} jiwer={jm}")
    if jm is not None and abs(c - jm) > 1e-12: diff.append((r, h, c, jm))
r, h = "a b", "b a"
print("cas minimal mots :", mer_canon(words(r), words(h)), "contre jiwer", jiwer.mer(r, h))
assert diff or mer_canon(words(r), words(h)) != jiwer.mer(r, h)
print("écarts sur les paires des tests existants :", diff)

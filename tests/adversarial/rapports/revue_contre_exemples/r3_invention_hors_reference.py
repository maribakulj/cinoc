"""Révision 3, N3 (§ 2.1 c) : analyse « invention hors référence » : « par pipeline,
le nombre de documents sans référence dont la sortie n'est pas vide, et la somme
exacte des unités inventées … publiés à côté de chaque macro ».

(a) « Par pipeline » = sur le support CONDITIONNEL de chaque pipeline. Un pipeline
    qui ÉCHOUE sur les pages blanches (hors D^μ, motif `step_failed`) n'y invente
    rien : il paraît plus propre qu'un pipeline qui les lit. A6 interdit pourtant
    toute comparaison hors support apparié, et ces deux nombres sont publiés côte
    à côte pour tous les pipelines.
(b) « Unités inventées » n'est pas défini pour toutes les familles dont le macro est
    publié : pour les proportions à dénominateur de référence (`numseq_*`,
    `searchability`, `diacritic_err`, `mufi_err`), la statistique (k, n) ne compte
    aucune unité de l'hypothèse (`metrics/structured_data.py:168-175` : seules les
    séquences de la VT sont comptées).
"""
# 4 pages blanches (référence vide). None = étape en échec ; sinon texte produit.
A = {"b1": None, "b2": None, "b3": None, "b4": ""}              # échoue sur 3 pages blanches sur 4
B = {"b1": "yy", "b2": "", "b3": "", "b4": ""}                  # lit les 4, invente 2 car. sur b1
def invention(P, docs):
    out = [d for d in docs if P[d] is not None and P[d] != ""]
    return len(out), sum(len(P[d]) for d in out)
cond = {p: invention(S, [d for d in S if S[d] is not None]) for p, S in {"A": A, "B": B}.items()}
paired = [d for d in A if A[d] is not None and B[d] is not None]
pair = {p: invention(S, paired) for p, S in {"A": A, "B": B}.items()}
print("par pipeline (conditionnel) : (documents, caractères inventés) =", cond)
print("sur le support apparié", paired, ":", pair)
assert cond["A"] == (0, 0) and cond["B"] == (1, 2) and pair["A"] == pair["B"]
print("A paraît n'inventer jamais parce qu'il a échoué ; sur le support apparié, A et B sont identiques.")
print("=> publier l'analyse sur le support apparié (ou global) avec la couverture des pages blanches,"
      " et définir l'unité inventée par famille (« non défini » pour les proportions à dénominateur de référence).")

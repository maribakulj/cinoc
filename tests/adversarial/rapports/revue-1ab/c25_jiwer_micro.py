"""C25 — M1 : CER/WER micro (comptes cumulés) contre jiwer sur corpus aléatoires
(Σ n_réf > 0, pages blanches comprises) ; S+D+I identiques, D/I peuvent différer."""
import random, jiwer
from cinoc.evaluation.metrics.text import cer, wer
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.statistics import combine, edit_rate
rng = random.Random(5); bad_c = bad_w = 0; diff_di = 0
W = ["le", "la", "ſoleil", "luit", "sur", "seine", "a", "b"]
for t in range(400):
    refs, hyps = [], []
    for _ in range(rng.randint(1, 6)):
        r = " ".join(rng.choice(W) for _ in range(rng.randint(0, 8)))
        h = " ".join(rng.choice(W) for _ in range(rng.randint(0, 8)))
        refs.append(r); hyps.append(h)
    if not all(r.split() for r in refs): continue
    sc = combine([cer.statistic(DocContext("d", r, h)) for r, h in zip(refs, hyps)])
    sw = combine([wer.statistic(DocContext("d", r, h)) for r, h in zip(refs, hyps)])
    # jiwer : listes de phrases ; il ignore/refuse les références vides selon version
    pr = [(r, h) for r, h in zip(refs, hyps)]
    oc = jiwer.process_characters([r for r, _ in pr], [h for _, h in pr])
    ow = jiwer.process_words([r for r, _ in pr if r], [h for r, h in pr if r]) if all(r.split() for r, _ in pr) else None
    if edit_rate(sc).value != oc.cer: bad_c += 1
    if ow is not None:
        if edit_rate(sw).value != ow.wer: bad_w += 1
        if (sw.deletions, sw.insertions) != (ow.deletions, ow.insertions): diff_di += 1
print("CER micro ≠ jiwer :", bad_c, "| WER micro ≠ jiwer :", bad_w, "| (D, I) WER ≠ jiwer (écart voulu, P1) :", diff_di)

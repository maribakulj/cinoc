"""C03 — Classe de calibration : int(c*10) (flottant) contre floor(Fraction(c)*10) (exact).
Et aller-retour JSON de CalibrationBin.confidence_sum (Fraction)."""
import math, random, json
from fractions import Fraction
from cinoc.evaluation.calibration import calibration_from_pairs
from cinoc.evaluation.analysis import CalibrationBin
rng = random.Random(3)
found = []
for k in range(1, 10):
    x = k / 10
    for _ in range(200):
        x = math.nextafter(x, 0)
        if int(x * 10) != math.floor(Fraction(x) * 10):
            found.append(x); break
print("confiances mal classées par int(c*10) :", found[:5])
if found:
    x = found[0]
    print(" ", repr(x), "exact*10 =", float(Fraction(x)*10), "< ", math.ceil(Fraction(x)*10), "; int(x*10) =", int(x*10))
    ece, mce, bins = calibration_from_pairs([(x, True)])
    print("  bin publié :", [(b.lower, b.upper) for b in bins])
_, _, bins = calibration_from_pairs([(0.31, True), (0.37, False)])
s = bins[0].model_dump_json()
print("JSON d'un bin :", s)
b2 = CalibrationBin.model_validate_json(s)
print("aller-retour égal :", b2 == bins[0], b2.confidence_sum == bins[0].confidence_sum)

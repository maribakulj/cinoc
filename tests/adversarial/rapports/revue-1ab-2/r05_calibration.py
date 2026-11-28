"""R05 — D14 : classe de calibration aux bornes float(k/10), comparaison exacte."""
import math
from cinoc.evaluation.calibration import calibration_from_pairs
vals = [0.0, 0.1, math.nextafter(0.1, 0), 0.3, math.nextafter(0.3, 0), math.nextafter(0.3, 1), 0.7, math.nextafter(0.7, 0), 0.8999999999999999, 0.9, 1.0, 0.1 + 0.2, 0.7 + 0.1]
for c in vals:
    _, _, bins = calibration_from_pairs([(c, True)])
    b = bins[0]
    ok = b.lower <= c < b.upper or (c == 1.0 and b.upper == 1.0)
    print(f"{c!r:22} → [{b.lower!r}, {b.upper!r}[  {'OK' if ok else 'HORS BORNES'}")

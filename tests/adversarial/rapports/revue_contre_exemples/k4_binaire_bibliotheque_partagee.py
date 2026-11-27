"""§2.3 c : binaries = « {exécutable résolu à l'appel: sha256} + fichiers de
données déclarés (traineddata) » ; I1 « modifier un ... binaire ... change
l'identité ».

Sur cette machine, `/usr/bin/tesseract` est une coquille : le moteur est dans
`libtesseract.so.5` (paquet distinct sous Debian/Ubuntu). Une mise à jour du
moteur ne change pas l'empreinte de l'exécutable. Même chose pour leptonica
(décodage d'image) et, côté Python, pour les .so liés (OpenBLAS de numpy).
"""
import hashlib, os, shutil, subprocess
exe = shutil.which("tesseract")
if exe is None:
    raise SystemExit("tesseract absent : contre-exemple non exécutable ici")
exe = os.path.realpath(exe)
size = os.path.getsize(exe)
libs = [l.split("=>")[1].split()[0] for l in subprocess.run(["ldd", exe], capture_output=True, text=True).stdout.splitlines() if "=>" in l]
eng = [l for l in libs if "tesseract" in l or "lept" in l]
print(f"{exe} : {size} octets, sha256 {hashlib.sha256(open(exe,'rb').read()).hexdigest()[:12]}")
for l in eng:
    r = os.path.realpath(l)
    print(f"  lié à {r} : {os.path.getsize(r)} octets (hors de l'empreinte « exécutable résolu »)")
assert size < 100_000 and eng

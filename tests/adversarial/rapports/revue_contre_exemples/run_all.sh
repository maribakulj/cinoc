#!/usr/bin/env bash
# Rejoue tous les contre-exemples de REVUE_CONTRATS.md. Code de sortie 0 = chaque
# contre-exemple a été reproduit (ses assertions passent).
set -u
S="${CINOC_SCRATCH:?définir CINOC_SCRATCH}"
CE=$S/ce-venv/bin/python; RV=$S/review-venv/bin/python
export PYTHONPATH=$S/contre-expertise
cd "$(dirname "$0")"
fail=0
for f in k*.py r2_*.py r3_*.py; do
  py=$CE; case $f in k4_bagit*|k1_ner_oracle*) py=$RV;; esac
  if $py -W ignore "$f" > "out_${f%.py}.txt" 2>&1; then echo "reproduit  $f"; else echo "ÉCHEC      $f"; fail=1; fi
done
exit $fail

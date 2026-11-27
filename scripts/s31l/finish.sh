#!/usr/bin/env bash
# S31L — clôture de la campagne locale, une fois campaign.sh fini.
# Relançable tel quel (rien n'est recalculé : tout est relu de l'archive).
#
#  Pour bnl-local, bnl-local-saknussemm, dresden-local :
#  1. chaque score noté EN LIGNE par une tranche = celui du RunResult final (relu
#     --offline) ; puis une seconde re-notation --offline, comparée au final
#     (pipelines, documents, cross_engine, analyses identiques ; usage hors `resumed`) ;
#  2. déterminisme : hashes d'artefacts du rejeu (archive neuve) contre la campagne,
#     |ΔCER| par pipeline quand ils diffèrent ;
#  3. oracle dinglehopper (venv d'oracle, script de S30) sur chaque unité notée ;
#  4. copie les RunResult finaux dans final/ (refus s'ils contiennent un chemin local).
#  Puis : durées par tranche, contrôle des unités saknussemm entièrement en repli.
#  Résumé : final/SUMMARY.txt.
set -u
SP=/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad
L=$SP/s31l
V=$L/venv/bin
OUT=$L/out
FINAL=$L/final
mkdir -p "$OUT" "$FINAL"
SUMMARY=$FINAL/SUMMARY.txt
: > "$SUMMARY"
say() { echo "$@" | tee -a "$SUMMARY"; }

for pair in bnl:bnl-local bnl:bnl-local-saknussemm dresden:dresden-local; do
  c=${pair%%:*}; spec=${pair#*:}
  cd "$SP/s30/$c" || exit 1
  say "=== $spec ==="
  if [ ! -s "$OUT/$spec.json" ]; then
    say "ABSENT : $OUT/$spec.json (le run final n'a pas fini) — on saute $spec."
    continue
  fi
  say "-- unités (issue) :"
  python3 -I - "$OUT/$spec.json" <<'EOF2' | tee -a "$SUMMARY"
import collections, json, sys
r = json.load(open(sys.argv[1], encoding="utf-8"))
c = collections.Counter((u["pipeline"], u["outcome"]) for u in r["usage"])
for (p, o), n in sorted(c.items()):
    print(f"   {p} : {o} × {n}")
EOF2
  say "-- scores notés en ligne (tranches) = RunResult final (relu hors ligne) :"
  python3 -I "$L/compare_chunks.py" "$OUT/$spec.json" $(ls "$OUT"/chunk-*.json | grep -v "chunk-det-" | if [ "$c" = bnl ]; then grep -E "chunk-(b|s)[0-9]"; else grep -E "chunk-d[0-9]"; fi) 2>&1 | tail -3 | tee -a "$SUMMARY"
  say "-- seconde re-notation hors ligne, comparée au final :"
  ( time "$V/cinoc" run "$spec.yaml" --offline --resume-dir "$L/archive-$c" \
      --json "$OUT/$spec.offline.json" -o "$OUT/$spec.offline.html" ) \
      > "$OUT/$spec-offline.log" 2>&1
  tail -3 "$OUT/$spec-offline.log" | tee -a "$SUMMARY"
  python3 -I "$L/compare.py" "$OUT/$spec.json" "$OUT/$spec.offline.json" | tee -a "$SUMMARY"

  if [ -s "$OUT/chunk-det-$spec.json" ]; then
    say "-- déterminisme (rejeu dans une archive neuve, contre la campagne) :"
    python3 -I "$L/determinism.py" "$L/archive-$c" "$L/archive-$spec-det" \
      "$OUT/$spec.json" "$OUT/chunk-det-$spec.json" | tee -a "$SUMMARY"
  else
    say "-- déterminisme : rejeu absent ($OUT/chunk-det-$spec.json)"
  fi

  say "-- oracle dinglehopper (vue texte (lignes)) :"
  "$SP/oracle-venv/bin/python" -I "$SP/s30/oracle.py" "$spec.yaml" "$L/archive-$c" \
    "$OUT/$spec.json" "$OUT/oracle-$spec.json" 2>&1 | tee -a "$SUMMARY"

  if grep -q -e "$SP" -e "/tmp/" -e "/home/" "$OUT/$spec.json"; then
    say "REFUS : $OUT/$spec.json contient un chemin local — non copié."
  else
    cp "$OUT/$spec.json" "$FINAL/$spec.run_result.json"
    say "RunResult final : $FINAL/$spec.run_result.json ($(du -k "$FINAL/$spec.run_result.json" | cut -f1) Ko)"
  fi
done

say "=== durées des unités exécutées par tranche (hors relues) ==="
for f in "$OUT"/chunk-*.json; do python3 -I "$L/timing.py" "$f" | cut -c1-220; done | tee -a "$SUMMARY"
say "=== contrôle : unités saknussemm archivées entièrement en repli (attendu : aucune) ==="
for a in "$L/archive-bnl" "$L/archive-dresden"; do
  python3 -I "$L/audit_fallbacks.py" "$a" | grep -E "100%-REPLI|délai [1-9]" || say "   $a : aucune"
done | tee -a "$SUMMARY"
say "=== fini : $(date -u +%FT%TZ) ==="

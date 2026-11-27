#!/usr/bin/env bash
# S31L — campagne locale (D-311), un seul run lourd à la fois, --workers 1.
#
# Découpée en tranches : `cinoc run` n'écrit son archive qu'en fin de run (défaut
# connu, corrigé par S31 dans son arbre) — une tranche tuée ne perd qu'elle.
# Chaque tranche reprend les pipelines et réglages des specs commitées tels quels
# (chunk.py) : la spec entière relit ensuite ses unités. Les RunResult finaux
# sont produits --offline (rien n'est rejoué, une unité en échec reste en échec),
# puis finish.sh re-note, compare, lance l'oracle et le contrôle des replis.
set -u
SP=/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad
L=$SP/s31l
V=$L/venv/bin
OUT=$L/out
CH=$L/chunks
mkdir -p "$OUT" "$CH"
log() { echo "[$(date -u +%FT%TZ)] $*"; }

E1T="E1 · segmentation → tesseract"
E3R="E3 · segmentation → tesseract → saknussemm (règles)"
E4R="E4 · segmentation → tesseract → saknussemm sélectif (règles"
E2="E2 · tesseract → qwen2.5:3b"
E1V="E1 · segmentation → qwen2.5vl:3b"
E3Q="E3 · segmentation → tesseract → saknussemm (qwen2.5:3b"
E4Q="E4 · segmentation → tesseract → saknussemm sélectif (qwen2.5:3b"
E5="E5 · qwen2.5vl:3b"

# run <corpus> <spec commitée> <nom de tranche> <archive> [args de chunk.py...]
run() {
  local corpus=$1 spec=$2 name=$3 arch=$4; shift 4
  cd "$SP/s30/$corpus" || return 1
  python3 -I "$L/chunk.py" "$spec.yaml" "$CH/$name.yaml" "$@" || return 1
  cp "$CH/$name.yaml" "./chunk-$name.yaml"
  log "début $name"
  ( time "$V/cinoc" run "chunk-$name.yaml" --workers 1 --resume-dir "$arch" \
      --json "$OUT/chunk-$name.json" -o "$OUT/chunk-$name.html" ) \
      > "$L/logs/chunk-$name.log" 2>&1
  log "fin $name (code $?) : $(grep -h 'Bilan' "$L/logs/chunk-$name.log" | tail -1)"
}

AB=$L/archive-bnl
AD=$L/archive-dresden

# 1. BNL : unités à fan-out sans clé (ré-exécutées depuis FANOUT_VERSION 2), E2.
run bnl bnl-local b1-fanout-sans-cle "$AB" --pipeline "$E1T" --pipeline "$E3R" --pipeline "$E4R"
run bnl bnl-local b2-e2 "$AB" --pipeline "$E2"
# 2. BNL, sous-ensemble fixé (rangs multiples de 8) : correction structurée par qwen2.5:3b.
run bnl bnl-local-saknussemm s1-e3-qwen "$AB" --pipeline "$E3Q"
run bnl bnl-local-saknussemm s2-e4-qwen "$AB" --pipeline "$E4Q"
# 3. Dresden : E5 local (6 unités en échec à 600 s en S30, --workers 2 : retentées
#    seules), unités à fan-out sans clé, E2.
run dresden dresden-local d1-e5 "$AD" --pipeline "$E5"
run dresden dresden-local d2-fanout-sans-cle "$AD" --pipeline "$E1T" --pipeline "$E3R"
run dresden dresden-local d3-e2 "$AD" --pipeline "$E2"
# 4. BNL : VLM par région, 35 pages restantes en 5 tranches (0000, 0001 déjà archivées).
run bnl bnl-local b3-e1v-1 "$AB" --pipeline "$E1V" --docs 0002,0008,0013,0018,0023,0028,0033
run bnl bnl-local b3-e1v-2 "$AB" --pipeline "$E1V" --docs 0003,0009,0014,0019,0024,0029,0035
run bnl bnl-local b3-e1v-3 "$AB" --pipeline "$E1V" --docs 0004,0010,0015,0020,0025,0030,0036
run bnl bnl-local b3-e1v-4 "$AB" --pipeline "$E1V" --docs 0006,0011,0016,0021,0026,0031,0037
run bnl bnl-local b3-e1v-5 "$AB" --pipeline "$E1V" --docs 0007,0012,0017,0022,0027,0032,0038

# 5. RunResult finaux, relus hors ligne (rien n'est rejoué).
for pair in bnl:bnl-local bnl:bnl-local-saknussemm dresden:dresden-local; do
  corpus=${pair%%:*}; spec=${pair#*:}
  cd "$SP/s30/$corpus" || continue
  log "final $spec"
  ( time "$V/cinoc" run "$spec.yaml" --offline --resume-dir "$L/archive-$corpus" \
      --json "$OUT/$spec.json" --csv "$OUT/$spec.csv" -o "$OUT/$spec.html" ) \
      > "$L/logs/final-$spec.log" 2>&1
  log "fin final $spec (code $?) : $(grep -h 'Bilan' "$L/logs/final-$spec.log" | tail -1)"
done

# 6. Preuve de déterminisme : rejeu de pages fixées dans des archives neuves.
run bnl bnl-local det-bnl-local "$L/archive-bnl-local-det" \
  --pipeline "$E2" --pipeline "$E1V" --pipeline "$E5" --docs 0003,0006,0031
run bnl bnl-local-saknussemm det-bnl-local-saknussemm "$L/archive-bnl-local-saknussemm-det" \
  --pipeline "$E3Q" --pipeline "$E4Q" --docs 0017
run dresden dresden-local det-dresden-local "$L/archive-dresden-local-det" \
  --pipeline "$E2" --pipeline "$E5" --docs Mscr.Dresd.K80_177,Mscr.Dresd.K80_178,Mscr.Dresd.K80_179

# 7. Clôture.
log "finish.sh"
bash "$L/finish.sh" > "$L/logs/finish.log" 2>&1
log "CAMPAGNE FINIE (code $?)"

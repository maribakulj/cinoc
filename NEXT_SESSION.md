# NEXT_SESSION.md — démarrage de la prochaine session

> Point d'entrée **mince** pour reprendre dans une session fraîche. Ce fichier
> **pointe, il ne recopie pas** : tout statut dupliqué ici pourrit (il est resté
> gelé à l'ère T1/TU2 pendant que T5→T7 étaient livrés — dérive verrouillée
> depuis par `tests/architecture/test_status_freshness.py`).

## 1. À lire, dans l'ordre

1. `CLAUDE.md` — contrat de travail : deux axes, 5 garde-fous, architecture
   en couches (chargé automatiquement).
2. `MIGRATION_PLAN.md` §roll-up **« Les deux axes »** — **l'autorité de
   statut** : ce qui est fait, ce qui est différé (et pourquoi), la prochaine
   étape. Le journal de décisions (`D-0xx`) y vit aussi.
3. `PLAN_PARITE.md` — le parcours **post-T7/S6** : tranches T8→T15 + S7 vers
   la parité fonctionnelle avec Picarones (périmètre arbitré : repris /
   abandonné).
4. `PLAN_FIN_MIGRATION.md` — **la route finale vers `1.0.0`** : les étapes
   ordonnées, du Space qui exécute un vrai OCR jusqu'à la release et au gel de
   Picarones, en passant par les phases `P#` que l'usage réel a fait naître
   (`P5a` dette du premier banc de presse, `P5b` calcul à la demande, `P5c`
   joignabilité) + références (abandons, verdict métrique-par-métrique,
   garde-fous). **C'est le plan que ces sessions exécutent**, une étape (ou
   sous-étape) à la fois ; **laquelle** est dit par `CLAUDE.md` §0, pas ici.
5. `PLAN_UI_COMPOSEUR.md` — la **conception** du composeur de pipelines
   (recettes, réglages, composition contrainte) qu'exécute `P5c` : les trois
   couches, l'arbitrage sur la déclaration des paramètres, et ce que la bascule
   vers un constructeur unique doit préserver.
6. La `DoD vivante` de chaque couche touchée
   (`cinoc/<couche>/{ANALYSE,MIGRATION}_COUCHE_*.md`).

## 2. Règles de session (rappel court)

- **Une tranche par session**, fine et de pleine profondeur ; s'arrêter à la
  fin de la tranche.
- **`make ci` complet avant tout push** — jamais « vert » sur un sous-ensemble
  (`CLAUDE.md §11`).
- **Docs et code dans le même commit** (rituel de réconciliation,
  `MIGRATION_PLAN.md`) : roll-up + DoD des couches touchées + journal si une
  décision est prise ou un écart arbitré.
- **Branche de dev** : celle désignée pour la session. Pas de PR sauf demande
  explicite.

# Archives brutes des campagnes de référence (novembre 2026)

Conservation demandée par le mainteneur (arbitrage 9 de la contre-expertise au commit `04a1c17b`) : préserver les sorties des campagnes pour leur **réévaluation ultérieure**, une fois les contrats d'évaluation revus. **Rien ici n'est publié ni citable** : les chiffres calculés par le code actuel relèvent des défauts établis par la contre-expertise (branche `claude/contre-expertise-04a1c17b`).

| Fichier | Contenu | Code qui l'a produit |
|---|---|---|
| `archives/s30-archive-bnl.tar.zst`, `s30-archive-dresden.tar.zst` | S30 : partie sans clé (Tesseract, règles, qwen2.5vl:3b local) | `main` à la date de S30 (D-304) |
| `archives/s31-arch-bnl.tar.zst`, `s31-arch-dresden.tar.zst` | S31 : partie Mistral, 5 répétitions (`repetition-<k>/`), E4 en 1 répétition, témoin d'E3 ; dépense mesurée 2,49 € | branche `claude/gele-s31-mistral` (`0.1.1.dev274+g32a56aae4`, D-312) |
| `images/bnl/`, `images/dresden/` | une copie de chaque image de page, nommée par son SHA-256 (vérifié : 47/47) ; les archives les nomment `../images/<sha256><suffixe>` | — |

| `archives/s31l-archive-bnl.tar.zst`, `s31l-archive-dresden.tar.zst` | S31L : campagne locale (qwen2.5:3b, qwen2.5vl:3b via Ollama, CPU), état final ; aucun appel facturé | branche `claude/gele-s31l-local` (`ee33f0a` pour la fin, archivage par unité), D-311 |
| `archives/s31l-originaux-archive-*.tar.zst` | S31L : copie des archives **avant** la reprise autorisée du 27/11 (archivage par tranche), conservée telle quelle | branche `claude/gele-s31l-local` (`58fd37f`) |
| `resultats/s31l/` | `RunResult` finaux relus hors ligne (BNL, BNL sous-ensemble saknussemm, Dresden) et `SUMMARY.txt` (re-notation, déterminisme, oracle dinglehopper, contrôle des replis) | idem |
| `sorties/s31l-sorties-brutes.tar.zst` | sorties brutes de chaque tranche (`out/`), journaux (`logs/`), specs de tranche (`work/`) | idem |
| `scripts/s30`, `scripts/s31`, `scripts/s31l` | scripts de génération, d'estimation, de tranchage, de comparaison, d'oracle et de clôture utilisés par les campagnes (hors produit) | — |

**Restaurer une archive** : `zstd -dc archives/<nom>.tar.zst | tar -x`, puis copier `images/<corpus>/*` dans `<archive>/images/` (et dans chaque `repetition-<k>/images/` pour S31). Les fichiers archivés sont identiques aux originaux (comptes vérifiés à la création pour S30/S31 : 889, 159, 17 883, 3 995 fichiers hors images). L'intégrité de chaque fichier de ce dépôt se vérifie par `sha256sum -c SHA256SUMS`.

**Limites connues** (contre-expertise, affirmation 7) : l'archive `ResumeStore` ne vérifie pas les empreintes à la relecture, ne contient ni la spec ni les vérités terrain (leurs SHA-256 sont listés dans `campaigns/2026-11-26-reference/README.md` de la branche `claude/gele-s31-mistral`), et la clé d'unité dépend des octets de l'image du corpus. Des unités d'avant le correctif fan-out (D-311) y subsistent sans être atteintes par aucune clé.

**Licences** : `37-GT-BNL` (BnL) — CC0. Dresden — vérité terrain CC BY-NC-SA 4.0, images Public Domain Mark : toute réutilisation de l'archive Dresden est bornée par CC BY-NC-SA 4.0 (attribution, pas d'usage commercial, partage dans les mêmes conditions). Aucun secret : les archives ont été parcourues (motifs de clés, en-têtes d'autorisation, chemins locaux) avant versement.

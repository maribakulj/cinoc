# Schémas XSD officiels — oracle de test

Copies **octet pour octet** des schémas publiés, utilisées par
`tests/formats/_xsd.py` pour valider ce que Cinoc **écrit** (arbitrage A9,
D-271 : validation des sorties, en test ; l'entrée reste tolérante, rien
n'est validé à l'exécution). Aucun fichier n'est modifié : l'`xsd:import`
distant est redirigé vers la copie locale par un résolveur lxml, et le
parseur refuse le réseau. Les empreintes ci-dessous sont revérifiées au
chargement ; un écart fait échouer les tests.

| Fichier | Source | Récupéré le | SHA-256 | Licence |
|---|---|---|---|---|
| `alto-4-4.xsd` | <https://www.loc.gov/standards/alto/v4/alto-4-4.xsd> (Library of Congress, ALTO Editorial Board ; `Last-Modified` 2023-04-07) | 2026-11-25 | `5564fd29d2dd090d8102b8a0aa081906afd677cd5ecc632312e56f21ea14702b` | CC BY-SA 4.0 (déclarée en tête du fichier) |
| `xlink.xsd` | <http://www.loc.gov/standards/xlink/xlink.xsd> (METS XLink Schema v. 2, Library of Congress ; identique à `https://www.loc.gov/standards/mets/xlink.xsd`) — c'est l'URL qu'importe `alto-4-4.xsd` | 2026-11-25 | `f1f5bb6003165cdd8f6c1fcc32f8fd1f965e1681010f3b9806d9460bcffa8a3c` | aucune mention dans le fichier ; publié par la Library of Congress comme partie du standard METS |

ALTO 4.4 couvre l'espace de noms `ns-v4`, le seul qu'écrit Cinoc. Les schémas
PAGE arrivent avec l'écrivain PAGE (session S3).

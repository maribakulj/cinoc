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
| `pagecontent-2019-07-15.xsd` | <https://www.primaresearch.org/schema/PAGE/gts/pagecontent/2019-07-15/pagecontent.xsd> (PRImA Research Lab, université de Salford ; `Last-Modified` 2026-01-16) — l'URL que désigne l'espace de noms qu'écrit Cinoc, et la copie que l'audit D-264 avait mesurée (même empreinte, redescendue le 2026-11-26). Le dépôt GitHub `PRImA-Research-Lab/PAGE-XML` n'en est **pas** une copie fidèle : la branche `master` porte le schéma 2024-07-15 (autre espace de noms), et le tag `2019-07-15` un état antérieur du même schéma (sans `MapRegion`, `UnderlineStyleSimpleType` nommé autrement, CRLF) — vérifié en comparant les deux, documentation retirée. | 2026-11-26 | `5d7da5af5f5e06d3b9cd1e78b407ffca1862f78ad9823ed89c302fb6409932d5` | Apache 2.0 (licence du dépôt `PRImA-Research-Lab/PAGE-XML`) ; aucune mention dans le fichier |

ALTO 4.4 couvre l'espace de noms `ns-v4`, le seul qu'écrit Cinoc en ALTO.
PAGE 2019-07-15 est le seul espace de noms qu'écrit Cinoc en PAGE : le schéma
2013-07-15 n'est pas vendorisé, puisque rien ne l'écrit plus (D-273 — un PAGE
2013 lu est réécrit en 2019). Le schéma PAGE n'importe rien.

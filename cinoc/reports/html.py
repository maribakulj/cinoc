"""Assemblage HTML **autonome** au design + échappement (couche 7).

Produit un document autonome (**CSS inline**, aucune dépendance CDN/JS), donc
hébergeable tel quel **et déterministe** (cf. plan §Cibles de distribution). Le
style reprend le **design** (gris chaud, chrome pilule, cartes ``sec``, tables
tabulaires) ; les **polices du design** — titres *Mona Sans*, corps *IBM Plex
Sans*, données *IBM Plex Mono*, accents *Fluxisch Else*, logo *OCR-A* — sont
**incorporées en data-URI** (``_style.font_face_css``) pour garder
l'identité typographique **et** l'autonomie (S4.b.1a, option (a) — cf. D-019). Les
**données** sont échappées via ``escape`` ; la **structure** est de l'``Html`` de
confiance.
"""

from __future__ import annotations

import html as _html

from cinoc.reports._style import font_face_css
from cinoc.reports.section import Html

#: CSS du rapport au design (sous-ensemble de ``design/tokens.css``). Les
#: ``@font-face`` (Mona/IBM Plex/Fluxisch/OCR-A, data-URI) sont préfixés au rendu par
#: ``font_face_css()``. Statique → le rapport reste octet-stable.
_CSS = (
    ":root{--paper:#EBE8E0;--surface:#F4F1EA;--raised:#FBFAF6;--g-50:#E4E0D7;"
    "--g-100:#D6D2C8;--g-300:#8D8879;--g-400:#6F6B60;--g-500:#54514A;"
    "--g-700:#26241F;--ink:#1A1917;--fern:oklch(0.50 0.07 145);"
    "--r-md:14px;--r-lg:20px;--r-pill:999px;"
    "--display:'Mona Sans VF','IBM Plex Sans',system-ui,sans-serif;"
    "--sans:'IBM Plex Sans',system-ui,sans-serif;"
    "--mono:'IBM Plex Mono',ui-monospace,monospace;"
    "--accent:'Fluxisch Else',Georgia,serif;"
    "--ocr:'OCRA','IBM Plex Mono',ui-monospace,monospace;}"
    "*{box-sizing:border-box;margin:0;padding:0;}"
    "body.report-board{background-color:var(--paper);"
    "background-image:url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg'"
    " width='3' height='3' viewBox='0 0 3 3'><circle cx='1' cy='1' r='0.6'"
    " fill='%231a1917' fill-opacity='0.28'/></svg>\");"
    "background-attachment:fixed;color:var(--ink);"
    "font-family:var(--sans);font-size:14px;line-height:1.5;padding:22px;"
    "display:flex;flex-direction:column;gap:18px;"
    "-webkit-font-smoothing:antialiased;}"
    ".report-chrome{display:flex;align-items:center;gap:16px;padding:12px 18px;"
    "background:var(--ink);border-radius:var(--r-pill);color:var(--paper);"
    "flex-wrap:wrap;}"
    ".report-chrome .wm-mark{display:inline-flex;align-items:center;"
    "justify-content:center;width:24px;height:24px;border-radius:50%;"
    "background:var(--paper);color:var(--ink);font-weight:700;font-size:12px;}"
    ".report-chrome .wm-name{font-family:var(--ocr);font-weight:400;"
    "font-size:18px;letter-spacing:0.01em;}"
    # Le « o » de Cinoc rendu en **capitale OCR-A** (glyphe octogonal iconique,
    # comme le « O » de l'ancien logo) ; le texte DOM reste « Cinoc ».
    ".report-chrome .wm-o{text-transform:uppercase;}"
    ".report-chrome .wm-sep{width:1px;height:16px;background:rgba(239,237,232,0.2);}"
    ".report-chrome .wm-sub{font-family:var(--mono);font-size:11px;"
    "letter-spacing:0.04em;color:rgba(239,237,232,0.6);}"
    # Méta de run (docs/moteurs/date) + actions d'export, poussées à droite.
    ".chrome-meta{margin-left:auto;display:flex;gap:14px;align-items:center;"
    "font-family:var(--mono);font-size:10.5px;color:rgba(239,237,232,0.55);}"
    ".chrome-meta .v{color:var(--paper);}"
    ".chrome-actions{display:flex;gap:6px;margin-left:2px;}"
    ".chrome-btn{background:rgba(239,237,232,0.10);color:var(--paper);"
    "text-decoration:none;padding:6px 12px;border-radius:var(--r-pill);"
    "font-family:var(--mono);font-size:10.5px;}"
    ".chrome-btn:hover{background:rgba(239,237,232,0.18);}"
    ".report-main{display:flex;flex-direction:column;gap:14px;}"
    # Grille de cartes (CSS Grid, sans JS) sur la **vue maître** (.tab-master) :
    # pistes auto-ajustées ~23rem, hauteur intrinsèque (pas de chevauchement),
    # ordre DOM = ordre de lecture, repli 1 colonne. Larges = grid-column:1/-1.
    # L'onglet (.tab-panel) n'est qu'un conteneur maître/détail ; le détail
    # (.tab-detail) est une pile pleine largeur ; ``[hidden]`` masque une vue.
    ".tab-master{display:grid;gap:14px;align-items:start;"
    "grid-template-columns:repeat(auto-fill,minmax(min(100%,23rem),1fr));}"
    ".tab-master>.view-hero,.tab-master>.r-block.r-wide{grid-column:1/-1;}"
    # min-width:0 : l'item de grille n'élargit pas sa piste (anti-débordement).
    ".tab-master>.r-block{min-width:0;}"
    ".tab-master[hidden],.tab-detail[hidden]{display:none;}"
    # Sous-titre thématique d'un onglet riche : bande pleine largeur, zéro JS.
    ".tab-subhead{grid-column:1/-1;font-family:var(--display);font-weight:800;"
    "font-size:13px;letter-spacing:0.08em;text-transform:uppercase;"
    "color:var(--g-400);margin:10px 2px 0;}"
    # Modes (Rapport/Explorer) : empilés sans JS, ``[hidden]`` masque l'inactif.
    # Spine = sommaire collant horizontal (ancres de groupe) en tête de mode.
    ".mode[hidden]{display:none;}"
    ".spine{position:sticky;top:0;z-index:5;display:flex;flex-wrap:wrap;"
    "gap:3px 5px;padding:8px 2px;margin-bottom:10px;background:var(--paper);"
    "border-bottom:1px solid var(--g-100);}"
    ".spine-link{font-family:var(--sans);font-size:13px;font-weight:500;"
    "color:var(--g-700);text-decoration:none;white-space:nowrap;"
    "padding:4px 10px;border-radius:var(--r-pill);line-height:1.25;}"
    ".spine-link:hover{color:var(--ink);background:var(--g-50);}"
    ".spine-link.on{color:var(--ink);font-weight:700;background:var(--g-50);}"
    ".sec{background:var(--raised);border-radius:var(--r-lg);padding:22px 26px 24px;}"
    ".sec h1{font-family:var(--display);font-size:24px;font-weight:800;"
    "font-optical-sizing:auto;letter-spacing:0;"
    "margin-bottom:6px;}"
    ".sec h2{font-family:var(--display);font-size:18px;font-weight:800;"
    "font-optical-sizing:auto;letter-spacing:0;"
    "color:var(--ink);margin:18px 0 10px;}.sec h2:first-of-type{margin-top:0;}"
    ".sec p.muted{font-size:12.5px;color:var(--g-400);margin-bottom:10px;}"
    "table{width:100%;border-collapse:collapse;font-size:13px;margin:.4rem 0;}"
    "th{text-align:left;font-size:10.5px;letter-spacing:0.06em;"
    "text-transform:uppercase;color:var(--g-400);font-weight:500;"
    "padding:10px 14px;border-bottom:1px solid var(--g-100);}"
    "td{padding:11px 14px;border-bottom:1px solid var(--g-50);color:var(--g-700);}"
    "tr:last-child td{border-bottom:none;}"
    "td.num{text-align:right;font-family:var(--mono);"
    "font-variant-numeric:tabular-nums;color:var(--ink);}"
    # Readouts (portée du corpus) + tables data-bars
    ".readouts{display:grid;grid-template-columns:repeat(auto-fit,minmax(116px,1fr));"
    "gap:10px;margin:14px 0 6px;}"
    ".readout{background:var(--surface);border-radius:var(--r-md);padding:14px 16px;"
    "display:flex;flex-direction:column;gap:6px;}"
    ".readout .r-label{font-size:10px;font-weight:500;letter-spacing:0.06em;"
    "text-transform:uppercase;color:var(--g-400);}"
    ".readout .r-value{font-family:var(--display);font-size:30px;"
    "font-weight:800;font-optical-sizing:auto;letter-spacing:0;"
    "font-variant-numeric:tabular-nums;"
    "line-height:1;color:var(--ink);}"
    # Grille de tables **côte à côte** : une longue liste est découpée en N
    # colonnes pour **utiliser la largeur** au lieu de descendre tout en bas
    # (`--n` posé en inline) ; replie en 1 colonne sur écran étroit.
    ".tcols{display:grid;grid-template-columns:repeat(var(--n,2),1fr);"
    "gap:0 26px;align-items:start;}"
    "@media (max-width:760px){.tcols{grid-template-columns:1fr;}}"
    ".table-scroll{overflow-x:auto;}"
    # Téléphone : un tableau large défile dans sa boîte, jamais la page (D-299).
    "@media (max-width:720px){table.data{display:block;overflow-x:auto;"
    "max-width:100%;}}"
    ".table-scroll table.data{min-width:max-content;}"
    "table.data.compact{width:auto;max-width:540px;}"
    "table.data td.lbl{text-align:left;color:var(--g-700);}"
    "table.data{width:100%;border-collapse:collapse;font-size:13px;margin:.4rem 0 0;}"
    "table.data th{text-align:left;font-size:10.5px;letter-spacing:0.04em;"
    "text-transform:uppercase;color:var(--g-400);font-weight:500;"
    "padding:8px 14px 10px;border-bottom:1px solid var(--g-100);}"
    "table.data th.num-cell{text-align:right;}"
    # Super-en-tête de groupe thématique (calque « Par moteur » du canon).
    "table.data tr.grp-row th{border-bottom:none;padding:8px 14px 0;}"
    "table.data tr.grp-row th.grp-head{font-size:9.5px;letter-spacing:0.05em;"
    "text-transform:uppercase;color:var(--g-300);font-weight:600;"
    "border-bottom:1px solid var(--g-100);}"
    # Tables vivantes : en-tête triable (clic) + définition au survol (E1).
    "table.data th.sortable{cursor:pointer;user-select:none;}"
    "table.data th.sortable:hover{color:var(--ink);}"
    "th .th-sort{font-size:9px;opacity:0.35;margin-left:2px;}"
    'th.sortable[aria-sort="ascending"] .th-sort,'
    'th.sortable[aria-sort="descending"] .th-sort{opacity:1;color:var(--fern);}'
    ".has-def{text-decoration:underline dotted;text-underline-offset:3px;"
    "text-decoration-color:var(--g-300);}"
    "table.data td.eng-cell{vertical-align:middle;padding:10px 14px;"
    "border-bottom:1px solid var(--g-50);color:var(--g-700);}"
    "table.data tr:last-child td{border-bottom:none;}"
    "table.data td.databar{position:relative;padding:0;font-family:var(--mono);"
    "font-variant-numeric:tabular-nums;font-size:12px;color:var(--ink);"
    "border-bottom:1px solid var(--g-50);vertical-align:middle;"
    # Teinte de cellule (canon) : fond sauge ∝ position sur l'axe de la colonne
    # (``--t`` ∈ [0,1], posé par ``bar_cell``). Valeurs proches → teintes proches,
    # contrairement à l'ancienne barre normalisée qui saturait la cellule.
    "background:rgba(120,134,107,calc(var(--t,0) * 0.26));}"
    # Barre fine de base : encore utilisée par image_quality / word_errors (où la
    # LONGUEUR = score/compte a un sens) — la table de métriques, elle, est teintée.
    "table.data td.databar .db-fill{position:absolute;left:14px;bottom:5px;height:3px;"
    "border-radius:2px;background:var(--fern);opacity:0.55;z-index:0;}"
    "table.data td.databar .db-num{position:relative;z-index:1;display:block;"
    "text-align:right;padding:12px 14px;}"
    "table.data td.disp{padding:11px 14px;text-align:right;font-family:var(--mono);"
    "font-size:11px;color:var(--g-500);border-bottom:1px solid var(--g-50);}"
    "table.data td.verdict{padding:11px 14px;font-family:var(--sans);font-size:11.5px;"
    "color:var(--g-400);border-bottom:1px solid var(--g-50);}"
    "table.data td.verdict.sig{color:var(--fern);font-weight:600;}"
    # Badge de significativité sur le verdict (synthèse) : le classement n'est
    # jamais lu sans sa qualification statistique. yes=écart confirmé (fern),
    # no=non séparable (gris), tie=égalité statistique (avertissement chaud).
    ".sig-badge{display:inline-flex;align-items:center;font-family:var(--mono);"
    "font-size:10.5px;padding:3px 9px;border-radius:var(--r-pill);"
    "letter-spacing:0.02em;white-space:nowrap;}"
    ".sig-yes{background:var(--fern);color:var(--paper);}"
    ".sig-no{background:var(--g-50);color:var(--g-400);}"
    ".sig-tie{background:rgba(214,176,90,0.32);color:var(--g-700);}"
    # Profil moteur (drill-in) : panneaux cachés, révélés au clic (report.js) ou
    # via :target (sans JS). Bande KPI + graphe CER/document.
    # Nom du moteur = lien vers son profil (couleur conservée, souligné au survol).
    ".eng-cell a{color:inherit;text-decoration:none;cursor:pointer;}"
    ".eng-cell a:hover{text-decoration:underline;text-decoration-color:var(--fern);}"
    ".drill-panel[hidden]{display:none;}"
    ".drill-panel:target{display:block;}"
    ".doc-card{text-decoration:none;color:inherit;cursor:pointer;}"
    ".doc-card:hover{outline:2px solid var(--fern);outline-offset:2px;}"
    # Détail document (drill-in) : CER par moteur + diff des pires lignes.
    # CER par moteur : grille compacte (badge · nom · valeur) — la valeur suit le
    # nom dans sa colonne (alignée ET proche), au lieu d'être projetée au bord.
    ".dd-cers{display:inline-grid;grid-template-columns:auto auto auto;"
    "gap:5px 10px;align-items:center;margin-bottom:14px;}"
    ".dd-row{display:contents;}"
    ".dd-name{font-family:var(--mono);font-size:12px;color:var(--g-700);}"
    ".dd-cer{font-variant-numeric:tabular-nums;font-family:var(--mono);"
    "font-size:12px;color:var(--g-700);text-align:right;}"
    ".dd-row.best .dd-cer{color:var(--fern);font-weight:600;}"
    ".dd-diffs{display:flex;flex-direction:column;gap:12px;}"
    ".dd-diff{background:var(--surface);border-radius:var(--r-md);padding:10px 12px;}"
    ".dd-diff-head{font-size:11px;color:var(--g-500);margin-bottom:6px;"
    "display:flex;align-items:center;gap:6px;}"
    # Détail document : fac-similé medium EN HAUT, zoomable/pan (molette + glisser).
    # Bandeau étroit **centré** au-dessus du diff (qui prend toute la largeur en
    # dessous) — image modeste, le texte respire.
    ".dd-fac-top{max-width:760px;margin:0 auto 14px;}"
    ".dd-fac-full{font-family:var(--sans);font-size:12px;font-weight:500;"
    "margin-left:10px;color:var(--g-500);text-decoration:none;white-space:nowrap;}"
    ".dd-fac-full:hover{color:var(--ink);text-decoration:underline;}"
    # Cartes secondaires du drill-in (CER, heatmap ligne, qualité image…) en
    # grille : chacune à sa hauteur intrinsèque, pistes auto-ajustées de ~21rem,
    # ``align-items:start`` (pas d'étirement ni de chevauchement, ≠ l'ancien
    # masonry ``columns``). Repli 1 colonne en deçà de 21rem.
    ".dd-flow{display:grid;gap:12px;margin-top:14px;align-items:start;"
    "grid-template-columns:repeat(auto-fill,minmax(min(100%,21rem),1fr));}"
    ".dd-card{border:1px solid var(--g-50);"
    "border-radius:var(--r-md);padding:13px 15px;background:var(--surface);}"
    ".dd-card.dd-wide{grid-column:1/-1;}"
    ".dd-fac-zoom{position:relative;overflow:auto;height:clamp(360px,62vh,640px);"
    "display:flex;align-items:center;justify-content:center;"
    "background:var(--surface);border-radius:var(--r-md);"
    "border:1px solid var(--g-50);cursor:zoom-in;}"
    ".dd-fac-img{max-width:100%;max-height:100%;display:block;flex:none;"
    "user-select:none;}"
    ".dd-zoom-ctl{position:absolute;top:8px;right:8px;display:flex;gap:4px;}"
    ".dd-zoom-ctl button{width:26px;height:26px;border:none;border-radius:6px;"
    "background:rgba(26,25,23,0.72);color:var(--paper);cursor:pointer;font-size:14px;"
    "line-height:1;display:flex;align-items:center;justify-content:center;}"
    # Diff côte à côte : 2 colonnes égales, chacune une carte bordée (en-tête +
    # corps serif scrollable, sauts de ligne respectés).
    ".dd-sbs{display:grid;grid-template-columns:1fr 1fr;gap:12px;align-items:start;}"
    ".dd-sbs-col{min-width:0;border:1px solid var(--g-50);border-radius:var(--r-md);"
    "background:var(--raised);overflow:hidden;}"
    ".dd-sbs-col .dd-diff-head{margin:0;padding:7px 12px;background:var(--surface);"
    "border-bottom:1px solid var(--g-50);}"
    "@media (max-width:720px){.dd-sbs{grid-template-columns:1fr;}}"
    # Qualité d'image du document : mini-barres mesurées (recentrées sur le doc).
    ".dd-iq{margin-bottom:14px;}"
    ".dd-iq-bars{display:flex;flex-direction:column;gap:5px;}"
    ".dd-iq-row{display:flex;align-items:center;gap:8px;font-size:12px;"
    "color:var(--g-700);}"
    ".dd-iq-lbl{flex:0 0 150px;}"
    # Primitive partagée : piste de proportion horizontale [0,1]. La coque est
    # commune (qualité d'image, percentiles, strates) ; l'appelant pose la largeur
    # du fill (`width:X%`) + sa couleur (classe `lh-*` ou style inline).
    ".track{flex:1;height:8px;background:var(--surface);border-radius:var(--r-pill);"
    "overflow:hidden;}"
    ".track>i{display:block;height:100%;border-radius:inherit;}"
    ".dd-iq-val{flex:0 0 40px;text-align:right;font-variant-numeric:tabular-nums;}"
    ".dd-iq-meta{font-size:11px;margin-top:6px;}"
    # CER ligne par ligne du document : un mini histogramme par moteur (hauteur
    # ∝ CER), repères début→fin. Une barre = une ligne GT.
    ".dd-lh{margin-bottom:14px;}"
    ".dd-lh-rows{display:flex;flex-direction:column;gap:12px;}"
    ".dd-lh-row{display:flex;align-items:flex-start;gap:8px;font-family:var(--mono);"
    "font-size:12px;color:var(--g-700);}"
    ".dd-lh-plot{flex:1;min-width:0;}"
    ".dd-lh-bars{display:flex;align-items:flex-end;justify-content:center;"
    "gap:2px;height:40px;padding-bottom:2px;}"
    ".dd-lh-bar{flex:1 1 0;min-width:2px;max-width:48px;border-radius:2px 2px 0 0;}"
    ".dd-lh-axis{display:flex;justify-content:space-between;font-size:10px;"
    "color:var(--g-400);margin-top:3px;}"
    ".lh-g{background:var(--fern);}.lh-m{background:#c9a227;}"
    ".lh-o{background:#c2702f;}.lh-b{background:#a23b3b;}"
    # Distribution par ligne : par moteur, badges + (carte thermique | percentiles).
    ".dd-ld-rows{display:flex;flex-direction:column;gap:12px;}"
    ".dd-ld-row{padding:10px 0;border-top:1px solid var(--g-50);}"
    ".dd-ld-head{display:flex;align-items:center;flex-wrap:wrap;gap:6px;"
    "font-family:var(--mono);font-size:12px;color:var(--g-700);margin-bottom:8px;}"
    ".dd-ld-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;}"
    "@media (max-width:720px){.dd-ld-grid{grid-template-columns:1fr;}}"
    ".dd-ld-sub{font-size:10px;text-transform:uppercase;letter-spacing:0.04em;"
    "color:var(--g-400);margin-bottom:5px;}"
    ".dd-pct-row{display:flex;align-items:center;gap:8px;font-family:var(--mono);"
    "font-size:11px;color:var(--g-700);margin-bottom:4px;}"
    ".dd-pct-lbl{flex:0 0 30px;}"
    ".dd-pct-val{flex:0 0 52px;text-align:right;font-variant-numeric:tabular-nums;}"
    # Analyse des hallucinations du document : par moteur, indicateurs + blocs.
    ".dd-hl{margin-bottom:14px;}"
    ".dd-hl-row{padding:10px 0;border-top:1px solid var(--g-50);}"
    ".dd-hl-head{display:flex;align-items:center;gap:8px;font-family:var(--mono);"
    "font-size:12px;color:var(--g-700);margin-bottom:6px;}"
    ".dd-hl-flag{color:var(--clay,#a23b3b);font-weight:600;font-size:11px;}"
    # Primitive partagée : pastille (chip) + leur rangée (chips). Petite étiquette
    # mono sur fond surface ; utilisée pour indicateurs et effectifs.
    ".chips{display:flex;flex-wrap:wrap;gap:6px;}"
    ".chip{font-family:var(--mono);font-size:11px;padding:3px 8px;"
    "background:var(--surface);border-radius:var(--r-pill);color:var(--g-700);}"
    ".dd-hl-blocks{margin-top:8px;font-size:12px;}"
    ".dd-hl-block{padding:7px 10px;margin-top:5px;border-radius:var(--r-md);"
    "background:rgba(229,154,138,0.18);line-height:1.6;word-break:break-word;}"
    # Diff pleine page : sélecteur de moteur (segmenté) + blocs diff (un visible).
    ".dd-fullwrap{margin-top:6px;}"
    ".dd-engine-tabs{display:inline-flex;gap:2px;padding:3px;margin-bottom:10px;"
    "background:var(--surface);border-radius:var(--r-pill);flex-wrap:wrap;}"
    ".dd-eng-btn{display:inline-flex;align-items:center;gap:6px;border:none;"
    "cursor:pointer;background:transparent;color:var(--g-500);font-family:var(--mono);"
    "font-size:11px;padding:5px 12px;border-radius:var(--r-pill);}"
    ".dd-eng-btn .eng-badge{margin-right:0;}"
    ".dd-eng-btn.on{background:var(--ink);color:var(--paper);}"
    ".dd-fulldiff[hidden]{display:none;}"
    ".dd-fulldiff .diff{max-height:360px;overflow-y:auto;padding:11px 13px;"
    "white-space:pre-wrap;word-break:break-word;"
    "font-family:Georgia,'Times New Roman',serif;font-size:13px;line-height:1.85;}"
    ".drill-head{display:flex;justify-content:space-between;align-items:center;"
    "gap:12px;flex-wrap:wrap;margin-bottom:10px;}"
    ".drill-back{font-family:var(--mono);font-size:12px;text-decoration:none;"
    "color:var(--g-500);}.drill-back:hover{color:var(--ink);}"
    ".drill-nav{display:flex;gap:6px;}"
    ".drill-nav .btn-sm{font-family:var(--mono);font-size:11px;text-decoration:none;"
    "color:var(--g-500);background:var(--surface);border-radius:var(--r-pill);"
    "padding:5px 12px;}.drill-nav .btn-sm:hover{color:var(--ink);}"
    ".drill-title{display:flex;align-items:center;gap:10px;"
    "font-family:var(--display);font-weight:800;font-optical-sizing:auto;"
    "font-size:22px;color:var(--ink);margin-bottom:14px;}"
    ".drill-pos{font-family:var(--mono);font-size:11px;font-weight:400;}"
    ".kpi-band{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));"
    "gap:10px;margin-bottom:16px;}"
    ".kpi{background:var(--surface);border-radius:var(--r-md);padding:12px 14px;}"
    ".kpi-k{font-family:var(--mono);font-size:10px;letter-spacing:0.06em;"
    "text-transform:uppercase;color:var(--g-400);}"
    ".kpi-v{font-family:var(--display);font-weight:800;font-optical-sizing:auto;"
    "font-size:24px;font-variant-numeric:tabular-nums;color:var(--ink);}"
    ".drill-caption{font-size:12px;color:var(--g-500);margin-bottom:6px;}"
    ".bars-svg{width:100%;height:120px;display:block;background:var(--surface);"
    "border-radius:var(--r-md);}"
    ".prof-row{display:flex;gap:22px;flex-wrap:wrap;margin-top:16px;}"
    ".prof-cell{flex:1;min-width:240px;}"
    # Bascule galerie ⇄ liste (vue Documents) : pilule à 2 boutons, sur la charte.
    ".view-toggle,.doc-filter{display:inline-flex;flex-wrap:wrap;gap:2px;padding:3px;"
    "background:var(--surface);border-radius:var(--r-pill);margin-bottom:8px;}"
    ".vt-btn,.df-btn{font-family:var(--mono);font-size:11px;border:none;cursor:pointer;"
    "background:transparent;color:var(--g-500);padding:6px 14px;"
    "border-radius:var(--r-pill);}"
    ".vt-btn:hover,.df-btn:hover{color:var(--ink);}"
    ".vt-btn.on,.df-btn.on{background:var(--ink);color:var(--paper);}"
    ".doc-view[hidden],.doc-card[hidden]{display:none;}"
    # Cellule de diff GT↔hypothèse (drill-in) : texte surligné, retour à la ligne.
    "table.data td.diff{padding:11px 14px;font-family:var(--mono);font-size:12px;"
    "color:var(--g-700);border-bottom:1px solid var(--g-50);white-space:pre-wrap;"
    "word-break:break-word;vertical-align:top;}"
    "del.d-del{background:rgba(229,154,138,0.30);text-decoration:none;"
    "color:var(--ink);}"
    "ins.d-ins{background:rgba(159,195,160,0.38);text-decoration:none;"
    "color:var(--ink);}"
    # Galerie de documents : grille de cartes au design (monochrome, charte rapport).
    ".doc-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(196px,1fr));"
    "gap:14px;margin:14px 0 4px;}"
    ".doc-card{background:var(--surface);border-radius:var(--r-md);padding:12px;"
    "display:flex;flex-direction:column;gap:10px;}"
    # Aperçu de page synthétique : lignes monochromes sur papier (≠ vignette colorée).
    ".doc-preview{height:78px;border-radius:10px;border:1px solid var(--g-50);"
    "background-color:var(--paper);background-image:repeating-linear-gradient("
    "180deg,transparent 0 6px,rgba(26,25,23,0.10) 6px 7px);}"
    # Vignette réelle : couvre la zone d'aperçu (objet centré, recadré).
    ".doc-preview-img{background:var(--g-50);overflow:hidden;padding:0;}"
    ".doc-preview-img img{width:100%;height:100%;object-fit:cover;display:block;}"
    ".doc-card .dc-id{font-family:var(--mono);font-size:12px;font-weight:600;"
    "color:var(--ink);word-break:break-all;}"
    ".dc-anom{margin-left:5px;color:var(--clay,#a23b3b);font-weight:400;}"
    ".anom-legend{font-size:11px;margin:6px 0 2px;}"
    ".dc-rows{display:flex;flex-direction:column;gap:4px;}"
    ".dc-row{display:flex;align-items:center;gap:6px;font-family:var(--mono);"
    "font-size:11px;color:var(--g-500);}"
    ".dc-row .eng-badge{margin-right:0;}"
    ".dc-row .dc-name{flex:1;overflow:hidden;text-overflow:ellipsis;"
    "white-space:nowrap;}"
    ".dc-row .dc-cer{font-variant-numeric:tabular-nums;color:var(--g-700);}"
    ".dc-row.best .dc-cer{color:var(--fern);font-weight:600;}"
    ".muted{color:var(--g-400);}"
    "::selection{background:var(--ink);color:var(--paper);}"
    # Composition du corpus par strate : nom + effectif, barre proportionnelle, part.
    ".strata-grid{display:flex;flex-direction:column;gap:14px;margin:14px 0 4px;}"
    ".strata-row{display:grid;grid-template-columns:1fr 2fr auto;gap:14px;"
    "align-items:center;}"
    ".strata-head{display:flex;align-items:center;gap:8px;}"
    ".strata-name{font-family:var(--display);font-weight:800;"
    "font-optical-sizing:auto;font-size:15px;color:var(--ink);}"
    ".strata-pct{font-family:var(--display);font-weight:800;"
    "font-optical-sizing:auto;font-size:22px;font-variant-numeric:tabular-nums;"
    "color:var(--ink);}"
    # Grille de dispersion CER (SVG serveur, échelle commune) : badge+nom, box
    # plot, labels min·méd·µ·max. Couleurs d'accent inline (palette engine_badges).
    ".disp-grid{display:flex;flex-direction:column;gap:14px;margin:14px 0 4px;}"
    ".disp-row{display:grid;grid-template-columns:170px 1fr;gap:6px 14px;"
    "align-items:center;}"
    ".disp-head{display:flex;align-items:center;gap:8px;}"
    ".disp-name{font-family:var(--mono);font-size:12px;color:var(--ink);"
    "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;}"
    ".disp-labels{grid-column:2;font-size:11px;color:var(--g-500);"
    "font-variant-numeric:tabular-nums;}"
    # Boîte à moustaches (SVG serveur) : moustaches min→max + capuchons, boîte
    # interquartile teintée, trait médian (couleur moteur), tick moyenne (encre).
    ".box-plot{width:100%;height:22px;display:block;}"
    ".box-whisker,.box-cap{stroke:var(--g-300);stroke-width:1.5;}"
    ".box-box{fill-opacity:0.32;stroke-width:1.5;}"
    ".box-med{stroke-width:2;}"
    ".box-mean{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 2;}"
    # Courbe de calibration (SVG serveur) : diagonale pointillée = parfaite,
    # polyligne + disques = le moteur. Plot carré à gauche, table à droite.
    ".calib-block{display:flex;gap:22px;align-items:flex-start;flex-wrap:wrap;"
    "margin:.4rem 0 1rem;}"
    ".calib-plot{display:flex;flex-direction:column;gap:4px;flex:0 0 auto;}"
    ".calib-svg{width:180px;height:180px;display:block;background:var(--surface);"
    "border-radius:var(--r-md);}"
    ".calib-axis{font-size:10px;color:var(--g-400);text-align:center;}"
    ".calib-block table.data{flex:1;min-width:240px;}"
    ".calib-diag{stroke:var(--g-300);stroke-width:1;stroke-dasharray:3 3;}"
    ".calib-line{fill:none;stroke-width:2;stroke-linejoin:round;}"
    # Composition d'erreurs (taxonomy) : barre empilée SVG + légende par classe.
    ".comp{display:flex;flex-direction:column;gap:10px;margin:.3rem 0 1rem;}"
    ".comp-bar{width:100%;height:14px;display:block;border-radius:6px;"
    "overflow:hidden;}"
    ".comp-legend{display:flex;flex-direction:column;gap:4px;}"
    # swatch · label · part · compte **groupés à gauche** (spacer 1fr en fin) :
    # sinon le label en 1fr poussait la valeur au bord droit (illisible en large).
    ".comp-row{display:grid;grid-template-columns:14px 132px auto auto 1fr;gap:10px;"
    "align-items:center;font-size:12px;}"
    ".comp-sw{width:12px;height:12px;border-radius:3px;}"
    ".comp-label{color:var(--g-700);}"
    ".comp-share{color:var(--ink);font-variant-numeric:tabular-nums;}"
    ".comp-count{color:var(--g-400);font-variant-numeric:tabular-nums;}"
    # Marque d'une métrique adaptée (≈) ou exploratoire (∗) en en-tête (D-289).
    ".cat-mark{font-size:9px;margin-left:2px;color:var(--g-400);}"
    # Camembert (anneau SVG serveur) : parts teintées + trou central couleur fond
    # (découpe). Légende = pastille + libellé + compte. Centré dans sa carte.
    ".donut-svg{width:140px;height:140px;display:block;margin:6px auto 4px;}"
    ".donut-seg{stroke:var(--surface);stroke-width:1;}"
    ".donut-hole{fill:var(--surface);}"
    ".donut-legend{text-align:center;}"
    ".donut-key{display:inline-block;width:9px;height:9px;border-radius:2px;"
    "vertical-align:middle;margin-right:2px;}"
    # Graphe haltère (SVG serveur) : une ligne par document, points = CER par
    # moteur reliés (min→max). Échelle uniforme, libellé doc à gauche.
    ".dumb-wrap{max-width:380px;margin:8px auto 4px;}"
    ".dumb-svg{width:100%;height:auto;display:block;}"
    ".dumb-link{stroke:var(--g-300);stroke-width:2;}"
    ".dumb-dot{stroke-width:1;fill-opacity:0.9;}"
    ".dumb-label{font-family:var(--mono);font-size:9px;fill:var(--g-400);}"
    ".dumb-legend{text-align:center;}"
    # Dot plot classé (SVG serveur) : par moteur, moustache d'IC 95 % + point à la
    # moyenne, axe commun. Montre l'écart ET son incertitude, sans verdict.
    ".dot-svg{width:100%;max-width:340px;height:auto;display:block;margin:6px 0;}"
    ".dot-axis{stroke:var(--g-100);stroke-width:1;}"
    ".dot-ci{stroke-width:2.5;stroke-linecap:round;opacity:0.55;}"
    ".dot-pt{stroke:var(--paper);stroke-width:1;}"
    ".dot-lbl{font-family:var(--mono);font-size:10px;fill:var(--g-500);}"
    # Carte des mots (heatmap SVG) : mots verbatim en lignes, moteurs en colonnes,
    # cases teintées par compte. Compagnon visuel de la table (aria-hidden).
    # Diagramme de Venn du recouvrement (2-3 moteurs) : cercles teintés par
    # moteur (faible opacité), compte par région inscrit.
    ".venn-svg{max-width:340px;height:auto;display:block;margin:.4rem auto .2rem;}"
    ".venn-circle{fill-opacity:0.13;stroke-width:1.5;}"
    ".venn-count{font-family:var(--mono);font-size:15px;fill:var(--ink);"
    "font-variant-numeric:tabular-nums;}"
    ".venn-label{font-family:var(--mono);font-size:11px;fill:var(--g-500);}"
    ".wmap-svg{max-width:100%;height:auto;display:block;background:var(--surface);"
    "border-radius:var(--r-md);margin:.4rem auto 0;}"
    ".wmap-word{font-family:var(--mono);font-size:11px;fill:var(--ink);}"
    ".wmap-head{font-family:var(--mono);font-size:10px;fill:var(--g-400);"
    "letter-spacing:0.04em;}"
    ".wmap-count{font-family:var(--mono);font-size:10px;"
    "font-variant-numeric:tabular-nums;}"
    ".wmap-cell{stroke:var(--surface);stroke-width:1;}"
    # Flux de confusion de caractères (#8) : glyphe attendu → produit, prominents
    # (« voir les symboles » ; le slot bordé rend une espace visible) + barre de
    # fréquence. Direction lisible (ſ→f ≠ f→ſ).
    ".cf-engine{margin:.4rem 0 1rem;}"
    ".cf-eng-name{font-family:var(--mono);font-size:12px;color:var(--g-500);}"
    ".cf-grid{display:flex;flex-wrap:wrap;gap:8px;margin-top:8px;}"
    ".cf-pair{display:flex;align-items:center;gap:7px;background:var(--surface);"
    "border-radius:var(--r-md);padding:7px 11px;}"
    ".cf-glyph{font-family:var(--mono);font-size:17px;line-height:1;min-width:1.3em;"
    "text-align:center;background:var(--raised);border:1px solid var(--g-50);"
    "border-radius:6px;padding:3px 5px;color:var(--ink);}"
    ".cf-arrow{color:var(--g-400);font-size:12px;}"
    ".cf-bar{height:6px;border-radius:var(--r-pill);background:var(--fern);"
    "opacity:0.55;min-width:2px;}"
    ".cf-count{font-family:var(--mono);font-size:11px;color:var(--g-500);"
    "font-variant-numeric:tabular-nums;}"
    # Flux mot→forme(s) (#16 sur-normalisation, #17 modernisation) : le mot source
    # (prominent) → la/les forme(s) produite(s) ; chip(s) ± barre (taille = compte).
    # Flux de modernisation en **colonnes journal** (≥ ~23em) au lieu d'une seule
    # colonne qui descend tout en bas ; chaque ligne reste insécable.
    ".wflow{columns:23em;column-gap:26px;margin:.4rem 0 1rem;}"
    ".wf-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap;"
    "break-inside:avoid;margin-bottom:7px;}"
    ".wf-word{font-family:var(--mono);font-size:13px;background:var(--surface);"
    "border:1px solid var(--g-50);border-radius:6px;padding:3px 8px;color:var(--ink);}"
    ".wf-src{background:var(--raised);font-weight:600;}"
    ".wf-arrow{color:var(--g-400);font-size:12px;}"
    ".wf-dst{display:inline-flex;align-items:center;gap:5px;}"
    ".wf-bar{height:5px;border-radius:var(--r-pill);background:var(--fern);"
    "opacity:0.5;min-width:2px;}"
    ".wf-count{font-family:var(--mono);font-size:10.5px;color:var(--g-500);"
    "font-variant-numeric:tabular-nums;}"
    ".wf-meta{font-family:var(--mono);font-size:10.5px;color:var(--g-400);}"
    # Glossaire pédagogique : disclosure natif (<details>), monochrome, charte.
    ".glossary{display:flex;flex-direction:column;gap:8px;margin:12px 0 4px;}"
    ".gl-item{background:var(--surface);border-radius:var(--r-md);"
    "padding:4px 16px;}"
    ".gl-term{font-family:var(--display);font-weight:800;font-size:14px;"
    "font-optical-sizing:auto;color:var(--ink);cursor:pointer;"
    "padding:10px 0;list-style:none;}"
    ".gl-term::-webkit-details-marker{display:none;}"
    ".gl-term::before{content:'+';display:inline-block;width:16px;"
    "font-family:var(--mono);color:var(--g-400);}"
    ".gl-item[open] .gl-term::before{content:'\\2212';}"
    ".gl-body{margin:0 0 12px 16px;display:grid;grid-template-columns:auto 1fr;"
    "gap:4px 14px;}"
    ".gl-k{font-size:10px;font-weight:500;letter-spacing:0.05em;"
    "text-transform:uppercase;color:var(--g-400);padding-top:2px;"
    "white-space:nowrap;}"
    ".gl-v{font-size:12.5px;color:var(--g-700);line-height:1.45;}"
    # Dialog du glossaire (périphérie, ouvert depuis le chrome). Modale native
    # avec JS (showModal + ::backdrop) ; repli ``:target`` (panneau centré) sans JS.
    ".glossary-dialog{border:none;border-radius:var(--r-lg);padding:22px 24px;"
    "max-width:680px;width:90vw;max-height:82vh;overflow:auto;"
    "background:var(--raised);color:var(--ink);"
    "box-shadow:0 16px 48px rgba(0,0,0,0.3);}"
    ".glossary-dialog::backdrop{background:rgba(26,25,23,0.45);}"
    ".glossary-dialog:target{display:block;position:fixed;top:9vh;left:50%;"
    "transform:translateX(-50%);z-index:60;}"
    ".gd-head{display:flex;align-items:center;justify-content:space-between;"
    "margin-bottom:4px;}"
    ".gd-head h2{margin:0;}"
    ".gd-close{font-family:var(--mono);font-size:14px;text-decoration:none;"
    "color:var(--g-400);padding:2px 8px;border-radius:var(--r-md);}"
    ".gd-close:hover{color:var(--ink);background:var(--g-50);}"
    # Onglets du rapport (IA 4 vues) — **intégrés au chrome** (fond sombre) :
    # bande translucide, onglet actif en pilule claire (cf. design/tokens.css).
    # Enrichissement progressif : sans JS, panneaux empilés et visibles, les
    # onglets sont de simples ancres (#panel-<t>) ; report.js bascule l'affichage.
    ".report-tabs{display:inline-flex;flex-wrap:wrap;gap:2px;padding:3px;"
    "background:rgba(239,237,232,0.08);border-radius:var(--r-pill);}"
    ".report-tab{font-family:var(--sans);font-weight:500;font-size:12px;"
    "text-decoration:none;color:rgba(239,237,232,0.78);padding:6px 14px;"
    "border-radius:var(--r-pill);white-space:nowrap;}"
    ".report-tab:hover{color:var(--paper);}"
    ".report-tab.on{background:var(--paper);color:var(--ink);}"
    ".tab-panel[hidden]{display:none;}"
    ".tab-panel:focus{outline:none;}"
    ".r-block{scroll-margin-top:18px;}"
    # Héros de vue (bande d'en-tête par onglet) — carte ``--raised`` : eyebrow
    # « VUE 0n · NOM » + titre display + desc + readouts de portée à droite.
    ".view-hero{background:var(--raised);border-radius:var(--r-lg);"
    "padding:22px 26px 20px;display:flex;align-items:flex-end;"
    "justify-content:space-between;gap:24px;flex-wrap:wrap;}"
    ".view-hero-eyebrow{font-family:var(--mono);font-size:10.5px;color:var(--g-400);"
    "letter-spacing:0.06em;text-transform:uppercase;}"
    ".view-hero-name{font-family:var(--display);font-weight:800;"
    "font-optical-sizing:auto;font-size:30px;letter-spacing:-0.02em;"
    "line-height:1.05;margin-top:4px;color:var(--ink);}"
    ".view-hero-desc{font-family:var(--accent);font-style:italic;font-size:14px;"
    "color:var(--g-500);max-width:60ch;margin-top:6px;}"
    ".view-hero-stats{display:flex;gap:24px;}"
    ".hero-stat{display:flex;flex-direction:column;gap:2px;text-align:right;}"
    ".hero-stat .v{font-family:var(--display);font-weight:800;"
    "font-optical-sizing:auto;font-size:26px;letter-spacing:-0.02em;"
    "font-variant-numeric:tabular-nums;color:var(--ink);line-height:1;}"
    ".hero-stat .k{font-family:var(--mono);font-size:10px;color:var(--g-400);"
    "letter-spacing:0.06em;text-transform:uppercase;}"
    # Badge moteur (lettre + accent cyclique) — identité stable entre sections.
    # Marqueur moteur = **pastille de couleur** (l'accent relie le moteur à ses
    # courbes/barres). La lettre est masquée (redondante avec le nom adjacent),
    # gardée dans le DOM pour les lecteurs d'écran / le repli sans couleur.
    ".eng-badge{display:inline-flex;align-items:center;justify-content:center;"
    "width:9px;height:9px;border-radius:50%;background:var(--badge,var(--ink));"
    "color:transparent;font-size:0;flex:0 0 auto;"
    "margin-right:8px;vertical-align:middle;}"
    # Widget « comparer un run » (client-side) — bouton + bandeau sticky des deltas.
    ".compare-bar{display:flex;justify-content:flex-end;margin-top:2px;}"
    ".compare-btn{font-family:var(--mono);font-size:12px;background:var(--ink);"
    "color:var(--paper);border:none;border-radius:var(--r-pill);"
    "padding:8px 16px;cursor:pointer;}"
    ".compare-banner{position:fixed;left:22px;right:22px;bottom:14px;"
    "background:var(--ink);color:var(--paper);border-radius:var(--r-md);"
    "padding:12px 16px;display:flex;flex-wrap:wrap;gap:8px 18px;align-items:center;"
    "font-family:var(--mono);font-size:12px;box-shadow:0 6px 24px rgba(0,0,0,0.25);"
    "z-index:50;}"
    ".compare-banner.empty{justify-content:center;color:var(--g-100);}"
    ".compare-banner .cb-title{font-weight:600;letter-spacing:0.02em;}"
    ".compare-banner .cb-row{display:inline-flex;gap:6px;align-items:baseline;}"
    ".compare-banner .cb-row .cb-delta{font-variant-numeric:tabular-nums;}"
    ".compare-banner .cb-row.worse .cb-delta{color:#E59A8A;}"
    ".compare-banner .cb-row.better .cb-delta{color:#9FC3A0;}"
    # Palette daltonien (``?palette=cb`` via report.js → classe sur <html>) : le
    # vert/rouge confusables → paire bleu/orange distinguable. Les badges moteur
    # portent une lettre → restent identifiables sans couleur.
    ".palette-cb{--fern:oklch(0.55 0.13 250);}"
    ".palette-cb .compare-banner .cb-row.worse .cb-delta{color:#E0A23C;}"
    ".palette-cb .compare-banner .cb-row.better .cb-delta{color:#7FB0D9;}"
    ".palette-cb del.d-del{background:rgba(224,162,60,0.32);}"
    ".palette-cb ins.d-ins{background:rgba(127,176,217,0.38);}"
)


def escape(text: str) -> str:
    """Échappe une donnée pour insertion sûre dans le HTML."""
    return _html.escape(text, quote=True)


def localized(lang: str, fr: str, en: str) -> str:
    """Choisit la chaîne selon la langue du rapport (``en`` si ``"en"``, sinon ``fr``).

    Mécanisme i18n **minimal** : les sections gardent leurs deux formulations
    **adjacentes** au point d'usage (revue/maintenance faciles), sélectionnées via
    ``SectionContext.lang`` — **pas de catalogue ni de registre** de chaînes. Repli
    sur le français pour toute langue non gérée (déterminisme : même langue →
    mêmes octets)."""
    return en if lang == "en" else fr


#: Libellés humains des vues d'évaluation : nom interne → (FR, EN). **Source
#: unique** consommée par toutes les sections (fin du « vue : text » brut dans les
#: titres). Une vue absente d'ici porte déjà un nom lisible (ex. « référence OCR
#: (pas une vérité-terrain manuelle) ») → affichée telle quelle.
_VIEW_LABELS: dict[str, tuple[str, str]] = {
    # Ni « brut » ni « plain » : la vue texte est normalisée (profil par
    # défaut, D-285) — son profil est écrit à côté du chiffre.
    "texte": ("Texte", "Text"),
    "texte (lignes)": ("Texte (lignes)", "Text (lines)"),
    "text": ("Texte", "Text"),
    "structure": ("Structure (mise en page)", "Layout structure"),
    "entites": ("Entités nommées", "Named entities"),
    "diplomatic": ("Transcription diplomatique", "Diplomatic transcription"),
}


def view_label(view: str, lang: str) -> str:
    """Libellé humain d'une vue d'évaluation (repli sur le nom brut si inconnu).

    Centralise la traduction du **nom interne** de vue (``"texte"``) vers un
    libellé lisible (« Texte » / « Text »). Déterministe (même vue + langue → mêmes
    octets) ; n'échappe pas (l'appelant échappe au point d'insertion HTML)."""
    pair = _VIEW_LABELS.get(view)
    if pair is None:
        return view
    return pair[1] if lang == "en" else pair[0]


def view_prefix(view: str, lang: str, *, multi: bool) -> str:
    """Préfixe de titre de bloc « <Libellé de vue> — », **seulement** si le run
    porte plusieurs vues à distinguer ; sinon ``""`` (le libellé est déjà porté
    par le héros/onglet → pas de ressassage « Texte brut — » sur chaque section).
    Déjà échappé (fragment HTML prêt) : l'appelant l'insère tel quel."""
    return f"{escape(view_label(view, lang))} — " if multi else ""


def render_document(
    title: str,
    body: Html,
    *,
    footer: Html | None = None,
    lang: str = "fr",
    tabs: str = "",
    meta: str = "",
) -> str:
    """Assemble un document HTML autonome, au design, et déterministe.

    ``footer`` (optionnel) : HTML inséré en fin de ``<body>``, après le contenu
    principal — p. ex. le widget « comparer un run » (client-side). Absent → rien
    n'est ajouté (le rapport reste identique au squelette, ex. la voie
    ``compare`` server-side qui n'embarque pas le widget). ``lang`` pilote
    l'attribut ``<html lang>`` (a11y / lecteurs d'écran). ``tabs``/``meta`` :
    HTML **de confiance** intégré au **chrome** (barre d'onglets et méta+exports) ;
    vides → chrome minimal (wordmark seul). Le corps n'est **plus** enveloppé dans
    une carte unique : chaque section rend **sa** carte ``.sec``."""
    safe_title = escape(title)
    safe_lang = escape(lang)
    sub = "Report · benchmark" if lang == "en" else "Rapport · benchmark"
    tail = f"{footer}" if footer is not None else ""
    return (
        "<!DOCTYPE html>\n"
        f'<html lang="{safe_lang}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{safe_title}</title>\n"
        f"<style>{font_face_css()}{_CSS}</style>\n"
        "</head>\n"
        '<body class="report-board">\n'
        '<header class="report-chrome">'
        '<span class="wm-mark">C</span>'
        '<span class="wm-name">Cin<span class="wm-o">o</span>c</span>'
        f'<span class="wm-sep"></span><span class="wm-sub">{sub}</span>'
        f"{tabs}{meta}</header>\n"
        f'<main class="report-main">{body}</main>\n'
        f"{tail}"
        "</body>\n"
        "</html>\n"
    )


__all__ = [
    "escape",
    "localized",
    "render_document",
    "view_label",
    "view_prefix",
]

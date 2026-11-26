"""Diff **GT ↔ hypothèse** surligné (couche 7) — caractère par caractère, déterministe.

Aligne référence et hypothèse par **l'alignement du CER** (Levenshtein de coût
minimal, ``evaluation._alignment.opcodes`` — D-287) et marque les écarts :
**suppressions** (caractères de la GT absents de l'hypothèse, ``<del>``) et
**insertions** (caractères de l'hypothèse absents de la GT, ``<ins>``). Le diff
surligne ainsi exactement les éditions que compte le CER affiché à côté : S + D
caractères côté GT, S + I côté hypothèse. ``difflib``, qu'il remplace, ancrait le
plus long bloc commun d'abord et surlignait parfois davantage (« un un » lu
« uaun » : 3 supprimés et 2 insérés pour 2 éditions).
Le texte est **échappé** avant marquage (les balises sont les seules non échappées,
de confiance) — frontière anti-XSS. Aucun JS : le surlignage est du HTML rendu côté
serveur, donc octet-stable.
"""

from __future__ import annotations

from cinoc.evaluation._alignment import opcodes
from cinoc.reports.html import escape
from cinoc.reports.section import Html


def char_diff(reference: str, hypothesis: str) -> tuple[Html, Html]:
    """``(ref_html, hyp_html)`` : écarts surlignés, alignés caractère à caractère.

    ``ref_html`` = la GT avec ses **suppressions** marquées ``<del class="d-del">`` ;
    ``hyp_html`` = l'hypothèse avec ses **insertions** marquées ``<ins class="d-ins">``.
    Les segments identiques sont rendus tels quels (échappés). Une substitution
    est une suppression **et** une insertion (les deux côtés sont marqués) ; des
    éditions contiguës forment un seul surlignage de chaque côté.
    """
    ref_parts: list[str] = []
    hyp_parts: list[str] = []
    ref_run: list[str] = []
    hyp_run: list[str] = []

    def close_run() -> None:
        # Éditions contiguës (une substitution suivie d'une suppression…)
        # surlignées d'un seul tenant de chaque côté.
        deleted, inserted = "".join(ref_run), "".join(hyp_run)
        if deleted:
            ref_parts.append(f'<del class="d-del">{escape(deleted)}</del>')
        if inserted:
            hyp_parts.append(f'<ins class="d-ins">{escape(inserted)}</ins>')
        ref_run.clear()
        hyp_run.clear()

    for op in opcodes(reference, hypothesis):
        ref_seg = reference[op.src_start : op.src_end]
        hyp_seg = hypothesis[op.dest_start : op.dest_end]
        if op.tag == "equal":
            close_run()
            ref_parts.append(escape(ref_seg))
            hyp_parts.append(escape(hyp_seg))
        else:
            ref_run.append(ref_seg)
            hyp_run.append(hyp_seg)
    close_run()
    return Html("".join(ref_parts)), Html("".join(hyp_parts))


__all__ = ["char_diff"]

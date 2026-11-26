"""La convention d'une vue, dite à côté de son chiffre (couche 7) — D-285.

Un CER ne se lit pas sans sa normalisation : sous ``nfc``, un moteur qui
déroule ses lignes payait une substitution par ligne ; à plat, non. Le profil
de chaque vue est donc écrit là où le chiffre l'est (mesures clés) et dans la
méthodologie, avec sa **définition**, dérivée des leviers du profil lui-même —
jamais une phrase tenue à la main qui pourrait dériver de ce que le code
applique (anti-hallucination §12).
"""

from __future__ import annotations

from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.representations import view_profile
from cinoc.reports.html import escape, localized


def _levers(view: EvaluationView, lang: str) -> list[str]:
    """Ce que fait le profil (connu) de la vue, levier par levier, dans
    l'ordre où il le fait."""
    profile = view_profile(view)
    assert profile is not None  # appelé seulement pour un profil connu
    out: list[str] = []
    if profile.unicode_form == "none":
        out.append(localized(lang, "aucune forme Unicode imposée", "no Unicode form"))
    else:
        out.append(profile.unicode_form)
    if profile.strip_invisible:
        out.append(
            localized(lang, "invisibles retirés", "invisible characters removed")
        )
    if profile.caseless:
        out.append(localized(lang, "casse ignorée", "case ignored"))
    if profile.exclude_chars:
        chars = " ".join(sorted(profile.exclude_chars))
        if profile.exclude_mode == "space":
            out.append(
                localized(lang, f"{chars} remplacés par une espace",
                          f"{chars} replaced by a space")
            )
        else:
            out.append(localized(lang, f"{chars} ignorés", f"{chars} ignored"))
    if profile.diplomatic_table:
        n = len(profile.diplomatic_table)
        out.append(
            localized(lang, f"table d’équivalences ({n} entrées)",
                      f"equivalence table ({n} entries)")
        )
    if profile.non_word_to_space:
        out.append(
            localized(lang, "tout caractère hors mot remplacé par une espace",
                      "every non-word character replaced by a space")
        )
    if profile.strip_diacritics:
        out.append(localized(lang, "diacritiques retirés", "diacritics removed"))
    if profile.whitespace == "flat":
        out.append(
            localized(
                lang,
                "tout blanc, saut de ligne compris, réduit à une espace",
                "every whitespace run, line breaks included, reduced to one space",
            )
        )
    elif profile.whitespace == "intra_line":
        out.append(
            localized(
                lang,
                "blancs d’une ligne réduits à une espace, sauts de ligne comptés",
                "whitespace within a line reduced to one space, line breaks counted",
            )
        )
    else:
        out.append(
            localized(lang, "blancs comptés tels quels",
                      "whitespace counted as is")
        )
    return out


def _known(view: EvaluationView) -> bool:
    """Profil nommé que ce code connaît (faux : brute, ou nom d'un
    ``RunResult`` relu d'ailleurs)."""
    if view.normalization_profile is None:
        return False
    try:
        view_profile(view)
    except EvaluationError:
        return False
    return True


def profile_definition(view: EvaluationView, lang: str) -> str:
    """« <code>flat_text</code> : NFC, invisibles retirés, … » (HTML échappé)."""
    name = view.normalization_profile
    if name is not None and not _known(view):
        text = f"<code>{escape(name)}</code>"
    elif name is None:
        text = localized(
            lang,
            "<code>null</code> : aucune normalisation (comparaison brute)",
            "<code>null</code>: no normalisation (raw comparison)",
        )
    else:
        levers = ", ".join(escape(lever) for lever in _levers(view, lang))
        text = f"<code>{escape(name)}</code>{localized(lang, ' : ', ': ')}"
        text += levers
    if view.char_exclude:
        text += localized(
            lang,
            f" ; puis caractères exclus : {escape(view.char_exclude)}",
            f"; then excluded characters: {escape(view.char_exclude)}",
        )
    return text


def comparability(view: EvaluationView, lang: str) -> str:
    """Ce que la convention rend comparable, aux outils de référence (HTML)."""
    if view.normalization_profile is not None and not _known(view):
        return ""
    profile = view_profile(view)
    whitespace = "none" if profile is None else profile.whitespace
    if whitespace == "flat":
        return localized(
            lang,
            "Un moteur qui déroule ses lignes n’est pas pénalisé. jiwer et "
            "dinglehopper comptent le saut de ligne (dinglehopper unifie en "
            "outre ’ et ') : le chiffre le plus proche des leurs est celui "
            "d’une vue qui garde les sauts de ligne (« texte (lignes) » par "
            "défaut).",
            "An engine that unrolls its lines is not penalised. jiwer and "
            "dinglehopper count the line break (dinglehopper also unifies ’ "
            "and '): the closest figure to theirs is that of a view that keeps "
            "line breaks (“text (lines)” by default).",
        )
    if whitespace == "intra_line":
        return localized(
            lang,
            "Chaque saut de ligne compte, comme chez jiwer et dinglehopper ; "
            "ceux-ci comptent aussi les espaces répétées, et dinglehopper "
            "unifie ’ et ', — et –, et quelques ligatures, que ce profil garde "
            "distincts.",
            "Each line break counts, as in jiwer and dinglehopper; those also "
            "count repeated spaces, and dinglehopper unifies ’ and ', — and –, "
            "and a few ligatures, which this profile keeps distinct.",
        )
    return localized(
        lang,
        "Chaque blanc compte, bords compris : jiwer retire au moins les bords "
        "du texte, dinglehopper ceux de chaque ligne.",
        "Every whitespace counts, edges included: jiwer at least strips the "
        "text’s edges, dinglehopper each line’s.",
    )


def convention_html(view: EvaluationView, lang: str) -> str:
    """Paragraphe « Normalisation : … » placé sous le titre d'une vue."""
    label = localized(lang, "Normalisation", "Normalisation")
    note = comparability(view, lang)
    tail = f" {note}" if note else ""
    return (
        f'<p class="muted">{label} {profile_definition(view, lang)}.'
        f"{tail}</p>\n"
    )


__all__ = ["comparability", "convention_html", "profile_definition"]

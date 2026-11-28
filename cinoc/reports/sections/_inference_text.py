"""Lecture d'un payload ``inference`` en phrases courtes (couche 7).

Partagé par les mesures clés (le test de la métrique principale) et la section
de significativité (le tableau et le post-hoc) : un seul libellé par test, par
motif d'absence et par statut, pour que les deux sections ne se contredisent
pas. Tout est une **lecture** du payload — aucun recalcul, aucune prose
générée : le nom du test, les p, la distance critique et les paires viennent
tels quels de ``evaluation.inference``.

**Aucun verdict.** Jusqu'à la tranche I (inférence conditionnelle), tout
résultat de test de l'ancienne inférence est **exploratoire** (``status`` du
payload) : les p sont des nombres, le test porte l'étiquette ``exploratoire``,
et ni « significatif » ni son contraire n'est employé comme verdict
(``CONTRATS.md`` § 2.1 d, révision n° 7). Le post-hoc de Nemenyi nomme les
paires que la distance critique **sépare**, comme paires.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import InferencePayload
from cinoc.evaluation.inference import MIN_SUPPORT
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.html import escape, localized


def p_text(value: float, lang: str) -> str:
    return localize_decimal(f"{value:.4f}", lang)


def omnibus_label(payload: InferencePayload, lang: str) -> str:
    """« Wilcoxon signé-rangs » / « Friedman » ; « non calculé » sinon."""
    if payload.test == "wilcoxon":
        return localized(lang, "Wilcoxon signé-rangs", "Wilcoxon signed-rank")
    if payload.test == "friedman":
        return "Friedman"
    return localized(lang, "non calculé", "not computed")


def reason_text(payload: InferencePayload, lang: str) -> str:
    """Pourquoi le test n'a pas été calculé (vide s'il l'a été)."""
    n = payload.n_documents
    if payload.not_computed == "single_pipeline":
        return localized(lang, "un seul pipeline", "a single pipeline")
    if payload.not_computed == "insufficient_support":
        return localized(
            lang,
            f"{n} cas complets, il en faut au moins {MIN_SUPPORT}",
            f"{n} complete cases, at least {MIN_SUPPORT} are needed",
        )
    if payload.not_computed == "no_difference":
        return localized(
            lang,
            f"aucune différence entre pipelines sur les {n} cas complets",
            f"no difference between pipelines over the {n} complete cases",
        )
    return ""


def exploratory_label(lang: str) -> str:
    """L'étiquette de statut de tout résultat de test (``status`` du payload)."""
    return localized(lang, "exploratoire", "exploratory")


def separated_pairs(payload: InferencePayload) -> str:
    """« a – b · c – d » des paires que la distance critique sépare (vide :
    aucune) — une lecture du post-hoc de Nemenyi, pas un verdict."""
    return " · ".join(
        f"{escape(pair.a)} – {escape(pair.b)}"
        for pair in payload.pairwise
        if pair.significant
    )


def cd_bars(payload: InferencePayload) -> str:
    """Barres CD (groupes qui se chevauchent) : « {a, b} · {b, c} »."""
    return " · ".join(
        "{" + ", ".join(escape(name) for name in group) + "}"
        for group in payload.cd_groups
    )


def posthoc_text(payload: InferencePayload, lang: str) -> str:
    """Ce que dit (ou pourquoi ne dit rien) le post-hoc, en une phrase."""
    if payload.test == "wilcoxon":
        return localized(
            lang,
            "2 pipelines : le Wilcoxon est la comparaison de la paire (pas de "
            "post-hoc).",
            "2 pipelines: the Wilcoxon test is the comparison of the pair (no "
            "post-hoc).",
        )
    if payload.test != "friedman":
        return ""
    if payload.critical_distance is None or payload.q_alpha is None:
        return localized(
            lang,
            "Post-hoc de Nemenyi non effectué : la p corrigée de Holm du "
            "Friedman n'est pas sous α.",
            "Nemenyi post-hoc not run: the Holm-corrected Friedman p is not "
            "below α.",
        )
    alpha = localize_decimal(f"{payload.alpha:g}", lang)
    cd = localize_decimal(f"{payload.critical_distance:.4f}", lang)
    q = localize_decimal(f"{payload.q_alpha:.4f}", lang)
    pairs = separated_pairs(payload)
    found = localized(
        lang,
        f"paires séparées par la distance critique : {pairs}" if pairs else "aucune "
        "paire ne dépasse la distance critique",
        f"pairs separated by the critical distance: {pairs}" if pairs else "no "
        "pair exceeds the critical distance",
    )
    return localized(
        lang,
        f"Post-hoc de Nemenyi (α = {alpha}, q = {q}, CD = {cd}) : {found}. "
        f"Barres CD (elles se chevauchent ; deux pipelines ne diffèrent que "
        f"s'ils n'en partagent aucune) : {cd_bars(payload)}.",
        f"Nemenyi post-hoc (α = {alpha}, q = {q}, CD = {cd}): {found}. "
        f"CD bars (they overlap; two pipelines differ only if they share "
        f"none): {cd_bars(payload)}.",
    )


__all__ = [
    "cd_bars",
    "exploratory_label",
    "omnibus_label",
    "p_text",
    "posthoc_text",
    "reason_text",
    "separated_pairs",
]

"""Section calibration : fiabilité des confidences moteur (couche 7).

Rend les payloads ``calibration`` en **lecture seule** : ECE/MCE par pipeline,
**courbe de fiabilité SVG** (confiance vs exactitude) et table par bin.
"""

from __future__ import annotations

from cinoc.evaluation.analysis import CalibrationPayload
from cinoc.evaluation.result import RunResult
from cinoc.reports._numbers import localize_decimal
from cinoc.reports.engine_badges import engine_accent, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._payload import render_payload_section
from cinoc.reports.svg import calibration_curve


def _bin_label(lower: float, upper: float, lang: str) -> str:
    """« [0,3 ; 0,4[ », et « [0,9 ; 1,0] » pour le dernier bin, fermé."""
    close = "]" if upper >= 1.0 else "["
    return localize_decimal(f"[{lower:.1f} ; {upper:.1f}{close}", lang)


def _block(
    view: str, payload: CalibrationPayload, order: dict[str, int], lang: str
) -> str:
    head = localized(
        lang,
        f"{view}calibration des confidences",
        f"{view}confidence calibration",
    )
    parts: list[str] = [f"<h3>{head}</h3>\n"]
    parts.append(
        localized(
            lang,
            '<p class="muted">Un moteur calibré a raison à hauteur de ce qu\'il '
            "annonce : la courbe suit la diagonale. ECE = écart moyen pondéré "
            "entre confiance et exactitude, MCE = écart maximal "
            "(plus bas = mieux). Confiances de l’étape que la vue note ; un mot "
            "est juste s’il figure dans la référence, l’un et l’autre préparés "
            "par le profil de la vue. Dix bins [b/10 ; (b+1)/10[, le dernier "
            "fermé à 1,0.</p>\n",
            '<p class="muted">A calibrated engine is right as often as it '
            "claims: the curve follows the diagonal. ECE = mean weighted gap "
            "between confidence and accuracy, MCE = maximum gap "
            "(lower = better). Confidences of the step the view scores; a word "
            "is correct if it occurs in the reference, both prepared by the "
            "view’s profile. Ten bins [b/10, (b+1)/10), the last one closed at "
            "1.0.</p>\n",
        )
    )
    tokens_word = localized(lang, "jetons", "tokens")
    conf_axis = localized(lang, "confiance →", "confidence →")
    th_bin = localized(lang, "bin", "bin")
    th_mean_conf = localized(lang, "confiance moyenne", "mean confidence")
    th_accuracy = localized(lang, "exactitude", "accuracy")
    th_tokens = localized(lang, "jetons", "tokens")
    step_word = localized(lang, "étape", "step")
    for row in payload.pipelines:
        bins = "".join(
            f'<tr><td class="disp">{_bin_label(b.lower, b.upper, lang)}</td>'
            f'<td class="disp">'
            f'{localize_decimal(f"{b.mean_confidence:.3f}", lang)}</td>'
            f'<td class="disp">{localize_decimal(f"{b.accuracy:.3f}", lang)}</td>'
            f'<td class="disp">{b.count}</td></tr>'
            for b in row.bins
        )
        curve = calibration_curve(
            [(b.mean_confidence, b.accuracy) for b in row.bins],
            accent=engine_accent(order.get(row.pipeline, 0)),
        )
        parts.append(
            f"<h4>{escape(row.pipeline)} · {step_word} "
            f"<code>{escape(row.step)}</code> — "
            f'ECE {localize_decimal(f"{row.ece:.4f}", lang)} · '
            f'MCE {localize_decimal(f"{row.mce:.4f}", lang)} · '
            f"{row.n_tokens} {tokens_word}</h4>\n"
            '<div class="calib-block">'
            f'<div class="calib-plot">{curve}'
            f'<div class="calib-axis mono">{conf_axis}</div></div>'
            f'<table class="data">\n<thead><tr><th>{th_bin}</th>'
            f'<th class="num-cell">{th_mean_conf}</th>'
            f'<th class="num-cell">{th_accuracy}</th>'
            f'<th class="num-cell">{th_tokens}</th></tr></thead>\n'
            f"<tbody>{bins}</tbody>\n</table></div>\n"
        )
    return "".join(parts)


class CalibrationSection:
    """ECE/MCE + bins de fiabilité, par pipeline produisant des confidences."""

    name = "calibration"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        # Ordre canonique des moteurs (accent stable, partagé avec les sections).
        order = engine_order(p.pipeline for p in result.pipelines)
        return render_payload_section(
            result,
            ctx,
            payload_type=CalibrationPayload,
            title=localized(ctx.lang, "Calibration", "Calibration"),
            block=lambda view, payload: _block(view, payload, order, ctx.lang),
        )


__all__ = ["CalibrationSection"]

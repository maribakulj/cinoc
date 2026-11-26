"""Runs répétés et **fourchette** de mesure (couche 6).

Un banc qui n'exécute une configuration qu'une fois ne peut publier qu'une
décimale isolée — et une décimale isolée ne dit pas si l'écart qu'on lui fait
porter dépasse le bruit du dispositif. La règle qui en découle : **≥5 runs par
configuration, publier une fourchette, jamais une décimale isolée.**

Ce module exécute la même spec ``n`` fois et réduit les ``RunResult`` obtenus à
une fourchette par ``(pipeline, vue, métrique)``. Il ne rend aucun verdict : il
donne de quoi voir si une comparaison tient debout.

Ce qui varie d'un run à l'autre n'est pas le code — c'est le **modèle** (un LLM
à température nulle n'est pas déterministe pour autant) et, sur une API, la
version servie derrière un même nom. C'est pourquoi la répétition mesure le
dispositif complet et non un composant.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from statistics import median

from pydantic import BaseModel, ConfigDict, Field

from cinoc.domain.errors import CinocError
from cinoc.evaluation.result import RunResult


class MetricSpread(BaseModel):
    """Fourchette d'une métrique sur ``n`` runs de la même configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    view: str = Field(min_length=1, max_length=128)
    metric: str = Field(min_length=1, max_length=128)
    #: Nombre de runs où la métrique était applicable (``value`` non ``None``).
    n: int = Field(ge=0)
    minimum: float | None = None
    median_value: float | None = None
    maximum: float | None = None
    #: Étendue relative à la médiane, en fraction. ``None`` si la médiane est
    #: nulle ou absente — diviser par zéro dirait « stable » là où on ne sait pas.
    spread: float | None = None

    @property
    def is_single_run(self) -> bool:
        """Un seul run applicable : la « fourchette » n'en est pas une."""
        return self.n <= 1


class VarianceSummary(BaseModel):
    """Bilan de ``n`` exécutions : les fourchettes, et ce qui les a produites."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: int = Field(ge=1)
    corpus: str = Field(min_length=1, max_length=256)
    spreads: tuple[MetricSpread, ...] = ()

    def widest(self, limit: int = 5) -> tuple[MetricSpread, ...]:
        """Les métriques les plus instables — celles qui bornent ce qu'on peut
        affirmer. Une comparaison plus serrée que la plus large d'entre elles
        est du bruit."""
        mesurables = [s for s in self.spreads if s.spread is not None]
        mesurables.sort(key=lambda s: (-(s.spread or 0.0), s.pipeline, s.metric))
        return tuple(mesurables[:limit])


def summarize_runs(results: Sequence[RunResult]) -> VarianceSummary:
    """Réduit des ``RunResult`` de la **même** spec à des fourchettes.

    Refuse une liste vide : il n'y a pas de fourchette de rien. Un seul run est
    accepté et **signalé comme tel** (``is_single_run``) plutôt que présenté
    comme une mesure stable — c'est exactement la confusion que ce module
    existe pour empêcher.
    """
    if not results:
        raise CinocError("summarize_runs : aucun run à résumer.")

    valeurs: dict[tuple[str, str, str], list[float]] = {}
    for result in results:
        for pipeline in result.pipelines:
            for score in pipeline.aggregate:
                if score.value is None:
                    continue
                cle = (pipeline.pipeline, pipeline.view, score.metric)
                valeurs.setdefault(cle, []).append(score.value)

    spreads = []
    for (nom, vue, metrique), serie in sorted(valeurs.items()):
        centre = median(serie)
        etendue = max(serie) - min(serie)
        spreads.append(
            MetricSpread(
                pipeline=nom,
                view=vue,
                metric=metrique,
                n=len(serie),
                minimum=min(serie),
                median_value=centre,
                maximum=max(serie),
                spread=(etendue / abs(centre)) if centre else None,
            )
        )
    return VarianceSummary(
        runs=len(results),
        corpus=results[0].manifest.corpus_name,
        spreads=tuple(spreads),
    )


def run_repeatedly(
    execute: Callable[[int], RunResult], times: int
) -> tuple[tuple[RunResult, ...], VarianceSummary]:
    """Exécute ``times`` fois et renvoie ``(résultats, fourchettes)``.

    ``execute`` reçoit l'index du run (0-based) : l'appelant s'en sert pour
    nommer ses sorties (``cinoc run`` y lit l'archive propre à la répétition,
    ``resume.repetition_dir``). Aucun run n'en relit un autre — répéter sur un
    même cache de reprise mesurerait le cache, pas le dispositif.
    """
    if times < 1:
        raise CinocError(f"run_repeatedly : {times} runs demandés, minimum 1.")
    results = tuple(execute(i) for i in range(times))
    return results, summarize_runs(results)


__all__ = ["MetricSpread", "VarianceSummary", "run_repeatedly", "summarize_runs"]

"""``ResourceUsage`` — consommation mesurée d'une exécution (couche 1).

Vocabulaire transversal : la couche 4 (exécuteur) mesure la durée et collecte
les jetons remontés par les modules LLM/VLM ; la couche 3 (``RunResult``) porte
l'agrégat par (pipeline × document). Les durées sont du **wall-clock** : comme
les horodatages du ``RunManifest``, elles sont une mesure d'environnement,
exclues de l'identité des artefacts (déterminisme — voir ``ProvenanceRecord``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: Issue d'une unité (pipeline × document), **produite par l'exécution** : la
#: couche 4 la tient en main (l'exception d'une étape, la raison d'arrêt d'un
#: LLM) et la couche 3 la transporte dans ``RunResult`` (``DocumentUsage``).
#: ``truncated`` = sortie obtenue mais coupée (raison d'arrêt d'un LLM) : non
#: notée par défaut, signalée, sa statistique gardée à part (§ 2.1 f).
#: ``partial`` = sortie obtenue mais **déclarée incomplète** par l'étape (régions
#: non reconnues d'un fan-out, lignes de correction restées en repli) : le
#: module ou l'exécuteur le **déclare**, l'évaluation le lit et ne le reconstruit
#: jamais. ``failed`` = aucune sortie : l'unité n'a rien à noter.
UnitOutcome = Literal["ok", "truncated", "partial", "failed"]

#: L'état **déclaré** d'une étape dont la sortie est incomplète — ce que
#: ``StepOutput`` déclare (``partial``, ``truncation``) et que l'unité porte, par
#: étape, pour que chaque vue lise l'état de **son** étape (``A2`` : une
#: correction aval coupée ne rend pas incomplète la lecture amont). La tranche 2
#: le déplace dans le ``StepRecord`` de l'étape, sans changer sa sémantique.
StepIssue = Literal["partial", "truncated"]

#: Motif **codé** d'un échec — ce qu'on peut agréger ou filtrer sans lire un
#: message libre. ``engine`` : le moteur (adapter) a levé ; ``infrastructure`` :
#: l'environnement du run (image distante injoignable…) ; ``unsupported`` : le
#: pipeline ne s'applique pas à ce document tel que déclaré (entrée ou sortie
#: d'étape manquante) ; ``cancelled`` : l'unité a été arrêtée par un **délai** —
#: celui du run ou celui de l'étape (réglage ``timeout`` d'un moteur), libellé
#: « arrêtée (délai) ». Un délai dépassé ne dit rien du moteur : sous
#: contention, une page de 2 s en dépasse 120 (pilote D-281, D3).
FailureReason = Literal["engine", "infrastructure", "unsupported", "cancelled"]


def _add(a: int | None, b: int | None) -> int | None:
    if a is None and b is None:
        return None
    return (a or 0) + (b or 0)


class LineOutcomes(BaseModel):
    """Les issues des lignes d'une étape de **correction structurée** (§ 2.1 f).

    Quatre classes, **disjointes**. Les trois premières sont des décisions du
    correcteur — l'unité reste complète : ``corrected`` (texte modifié, hors
    ``review_required``), ``review_required`` (correction gardée, que le
    correcteur déclare ne pas pouvoir établir), ``abstained`` (texte source
    proposé inchangé), ``refused`` (garde-fou ou revue : la source est gardée,
    avec son code, hors replis). La quatrième est un incident d'exécution :
    ``fallback`` (aucune proposition exploitable : ``all_attempts_exhausted``,
    ``chunk_error_absorbed``) rend l'étape **partielle**. Le total des
    corrections est ``corrected + review_required``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    corrected: int = Field(default=0, ge=0)
    review_required: int = Field(default=0, ge=0)
    abstained: int = Field(default=0, ge=0)
    refused: dict[str, int] = Field(default_factory=dict)
    fallback: dict[str, int] = Field(default_factory=dict)

    def merged_with(self, other: LineOutcomes | None) -> LineOutcomes:
        """Somme compte par compte (par code pour ``refused`` et ``fallback``)."""
        if other is None:
            return self
        return LineOutcomes(
            corrected=self.corrected + other.corrected,
            review_required=self.review_required + other.review_required,
            abstained=self.abstained + other.abstained,
            refused=_sum_by_code(self.refused, other.refused),
            fallback=_sum_by_code(self.fallback, other.fallback),
        )


def _sum_by_code(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    return {code: a.get(code, 0) + b.get(code, 0) for code in sorted({*a, *b})}


class ResourceUsage(BaseModel):
    """Durée et jetons consommés. ``None`` = non mesuré / non applicable."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: Durée wall-clock en secondes (mesurée par l'exécuteur, jamais par le
    #: module — source unique).
    duration_seconds: float | None = Field(default=None, ge=0)
    #: Jetons d'entrée/sortie d'un appel LLM/VLM (remontés par l'adapter quand
    #: le fournisseur les expose ; ``None`` pour un moteur non facturé au jeton).
    #: ``tokens_in`` est **toute** l'entrée, cache compris (Anthropic la
    #: ventile en ``input_tokens`` hors cache + lectures + écritures : l'adapter
    #: les additionne) ; ``tokens_out`` toute la sortie, raisonnement compris.
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    #: **Parties** des totaux ci-dessus, quand la réponse les rend — ``None`` =
    #: non rendu (jamais un 0 supposé). ``tokens_cache_read`` : entrée lue dans
    #: le cache du fournisseur ; ``tokens_cache_write`` : entrée écrite en
    #: cache ; ``tokens_reasoning`` : sortie de raisonnement — facturée comme
    #: sortie et déjà dans ``tokens_out``, donc jamais ajoutée au coût.
    tokens_cache_read: int | None = Field(default=None, ge=0)
    tokens_cache_write: int | None = Field(default=None, ge=0)
    tokens_reasoning: int | None = Field(default=None, ge=0)
    #: Pages facturées par un OCR distant facturé à la page (Mistral OCR,
    #: Azure DI, Google Vision) : **chaque tentative facturable** — une requête
    #: par image, donc une par région en fan-out, et une tentative coupée après
    #: envoi en plus du succès. ``None`` = non compté (moteur non facturé à la
    #: page, JSON antérieur) : l'économie compte alors une page par unité.
    billed_pages: int | None = Field(default=None, ge=0)

    def merged_with(self, other: ResourceUsage | None) -> ResourceUsage:
        """Somme champ à champ (``None``-tolérante) — agrégation par document."""
        if other is None:
            return self
        duration: float | None
        if self.duration_seconds is None and other.duration_seconds is None:
            duration = None
        else:
            duration = (self.duration_seconds or 0.0) + (
                other.duration_seconds or 0.0
            )
        return ResourceUsage(
            duration_seconds=duration,
            tokens_in=_add(self.tokens_in, other.tokens_in),
            tokens_out=_add(self.tokens_out, other.tokens_out),
            tokens_cache_read=_add(self.tokens_cache_read, other.tokens_cache_read),
            tokens_cache_write=_add(
                self.tokens_cache_write, other.tokens_cache_write
            ),
            tokens_reasoning=_add(self.tokens_reasoning, other.tokens_reasoning),
            billed_pages=_add(self.billed_pages, other.billed_pages),
        )


__all__ = [
    "FailureReason",
    "LineOutcomes",
    "ResourceUsage",
    "StepIssue",
    "UnitOutcome",
]

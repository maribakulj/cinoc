"""Exceptions du domaine.

Hiérarchie centrée sur ``CinocError`` : un caller peut attraper toute
erreur métier Cinoc avec un seul ``except``.

Règle : ne jamais attraper ``CinocError`` dans le code métier sans la
re-lever — c'est le rôle de la couche transport (``app`` puis
``interfaces``) de mapper ces erreurs vers HTTP 4xx / sortie CLI.

Hiérarchie volontairement plate : on ajoute une sous-classe quand un
caller a besoin de discriminer.
"""

from __future__ import annotations

from cinoc.domain.usage import ResourceUsage


class CinocError(Exception):
    """Racine de la hiérarchie d'erreurs métier de Cinoc."""


class ArtifactValidationError(CinocError):
    """Un artefact ne respecte pas les invariants de son type."""


class ProjectionError(CinocError):
    """Un projecteur ne peut pas convertir l'artefact source.

    Le caller doit propager cette erreur dans le rapport de projection
    plutôt que de l'absorber silencieusement.
    """


class CorpusSpecError(CinocError):
    """Le ``CorpusSpec`` est mal formé (id dupliqués, GT incohérente…)."""


class AdapterStepError(CinocError):
    """Racine commune des erreurs d'adapter (OCR / LLM / VLM).

    Permet à un caller (typiquement l'executor) d'attraper « toute
    erreur d'adapter » sans connaître la sous-classe spécifique.

    ``billed`` : ce que l'étape a **fait facturer** avant d'échouer — la page
    soumise à Azure dont la sonde s'est perdue, les jetons d'une réponse
    refusée, une tentative coupée après envoi. L'unité est en échec (rien à
    noter), mais sa consommation facturable est comptée à l'économie. ``None``
    = rien de facturable connu.
    """

    def __init__(self, *args: object, billed: ResourceUsage | None = None) -> None:
        super().__init__(*args)
        self.billed = billed


class DeadlineExceeded(AdapterStepError):
    """Un adapter a détecté l'expiration de la ``Deadline`` reçue.

    Levée par un adapter qui respecte coopérativement la deadline
    propagée. Distincte des autres ``AdapterStepError`` pour permettre au
    runner de distinguer un timeout coopératif d'un échec fonctionnel.

    Un adapter doit lever ``DeadlineExceeded`` quand :

    - sa boucle interne détecte ``context.deadline.is_expired()`` avant
      d'avoir fini ;
    - son SDK lève un ``TimeoutError`` parce qu'on lui a passé
      ``context.deadline.as_sdk_timeout()`` qui s'est déclenché
      (l'adapter wrap et re-lève en ``DeadlineExceeded``) ;
    - le **délai propre de l'étape** (réglage ``timeout`` : Tesseract, outil
      externe, moteur distant) est dépassé — c'est la deadline de l'étape,
      la plus proche de celle du run et de ce réglage. Un délai dépassé ne dit
      rien du moteur (sous contention, une page de 2 s en dépasse 120 : pilote
      D-281, D3) : motif ``cancelled``, « arrêtée (délai) », pas ``engine``.

    Un adapter ne doit PAS lever ``DeadlineExceeded`` pour une expiration
    côté serveur (504) → ``AdapterStepError`` standard (retentée par
    ``call_resilient`` tant que le délai le permet).
    """


class RunCancelledError(CinocError):
    """Levée quand une cancellation coopérative a été signalée.

    Distincte de ``DeadlineExceeded`` : la cancellation est un signal
    explicite du caller (utilisateur, deadline globale du run), pas une
    expiration de la deadline du document en cours.
    """


class FormatError(CinocError):
    """Racine des erreurs de lecture/écriture d'un format documentaire.

    Permet à un caller (chargeur de corpus, projecteur) d'attraper « toute
    erreur de format » sans connaître le format précis. Les sous-classes
    spécifiques (``AltoParseError``, ``PageParseError``) vivent dans leur
    module de format (couche 2).
    """


__all__ = [
    "CinocError",
    "ArtifactValidationError",
    "ProjectionError",
    "CorpusSpecError",
    "AdapterStepError",
    "DeadlineExceeded",
    "RunCancelledError",
    "FormatError",
]

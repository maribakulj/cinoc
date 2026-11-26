"""Résolution de la version de code estampillée dans les runs (couche 6).

Source unique : la version du paquet **installé**, sinon le fallback ``domain``
(``FALLBACK_VERSION``). Centralisé ici car la version entre dans la **provenance**
(`RunManifest`) — un concern d'``app`` — et était auparavant recopiée dans
plusieurs interfaces (CLI, web).

**Pourquoi « installé » n'allait pas de soi.** ``importlib.metadata`` parcourt
``sys.path`` et retient la **première** métadonnée trouvée. Une copie de travail
du dépôt y laisse un ``cinoc.egg-info`` — un artefact de build, figé au dernier
``pip install`` et jamais rafraîchi ensuite — qui passait devant le ``dist-info``
du venv. La même commande rendait donc deux versions selon l'endroit d'où on la
lançait ::

    depuis ~/cinoc          0.1.1.dev550+gc6622f883.d20260916   (egg-info)
    depuis ailleurs         0.1.1.dev505+gbc2f66da9.d20260910   (installé)

Le script console y aide : il pose ``sys.path[0] = ''``, donc le répertoire
courant passe en tête. Et sous ``pytest``, la racine du dépôt est sur
``sys.path`` **en absolu** — l'``egg-info`` est alors atteignable quel que soit
le répertoire courant. Écarter le seul répertoire courant n'aurait donc pas
suffi.

Deux conséquences, toutes deux vécues. La **clé de reprise** inclut la version :
le cache d'un banc était intégralement manqué au premier changement de
répertoire, et 120 unités déjà calculées — dont des appels d'API facturés — ont
été relancées pour rien. Et le ``RunManifest`` enregistrait **deux versions pour
un code identique**, ce qui contredit frontalement l'invariant de
reproductibilité (``CLAUDE.md`` §12).

**La règle retenue** : fait autorité la distribution réellement **installée**,
reconnue à son ``RECORD`` — le manifeste de fichiers que la PEP 376 impose à
toute installation, et que ``importlib.metadata`` expose publiquement. Un
``egg-info`` de copie de travail n'en a pas. À défaut de toute distribution
installée, on retient la première trouvée plutôt que rien : un installeur
exotique qui omettrait ``RECORD`` doit rester utilisable.
"""

from __future__ import annotations

import re
from importlib.metadata import Distribution, PackageNotFoundError, distributions
from importlib.metadata import version as distribution_version

from cinoc.domain._version_fallback import FALLBACK_VERSION


def _est_installee(distribution: Distribution) -> bool:
    """Vrai si la distribution provient d'une **installation**, pas d'un build.

    ``RECORD`` est le manifeste de fichiers qu'une installation écrit (PEP 376).
    Un ``*.egg-info`` laissé dans un arbre source n'en a aucun : c'est
    précisément ce qui le distingue d'un paquet posé par ``pip``.
    """
    try:
        return distribution.read_text("RECORD") is not None
    except OSError:  # métadonnée illisible : on ne peut rien en conclure
        return False


def _cinoc_distribution() -> Distribution | None:
    """La distribution ``cinoc`` qui fait autorité (installée, sinon la première)."""
    repli: Distribution | None = None
    for distribution in distributions(name="cinoc"):
        if not distribution.version:
            continue
        if _est_installee(distribution):
            return distribution
        if repli is None:
            repli = distribution
    return repli


def resolve_code_version() -> str:
    """Version du paquet ``cinoc`` installé, ou le fallback ``domain``.

    Indépendante du répertoire d'appel — voir le module pour la raison.
    """
    distribution = _cinoc_distribution()
    return str(distribution.version) if distribution is not None else FALLBACK_VERSION


#: Extras qui ne servent qu'aux tests (outillage, oracles) : un run ne les
#: exécute jamais, leurs versions ne disent rien de ce qu'il a produit.
_EXTRAS_HORS_RUN = frozenset({"dev", "hipe-oracle"})
#: Nom de distribution en tête d'une exigence PEP 508 (``mistralai>=3,<4``).
_NOM = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
_EXTRA = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")


def dependencies_lock() -> dict[str, str]:
    """``{distribution: version}`` de ``cinoc`` et de ce qu'il peut faire tourner.

    La liste vient des **métadonnées** de ``cinoc`` (``Requires-Dist``), pas d'une
    table tenue à la main : dépendances de base (``numpy``, ``scipy``,
    ``rapidfuzz``, ``lxml``, ``pydantic``…) et extras d'exécution — donc le SDK
    de chaque moteur (``openai``, ``mistralai``, ``spacy``…). Seules les
    distributions **installées** y figurent, à leur version installée. Un SDK
    installé mais inutilisé par le run y figure aussi : la liste décrit
    l'environnement qui a produit le run, au complet, et ne dépend pas de ce
    qu'un processus a importé (le même run lancé du web et de la CLI a le même
    verrou). Les extras d'outillage (:data:`_EXTRAS_HORS_RUN`) n'y entrent pas.
    """
    distribution = _cinoc_distribution()
    if distribution is None:
        return {}
    noms: set[str] = set()
    for exigence in distribution.requires or ():
        tete = _NOM.match(exigence)
        if tete is None:
            continue
        extra = _EXTRA.search(exigence)
        if extra is not None and extra.group(1) in _EXTRAS_HORS_RUN:
            continue
        noms.add(tete.group(1).lower().replace("_", "-"))
    lock = {"cinoc": str(distribution.version)}
    for nom in sorted(noms):
        try:
            lock[nom] = distribution_version(nom)
        except PackageNotFoundError:
            continue
    return lock


__all__ = ["dependencies_lock", "resolve_code_version"]

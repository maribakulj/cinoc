"""Résoudre les analyses demandées au lancement (couche 6).

Le **mode rapide est le défaut** : une spec qui ne dit rien ne paie que ses
métriques. Le mode détaillé se réclame — dans la spec, ou au lancement, ce qui
évite d'éditer un fichier pour une question qu'on se pose une fois.

Placé en ``app`` parce que c'est une **capacité**, pas un détail de transport :
la ligne de commande et le lanceur web doivent l'offrir de la même façon
(``CLAUDE.md`` §8.4, D-224). Une seconde implémentation côté CLI dériverait.
"""

from __future__ import annotations

from cinoc.domain.evaluation import EvaluationSpec
from cinoc.domain.run_spec import RunSpec

#: Valeur réclamant le mode détaillé, en spec comme en ligne de commande.
TOUTES = "toutes"

#: Valeur réclamant explicitement le mode rapide. Utile pour **contredire** une
#: spec qui demande tout, sans l'éditer.
AUCUNE = "aucune"


def appliquer_analyses(spec: RunSpec, demande: str | None) -> RunSpec:
    """Applique une demande d'analyses à une spec, sans la muter.

    ``demande`` vaut ``None`` (la spec décide), ``"toutes"``, ``"aucune"``, ou
    une liste de ``kind`` séparés par des virgules. Elle **prime** sur la spec :
    c'est l'intérêt d'une option de lancement — répondre à une question ponctuelle
    sans modifier un fichier qu'on partage.
    """
    if demande is None:
        return spec
    voulu: tuple[str, ...] | str
    texte = demande.strip()
    if texte == TOUTES:
        voulu = TOUTES
    elif texte in (AUCUNE, ""):
        voulu = ()
    else:
        voulu = tuple(
            nom.strip() for nom in texte.split(",") if nom.strip()
        )
    evaluation = EvaluationSpec(views=spec.evaluation.views, analyses=voulu)
    return spec.model_copy(update={"evaluation": evaluation})


__all__ = ["AUCUNE", "TOUTES", "appliquer_analyses"]

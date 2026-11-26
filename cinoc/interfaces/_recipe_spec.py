"""``cinoc run --recipe`` : la face CLI des recettes (couche 8, pilote D24).

**Le même chemin que la page**, rien de plus. Le web prend un corpus dans son
dépôt et appelle ``plan_recipe_run`` ; la ligne de commande prend le corpus
dans un YAML (celui qu'écrit ``cinoc corpus import``) et appelle la même
fonction, avec la même file (``recipe_entries`` lit ``--recipe``, ``--brick``,
``--set``, ``--with``) et les mêmes options de notation. Ce qui suit —
cohérence, modèles, réglages, ``--check``, archive, rapport — est celui de
``cinoc run`` : une recette instanciée **est** une spec.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from cinoc.app import load_run_spec
from cinoc.app.evaluation_views import EvaluationOptions
from cinoc.app.loader import load_corpus_spec
from cinoc.app.recipe_queue import plan_recipe_run, recipe_entries
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec


def scoring_options(args: argparse.Namespace) -> EvaluationOptions:
    """Les options de notation de la ligne de commande — celles du web."""
    return EvaluationOptions(
        normalization=args.normalization,
        char_exclude=args.char_exclude,
        metric_profile=args.metric_profile,
    )


def spec_loader(args: argparse.Namespace) -> Callable[[str | Path], RunSpec]:
    """Comment ``cinoc run`` lit CONFIG : une spec, ou un corpus + des recettes.

    Une spec YAML écrit ses propres vues : lui passer des options de recette
    ou de notation serait les ignorer en silence — refusé, nommé.
    """
    options = scoring_options(args)
    if not args.recipe:
        orphelines = [
            nom
            for nom, posee in (
                ("--brick", args.brick),
                ("--set", args.set),
                ("--with", args.with_steps),
                ("--normalization", args.normalization),
                ("--metric-profile", args.metric_profile),
                ("--char-exclude", args.char_exclude),
            )
            if posee
        ]
        if orphelines:
            raise CinocError(
                f"{', '.join(orphelines)} : sans --recipe, CONFIG est une spec "
                "qui décrit déjà ses pipelines et ses vues."
            )
        return load_run_spec

    def _recette(path: str | Path) -> RunSpec:
        return plan_recipe_run(
            load_corpus_spec(path),
            recipe_entries(
                args.recipe,
                bricks=args.brick,
                settings=args.set,
                optional=args.with_steps,
            ),
            run_id=None,
            options=options,
        )

    return _recette


__all__ = ["scoring_options", "spec_loader"]

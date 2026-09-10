"""La surface déclarée de la CLI ne peut pas dériver du parseur réel.

``SUBCOMMANDS`` est une constante : ``argparse`` n'offre aucune API publique pour
relire ses sous-commandes, et fouiller ses internes dans le code livré serait le
couplage fragile que ``test_no_foreign_private_access`` existe pour contenir. Le
compromis tient à une condition — que la constante soit **confrontée** au
parseur. C'est ce que fait ce test, et l'accès aux internes reste ici, dans un
test, où il ne coûte qu'un échec bruyant si ``argparse`` change de forme.

Deux garde-fous s'appuient sur cette constante (documentation au ``README``,
parité web ⇄ CLI) : une constante fausse les rendrait tous les deux menteurs.
"""

from __future__ import annotations

import argparse

from cinoc.interfaces._cli_parser import SUBCOMMANDS, build_parser


def _parser_subcommands() -> frozenset[str]:
    """Les sous-commandes que le parseur déclare **vraiment**."""
    parser = build_parser()
    groupes = parser._subparsers  # noqa: SLF001 — pas d'API publique, cf. module
    assert groupes is not None, "le parseur doit porter des sous-commandes."
    return frozenset(
        nom
        for action in groupes._group_actions  # noqa: SLF001
        if isinstance(action, argparse._SubParsersAction)  # noqa: SLF001
        for nom in action.choices
    )


def test_declared_surface_matches_the_parser() -> None:
    assert frozenset(SUBCOMMANDS) == _parser_subcommands(), (
        "SUBCOMMANDS a dérivé du parseur. Mets la constante à jour : les "
        "garde-fous README et parité web ⇄ CLI la lisent comme un contrat."
    )


def test_the_declaration_has_no_duplicate() -> None:
    """Un doublon passerait le test d'égalité d'ensembles sans se voir."""
    assert len(SUBCOMMANDS) == len(set(SUBCOMMANDS)), (
        f"doublon dans SUBCOMMANDS : {SUBCOMMANDS}."
    )


def test_a_subcommand_is_required() -> None:
    """``cinoc`` seul ne doit pas « réussir » en ne faisant rien."""
    parser = build_parser()
    try:
        parser.parse_args([])
    except SystemExit as exc:
        assert exc.code != 0
    else:  # pragma: no cover — filet : le contrat serait rompu
        raise AssertionError("une sous-commande doit être exigée.")

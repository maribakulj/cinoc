"""Garde-fou anti-dérive du statut (`CLAUDE.md §0` ⇄ roll-up `MIGRATION_PLAN.md`).

**Pourquoi ce test existe.** `CLAUDE.md §0` est resté gelé à l'ère T1
(« ~158 tests », « Prochaine étape = T2 ») longtemps **après** que T2→T4e furent
livrés ; cette consigne périmée s'est ensuite **propagée** dans les plans UI. La
cause : un statut **dupliqué** dans `§0` au lieu d'être **délégué** au roll-up
(la `rituel de réconciliation` du projet exige de mettre à jour les docs dans le
même commit que le code — ce qui n'a pas été tenu pour `§0`).

Ce test verrouille les trois travers **mécaniques** de cette dérive :

1. `§0` **délègue** au roll-up (référence `MIGRATION_PLAN.md`) ;
2. `§0` ne **fige pas** un compte de tests (la dérive « 158 → 356 ») ;
3. `§0` ne désigne **jamais** comme « Prochaine étape » une tranche que le
   roll-up marque déjà « ✅ fait » (le bug exact : « = T2 » alors que « T2 …
   ✅ fait »).
"""

from __future__ import annotations

import re
from pathlib import Path

from cinoc.interfaces._cli_parser import SUBCOMMANDS

ROOT = Path(__file__).resolve().parents[2]


def _status_section() -> str:
    """Le bloc « ## 0. Statut actuel » de ``CLAUDE.md`` (jusqu'au titre suivant)."""
    text = (ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    start = text.index("## 0. Statut actuel")
    rest = text[start + 1 :]  # +1 : sauter le 1er '#' pour trouver le titre suivant
    return rest[: rest.index("\n## ")]


def _done_tranches() -> set[str]:
    """Tranches et phases déjà livrées, d'après les **deux** plans d'autorité.

    Les axes ``T#``/``S#`` (roll-up de ``MIGRATION_PLAN.md``) **et** les phases
    ``P#`` cochées dans la checklist « 1.0 prête » de ``PLAN_FIN_MIGRATION.md``.
    Ne lire que le premier laissait la porte ouverte à la dérive suivante : les
    axes ``T#``/``S#`` sont terminés, le plan qu'exécutent les sessions parle en
    ``P#``, et une « prochaine étape » nommée dans ce vocabulaire-là échappait
    au contrôle.
    """
    done: set[str] = set()
    plan = (ROOT / "MIGRATION_PLAN.md").read_text(encoding="utf-8")
    for line in plan.splitlines():
        if "✅" in line and "fait" in line:
            done.update(re.findall(r"\b[TS]\d\b", line))
    fin = (ROOT / "PLAN_FIN_MIGRATION.md").read_text(encoding="utf-8")
    for line in fin.splitlines():
        if line.startswith("- [x]"):
            done.update(re.findall(r"\bP\d\b", line))
    return done


def test_status_section_delegates_to_rollup() -> None:
    assert "MIGRATION_PLAN.md" in _status_section(), (
        "CLAUDE.md §0 doit déléguer le détail au roll-up de MIGRATION_PLAN.md."
    )


def test_status_section_has_no_hardcoded_test_count() -> None:
    assert not re.search(r"\d+\s*tests", _status_section(), re.IGNORECASE), (
        "CLAUDE.md §0 ne doit pas figer un compte de tests (il se périme) — "
        "déléguer au roll-up."
    )


def test_next_step_is_not_an_already_done_tranche() -> None:
    match = re.search(r"Prochaine étape\s*=\s*([TSP]U?\d[a-z]?)", _status_section())
    assert match, "CLAUDE.md §0 doit nommer une « Prochaine étape = T…/S…/P… »."
    next_step = match.group(1)
    done = _done_tranches()
    assert next_step not in done, (
        f"CLAUDE.md §0 désigne « {next_step} » comme prochaine étape, mais les "
        f"plans d'autorité la marquent déjà livrée ({sorted(done)}). "
        "Réconcilie le statut."
    )


def _next_session() -> str:
    return (ROOT / "NEXT_SESSION.md").read_text(encoding="utf-8")


def test_next_session_delegates_to_rollup() -> None:
    # Même dérive que CLAUDE.md §0, même verrou : NEXT_SESSION.md est resté gelé
    # à l'ère T1/TU2 (« prochaine = T2 », récaps de tranches livrées) longtemps
    # après T5→T7. Il doit pointer, pas recopier.
    assert "MIGRATION_PLAN.md" in _next_session(), (
        "NEXT_SESSION.md doit déléguer le statut au roll-up de MIGRATION_PLAN.md."
    )


def test_next_session_has_no_hardcoded_test_count() -> None:
    assert not re.search(
        r"\d+\s*(?:tests|verts)\b", _next_session(), re.IGNORECASE
    ), (
        "NEXT_SESSION.md ne doit pas figer un compte de tests (il se périme) — "
        "déléguer au roll-up."
    )


def test_next_session_does_not_recap_delivered_tranches() -> None:
    # Un titre « ## TU2.x — fait » (récap de tranche livrée) est exactement la
    # duplication de statut qui a pourri ce fichier : le détail vit dans le
    # roll-up et les DoD de couche, pas ici.
    assert not re.search(
        r"^##.*\b[TS]U?\d.*fait", _next_session(), re.MULTILINE
    ), (
        "NEXT_SESSION.md ne doit pas porter de récap « tranche — fait » : "
        "déléguer au roll-up de MIGRATION_PLAN.md."
    )


def test_every_cli_command_is_documented_in_the_readme() -> None:
    """Une commande absente du README n'est pas une commande — personne ne peut
    la trouver.

    La surface est lue dans ``_cli_parser.SUBCOMMANDS`` — le contrat que la CLI
    déclare — et non devinée par expression régulière dans sa source.

    Ce contrôle est né d'un cas réel : ``cinoc correct`` (post-correction
    structurée) a vécu des semaines livrée, testée et invisible — ni dans le
    README, ni dans aucun plan. Les trois autres contrôles de ce fichier
    surveillent la **forme** du statut ; celui-ci surveille la seule chose qu'on
    puisse vérifier mécaniquement de son **fond** : la surface utilisateur est
    décrite là où un utilisateur la cherche.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manquantes = sorted(nom for nom in SUBCOMMANDS if f"cinoc {nom}" not in readme)
    assert not manquantes, (
        f"commandes absentes du README : {manquantes}. Une commande livrée mais "
        "non documentée est invisible : la documenter, ou la retirer."
    )

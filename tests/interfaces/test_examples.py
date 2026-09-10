"""L'exemple de configuration livré ne peut pas se périmer en silence.

Le `README` renvoyait à `config.yaml` **trois fois** sans qu'un seul exemple
existe dans le dépôt : l'entrée la plus générale de Cinoc — un `RunSpec` complet
en YAML — était la seule qu'on ne pouvait pas utiliser sans lire le code.

Un exemple qui n'est pas exécuté pourrit à la première évolution du modèle. Ces
tests le **chargent** et le **font tourner** : le jour où un champ change de nom,
c'est ici que ça casse, pas chez la personne qui découvre l'outil.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.loader import load_run_spec
from cinoc.interfaces.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _configs() -> list[Path]:
    return sorted(EXAMPLES.glob("*.yaml"))


def test_at_least_one_example_is_shipped() -> None:
    """Un dossier d'exemples vide passerait tous les autres tests."""
    assert _configs(), f"aucun exemple sous {EXAMPLES}"


@pytest.mark.parametrize("config", _configs(), ids=lambda p: p.name)
def test_every_example_is_a_valid_run_spec(config: Path) -> None:
    spec = load_run_spec(config)
    assert spec.pipelines, "un exemple sans pipeline ne montre rien"
    assert spec.evaluation.views, "un exemple sans vue ne note rien"


@pytest.mark.parametrize("config", _configs(), ids=lambda p: p.name)
def test_every_example_actually_runs(config: Path, tmp_path: Path) -> None:
    """Valide **et** exécutable : c'est la promesse de l'en-tête du fichier.

    L'exemple s'appuie sur ``precomputed``, donc ce test ne touche ni le réseau
    ni un binaire externe — ce qui est précisément pourquoi l'exemple est bâti
    ainsi : un débutant doit pouvoir le lancer avant d'installer quoi que ce soit.
    """
    sortie = tmp_path / "rapport.html"
    assert main(["run", str(config), "-o", str(sortie)]) == 0
    assert sortie.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


@pytest.mark.parametrize("config", _configs(), ids=lambda p: p.name)
def test_every_example_explains_itself(config: Path) -> None:
    """Un exemple sans commentaires est un fichier à recopier, pas à comprendre."""
    lignes = config.read_text(encoding="utf-8").splitlines()
    commentaires = [ligne for ligne in lignes if ligne.startswith("#")]
    assert len(commentaires) >= 10, (
        f"{config.name} : trop peu d'explications en tête. Les quatre blocs "
        "(corpus, pipelines, evaluation, adapter_kwargs) doivent être nommés."
    )
    entete = "\n".join(commentaires)
    for bloc in ("corpus", "pipelines", "evaluation", "adapter_kwargs"):
        assert bloc in entete, f"{config.name} : le bloc {bloc!r} n'est pas expliqué"

"""Une spec peut être **typée juste** et décrire un montage qui ment.

Le cas qui a motivé ce module, mesuré sur la campagne BNL : une table
``psm_by_class`` écrite pour les classes d'un détecteur, posée sur un pipeline
qui en utilise un autre. Rien ne matchait, chaque région retombait sur le
réglage par défaut, et le run s'exécutait **sans un mot** — le défaut
n'apparaissait que dans un CER légèrement dégradé, indiscernable d'un moteur
médiocre.

Ces contrôles regardent ce qui ne se lit que sur **plusieurs étapes à la fois**,
donc ce qu'aucune brique isolée ne peut vérifier.
"""

from __future__ import annotations

import pytest

from cinoc.app.spec_coherence import SpecCoherenceError, check, declared_labels
from cinoc.domain.run_spec import RunSpec


def _spec(segmenteur: str, table: str) -> RunSpec:
    return RunSpec.model_validate(
        {
            "run_id": "r",
            "corpus": {
                "name": "c",
                "documents": [{"id": "d", "image_uri": "a.png", "ground_truths": []}],
            },
            "pipelines": [
                {
                    "name": "p",
                    "initial_inputs": ["image"],
                    "steps": [
                        {
                            "id": "seg",
                            "kind": "segmentation",
                            "adapter_name": segmenteur,
                            "input_types": ["image"],
                            "output_types": ["layout"],
                        },
                        {
                            "id": "reco",
                            "kind": "recognition",
                            "adapter_name": "tesseract:b",
                            "input_types": ["layout", "image"],
                            "output_types": ["layout"],
                            "inputs_from": {"layout": "seg"},
                            "fanout": True,
                            "crop": True,
                        },
                    ],
                }
            ],
            "evaluation": {"views": []},
            "adapter_kwargs": {
                "tesseract:b": {"label": "b", "psm_by_class": table},
                segmenteur: {},
            },
        }
    )


def test_a_table_written_for_another_model_is_refused() -> None:
    """**Le défaut que ce module ferme.**

    ``article``/``author`` sont les classes du modèle American Stories qu'utilise
    NDNP. Posées sur un détecteur dont le vocabulaire est celui de
    DocStructBench, elles ne matchent rien — et se taisaient.
    """
    with pytest.raises(SpecCoherenceError, match="Aucune classe en commun"):
        check(_spec("doclayout_yolo", "article:6,author:6"))


def test_a_table_that_speaks_the_right_vocabulary_passes() -> None:
    """Le pendant, et il compte autant : un contrôle qui refuse tout ne protège
    de rien. ``plain text`` et ``title`` sont bien des classes de ce modèle."""
    check(_spec("doclayout_yolo", "plain text:6,title:6"))


def test_a_partial_overlap_passes() -> None:
    """Régler deux classes sur dix est un **choix légitime** — on ne règle que
    ce qu'on veut. C'est n'en régler *aucune* qui trahit une table étrangère."""
    check(_spec("doclayout_yolo", "title:6,inexistante:3"))


def test_a_table_on_a_segmenter_without_classes_is_refused() -> None:
    """Tesseract découpe la page mais ne dit pas « ceci est un article ».

    Un vocabulaire **vide** n'est pas un oubli de déclaration : c'est
    l'affirmation qu'il n'y a aucune classe à laquelle accrocher un réglage. Une
    table posée là est une erreur de conception, pas une faute de frappe.
    """
    with pytest.raises(SpecCoherenceError, match="aucune classe sémantique"):
        check(_spec("tesseract_layout", "plain text:6"))


def test_no_table_means_nothing_to_check() -> None:
    """Sans table, il n'y a rien à contredire — le contrôle ne doit pas inventer
    d'exigence."""
    check(_spec("doclayout_yolo", ""))


def test_a_brick_that_declares_nothing_is_not_judged() -> None:
    """``None`` et l'ensemble vide sont deux choses différentes : « je ne me
    prononce pas » n'est pas « je ne pose aucune classe ». On ne refuse que ce
    qu'on peut réfuter."""
    assert declared_labels("tesseract", {"label": "x"}) is None


def test_the_declared_vocabulary_is_the_model_s_own() -> None:
    """Verrou sur de la **donnée** : ces étiquettes sont lues sur les poids
    publiés, pas choisies. Les changer sans changer de modèle ferait accepter
    des tables que le détecteur ignorerait."""
    labels = declared_labels("doclayout_yolo", {})
    assert labels is not None
    assert {"plain text", "title", "abandon", "table", "figure"} <= labels

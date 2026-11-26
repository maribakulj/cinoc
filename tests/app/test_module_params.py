"""La déclaration ``PARAMS`` appliquée : types, choix, bornes, tiers, rôles, CLI."""

from __future__ import annotations

from typing import ClassVar

import pytest

from cinoc.adapters.ocr.precomputed import PrecomputedTextAdapter
from cinoc.app.modules import ModuleRegistry, register_default_modules
from cinoc.app.modules.params import ModuleSettingsError, check_settings
from cinoc.app.recipes import plan_from_recipe, recipe_by_name, roles
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.pipeline import INITIAL_STEP_ID
from cinoc.interfaces.cli import main
from cinoc.pipeline.params import Param

_PSM = Param("psm", "int", "p", "p", default=6, minimum=0, maximum=13)
_MODE = Param("role", "str", "m", "m", default="a", choices=("a", "b"))
_T = Param("temperature", "float", "t", "t", default=0.0, minimum=0.0, maximum=2.0)
_REQ = Param("label", "str", "l", "l", required=True)


def _registre() -> ModuleRegistry:
    registre = ModuleRegistry()
    register_default_modules(registre)
    return registre


@pytest.mark.parametrize(
    ("reglages", "motif"),
    [
        ({"label": "x", "psm": "6"}, "int attendu"),
        ({"label": "x", "psm": True}, "int attendu"),  # un booléen n'est pas un nombre
        ({"label": "x", "psm": 14}, "14 > 13"),
        ({"label": "x", "role": "c"}, "hors des choix"),
        ({"psm": 6}, "'label' requis"),
        ({"label": "x", "pms": 6}, "vouliez-vous 'psm'"),
    ],
)
def test_a_setting_is_refused_with_its_reason(
    reglages: dict[str, object], motif: str
) -> None:
    with pytest.raises(ModuleSettingsError, match=motif):
        check_settings("brique:x", (_REQ, _PSM, _MODE, _T), reglages)


def test_an_integer_is_an_admissible_float() -> None:
    """Un YAML écrit ``temperature: 0`` : c'est un entier, et c'est valide."""
    check_settings("brique:x", (_REQ, _T), {"label": "x", "temperature": 0})


def test_an_empty_declaration_refuses_every_setting() -> None:
    """``PARAMS = ()`` affirme « aucun réglage » — distinct de l'absence."""
    with pytest.raises(ModuleSettingsError, match="Réglages acceptés : aucun"):
        _registre().build("alto_assembler", {"label": "x"})


class _Tiers(PrecomputedTextAdapter):
    """Un module tiers écrit **avant** la déclaration : ``PARAMS`` absent."""

    PARAMS = None  # type: ignore[assignment]


class _TiersDeclare(PrecomputedTextAdapter):
    """Un module tiers qui déclare ses réglages."""

    PARAMS: ClassVar[tuple[Param, ...]] = (
        Param("source_label", "str", "s", "s", required=True),
    )


def _tiers(cls: type[PrecomputedTextAdapter]) -> ModuleRegistry:
    registre = ModuleRegistry()
    registre.register_builder(
        "precomputed", lambda kw: cls(source_label=str(kw["source_label"]))
    )
    return registre


def test_an_undeclared_third_party_module_keeps_free_settings() -> None:
    """Rétrocompatibilité de l'API publique : un module tiers qui ne déclare
    rien n'est pas contrôlé — on ne refuse que ce qu'on peut réfuter."""
    module = _tiers(_Tiers).build("precomputed:s", {"source_label": "s", "libre": 1})
    assert module.name == "precomputed:s"
    assert _tiers(_Tiers).declared_params("precomputed") is None


def test_a_declaring_third_party_module_is_checked_once_built() -> None:
    """Sa déclaration se lit sur sa classe, après construction : la faute de
    frappe est refusée comme chez le socle."""
    registre = _tiers(_TiersDeclare)
    with pytest.raises(ModuleSettingsError, match="'libre'"):
        registre.build("precomputed:s", {"source_label": "s", "libre": 1})


# --------------------------------------------------------------------------- #
# Les deux rôles manquants (PLAN_UI_COMPOSEUR §2, tranche 2)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("recette", "etape", "entrees", "sortie"),
    [
        ("vlm_seul", "vlm", {ArtifactType.IMAGE}, ArtifactType.RAW_TEXT),
        (
            "ocr_puis_vlm",
            "correction",
            {ArtifactType.RAW_TEXT, ArtifactType.IMAGE},
            ArtifactType.CORRECTED_TEXT,
        ),
    ],
)
def test_a_recipe_describes_the_vision_modes(
    recette: str, etape: str, entrees: set[ArtifactType], sortie: ArtifactType
) -> None:
    """``zero_shot`` et ``text_and_image`` : une recette décrit désormais ce que
    le composeur décrit, et la brique construite a **la signature du rôle**."""
    spec, kwargs = plan_from_recipe(recipe_by_name(recette))
    step = next(s for s in spec.steps if s.id == etape)
    assert set(step.input_types) == entrees
    assert sortie in step.output_types
    if ArtifactType.IMAGE in entrees and len(entrees) > 1:
        # Le texte vient de l'OCR, l'image de l'entrée initiale.
        assert step.inputs_from == {
            ArtifactType.RAW_TEXT: "ocr",
            ArtifactType.IMAGE: INITIAL_STEP_ID,
        }
    for fournisseur in roles()[step.kind].briques:
        nom = f"{fournisseur}:{etape}"
        module = _registre().build(nom, {**kwargs[step.adapter_name], "model": "m"})
        assert module.input_types == frozenset(entrees), fournisseur
        assert sortie in module.output_types, fournisseur


def test_the_vision_roles_offer_only_vision_providers() -> None:
    from cinoc.app.engines import providers_for_mode

    for role in ("zero_shot", "text_and_image"):
        assert set(roles()[role].briques) == set(providers_for_mode(role))
        assert roles()[role].mode == role


# --------------------------------------------------------------------------- #
# Exposée là où un consommateur existe : `cinoc list engines <brique>`
# --------------------------------------------------------------------------- #


def test_list_engines_describes_the_settings_of_a_brick(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["list", "engines", "openai"]) == 0
    sortie = capsys.readouterr().out
    for nom in ("temperature", "base_url", "prompt_name", "self_hosted"):
        assert nom in sortie
    assert "hors empreinte" in sortie
    assert "requis" in sortie  # le modèle


def test_list_engines_refuses_an_unknown_brick(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["list", "engines", "tesseractt"]) == 1
    assert "brique inconnue" in capsys.readouterr().err


def test_list_engines_marks_a_secret(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["list", "engines", "remote_segmenter"]) == 0
    assert "secret" in capsys.readouterr().out

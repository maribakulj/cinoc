"""Garde-fou : une capacité se lit là où elle est implémentée, jamais recopiée.

**Le défaut que ce test empêche.** L'ancien composeur tenait deux littéraux —
`_LLM_ENGINES` et `_VLM_ENGINES` — énumérant les fournisseurs par mode. Quand
l'adapter `ollama` a gagné ses modes vision en août 2026, personne n'a mis ces
listes à jour : le planificateur a continué de refuser deux modes que l'adapter
savait exécuter, et le seul VLM **local et gratuit** est resté inutilisable pour
la transcription directe et la correction voyant l'image. Pendant des semaines,
et sans qu'aucun test ne s'en aperçoive (D-233).

La leçon n'est pas « mettre la liste à jour » : c'est qu'une capacité recopiée
dérive. Elle est désormais déclarée sur la classe d'adapter et **dérivée** par le
planificateur. Ce test verrouille les deux moitiés du contrat : que chaque
adapter déclare, et que rien ne ré-énumère à côté.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import get_args

import pytest

from cinoc.app.engines import CLI_ONLY_KINDS, llm_modes, providers_for_mode
from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
from cinoc.app.recipes import roles
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.pipeline import PipelineMode

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

#: Les quatre fournisseurs LLM/VLM du socle.
FOURNISSEURS = ("openai", "anthropic", "mistral", "ollama")

#: Les modes du contrat ``run_llm_step`` — **dérivés du type du domaine**.
#:
#: Les recopier ici aurait rejoué le défaut que ce fichier existe pour
#: fermer : le jour où un mode s'ajoute, le garde-fou déclarerait « mode
#: inconnu » sur le mode tout neuf.
MODES: tuple[PipelineMode, ...] = get_args(PipelineMode)


def test_every_provider_declares_its_modes() -> None:
    """Un fournisseur sans déclaration est un fournisseur dont on devine."""
    declares = llm_modes()
    assert set(declares) == set(FOURNISSEURS), (
        f"fournisseurs déclarés : {sorted(declares)} ≠ {sorted(FOURNISSEURS)}"
    )
    for nom, modes in declares.items():
        assert modes, f"{nom} ne déclare aucun mode"
        inconnus = sorted(modes - set(MODES))
        assert not inconnus, f"{nom} déclare des modes inconnus : {inconnus}"


_CORPUS = CorpusSpec(
    name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
)


def _role_du_mode(mode: str) -> str:
    """Le rôle de recette qui pose ``mode`` sur sa brique."""
    (nom,) = (n for n, r in roles().items() if r.mode == mode and not r.fanout)
    return nom


def test_every_declared_mode_has_its_role() -> None:
    """Aucun mode ne peut être **inatteignable** sans qu'on l'ait décidé.

    Jusqu'à D-295, ``refine`` n'était offert que par une spec écrite à la main
    et deux modes manquaient aux recettes ; depuis que le composeur à onglets
    est une file de recettes (D-298), chacun des quatre modes est un rôle.
    """
    for mode in MODES:
        _role_du_mode(mode)


@pytest.mark.parametrize("mode", sorted(MODES))
def test_the_roles_follow_the_declaration_at_runtime(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le rôle **suit** la déclaration, il n'en garde pas une copie.

    Comparer « déclaré » à « accepté » serait tautologique maintenant que le
    second dérive du premier. Ce qu'on vérifie est plus fort : qu'on retire un
    mode à un adapter, et la recette cesse de l'offrir — donc la lecture est
    vivante, pas figée à l'import. C'est exactement la situation d'août 2026,
    jouée à l'envers.
    """
    from cinoc.adapters.llm.ollama import OllamaAdapter

    assert "ollama" in roles()[_role_du_mode(mode)].briques

    monkeypatch.setattr(
        OllamaAdapter, "SUPPORTED_MODES", frozenset(m for m in MODES if m != mode)
    )
    assert "ollama" not in providers_for_mode(mode), (
        "la capacité est lue trop tard, ou mise en cache"
    )
    assert "ollama" not in roles()[_role_du_mode(mode)].briques, (
        f"la recette offre encore le mode {mode!r} à ollama alors que "
        "l'adapter ne le déclare plus : une liste parallèle a survécu."
    )


def test_a_declared_mode_is_actually_planifiable() -> None:
    """L'inverse : ce qui est déclaré doit produire une spec, pas un refus.

    C'est le bug d'août vu de face — `ollama` déclarait savoir transcrire, le
    planificateur répondait « n'a pas de VLM ».
    """
    for fournisseur in sorted(providers_for_mode("zero_shot")):
        spec = plan_recipe_run(
            _CORPUS,
            (
                RecipeEntry(
                    recipe="vlm_seul",
                    choices={"vlm": fournisseur},
                    params={"vlm": {"model": "m"}},
                ),
            ),
            run_id="r",
        )
        assert spec.pipelines, f"{fournisseur} : zero_shot déclaré mais non planifiable"


def test_no_hand_written_provider_list_remains() -> None:
    """Aucun module ne ré-énumère les fournisseurs dans un littéral.

    Une liste peut réapparaître ailleurs sous un autre nom, et le contrôle
    ci-dessus ne la verrait pas. Celui-ci cherche la **forme** du défaut : un
    ensemble, un tuple, une liste — **ou les clés d'un dictionnaire** —
    contenant au moins deux noms de fournisseurs.

    Le dictionnaire a été ajouté après coup : il était l'angle mort évident de
    ce contrôle, puisqu'une table ``{"mistral": …, "ollama": …}`` est une liste
    de fournisseurs sous un autre habit et passait sans un mot.
    """
    coupables: dict[str, list[str]] = {}
    for chemin in sorted(CINOC.rglob("*.py")):
        if "__pycache__" in chemin.parts:
            continue
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if isinstance(noeud, ast.Dict):
                elements: list[ast.expr] = [k for k in noeud.keys if k is not None]
            elif isinstance(noeud, ast.Set | ast.Tuple | ast.List):
                elements = list(noeud.elts)
            else:
                continue
            noms = {
                e.value
                for e in elements
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            trouves = noms & set(FOURNISSEURS)
            if len(trouves) >= 2:
                rel = chemin.relative_to(CINOC).as_posix()
                coupables.setdefault(rel, []).append(
                    f"L{noeud.lineno} {sorted(trouves)}"
                )
    # Trois **tables sources** — pas des copies. Nommées ici pour que toute
    # autre occurrence ressorte, et vérifiées par le test suivant : une source
    # autorisée dont les clés dérivent serait le pire des deux mondes.
    #
    #   app/engines.py                        fournisseur → classe d'adapter
    #   app/models.py                         fournisseur → modèles suggérés (curé)
    #   adapters/layout/saknussemm_correct.py producteur saknussemm → client
    #
    # Le dernier n'est **pas** dérivable de `providers_for_mode` : saknussemm
    # consomme un `StructuredCompletionClient`, écrit à la main par fournisseur.
    # Un fournisseur de cinoc absent de sa table est un client qui n'existe pas
    # encore, pas un oubli.
    autorise = {
        "app/engines.py",
        "app/models.py",
        "adapters/layout/saknussemm_correct.py",
    }
    fautifs = {k: v for k, v in coupables.items() if k not in autorise}
    assert not fautifs, (
        f"listes de fournisseurs recopiées : {fautifs}. Lis les capacités via "
        "`app.engines.providers_for_mode` — une liste parallèle dérive."
    )


def test_every_segmenter_pairs_with_every_block_reader() -> None:
    """La même intention ne peut pas recevoir deux réponses selon l'entrée.

    Le composeur (un hybride jugé côte à côte avec d'autres) et la transcription
    autonome tenaient deux ensembles de segmenteurs et de reconnaisseurs : le
    rejeu manquait au premier (D-233). Il n'y a plus qu'un constructeur
    (D-298) ; reste à prouver que **chaque** couple proposé se construit, brique
    par brique, avec ses réglages.
    """
    from cinoc.app.modules.registry import (
        ModuleRegistry,
        check_spec_settings,
        register_default_modules,
    )

    registre = ModuleRegistry()
    register_default_modules(registre)
    segmenteurs = [b for b in roles()["segmenter"].briques if b not in CLI_ONLY_KINDS]
    refus: list[str] = []
    for segmenteur in segmenteurs:
        for reconnaisseur in roles()["region_recognizer"].briques:
            reglages: dict[str, dict[str, str | int | float | bool]] = {}
            if segmenteur == "remote_segmenter":
                reglages["seg"] = {"endpoint": "https://e.test"}
            reglages["reco"] = (
                {"source_label": "l"}
                if reconnaisseur == "precomputed_region"
                else {"model": "m"}
                if reconnaisseur
                not in {"tesseract", "tesseract_layout", "google_vision", "azure_di"}
                else {}
            )
            try:
                spec = plan_recipe_run(
                    _CORPUS,
                    (
                        RecipeEntry(
                            recipe="segmentation_puis_lecture",
                            choices={"seg": segmenteur, "reco": reconnaisseur},
                            params=reglages,
                        ),
                    ),
                    run_id="r",
                )
                check_spec_settings(spec, registre)
            except Exception as exc:  # noqa: BLE001 — on collecte pour nommer
                refus.append(f"{segmenteur}/{reconnaisseur} : {exc}")
    assert not refus, "couples proposés mais refusés :\n  " + "\n  ".join(refus)


def test_no_module_level_mode_list_shadows_the_declaration() -> None:
    """Aucun module ne ré-énumère les **modes** à côté de la déclaration.

    Ce contrôle est né d'une récidive, et par moi. En posant `SUPPORTED_MODES`
    sur les classes (D-233), je n'avais pas vu que chaque adapter gardait aussi
    un `_SUPPORTED` au niveau module : deux sources coexistaient, et l'ajout du
    mode `refine` n'a été refusé que par la seconde (D-236). Le contrôle des
    *fournisseurs* ne voyait pas celui des *modes* — il en fallait un pour
    chaque forme du même défaut.
    """
    llm = CINOC / "adapters" / "llm"
    coupables: dict[str, list[str]] = {}
    for chemin in sorted(llm.glob("*.py")):
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            # Une affectation au niveau module (pas un attribut de classe).
            if not isinstance(noeud, ast.Module):
                continue
            for instruction in noeud.body:
                cible = _nom_affecte(instruction)
                if cible is None:
                    continue
                litteraux = {
                    e.value
                    for e in ast.walk(instruction)
                    if isinstance(e, ast.Constant) and isinstance(e.value, str)
                }
                if len(litteraux & set(MODES)) >= 2:
                    coupables.setdefault(chemin.name, []).append(cible)
    assert not coupables, (
        f"listes de modes au niveau module : {coupables}. Les modes se "
        "déclarent sur la classe d'adapter (`SUPPORTED_MODES`), qui est la "
        "seule source — une liste parallèle a déjà dérivé une fois."
    )


def _nom_affecte(instruction: ast.stmt) -> str | None:
    """Nom de la variable affectée par une instruction de module, ou ``None``."""
    if isinstance(instruction, ast.AnnAssign) and isinstance(
        instruction.target, ast.Name
    ):
        return instruction.target.id
    if isinstance(instruction, ast.Assign) and len(instruction.targets) == 1:
        cible = instruction.targets[0]
        if isinstance(cible, ast.Name):
            return cible.id
    return None


def test_the_allowed_source_tables_only_name_real_providers() -> None:
    """Une table **source** peut garder ses clés en dur — pas les inventer.

    Sans ce contrôle, l'autorisation du test précédent serait un blanc-seing :
    un fournisseur retiré de cinoc continuerait d'être suggéré par le catalogue
    de modèles, ou proposé comme producteur de correction, et rien ne le dirait.
    Ici les clés sont **confrontées** aux fournisseurs réels ; le contenu, lui,
    reste curé à la main (c'est ce qui fait de ces tables des sources).

    ``saknussemm`` a un nom en plus, et c'est voulu : ``mistral_vision`` n'est
    pas un fournisseur mais une **capacité** (regarder le scan) offerte par un
    fournisseur qui, lui, doit exister.
    """
    from cinoc.adapters.layout.saknussemm_correct import MODEL_PRODUCERS
    from cinoc.app.models import model_providers

    reels = set(FOURNISSEURS)
    # ``mistral_ocr`` : un moteur OCR, pas un fournisseur LLM — même compte et
    # même liste que ``mistral``.
    listes = set(model_providers()) - {"mistral_ocr"}
    assert listes <= reels, (
        f"app/models.py liste des modèles pour {listes - reels}, "
        "qui n'est plus un fournisseur de cinoc."
    )
    producteurs = set(MODEL_PRODUCERS) - {"mistral_vision"}
    assert producteurs <= reels, (
        f"saknussemm propose {producteurs - reels} comme producteur, mais cinoc "
        "ne connaît pas ce fournisseur."
    )
    assert "mistral" in MODEL_PRODUCERS, (
        "mistral_vision est une capacité de mistral : le fournisseur texte doit "
        "rester câblé à côté."
    )

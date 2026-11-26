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


def _litteraux_nommant(noms: frozenset[str]) -> dict[str, list[str]]:
    """Fichier → littéraux qui nomment **au moins deux** de ``noms``.

    La **forme** du défaut : un ensemble, un tuple, une liste — **ou les clés
    d'un dictionnaire** (ajoutées après coup : une table ``{"mistral": …,
    "ollama": …}`` est une liste sous un autre habit et passait sans un mot).
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
            trouves = noms & {
                e.value
                for e in elements
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if len(trouves) >= 2:
                rel = chemin.relative_to(CINOC).as_posix()
                coupables.setdefault(rel, []).append(
                    f"L{noeud.lineno} {sorted(trouves)}"
                )
    return coupables


def _moteurs_ocr() -> frozenset[str]:
    from cinoc.app.modules.registry import socle_ocr_engines

    moteurs = frozenset(socle_ocr_engines())
    # Garde-fou du garde-fou : une dérivation vide rendrait le contrôle muet.
    assert {"tesseract", "kraken", "mistral_ocr"} <= moteurs
    return moteurs


#: Famille → (noms, **tables sources** autorisées). Une table source n'est pas
#: une copie : elle est nommée ici pour que toute autre occurrence ressorte, et
#: ses clés sont confrontées aux briques réelles par un test dédié.
#:
#: Fournisseurs LLM/VLM —
#:   app/engines.py                        fournisseur → classe d'adapter
#:   app/models.py                         fournisseur → modèles suggérés (curé)
#:   adapters/layout/saknussemm_correct.py producteur saknussemm → client
#: Le dernier n'est **pas** dérivable de ``providers_for_mode`` : saknussemm
#: consomme un ``StructuredCompletionClient``, écrit à la main par fournisseur.
#:
#: Moteurs OCR (D-301) — le catalogue était tenu à la main en quatre endroits ;
#: il n'en reste qu'un, le socle du registre, dans l'ordre de préférence :
#:   app/modules/registry.py  le socle (``_SOCLE``) — la source
#:   app/engines.py           moteur → sonde de disponibilité (binaire, SDK,
#:                            clé : propre à chacun), confrontée au socle
#:   app/demo.py              **données** : les textes figés du corpus de
#:                            démonstration, nommés d'après deux moteurs
#:                            (rejoués par ``precomputed``, aucun n'est lancé)
_SOURCES: dict[str, set[str]] = {
    "fournisseurs": {
        "app/engines.py",
        "app/models.py",
        "adapters/layout/saknussemm_correct.py",
    },
    "moteurs OCR": {"app/modules/registry.py", "app/engines.py", "app/demo.py"},
}


@pytest.mark.parametrize("famille", sorted(_SOURCES))
def test_no_hand_written_catalogue_remains(famille: str) -> None:
    """Aucun module ne ré-énumère une famille de briques dans un littéral.

    Une liste peut réapparaître ailleurs sous un autre nom, et les contrôles de
    comportement ne la verraient pas : celui-ci cherche la **forme** du défaut.
    Un seul contrôle pour les deux familles — fournisseurs (D-233) et moteurs
    OCR (D-301) — là où chacune avait son patrouilleur.
    """
    noms = frozenset(FOURNISSEURS) if famille == "fournisseurs" else _moteurs_ocr()
    fautifs = {
        k: v for k, v in _litteraux_nommant(noms).items() if k not in _SOURCES[famille]
    }
    assert not fautifs, (
        f"{famille} recopiés : {fautifs}. Lis-les sur le registre "
        "(`socle_ocr_engines`, `providers_for_mode`) — une liste parallèle dérive."
    )


def test_the_ocr_roles_follow_the_registry_at_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retirer un moteur du socle le retire des recettes **et** du catalogue
    des moteurs : la lecture est vivante, aucune copie ne le garde."""
    from cinoc.app import engines
    from cinoc.app.modules import registry

    assert "kraken" in roles()["ocr"].briques
    monkeypatch.setattr(
        registry,
        "_SOCLE",
        tuple(entree for entree in registry._SOCLE if entree[0] != "kraken"),
    )
    assert "kraken" not in roles()["ocr"].briques
    assert "kraken" not in roles()["region_recognizer"].briques
    assert "kraken" not in {s.kind for s in engines.engine_statuses()}


def test_every_ocr_engine_has_its_probe_and_no_more() -> None:
    """La table des sondes est une source autorisée **parce qu'elle est
    confrontée** : un moteur sans sonde serait absent de ``cinoc list
    engines`` ; une sonde sans moteur, un moteur fantôme."""
    from cinoc.app.engines import OCR_PROBES

    assert set(OCR_PROBES) == set(_moteurs_ocr())


def test_a_declared_default_is_not_copied_outside_its_adapter() -> None:
    """Les défauts ``lang="fra"`` (×8) et ``fr_core_news_sm`` (×4) vivaient
    dans les planificateurs, le parseur CLI et l'i18n web (audit D-264) ;
    depuis la déclaration des réglages (D-295), ils sont lus sur l'adaptateur.
    Ce contrôle empêche qu'ils reviennent : aucun littéral égal au défaut
    déclaré d'une langue ou d'un modèle hors de ``adapters/``."""
    from cinoc.app.modules.registry import ModuleRegistry, register_default_modules

    registre = ModuleRegistry()
    register_default_modules(registre)
    defauts = {
        p.default
        for kind in registre.kinds()
        for p in registre.declared_params(kind) or ()
        if p.name in {"lang", "model"} and isinstance(p.default, str) and p.default
    }
    assert {"fra", "fr_core_news_sm"} <= defauts
    coupables: list[str] = []
    for chemin in sorted(CINOC.rglob("*")):
        if chemin.suffix not in {".py", ".js", ".html"} or "adapters" in chemin.parts:
            continue
        if chemin.suffix == ".py":
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Constant) and noeud.value in defauts:
                    coupables.append(f"{chemin.relative_to(CINOC)}:L{noeud.lineno}")
        else:
            texte = chemin.read_text(encoding="utf-8")
            coupables += [
                f"{chemin.relative_to(CINOC)} {d!r}"
                for d in defauts
                if f"'{d}'" in texte or f'"{d}"' in texte
            ]
    assert not coupables, f"défauts recopiés hors de l'adaptateur : {coupables}"


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

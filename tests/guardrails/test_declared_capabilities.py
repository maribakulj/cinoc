"""Garde-fou : une capacité se lit là où elle est implémentée, jamais recopiée.

**Le défaut que ce test empêche.** `run_planning` tenait deux littéraux —
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

import pytest

from cinoc.app.engines import llm_modes, providers_for_mode
from cinoc.app.run_planning import _llm_engines, _vlm_engines
from cinoc.domain.pipeline import PipelineMode

CINOC = Path(__file__).resolve().parents[2] / "cinoc"

#: Les quatre fournisseurs LLM/VLM du socle.
FOURNISSEURS = ("openai", "anthropic", "mistral", "ollama")

#: Les trois modes du contrat ``run_llm_step``.
MODES: tuple[PipelineMode, ...] = ("text_only", "text_and_image", "zero_shot")


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


@pytest.mark.parametrize("mode", MODES)
def test_the_planner_follows_the_declaration_at_runtime(
    mode: PipelineMode, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Le planificateur **suit** la déclaration, il n'en garde pas une copie.

    Comparer « déclaré » à « accepté » serait tautologique maintenant que le
    second dérive du premier. Ce qu'on vérifie est plus fort : qu'on retire un
    mode à un adapter, et le planificateur cesse de l'offrir — donc la lecture
    est vivante, pas figée à l'import. C'est exactement la situation d'août
    2026, jouée à l'envers.
    """
    from cinoc.adapters.llm.ollama import OllamaAdapter

    avant = providers_for_mode(mode)
    assert "ollama" in avant, "ollama déclare les trois modes depuis la PR #91"

    monkeypatch.setattr(
        OllamaAdapter, "SUPPORTED_MODES", frozenset(m for m in MODES if m != mode)
    )
    apres = providers_for_mode(mode)
    accepte = _llm_engines() if mode == "text_only" else _vlm_engines()

    assert "ollama" not in apres, "la capacité est lue trop tard, ou mise en cache"
    assert "ollama" not in accepte, (
        f"le planificateur offre encore le mode {mode!r} à ollama alors que "
        "l'adapter ne le déclare plus : une liste parallèle a survécu."
    )


def test_a_declared_mode_is_actually_planifiable() -> None:
    """L'inverse : ce qui est déclaré doit produire une spec, pas un refus.

    C'est le bug d'août vu de face — `ollama` déclarait savoir transcrire, le
    planificateur répondait « n'a pas de VLM ».
    """
    from pathlib import Path as _P

    from cinoc.app.run_planning import Competitor, plan_benchmark_run
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.domain.documents import DocumentRef

    corpus = CorpusSpec(
        name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
    )
    for fournisseur in sorted(providers_for_mode("zero_shot")):
        spec = plan_benchmark_run(
            (Competitor(engine=fournisseur, mode="zero_shot"),), corpus, "r"
        )(_P("/tmp"))
        assert spec.pipelines, f"{fournisseur} : zero_shot déclaré mais non planifiable"


def test_no_hand_written_provider_list_remains() -> None:
    """Aucun module ne ré-énumère les fournisseurs dans un littéral.

    Une liste peut réapparaître ailleurs sous un autre nom, et le contrôle
    ci-dessus ne la verrait pas. Celui-ci cherche la **forme** du défaut : un
    ensemble ou un tuple littéral contenant au moins deux noms de fournisseurs.
    """
    coupables: dict[str, list[str]] = {}
    for chemin in sorted(CINOC.rglob("*.py")):
        if "__pycache__" in chemin.parts:
            continue
        arbre = ast.parse(chemin.read_text(encoding="utf-8"))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Set | ast.Tuple | ast.List):
                continue
            noms = {
                e.value
                for e in noeud.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            trouves = noms & set(FOURNISSEURS)
            if len(trouves) >= 2:
                rel = chemin.relative_to(CINOC).as_posix()
                coupables.setdefault(rel, []).append(
                    f"L{noeud.lineno} {sorted(trouves)}"
                )
    # `_LLM_ADAPTERS` (app/engines.py) est **la** table de correspondance
    # fournisseur → classe : c'est la source, pas une copie. Elle est nommée ici
    # pour que toute autre occurrence ressorte.
    autorise = {"app/engines.py"}
    fautifs = {k: v for k, v in coupables.items() if k not in autorise}
    assert not fautifs, (
        f"listes de fournisseurs recopiées : {fautifs}. Lis les capacités via "
        "`app.engines.providers_for_mode` — une liste parallèle dérive."
    )


def test_both_planners_accept_the_same_bricks() -> None:
    """La même intention ne peut pas recevoir deux réponses selon le mode d'entrée.

    ``plan_benchmark_run`` (un hybride jugé côte à côte avec d'autres) et
    ``plan_hybrid_run`` (une transcription autonome) décrivent le même montage.
    Ils tenaient pourtant deux ensembles distincts de segmenteurs et de
    reconnaisseurs valides : le rejeu manquait au premier, si bien qu'une
    démonstration exécutable en transcription était refusée en benchmark
    (D-233).
    """
    from pathlib import Path as _P

    from cinoc.app.run_planning import Competitor, plan_benchmark_run
    from cinoc.app.structure_planning import (
        PIPELINE_SEGMENTERS,
        pipeline_recognizers,
        plan_hybrid_run,
    )
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.domain.documents import DocumentRef

    corpus = CorpusSpec(
        name="c", documents=(DocumentRef(id="d", image_uri="d.png", ground_truths=()),)
    )
    refus: list[str] = []
    for segmenteur in sorted(PIPELINE_SEGMENTERS):
        for reconnaisseur in sorted(pipeline_recognizers()):
            options = {"segmenter_endpoint": "https://e.test"} if (
                segmenteur == "remote_segmenter"
            ) else {}
            try:
                plan_benchmark_run(
                    (
                        Competitor(
                            engine=reconnaisseur, segmenter=segmenteur, **options
                        ),
                    ),
                    corpus,
                    "r",
                )(_P("/tmp"))
            except Exception as exc:  # noqa: BLE001 — on collecte pour nommer
                refus.append(f"benchmark {segmenteur}/{reconnaisseur} : {exc}")
            try:
                plan_hybrid_run(
                    corpus,
                    "h",
                    segmenter=segmenteur,
                    ocr=reconnaisseur,
                    label="l",
                    source_label="l",
                    endpoint=options.get("segmenter_endpoint"),
                )(_P("/tmp"))
            except Exception as exc:  # noqa: BLE001
                refus.append(f"autonome {segmenteur}/{reconnaisseur} : {exc}")
    assert not refus, (
        "couples valides d'un côté et refusés de l'autre :\n  " + "\n  ".join(refus)
    )

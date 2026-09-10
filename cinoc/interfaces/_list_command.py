"""Commande ``cinoc list`` : ce que l'installation sait faire, en texte.

**Deuxième transport, zéro logique nouvelle.** Les quatre sondes vivent en
couche ``app`` — ``engine_statuses`` / ``segmenter_statuses`` / ``ner_status``,
``provider_models``, ``normalization_profiles``, ``curated_prompts`` — et le web
les rendait en HTML (page Moteurs, ``<select>`` du composeur, aperçu de
normalisation). Ce module les rend en texte. Rien d'autre.

Un **verbe unique** et des sujets, plutôt qu'une commande par sujet : lire l'état
de son installation est **une** capacité (``CLAUDE.md`` §8.4).

Ce qui compte dans la sortie : un moteur indisponible dit **pourquoi** il l'est.
Une liste qui se contenterait de masquer ce qui manque laisserait l'utilisateur
chercher pendant une heure ce qu'un extra absent explique en une ligne.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from cinoc.app.engines import (
    EngineStatus,
    correction_status,
    curated_prompts,
    engine_statuses,
    llm_modes,
    ner_status,
    normalization_profiles,
    preprocess_status,
    segmenter_statuses,
)
from cinoc.app.models import provider_models
from cinoc.app.normalization_preview import preview_normalization
from cinoc.domain.errors import CinocError


def _print_statuses(titre: str, statuses: tuple[EngineStatus, ...]) -> None:
    print(f"\n{titre}")
    for status in statuses:
        marque = "✓" if status.available else "·"
        ligne = f"  {marque} {status.kind:<18} {status.label}"
        print(f"{ligne}\n      {status.detail}" if status.detail else ligne)


def run_list_engines(args: argparse.Namespace) -> int:
    """Moteurs, segmenteurs et étape NER, avec la **cause** d'indisponibilité."""
    _print_statuses("Moteurs (OCR / HTR / LLM / VLM)", engine_statuses())
    _print_statuses("Segmenteurs de mise en page", segmenter_statuses())
    _print_statuses(
        "Pré- et post-traitement (briques, pas des moteurs)",
        (preprocess_status(), correction_status(), ner_status()),
    )
    print(
        "\n✓ = utilisable ici et maintenant. Un moteur listé mais indisponible "
        "n'est pas une erreur : il dit ce qui lui manque (extra, binaire, clé)."
    )
    return 0


def run_list_models(args: argparse.Namespace) -> int:
    """Modèles canoniques d'un fournisseur — les mêmes suggestions qu'à l'UI."""
    # Lus sur les adapters : une liste recopiée ici dériverait le jour où un
    # fournisseur arrive ou perd un mode (cf. le garde-fou des capacités).
    fournisseurs = (args.provider,) if args.provider else sorted(llm_modes())
    for provider in fournisseurs:
        modeles = provider_models(provider)
        print(f"\n{provider}")
        if not modeles:
            print(
                "  (aucun modèle canonique — le champ reste libre ; pour ollama, "
                "ce sont les modèles réellement tirés en local qui comptent)"
            )
            continue
        for modele in modeles:
            vision = "  [vision]" if modele.vision else ""
            print(f"  {modele.name}{vision}")
    return 0


def run_list_profiles(args: argparse.Namespace) -> int:
    """Profils de normalisation, et — sur demande — ce qu'ils font d'un texte.

    L'aperçu est **sans persistance**, comme côté web : une config YAML passée
    ici est appliquée à la volée, jamais enregistrée.
    """
    profils = normalization_profiles()
    if args.preview is None:
        print("Profils de normalisation :")
        for profil in profils:
            print(f"  {profil}")
        print(
            "\nVoir ce qu'un profil fait d'un texte :\n"
            '  cinoc list profiles --preview "Il eſtoit vne fois" --profile heritage'
        )
        return 0

    config = None
    if args.config is not None:
        config = Path(args.config).read_text(encoding="utf-8")
    if args.profile is None and config is None:
        raise CinocError(
            "--preview attend --profile <nom> ou --config <fichier.yaml> : "
            "normaliser « par défaut » ne veut rien dire."
        )
    print(f"avant : {args.preview!r}")
    apres = preview_normalization(
        args.preview, profile=args.profile, config=config
    )
    print(f"après : {apres!r}")
    return 0


def run_list_prompts(args: argparse.Namespace) -> int:
    """Prompts curés par période — donnée versionnée, pas de la surface."""
    print("Prompts curés (correction et transcription, calibrés par période) :")
    for prompt in curated_prompts():
        print(f"  {prompt}")
    print(
        "\nÀ poser en `prompt_name` d'un concurrent. Un prompt libre reste "
        "possible et prime sur le prompt curé."
    )
    return 0


__all__ = [
    "run_list_engines",
    "run_list_models",
    "run_list_profiles",
    "run_list_prompts",
]

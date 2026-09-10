"""Commande ``cinoc corpus`` : acquérir un corpus depuis la ligne de commande.

**Deuxième transport d'une capacité qui existait déjà.** Les six importeurs
vivent en couche ``app`` (``app/corpus_import.py``) et n'avaient qu'un seul
appelant : le routeur web. Ce module n'en ré-implémente aucun — il fait
exactement ce que fait le routeur (choisir le builder, le passer à
``materialize_corpus``, résumer), à ceci près que la **destination** diffère :

* le web matérialise dans un ``CorpusStore`` serveur, indexé par un identifiant
  qu'il rend à l'appelant ;
* la CLI matérialise dans un **dossier choisi par l'utilisateur** et écrit à
  côté un ``corpus.yaml`` — le « store » d'une ligne de commande est un fichier.

Le YAML porte la clé ``corpus``, celle d'un ``RunSpec`` : il se complète de
``pipelines:`` / ``evaluation:``, ou se colle dans un fichier de run existant.

Ce module reçoit le ``Namespace`` d'``argparse``. C'est délibéré : il est
lui-même du **transport CLI**, et lui faire traverser six signatures distinctes
(une par source, chacune avec ses options) n'aurait rien clarifié. Aucune
logique ici — la couche ``app`` porte tout.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path

from cinoc.adapters.corpus.htr_united import fetch_catalogue
from cinoc.adapters.corpus.huggingface import discover_curated
from cinoc.app.corpus_import import (
    import_curated_hf_corpus,
    import_escriptorium_corpus,
    import_gallica_corpus,
    import_hf_corpus,
    import_iiif_corpus,
    materialize_corpus,
    resolve_curated_author,
)
from cinoc.app.corpus_upload import extract_corpus_zip
from cinoc.app.loader import dump_corpus_spec
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError


def _builder(args: argparse.Namespace) -> Callable[[Path], CorpusSpec]:
    """Le constructeur de corpus correspondant à la source demandée.

    Un ``match`` **exhaustif** : une source non câblée lève au lieu de retomber
    silencieusement sur une autre (même garde-fou que le dispatch moteur du
    planificateur).
    """
    match args.source:
        case "iiif":
            return lambda dest: import_iiif_corpus(
                args.manifest_url, dest, name=args.name or "iiif", limit=args.limit
            )
        case "gallica":
            return lambda dest: import_gallica_corpus(
                args.ark,
                dest,
                name=args.name,
                limit=args.limit,
                include_ocr=args.include_ocr,
            )
        case "escriptorium":
            return lambda dest: import_escriptorium_corpus(
                args.base_url,
                args.token,
                args.doc_pk,
                dest,
                name=args.name,
                layer=args.layer,
                limit=args.limit,
            )
        case "hf":
            return lambda dest: import_hf_corpus(
                args.dataset_id,
                dest,
                name=args.name,
                split=args.split,
                limit=args.limit,
            )
        case "curated":
            return lambda dest: import_curated_hf_corpus(
                args.repo_id, dest, revision=args.revision, name=args.name
            )
        case "zip":
            archive = Path(args.archive).read_bytes()
            return lambda dest: extract_corpus_zip(
                archive, dest, name=args.name or Path(args.archive).stem
            )
        case _:  # pragma: no cover — argparse borne déjà les choix
            raise CinocError(f"source de corpus inconnue : {args.source!r}.")


def run_corpus_import(args: argparse.Namespace) -> int:
    """Matérialise un corpus sous ``--dest`` et écrit son YAML."""
    dest = Path(args.dest)
    if dest.exists() and any(dest.iterdir()):
        raise CinocError(
            f"{dest} n'est pas vide. Un import écrit dans un dossier neuf : "
            "réutiliser un dossier peuplé mêlerait deux corpus sans le dire."
        )
    spec = materialize_corpus(dest, _builder(args))
    sortie = dump_corpus_spec(spec, args.output or dest / "corpus.yaml")
    print(
        f"{len(spec.documents)} document(s) — corpus « {spec.name} » "
        f"matérialisé dans {dest}"
    )
    print(f"Corpus écrit : {sortie}")
    print(
        "Complète ce fichier de `pipelines:` et `evaluation:`, ou colle son "
        "bloc `corpus:` dans un fichier de run, puis : cinoc run <fichier>"
    )
    return 0


def run_corpus_search(args: argparse.Namespace) -> int:
    """Cherche dans le catalogue HTR-United (mêmes entrées que la page web)."""
    catalogue = fetch_catalogue()
    entrees = catalogue.search(args.query, language=args.language)
    if not entrees:
        print(f"Aucune entrée pour {args.query!r}.")
        return 0
    if catalogue.is_demo:
        print("(catalogue de démonstration — le catalogue distant est injoignable)")
    for entree in entrees[: args.limit]:
        langues = ", ".join(entree.languages) or "—"
        print(f"{entree.id}  [{langues}]\n  {entree.title}\n  {entree.url}")
    reste = len(entrees) - args.limit
    if reste > 0:
        print(f"… et {reste} autre(s) — affine la recherche ou relève --limit.")
    return 0


def run_corpus_discover(args: argparse.Namespace) -> int:
    """Liste les datasets curés Cinoc d'un compte HuggingFace.

    Sans ``--author``, le compte est résolu comme côté web : ``CINOC_HF_AUTHOR``,
    puis un jeton HF, puis le propriétaire du ``SPACE_ID``.
    """
    author = args.author or resolve_curated_author()
    if not author:
        raise CinocError(
            "aucun compte HuggingFace à interroger : passe --author, ou pose "
            "CINOC_HF_AUTHOR (ou un jeton HF_TOKEN)."
        )
    refs = discover_curated(author)
    if not refs:
        print(f"Aucun dataset curé Cinoc chez {author}.")
        return 0
    for ref in refs:
        revision = f" @{ref.revision[:12]}" if ref.revision else ""
        print(f"{ref.repo_id}{revision}\n  {ref.title}  ({ref.last_modified})")
    print("\nImporter : cinoc corpus import curated <repo_id> --dest <dossier>")
    return 0


__all__ = ["run_corpus_discover", "run_corpus_import", "run_corpus_search"]

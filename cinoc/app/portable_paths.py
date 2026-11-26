"""Chemins **portables** du ``RunResult`` : relatifs à une racine, jamais absolus.

Un ``RunResult`` se publie (Hub, campagne, archive envoyée à un tiers). Il
portait les chemins absolus de la machine qui l'avait produit — l'image de
chaque document, le dossier d'archive, le chemin cité par un message d'échec —
donc l'arborescence et le nom d'utilisateur de qui l'avait lancé (pilote D-281,
D5).

**La racine** est celle contre laquelle la spec résout ses propres chemins : le
dossier du fichier de run pour la CLI (``load_run_spec``), le dossier des corpus
déposés pour le web. Une référence d'image s'écrit donc **comme la spec
l'écrit** (``0000.png``, ``corpus/folio_001.png``) et se relit contre la même
racine. Ce module porte les deux sens : :func:`portable_result` à l'écriture,
:func:`resolve_image_ref` à la lecture (rapport, route servie).

Hors de la racine, une image n'a **pas** de référence (``None``) : un chemin
qu'on ne saurait pas relire n'en est pas une, et un absolu fuirait à nouveau.
Le cas ne se présente pas en CLI — ``validated_path`` confine déjà chaque chemin
de la spec sous le dossier du fichier — et, côté web, il désigne un corpus de
démonstration écrit dans le workspace temporaire du job, effacé à la fin du run.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePath

from cinoc.app.security import PathSecurityError, validated_path
from cinoc.evaluation.result import RunResult

_REMOTE = ("http://", "https://")


def _relative(path: str, root: Path) -> str | None:
    """``path`` relatif à ``root`` en POSIX ; ``None`` s'il en sort."""
    try:
        return Path(path).resolve().relative_to(root).as_posix()
    except (ValueError, OSError):
        return None


def portable_image_ref(ref: str | None, root: Path) -> str | None:
    """Référence d'image à publier : URL inchangée, chemin local relatif."""
    if ref is None or ref.startswith(_REMOTE):
        return ref
    return _relative(ref, root)


def portable_dir(path: str, root: Path) -> str:
    """Dossier (archive) à publier : relatif à ``root``, sinon son seul nom.

    Personne ne le relit par programme — il dit où chercher l'archive ; son nom
    suffit à la reconnaître, son chemin absolu n'apprendrait que la machine.
    """
    return _relative(path, root) or Path(path).name


def relativize_message(message: str, root: PurePath) -> str:
    """Les chemins sous ``root`` cités par un message, rendus relatifs (POSIX).

    Le séparateur est accepté sous ses deux formes et **redoublé** : un message
    qui cite un chemin par ``repr`` le porte, sous Windows, avec des ``\\\\``.
    """
    parts = [re.escape(part) for part in re.split(r"[\\/]+", str(root)) if part]
    if not parts:
        return message
    lead = r"[\\/]+" if str(root)[:1] in ("/", "\\") else ""
    pattern = lead + r"[\\/]+".join(parts) + r"[\\/]+([^\s'\"]*)"
    return re.sub(pattern, lambda m: re.sub(r"[\\/]+", "/", m.group(1)), message)


def portable_result(result: RunResult, root: Path) -> RunResult:
    """``result`` sans chemin absolu local : images et archive sous ``root``."""
    manifest = result.manifest
    if manifest.artifacts_dir is not None:
        manifest = manifest.model_copy(
            update={"artifacts_dir": portable_dir(manifest.artifacts_dir, root)}
        )
    documents = tuple(
        document.model_copy(
            update={"image_ref": portable_image_ref(document.image_ref, root)}
        )
        for document in result.documents
    )
    return result.model_copy(update={"manifest": manifest, "documents": documents})


def resolve_image_ref(ref: str, root: Path | None) -> str | None:
    """Référence d'image du ``RunResult`` → ce qu'on peut ouvrir (chemin, URL).

    Une référence relative se lit contre ``root`` **et y reste confinée** (un
    ``RunResult`` servi peut venir d'ailleurs : ``../`` n'en sort pas). Sans
    racine, ou pour un absolu (``RunResult`` antérieur à D-282) et une URL, la
    référence est rendue telle quelle.
    """
    if root is None or ref.startswith(_REMOTE) or Path(ref).is_absolute():
        return ref
    try:
        return str(validated_path(ref, root))
    except PathSecurityError:
        return None


def confine_image_refs(result: RunResult, root: Path) -> RunResult:
    """``result`` dont chaque image **locale** se relit sous ``root``, ou n'a pas
    de référence.

    Pour un ``RunResult`` **servi** : le serveur lit les images qu'un JSON
    déposé lui nomme, et un JSON se dépose depuis ailleurs. Un absolu (JSON
    antérieur à D-282) ne passe donc que s'il tombe sous ``root`` — au lieu de
    faire ouvrir au serveur un fichier de son choix —, et un relatif qui en
    sort perd sa référence comme dans :func:`resolve_image_ref`. Une URL reste
    telle quelle. Le rendu local (CLI), lui, relit le JSON de la machine même :
    il garde la règle de :func:`resolve_image_ref`.
    """
    documents = tuple(
        document
        if document.image_ref is None
        or document.image_ref.startswith(_REMOTE)
        or _confined(document.image_ref, root)
        else document.model_copy(update={"image_ref": None})
        for document in result.documents
    )
    return result.model_copy(update={"documents": documents})


def _confined(ref: str, root: Path) -> bool:
    try:
        validated_path(ref, root)
    except PathSecurityError:
        return False
    return True


__all__ = [
    "confine_image_refs",
    "portable_dir",
    "portable_image_ref",
    "portable_result",
    "relativize_message",
    "resolve_image_ref",
]

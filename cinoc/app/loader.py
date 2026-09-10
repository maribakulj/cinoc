"""Pont YAML ⇄ specs (couche 6) : lire un ``RunSpec``, écrire un corpus.

Un run est décrit par un fichier YAML, **validé** par Pydantic
(``RunSpec.model_validate`` — ``extra="forbid"`` rejette les clés inconnues),
puis dont les **chemins sont sécurisés** (``validated_path``, relatifs au dossier
du fichier ou à ``base_dir``). **Aucune résolution de classe d'adapter** ici : le
registre résout ``adapter_name → Module`` au runtime (journal D-010) — donc pas
d'import de chemin pointé arbitraire.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from cinoc.app.security import validated_path
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec


class RunSpecError(CinocError):
    """Le fichier de run est illisible ou ne décrit pas un ``RunSpec`` valide."""


def load_run_spec(
    path: str | Path, *, base_dir: str | Path | None = None
) -> RunSpec:
    """Charge un ``RunSpec`` depuis un YAML, chemins sécurisés sous ``base_dir``."""
    yaml_path = Path(path)
    base = Path(base_dir) if base_dir is not None else yaml_path.parent
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RunSpecError(f"YAML illisible : {exc}.") from exc
    if not isinstance(raw, dict):
        raise RunSpecError("YAML : un objet est attendu à la racine.")
    try:
        spec = RunSpec.model_validate(raw)
    except ValidationError as exc:
        raise RunSpecError(f"RunSpec invalide : {exc}.") from exc
    return _secure_paths(spec, base)


def _secure_paths(spec: RunSpec, base: Path) -> RunSpec:
    documents = tuple(_secure_document(doc, base) for doc in spec.corpus.documents)
    corpus = spec.corpus.model_copy(update={"documents": documents})
    return spec.model_copy(update={"corpus": corpus})


def _secure_document(document: DocumentRef, base: Path) -> DocumentRef:
    # Une image **distante** (corpus curé : référence http/https épinglée) passe
    # telle quelle — l'orchestrateur la matérialise au run via le fetch durci
    # (anti-SSRF + plafond). ``validated_path`` ne garde que les chemins locaux.
    raw_image = document.image_uri
    if raw_image is not None and raw_image.startswith(("http://", "https://")):
        image_uri: str | None = raw_image
    else:
        image_uri = (
            str(validated_path(raw_image, base)) if raw_image is not None else None
        )
    # La vérité-terrain est lue par l'évaluation : exiger son existence dès le
    # chargement donne une erreur claire (RunSpecError) au lieu d'un OSError
    # opaque en plein run. L'image, elle, n'est pas exigée ici — certains modules
    # (precomputed) ne la lisent pas, et tesseract signale clairement son absence.
    ground_truths = tuple(
        truth.model_copy(
            update={"uri": str(validated_path(truth.uri, base, must_exist=True))}
        )
        for truth in document.ground_truths
    )
    return document.model_copy(
        update={"image_uri": image_uri, "ground_truths": ground_truths}
    )


def dump_corpus_spec(spec: CorpusSpec, path: str | Path) -> Path:
    """Écrit ``spec`` en YAML sous la clé ``corpus`` — le bloc d'un ``RunSpec``.

    **Pourquoi la clé et pas l'objet nu** : un ``RunSpec`` refuse les clés
    inconnues, donc un fichier corpus se colle tel quel dans un fichier de run,
    ou se complète de ``pipelines:`` et ``evaluation:``. Un objet nu obligerait à
    le ré-indenter à la main.

    **Chemins relatifs au fichier écrit** : l'import matérialise des images sous
    un dossier, et un chemin absolu rendrait le corpus intransportable d'une
    machine à l'autre. ``load_run_spec`` résout les relatifs contre le dossier du
    YAML — la boucle est donc fermée. Les URI **distantes** (``http``/``https``,
    corpus curé à références épinglées) passent inchangées : les réécrire n'aurait
    aucun sens.
    """
    cible = Path(path)
    base = cible.parent
    documents = [
        _relative_document(document, base) for document in spec.documents
    ]
    charge = {
        "corpus": {
            "name": spec.name,
            "documents": documents,
            **({"metadata": dict(spec.metadata)} if spec.metadata else {}),
        }
    }
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_text(
        yaml.safe_dump(charge, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return cible


def _relative_document(document: DocumentRef, base: Path) -> dict[str, object]:
    entree: dict[str, object] = {"id": document.id}
    if document.image_uri is not None:
        entree["image_uri"] = _portable_uri(document.image_uri, base)
    if document.ground_truths:
        entree["ground_truths"] = [
            {"type": truth.type.value, "uri": _portable_uri(truth.uri, base)}
            for truth in document.ground_truths
        ]
    if document.metadata:
        entree["metadata"] = dict(document.metadata)
    return entree


def _portable_uri(uri: str, base: Path) -> str:
    """Chemin local → relatif à ``base`` (POSIX) ; URI distante → inchangée."""
    if uri.startswith(("http://", "https://")):
        return uri
    chemin = Path(uri)
    try:
        return chemin.relative_to(base).as_posix()
    except ValueError:
        # Hors du dossier du YAML (l'utilisateur a choisi deux emplacements
        # sans rapport) : on garde l'absolu plutôt qu'une chaîne de « .. »
        # qui casserait au premier déplacement.
        return chemin.as_posix()


__all__ = ["RunSpecError", "dump_corpus_spec", "load_run_spec"]

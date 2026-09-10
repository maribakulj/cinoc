"""Matérialisation d'un corpus IIIF en ``CorpusSpec`` (couche 6).

Sépare **localiser** (l'adapter ``IIIFImporter`` parle IIIF) de **matérialiser**
(ici : télécharger les images sous ``dest`` validé, fabriquer le ``CorpusSpec``).
Sortie **unique** : un ``CorpusSpec`` (jamais un dict-manifeste), prêt pour un run.

Images seules → ``DocumentRef`` sans vérité-terrain : le corpus est OCR-able mais
non scoré tant qu'une GT n'est pas appariée (cf. ``adapters/corpus/iiif.py``).

``importer`` et ``download`` sont **injectables** → le chemin de matérialisation
se teste sans réseau ; le test ``live`` couvre le vrai fetch IIIF.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol
from urllib.parse import urlsplit

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus.escriptorium import DEFAULT_LAYER, EScriptoriumImporter
from cinoc.adapters.corpus.gallica import GALLICA_BASE, GallicaImporter, vue_number
from cinoc.adapters.corpus.huggingface import (
    HFPage,
    snapshot_curated_layout,
    stream_pages,
    whoami,
)
from cinoc.adapters.corpus.iiif import IIIFImage, IIIFImporter
from cinoc.app.security import PathSecurityError, validated_path
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError

logger = logging.getLogger(__name__)

#: Extensions d'image reconnues pour nommer le fichier téléchargé.
_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".jp2"})
_DEFAULT_EXT = ".jpg"

ImageFetcher = Callable[[str], "tuple[IIIFImage, ...]"]
OcrFetcher = Callable[[int], str]
#: Streame les pages d'un dataset HF conforme. Injectable (test sans ``datasets``).
HFStreamer = Callable[..., "Iterator[HFPage]"]


class Downloader(Protocol):
    """Télécharge ``url`` vers ``dest`` ; ``headers`` optionnels (auth même-hôte)."""

    def __call__(
        self, url: str, dest: Path, *, headers: dict[str, str] | None = None
    ) -> None: ...


class CorpusImportError(CinocError):
    """L'import d'un corpus distant n'a produit aucune page exploitable."""


def _image_ext(image_url: str) -> str:
    suffix = Path(urlsplit(image_url).path).suffix.lower()
    return suffix if suffix in _IMAGE_EXT else _DEFAULT_EXT


def _download_image(
    fetch_bytes: Downloader,
    image_url: str,
    doc_id: str,
    dest_dir: Path,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    """Télécharge une image sous ``dest_dir`` (chemin validé) ; renvoie l'URI local.

    ``headers`` (ex. ``Authorization``) n'est fourni que pour un média **même-hôte**
    (cf. ``import_escriptorium_corpus``) ; les imports publics (IIIF/Gallica)
    passent ``None``.
    """
    target = validated_path(f"{doc_id}{_image_ext(image_url)}", dest_dir)
    fetch_bytes(image_url, target, headers=headers)
    return str(target)


def import_iiif_corpus(
    manifest_url: str,
    dest: str | Path,
    *,
    name: str,
    limit: int | None = None,
    importer: IIIFImporter | None = None,
    download: Downloader | None = None,
) -> CorpusSpec:
    """Importe un manifeste IIIF → images téléchargées sous ``dest`` → ``CorpusSpec``.

    ``limit`` borne le nombre de pages (les premières). ``dest`` est créé au besoin ;
    chaque fichier passe par ``validated_path`` (anti-traversal).
    """
    fetch_images: ImageFetcher = (importer or IIIFImporter()).fetch_images
    fetch_bytes: Downloader = download or _http.download
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    images = fetch_images(manifest_url)
    if limit is not None:
        images = images[:limit]
    if not images:
        raise CorpusImportError(
            f"aucune image exploitable dans le manifeste {manifest_url!r}."
        )

    documents: list[DocumentRef] = []
    for index, image in enumerate(images, start=1):
        doc_id = f"page_{index:04d}"
        image_uri = _download_image(fetch_bytes, image.image_url, doc_id, dest_dir)
        documents.append(
            DocumentRef(id=doc_id, image_uri=image_uri, ground_truths=())
        )

    return CorpusSpec(
        name=name,
        documents=tuple(documents),
        metadata={"source": "iiif", "manifest_url": manifest_url},
    )


def import_escriptorium_corpus(
    base_url: str,
    token: str,
    doc_pk: int,
    dest: str | Path,
    *,
    name: str | None = None,
    layer: str = DEFAULT_LAYER,
    limit: int | None = None,
    importer: EScriptoriumImporter | None = None,
    download: Downloader | None = None,
) -> CorpusSpec:
    """Importe un document eScriptorium → corpus **scorable** sous ``dest``.

    Pour chaque page : télécharge l'image et écrit le texte de la couche ``layer``
    comme vérité-terrain (``.gt.txt`` → ``GroundTruthRef`` ``RAW_TEXT``). Une page
    sans texte reste image-seule ; une page sans image est ignorée (avertie).

    Média gardé : le jeton ``Authorization`` n'est joint au download que si le
    média est **sur le même hôte** que ``base_url`` (règle host de D-050). Un média
    servi par un autre hôte (CDN tiers) est téléchargé **sans jeton** — on ne livre
    pas le credential à un tiers (un média gardé y répondra 401, sans fuite).
    """
    imp = importer or EScriptoriumImporter(base_url, token, layer=layer)
    fetch_bytes: Downloader = download or _http.download
    base_host = urlsplit(base_url).hostname
    media_auth = {"Authorization": f"Token {token}"}
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    pages = imp.fetch_pages(doc_pk)
    if limit is not None:
        pages = pages[:limit]

    documents: list[DocumentRef] = []
    for page in pages:
        if not page.image_url:
            logger.warning("[escriptorium] part %s sans image — ignorée.", page.pk)
            continue
        doc_id = f"part_{page.pk:05d}"
        same_host = urlsplit(page.image_url).hostname == base_host
        headers = media_auth if same_host else None
        if not same_host:
            logger.warning(
                "[escriptorium] média part %s hors hôte (%s) — téléchargé sans "
                "jeton (pas de fuite vers un tiers).",
                page.pk,
                urlsplit(page.image_url).hostname,
            )
        image_uri = _download_image(
            fetch_bytes, page.image_url, doc_id, dest_dir, headers=headers
        )
        ground_truths: tuple[GroundTruthRef, ...] = ()
        if page.gt_text.strip():
            gt_target = validated_path(f"{doc_id}.gt.txt", dest_dir)
            gt_target.write_text(page.gt_text, encoding="utf-8")
            ground_truths = (
                GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt_target)),
            )
        documents.append(
            DocumentRef(id=doc_id, image_uri=image_uri, ground_truths=ground_truths)
        )

    if not documents:
        raise CorpusImportError(
            f"document eScriptorium {doc_pk} : aucune page avec image exploitable."
        )
    return CorpusSpec(
        name=name or f"escriptorium-{doc_pk}",
        documents=tuple(documents),
        metadata={
            "source": "escriptorium",
            "base_url": base_url.rstrip("/"),
            "doc_pk": str(doc_pk),
            "layer": layer,
        },
    )


def import_gallica_corpus(
    ark: str,
    dest: str | Path,
    *,
    base_url: str = GALLICA_BASE,
    name: str | None = None,
    limit: int | None = None,
    include_ocr: bool = True,
    image_importer: IIIFImporter | None = None,
    download: Downloader | None = None,
    fetch_ocr: OcrFetcher | None = None,
) -> CorpusSpec:
    """Importe un document Gallica (ARK) → images (via IIIF) + OCR Gallica optionnel.

    Les images viennent du **manifeste IIIF** Gallica ; si ``include_ocr``, l'OCR
    brut de chaque vue (``texteBrut``) est écrit comme **référence étiquetée** :
    type domaine ``REFERENCE_TEXT`` (≠ vérité-terrain manuelle) + métadonnée
    ``gt_source=gallica_ocr``. Une vue d'évaluation par défaut **ne le score pas**
    comme une GT ; seule une vue *référence* dédiée (opt-in) le compare.

    Le numéro de vue est **lu dans l'URL de l'image** (``/f{n}/``), pas déduit de la
    position : un canvas sans image sauté par le parseur IIIF décalerait sinon tout
    l'OCR (le bug ``selected_indices+1`` réintroduit). Position 1-based = repli si
    l'URL ne porte pas de ``/f{n}/``.
    """
    gallica = GallicaImporter(ark, base_url=base_url)
    fetch_bytes: Downloader = download or _http.download
    ocr_of: OcrFetcher = fetch_ocr or gallica.fetch_ocr_text
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    images = (image_importer or IIIFImporter()).fetch_images(gallica.manifest_url)
    if limit is not None:
        images = images[:limit]
    if not images:
        raise CorpusImportError(f"aucune image pour l'ARK Gallica {gallica.ark!r}.")

    documents: list[DocumentRef] = []
    has_ocr_gt = False
    for position, image in enumerate(images, start=1):
        vue = vue_number(image.image_url) or position
        doc_id = f"f{vue:04d}"
        image_uri = _download_image(fetch_bytes, image.image_url, doc_id, dest_dir)
        ground_truths: tuple[GroundTruthRef, ...] = ()
        if include_ocr:
            text = ocr_of(vue)
            if text.strip():
                gt_target = validated_path(f"{doc_id}.gallica_ocr.txt", dest_dir)
                gt_target.write_text(text, encoding="utf-8")
                ground_truths = (
                    GroundTruthRef(
                        type=ArtifactType.REFERENCE_TEXT, uri=str(gt_target)
                    ),
                )
                has_ocr_gt = True
        documents.append(
            DocumentRef(id=doc_id, image_uri=image_uri, ground_truths=ground_truths)
        )

    metadata = {
        "source": "gallica",
        "ark": gallica.ark,
        "manifest_url": gallica.manifest_url,
    }
    if has_ocr_gt:
        metadata["gt_source"] = "gallica_ocr"
    return CorpusSpec(
        name=name or f"gallica-{gallica.ark.split('/')[-1]}",
        documents=tuple(documents),
        metadata=metadata,
    )


def import_hf_corpus(
    dataset_id: str,
    dest: str | Path,
    *,
    name: str | None = None,
    split: str = "train",
    limit: int | None = None,
    stream: HFStreamer | None = None,
) -> CorpusSpec:
    """Importe un dataset **HuggingFace** (convention Cinoc) → ``CorpusSpec`` scorable.

    Streamé **page-par-page** (jamais de snapshot complet) : chaque page écrit son
    image et son texte de vérité-terrain. La GT d'un dataset Cinoc curé est une
    **vraie GT** (``GroundTruthRef`` ``RAW_TEXT``), pas une référence OCR. ``limit``
    borne le nombre de pages. ``stream`` est injectable (test sans ``datasets``).
    """
    pages = (stream or stream_pages)(dataset_id, split=split, limit=limit)
    dest_dir = Path(dest)
    dest_dir.mkdir(parents=True, exist_ok=True)

    documents: list[DocumentRef] = []
    for index, page in enumerate(pages, start=1):
        doc_id = f"page_{index:04d}"
        target = validated_path(f"{doc_id}{page.image_ext}", dest_dir)
        target.write_bytes(page.image_bytes)
        ground_truths: tuple[GroundTruthRef, ...] = ()
        if page.gt_text.strip():
            gt_target = validated_path(f"{doc_id}.gt.txt", dest_dir)
            gt_target.write_text(page.gt_text, encoding="utf-8")
            ground_truths = (
                GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt_target)),
            )
        documents.append(
            DocumentRef(id=doc_id, image_uri=str(target), ground_truths=ground_truths)
        )

    if not documents:
        raise CorpusImportError(
            f"dataset HuggingFace {dataset_id!r} (split {split!r}) : aucune page."
        )
    return CorpusSpec(
        name=name or f"hf-{dataset_id.replace('/', '-')}",
        documents=tuple(documents),
        metadata={"source": "huggingface", "dataset_id": dataset_id, "split": split},
    )


def _curated_entry(entry: object, root: Path, base_url: str | None) -> DocumentRef:
    """Une entrée ``corpus.json`` → ``DocumentRef`` (image = référence, GT = vraie).

    Image : ``base_url`` + chemin relatif si fourni — le chemin est un dérivé
    **IIIF statique** du layout (``iiif/<id>/full/…``), et ``base_url`` la racine
    ``resolve`` HF épinglée (ou un serveur IIIF d'institution) ; sinon chemin
    local du dérivé medium. La référence est matérialisée **au run** par
    l'orchestrateur. GT : ``RAW_TEXT`` sur le ``.gt.txt`` local. Chemins relatifs
    durcis (``validated_path`` rejette ``..``) — un dataset tiers hostile ne peut
    pas pointer hors du layout."""
    if not isinstance(entry, dict):
        raise CorpusImportError(f"entrée corpus.json invalide : {entry!r}")
    try:
        doc_id, image_rel, gt_rel = entry["id"], entry["image"], entry["ground_truth"]
    except (KeyError, TypeError) as exc:
        raise CorpusImportError(f"entrée corpus.json incomplète : {entry!r}") from exc
    try:
        gt_path = validated_path(str(gt_rel), root)  # rejette le path-traversal
        image_local = validated_path(str(image_rel), root)  # idem + valide la forme
    except PathSecurityError as exc:
        raise CorpusImportError(f"chemin non sûr dans corpus.json : {exc}") from exc
    image_uri = (
        f"{base_url.rstrip('/')}/{str(image_rel).lstrip('/')}"
        if base_url
        else str(image_local)
    )
    stratum = entry.get("stratum")
    return DocumentRef(
        id=str(doc_id),
        image_uri=image_uri,
        ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt_path)),),
        metadata={"stratum": str(stratum)} if stratum else {},
    )


def import_curated_corpus(
    layout_dir: str | Path,
    *,
    base_url: str | None = None,
    revision: str | None = None,
    name: str | None = None,
) -> CorpusSpec:
    """Importe un **layout dataset canonique Cinoc** → ``CorpusSpec`` scorable.

    Variante **par référence** de ``import_hf_corpus`` (même sortie, pas un format
    parallèle) : produit par ``app.dataset_standardize`` ou snapshot d'un dataset
    HF publié. L'image est une **référence** (``base_url`` + dérivé IIIF statique
    du layout — en pratique une URL ``resolve`` HF épinglée ; sinon chemin local
    du dérivé medium), matérialisée au run par l'orchestrateur ; la GT est une
    **vraie GT** ``RAW_TEXT``. ``base_url`` + ``revision`` (SHA HF) →
    reproductibilité pinnée (``RunManifest``).
    """
    root = Path(layout_dir)
    manifest_path = root / "corpus.json"
    if not manifest_path.is_file():
        raise CorpusImportError(f"layout curé sans corpus.json : {root}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CorpusImportError(f"corpus.json illisible ({root}) : {exc}") from exc
    entries = manifest.get("documents") if isinstance(manifest, dict) else None
    if not isinstance(entries, list) or not entries:
        raise CorpusImportError(f"corpus.json sans documents : {root}")

    documents = tuple(_curated_entry(e, root, base_url) for e in entries)
    corpus_meta: dict[str, str] = {"source": "curated"}
    if revision:
        corpus_meta["revision"] = revision
    licenses = manifest.get("license")
    if isinstance(licenses, dict):
        for key, value in licenses.items():
            corpus_meta[f"license_{key}"] = str(value)
    return CorpusSpec(
        name=name or str(manifest.get("name") or root.name),
        documents=documents,
        metadata=corpus_meta,
    )


#: Télécharge un layout curé HF → dossier local (au moins ``corpus.json`` + GT).
#: Injectable → l'import distant se teste sans réseau ni ``huggingface_hub``.
CuratedFetcher = Callable[[str, Path, "str | None"], Path]


def _hf_resolve_base(repo_id: str, revision: str | None) -> str:
    """Racine ``resolve`` d'un dataset HF, épinglée à ``revision`` (sinon ``main``)."""
    return f"https://huggingface.co/datasets/{repo_id}/resolve/{revision or 'main'}"


def import_curated_hf_corpus(
    repo_id: str,
    dest: str | Path,
    *,
    revision: str | None = None,
    name: str | None = None,
    fetch: CuratedFetcher | None = None,
) -> CorpusSpec:
    """Importe un **dataset curé Cinoc publié sur HF** → ``CorpusSpec`` scorable.

    Variante **distante** de ``import_curated_corpus`` : télécharge **uniquement**
    le manifeste + la GT (les images restent des références IIIF HF, épinglées à
    ``revision``), puis délègue à l'importeur local. Un corpus de référence publié
    devient ainsi sélectionnable au Banc d'essai en quelques secondes, sans
    rapatrier les images. ``fetch`` est injectable (test sans réseau).
    """
    layout_dir = (fetch or snapshot_curated_layout)(repo_id, Path(dest), revision)
    return import_curated_corpus(
        layout_dir,
        base_url=_hf_resolve_base(repo_id, revision),
        revision=revision,
        name=name,
    )


#: Variable d'environnement nommant explicitement le compte HF à interroger.
HF_AUTHOR_ENV = "CINOC_HF_AUTHOR"

#: Jetons HF reconnus, dans l'ordre de lecture : présent → le handle de
#: l'opérateur est résolu par ``whoami``, ses datasets curés apparaissent sans
#: configuration.
HF_TOKEN_ENVS = ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HUGGING_FACE_HUB_TOKEN")

#: Identifiant du Space (``owner/name``, injecté par HuggingFace). Son ``owner``
#: **est** le handle de l'opérateur → résolution pure, sans réseau.
SPACE_ID_ENV = "SPACE_ID"


def resolve_curated_author() -> str | None:
    """Compte HF dont lister les datasets curés — **zéro config** quand possible.

    Ordre : ``CINOC_HF_AUTHOR`` explicite > handle résolu d'un jeton HF
    (``whoami``, poste local connecté) > ``owner`` du ``SPACE_ID`` (sur un Space,
    le propriétaire **est** l'opérateur — pur, sans réseau). Aucun signal →
    ``None`` : on ne devine pas « vos » datasets, mais l'import manuel par
    ``repo_id`` reste offert.

    Vit en couche ``app`` et non dans un transport : « quel compte est le mien »
    est une **capacité**, et la CLI comme le web doivent y répondre pareil
    (``CLAUDE.md`` §8.4 — une capacité, une fonction, deux transports).
    """
    explicit = os.environ.get(HF_AUTHOR_ENV, "").strip()
    if explicit:
        return explicit
    for env in HF_TOKEN_ENVS:
        token = os.environ.get(env, "").strip()
        if token:
            handle = whoami(token)
            if handle:
                return handle
    space = os.environ.get(SPACE_ID_ENV, "").strip()
    if space:
        owner = space.split("/", 1)[0].strip()
        if owner:
            return owner
    return None


def materialize_corpus(
    dest: str | Path, builder: Callable[[Path], CorpusSpec]
) -> CorpusSpec:
    """Construit un corpus dans ``dest``, **atomiquement**.

    ``builder`` reçoit le dossier de destination et renvoie la ``CorpusSpec``
    matérialisée — agnostique de la source. Si le builder échoue en cours de
    route (réseau, source non conforme, annulation), le dossier **partiellement**
    matérialisé est nettoyé : pas de corpus à demi importé laissé derrière.

    Unique implémentation de cette garantie : le ``CorpusStore`` du web y délègue
    (il n'ajoute que l'allocation d'un identifiant et l'enregistrement au
    registre), la CLI l'appelle avec un dossier choisi par l'utilisateur.
    """
    dest_dir = Path(dest)
    try:
        return builder(dest_dir)
    except BaseException:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise


__all__ = [
    "HF_AUTHOR_ENV",
    "HF_TOKEN_ENVS",
    "SPACE_ID_ENV",
    "CorpusImportError",
    "import_curated_corpus",
    "import_curated_hf_corpus",
    "import_escriptorium_corpus",
    "import_gallica_corpus",
    "import_hf_corpus",
    "import_iiif_corpus",
    "materialize_corpus",
    "resolve_curated_author",
]

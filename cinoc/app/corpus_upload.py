"""Ingestion **sûre** d'un corpus depuis une archive ZIP (couche 6).

Le concept central est la **sécurité d'ingestion** : une archive
vient de l'extérieur, on la traite en supposant qu'elle est hostile.

Défenses (toutes testées) :

- **anti-traversal** : on **aplatit au basename** (aucun sous-dossier conservé)
  et on repasse chaque nom par ``validated_path`` (défense en profondeur) ;
- **anti-zip-bomb** : la taille **réellement décompressée** est plafonnée par
  fichier *et* au total (on ne fait pas confiance au ``file_size`` du header) ;
- **quotas** : taille de l'archive, nombre d'entrées, taille par fichier ;
- **dédup** : un basename en double est refusé ;
- **liste blanche d'extensions** + **signature** des images (magic bytes) ;
- **noms** restreints à un charset sûr (→ ``DocumentRef.id`` valide).

Sortie : une ``CorpusSpec`` (images appariées à leur vérité-terrain ``.txt`` par
radical) matérialisée sous ``dest`` — prête pour un run.
"""

from __future__ import annotations

import io
import re
import shutil
import threading
import uuid
import zipfile
from collections.abc import Callable
from pathlib import Path

from pydantic import ValidationError

from cinoc.app.corpus_import import materialize_corpus
from cinoc.app.security import validated_path
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError, CorpusSpecError, FormatError
from cinoc.evaluation.projectors import layout_to_text
from cinoc.formats.alto import parse_alto
from cinoc.formats.alto.layout_map import alto_to_layout
from cinoc.formats.pagexml import parse_pagexml
from cinoc.formats.pagexml.layout_map import page_to_layout

#: Quotas (généreux mais bornés) — un Space gratuit n'est pas un entrepôt.
MAX_ZIP_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 200 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ENTRIES = 1000

_IMAGE_EXT = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff"})
_GT_EXT = frozenset({".txt"})
#: Vérité-terrain au format mise-en-page : ALTO 4.x ou PAGE XML. Convertie en
#: texte d'ordre de lecture à l'ingestion (cf. ``_xml_to_text``).
_GT_XML_EXT = frozenset({".xml"})
_IMAGE_MAGIC = (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")
#: Basename sûr → garantit un ``DocumentRef.id`` valide (pas d'espace/accent/slash).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9_.\-]+$")


class CorpusUploadError(CinocError):
    """Archive rejetée (non sûre, hors quota, vide, ou mal formée)."""


def extract_corpus_zip(data: bytes, dest: Path, *, name: str) -> CorpusSpec:
    """Valide et extrait ``data`` (ZIP) sous ``dest`` → ``CorpusSpec``."""
    if len(data) > MAX_ZIP_BYTES:
        raise CorpusUploadError("archive trop volumineuse.")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CorpusUploadError("archive ZIP invalide.") from exc

    entries = [
        info
        for info in archive.infolist()
        if not info.is_dir() and not _is_macos_metadata(info.filename)
    ]
    if not entries:
        raise CorpusUploadError("archive vide.")
    if len(entries) > MAX_ENTRIES:
        raise CorpusUploadError(f"trop d'entrées (> {MAX_ENTRIES}).")

    dest.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    total = 0
    for info in entries:
        base = _safe_basename(info.filename)
        ext = Path(base).suffix.lower()
        if ext not in _IMAGE_EXT and ext not in _GT_EXT and ext not in _GT_XML_EXT:
            raise CorpusUploadError(f"extension non autorisée : {base!r}.")
        if base in written:
            raise CorpusUploadError(f"doublon de nom : {base!r}.")
        payload = _read_capped(archive, info)
        total += len(payload)
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise CorpusUploadError("archive trop volumineuse décompressée (bombe ?).")
        if ext in _IMAGE_EXT and not payload.startswith(_IMAGE_MAGIC):
            raise CorpusUploadError(f"image non reconnue : {base!r}.")
        target = validated_path(base, dest)  # défense en profondeur
        target.write_bytes(payload)
        written[base] = target

    # Les radicaux d'image deviennent des `DocumentRef.id` et le nom de fichier
    # devient le nom de corpus : deux images de même radical (`a.png`+`a.jpg`),
    # un radical invalide (`..`) ou un nom trop long font lever le `domain`
    # (`CorpusSpecError` / `ValidationError`). On les **traduit** en rejet propre
    # (→ 422), jamais en 500 : une archive « sûre mais bancale » reste une entrée.
    try:
        documents = _pair_documents(written)
        if not documents:
            raise CorpusUploadError("aucune image dans l'archive.")
        return CorpusSpec(name=name, documents=documents)
    except (CorpusSpecError, ValidationError) as exc:
        raise CorpusUploadError(f"corpus invalide : {exc}") from exc


def _is_macos_metadata(name: str) -> bool:
    """Entrées parasites des ZIP créés sous macOS, à ignorer silencieusement.

    AppleDouble (``._fichier`` — fork de ressources, jamais une vraie image) et
    le dossier ``__MACOSX/``. Les filtrer évite un rejet « image non reconnue »
    sur des sidecars que l'utilisateur n'a jamais voulu déposer.
    """
    parts = name.split("/")
    return "__MACOSX" in parts or parts[-1].startswith("._")


def _safe_basename(raw_name: str) -> str:
    """Basename validé : pas de traversal, charset sûr (→ id de document valide)."""
    if raw_name.startswith("/") or "\\" in raw_name or ".." in Path(raw_name).parts:
        raise CorpusUploadError(f"entrée non sûre : {raw_name!r}.")
    base = Path(raw_name).name
    if not base or not _SAFE_NAME.match(base):
        raise CorpusUploadError(f"nom de fichier non sûr : {raw_name!r}.")
    return base


def _read_capped(archive: zipfile.ZipFile, info: zipfile.ZipInfo) -> bytes:
    """Lit l'entrée avec un **plafond dur** (indépendant du ``file_size`` annoncé)."""
    with archive.open(info) as src:
        payload = src.read(MAX_FILE_BYTES + 1)
    if len(payload) > MAX_FILE_BYTES:
        raise CorpusUploadError(f"fichier trop volumineux : {info.filename!r}.")
    return payload


def _pair_documents(written: dict[str, Path]) -> tuple[DocumentRef, ...]:
    """Apparie chaque image à sa vérité-terrain par radical (``_ground_truth_for``)."""
    documents: list[DocumentRef] = []
    for base, path in sorted(written.items()):
        if Path(base).suffix.lower() not in _IMAGE_EXT:
            continue
        stem = Path(base).stem
        documents.append(
            DocumentRef(
                id=stem,
                image_uri=str(path),
                ground_truths=_ground_truth_for(stem, written),
            )
        )
    return tuple(documents)


def _ground_truth_for(
    stem: str, written: dict[str, Path]
) -> tuple[GroundTruthRef, ...]:
    """Vérité-terrain ``RAW_TEXT`` d'un radical, par priorité de format.

    1. ``.txt`` manuel (``<rad>.gt.txt`` puis ``<rad>.txt``) — chemin direct.
    2. À défaut, ALTO/PAGE (``<rad>.gt.xml`` puis ``<rad>.xml``) : texte d'ordre
       de lecture extrait par ``layout_to_text`` (la **projection même** du
       scoring), matérialisé en ``<rad>.gt.txt`` dérivé → le GT reste un
       ``RAW_TEXT``, un seul chemin d'évaluation, déterministe.
    3. Sinon ``()`` : le run reste exécutable, simplement non scoré.
    """
    txt = next((c for c in (f"{stem}.gt.txt", f"{stem}.txt") if c in written), None)
    if txt is not None:
        return (GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(written[txt])),)
    xml = next((c for c in (f"{stem}.gt.xml", f"{stem}.xml") if c in written), None)
    if xml is None:
        return ()
    derived = written[xml].with_name(f"{stem}.gt.txt")
    derived.write_text(_xml_to_text(written[xml]), encoding="utf-8")
    return (GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(derived)),)


def _xml_to_text(path: Path) -> str:
    """Texte d'ordre de lecture d'une vérité-terrain ALTO/PAGE.

    ALTO ou PAGE selon le marqueur de racine (même heuristique que l'évaluation).
    Le parse passe par la couche 2 (``safe_parse_xml`` durci : pas de XXE/DTD).
    Parse en échec ou texte vide → rejet propre (``CorpusUploadError`` → 422),
    jamais un 500.
    """
    data = path.read_bytes()
    head = data[:4096].lower()
    is_page = b"pcgts" in head or b"pagecontent" in head
    try:
        layout = (
            page_to_layout(parse_pagexml(data))
            if is_page
            else alto_to_layout(parse_alto(data))
        )
    except (ValueError, FormatError) as exc:
        kind = "PAGE" if is_page else "ALTO"
        raise CorpusUploadError(
            f"vérité-terrain {kind} illisible : {path.name!r} ({exc})."
        ) from exc
    text = layout_to_text(layout, {})
    if not isinstance(text, str) or not text.strip():
        raise CorpusUploadError(
            f"vérité-terrain XML sans texte exploitable : {path.name!r}."
        )
    return text


class CorpusStore:
    """Registre **en mémoire** des corpus uploadés (id → ``CorpusSpec`` + dossier).

    Le contenu vit sous ``base_dir`` (éphémère sur HF — acceptable : ce sont des
    **entrées** de travail ; les *résultats* sont, eux, publiés vers un dépôt distant).
    """

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._corpora: dict[str, CorpusSpec] = {}
        self._lock = threading.Lock()

    def save(self, name: str, data: bytes) -> tuple[str, CorpusSpec]:
        """Extrait l'archive dans un dossier neuf et enregistre la ``CorpusSpec``."""
        corpus_id = uuid.uuid4().hex
        spec = extract_corpus_zip(data, self._base / corpus_id, name=name or corpus_id)
        with self._lock:
            self._corpora[corpus_id] = spec
        return corpus_id, spec

    def materialize(
        self, builder: Callable[[Path], CorpusSpec]
    ) -> tuple[str, CorpusSpec]:
        """Enregistre un corpus **construit** dans un dossier neuf sous ``base_dir``.

        ``builder`` reçoit le dossier de destination et renvoie la ``CorpusSpec``
        matérialisée — agnostique de la source (importeurs IIIF/eScriptorium/
        Gallica…). Le store reste un **registre** : il alloue l'id et le dossier,
        sans connaître le format d'entrée.

        **Atomicité (F3)** : déléguée à ``materialize_corpus`` — un builder qui
        échoue en cours de route ne laisse pas de dossier à demi importé, et rien
        n'est enregistré. Le store n'ajoute que ce qui lui est propre :
        l'allocation d'un identifiant et l'inscription au registre. La garantie,
        elle, n'a **qu'une** implémentation, partagée avec la CLI.
        """
        corpus_id = uuid.uuid4().hex
        dest = self._base / corpus_id
        spec = materialize_corpus(dest, builder)
        with self._lock:
            self._corpora[corpus_id] = spec
        return corpus_id, spec

    def get(self, corpus_id: str) -> CorpusSpec | None:
        with self._lock:
            return self._corpora.get(corpus_id)

    def list_corpora(self) -> list[tuple[str, CorpusSpec]]:
        """Corpus enregistrés ``(id, spec)``, triés par nom puis id (ordre stable)."""
        with self._lock:
            items = list(self._corpora.items())
        return sorted(items, key=lambda kv: (kv[1].name, kv[0]))

    def delete(self, corpus_id: str) -> bool:
        """Supprime un corpus (registre **et** dossier). Vrai s'il existait."""
        with self._lock:
            existed = self._corpora.pop(corpus_id, None) is not None
        if existed:
            shutil.rmtree(self._base / corpus_id, ignore_errors=True)
        return existed


__all__ = [
    "MAX_ZIP_BYTES",
    "CorpusStore",
    "CorpusUploadError",
    "extract_corpus_zip",
]

"""``Artifact`` et ``ArtifactType``.

Toute sortie d'une étape de pipeline est un artefact traçable :
identifiant stable, type explicite, hash du contenu, provenance.

Distinctions clés pour les vues d'évaluation :

- ``RAW_TEXT`` vs ``CORRECTED_TEXT`` — même structure (string), contrats
  différents : seul le second a été modifié par un modèle après l'OCR.
- ``LAYOUT`` vs ``CANONICAL_DOCUMENT`` — ``LAYOUT`` porte la structure
  spatiale neutre (régions/lignes/mots/géométrie, payload
  ``CanonicalLayout``) ; ``CANONICAL_DOCUMENT`` est un contenu textuel
  riche sans coordonnées (markdown/JSON de VLM).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ArtifactType(StrEnum):
    """Type d'un artefact produit ou consommé par une étape de pipeline.

    Convention : ``UPPER_SNAKE_CASE`` pour le nom Python,
    ``lower_snake_case`` pour la valeur sérialisée (YAML de pipeline,
    exports JSON).
    """

    #: Image source (PNG, TIFF, JPEG). Entrée typique d'un OCR.
    IMAGE = "image"

    #: Texte brut produit par un OCR (avant correction LLM).
    RAW_TEXT = "raw_text"

    #: Texte corrigé par un LLM ou un module de post-correction.
    CORRECTED_TEXT = "corrected_text"

    #: Texte de **référence** (ex. OCR pré-existant fourni par une source :
    #: ``texteBrut`` Gallica) — **distinct d'une vérité-terrain manuelle**. Sert
    #: de référence de comparaison *étiquetée* : un score contre un
    #: ``REFERENCE_TEXT`` mesure l'**accord avec un autre OCR**, pas l'exactitude.
    #: N'est jamais résolu par une vue d'évaluation par défaut (opt-in explicite
    #: via une projection ``reference_text → raw_text``).
    REFERENCE_TEXT = "reference_text"

    #: ALTO XML 4.x (lignes, mots, coordonnées, ordre de lecture).
    ALTO_XML = "alto_xml"

    #: PAGE XML (PRIMA / Transkribus).
    PAGE_XML = "page_xml"

    #: Représentation canonique textuelle riche sans coordonnées (sortie
    #: VLM : markdown, JSON canonique).
    CANONICAL_DOCUMENT = "canonical_document"

    #: Structure de mise en page neutre (ALTO/PAGE unifiés) : pages,
    #: régions, lignes, mots, géométrie. Payload = ``CanonicalLayout``.
    #: Une sortie de segmentation est un ``LAYOUT`` à régions sans lignes.
    LAYOUT = "layout"

    #: Liste d'entités nommées (PER, LOC, ORG, DATE, MISC…).
    ENTITIES = "entities"

    #: Liste ordonnée d'IDs de régions définissant l'ordre de lecture.
    READING_ORDER = "reading_order"

    #: Alignement entre deux artefacts (ex. ``RAW_TEXT`` → ``CORRECTED_TEXT``).
    ALIGNMENT = "alignment"

    #: Confidences OCR au niveau token (sidecar JSON).
    CONFIDENCES = "confidences"

    #: **Réponse native brute** d'un moteur distant (sidecar JSON) : le corps que
    #: l'API a rendu, avant toute conversion en texte — sérialisé par
    #: :func:`native_json_bytes` (clés triées), sans en-tête, URL ni clé.
    #:
    #: Le texte n'est qu'une **lecture** de cette réponse ; une autre lecture
    #: (un meilleur protocole, une projection vers ``LAYOUT``) se refait depuis
    #: le sidecar sans re-payer l'appel. Une étape qui appelle plusieurs fois par
    #: page le dit par une enveloppe : ``{"regions": [{"region_id", "response"}]}``
    #: pour un fan-out (ordre de lecture), ``{"responses": [...]}`` pour la
    #: correction structurée (ordre d'appel). **Jamais noté** : une vue qui le
    #: déclarerait candidat est refusée (``EvaluationView``). Ne voyage pas dans
    #: le ``RunResult`` ; il vit dans le dossier d'artefacts du run
    #: (``RunManifest.artifacts_dir``) quand il en a un.
    NATIVE_JSON = "native_json"

    #: **Décisions ligne à ligne** d'une étape de post-correction : ce qu'elle a
    #: changé, ce qu'elle a refusé de changer, et **pourquoi**. Sidecar JSON.
    #:
    #: Un correcteur qui rend un texte ne dit pas s'il a délibérément laissé une
    #: ligne intacte ou s'il n'a rien trouvé — deux situations que rien ne
    #: distingue une fois le texte écrit. Ce type existe pour porter cette
    #: différence jusqu'au rapport, faute de quoi elle est calculée puis perdue.
    DECISIONS = "decisions"

    @classmethod
    def _missing_(cls, value: object) -> ArtifactType | None:
        """Accepte les chaînes courtes ``"text"``/``"alto"``/``"page"`` en
        plus des valeurs canoniques (commodité pour les specs YAML)."""
        short_map: dict[str, ArtifactType] = {
            "text": cls.RAW_TEXT,
            "alto": cls.ALTO_XML,
            "page": cls.PAGE_XML,
        }
        if not isinstance(value, str):
            return None
        return short_map.get(value)


def compute_content_hash(payload: bytes) -> str:
    """SHA-256 hex (64 chars) d'un payload binaire.

    Helper exposé au domain pour que les adapters calculent un hash
    compatible avec ``Artifact.content_hash``.
    """
    return hashlib.sha256(payload).hexdigest()


def native_json_bytes(response: object) -> bytes:
    """Forme **canonique** d'un payload ``NATIVE_JSON`` : JSON UTF-8, clés triées.

    Une seule sérialisation pour tous les producteurs (adaptateurs, fan-out) :
    deux réponses égales donnent les mêmes octets, donc le même ``content_hash``.
    ``TypeError``/``ValueError`` si ``response`` n'est pas une valeur JSON.
    """
    return json.dumps(
        response,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


# Identifiant stable et filesystem-safe (utilisable comme nom de fichier
# dans un store) sans format trop restrictif.
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-:/]+$")


class Artifact(BaseModel):
    """Une sortie traçable d'une étape de pipeline.

    Immuable (``frozen=True``) : pour « modifier » un artefact, une étape
    en produit un nouveau. Sérialisation déterministe
    (``model_dump_json()`` stable) — indispensable pour le cache.

    Attributs
    ---------
    id:
        Identifiant unique dans le contexte d'un run. Convention :
        ``"<doc_id>:<step>:<type>"`` (le caller est libre tant que c'est
        unique et matche ``_ID_RE``).
    document_id:
        ``DocumentRef.id`` du document auquel l'artefact appartient.
    type:
        Type de l'artefact.
    uri:
        Chemin/URI vers le contenu. ``None`` si stocké inline.
    content_hash:
        SHA-256 hex (64 chars). ``None`` seulement pour les artefacts
        initiaux fournis par l'utilisateur ; immuable une fois calculé.
    produced_by_step:
        Nom de l'étape qui a produit l'artefact. ``None`` pour les
        artefacts initiaux.
    region_id:
        Identifiant de la région d'origine quand l'artefact est rattaché
        à un bloc (fan-out par bloc). ``None`` = artefact au niveau page.
    provenance:
        ``ProvenanceRecord`` (``code_version`` + ``parameters_hash``).
        ``None`` pour les artefacts initiaux.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1, max_length=512)
    document_id: str = Field(min_length=1, max_length=256)
    type: ArtifactType
    uri: str | None = Field(default=None, max_length=2048)
    content_hash: str | None = Field(default=None, min_length=64, max_length=64)
    produced_by_step: str | None = Field(default=None, max_length=256)
    region_id: str | None = Field(default=None, max_length=256)
    provenance: ProvenanceRecord | None = Field(default=None)

    @field_validator("id", "document_id")
    @classmethod
    def _validate_filesystem_safe_id(cls, v: str) -> str:
        if not _ID_RE.match(v):
            from cinoc.domain.errors import ArtifactValidationError

            raise ArtifactValidationError(
                f"id invalide : {v!r}. Doit matcher {_ID_RE.pattern!r} "
                "(alphanum + ``_.-:/``)."
            )
        return v

    @field_validator("content_hash")
    @classmethod
    def _validate_hex_hash(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            int(v, 16)
        except ValueError:
            from cinoc.domain.errors import ArtifactValidationError

            raise ArtifactValidationError(
                f"content_hash doit être hex SHA-256 64 chars : {v!r}"
            ) from None
        return v.lower()


# Forward reference pour ``provenance``.
from cinoc.domain.provenance import ProvenanceRecord  # noqa: E402

Artifact.model_rebuild()


#: Sorties d'une exécution **étape par étape** : ``{id d'étape: {type: artefact}}``,
#: dans l'**ordre d'exécution** (les entrées initiales d'abord, sous
#: ``INITIAL_STEP_ID``). Deux étapes du même type y restent distinctes — c'est
#: ce qui permet de noter une étape intermédiaire.
StepArtifacts = Mapping[str, Mapping[ArtifactType, Artifact]]


def latest_by_type(by_step: StepArtifacts) -> dict[ArtifactType, Artifact]:
    """Le **pool** : dernier artefact de chaque type, dans l'ordre d'exécution.

    Ce n'est pas une seconde structure, mais une lecture de ``by_step`` : celle
    qu'attend une étape sans ``inputs_from`` (« la version la plus récente de
    chaque type ») et un consommateur qui ne veut que la sortie finale (export
    ALTO, JSONL HIPE).
    """
    pool: dict[ArtifactType, Artifact] = {}
    for outputs in by_step.values():
        pool.update(outputs)
    return pool


__all__ = [
    "Artifact",
    "ArtifactType",
    "StepArtifacts",
    "compute_content_hash",
    "latest_by_type",
    "native_json_bytes",
]

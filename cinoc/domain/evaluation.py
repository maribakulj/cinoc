"""``MetricSpec``, ``EvaluationView``, ``EvaluationSpec``.

Comparer des pipelines hétérogènes en projetant leurs sorties vers une
vue d'évaluation explicite. On ne compare jamais directement un OCR brut
et une sortie ALTO reconstruite : on compare leur projection dans une vue
commune, et le rapport explicite ce que la vue ignore.

- ``MetricSpec`` — déclare une métrique (nom + signature de types +
  catégorie + unité). **Purement déclaratif** : pas de callable.
  L'association nom → fonction se fait dans le registre runtime (couche
  evaluation), pas ici.
- ``EvaluationView`` — déclare une vue (candidats + projection + métriques
  + dimensions ignorées).
- ``EvaluationSpec`` — container de N vues.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    field_serializer,
    field_validator,
    model_serializer,
)

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.errors import CinocError
from cinoc.domain.projection import ProjectionSpec

#: Profil de normalisation d'une vue qui n'en nomme aucun (D-271, D-285) :
#: NFC, invisibles retirés, **tout blanc** — saut de ligne compris — réduit à une
#: espace. Le nom vit ici parce que le champ en a besoin ; le profil lui-même
#: est une donnée de la couche ``formats`` (``NORMALIZATION_PROFILES``), qui
#: vérifie qu'il existe. La comparaison **brute** se demande explicitement :
#: ``normalization_profile: null``.
DEFAULT_NORMALIZATION_PROFILE = "flat_text"


class MetricCategory(StrEnum):
    """Validité qu'une métrique peut revendiquer (D-289).

    - ``ESTABLISHED`` — conforme à une référence **nommée** (outil ou
      publication), dont un oracle vérifie le calcul quand il est exécutable ;
    - ``ADAPTED`` — variante justifiée d'une référence nommée (repli,
      tolérance, appariement propre) : la variante est dite à la fiche ;
    - ``EXPLORATORY`` — construction de Cinoc sans référence nommée.

    Seules les établies entrent au classement et aux tests de significativité ;
    une exploratoire n'est pas fausse, elle n'a pas encore la validité qu'un
    classement lui prêterait.
    """

    ESTABLISHED = "established"
    ADAPTED = "adapted"
    EXPLORATORY = "exploratory"


class MetricUnit(StrEnum):
    """Ce que dénombre le **poids** d'une métrique — le dénominateur de son
    agrégat micro (D-016) : un CER compte des caractères de référence, un WER
    des mots. C'est l'unité que la fiche du glossaire doit nommer."""

    CHARACTER = "character"
    WORD = "word"
    CHARACTER_TRIGRAM = "character_trigram"
    LINE = "line"
    REGION = "region"
    ENTITY = "entity"
    NUMERIC_SEQUENCE = "numeric_sequence"


class MetricSpec(BaseModel):
    """Description déclarative d'une métrique enregistrable.

    Attributs
    ---------
    name:
        Identifiant unique dans un registre.
    input_types:
        Tuple ``(reference_type, hypothesis_type)`` ; le registre
        sélectionne les métriques applicables à une jonction par cette
        signature.
    higher_is_better:
        ``True`` pour les métriques de qualité (F1, recall), ``False``
        pour les métriques d'erreur (CER, WER).
    tags:
        Étiquettes libres pour grouper (``"text"``, ``"structure"``…).
    category:
        :class:`MetricCategory` — **requise** : une métrique sans catégorie
        n'est pas enregistrable (D-289).
    unit:
        :class:`MetricUnit` — **requise** : ce que compte le poids.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    input_types: tuple[ArtifactType, ArtifactType]
    description: str = ""
    higher_is_better: bool = False
    tags: frozenset[str] = Field(default_factory=frozenset)
    category: MetricCategory
    unit: MetricUnit

    @field_serializer("tags", when_used="json")
    def _tags_sorted(self, value: frozenset[str]) -> list[str]:
        # Un ``frozenset`` de chaînes s'itère selon le hachage, randomisé d'un
        # processus à l'autre : trié, le JSON est le même à chaque run (§12).
        return sorted(value)


class EvaluationView(BaseModel):
    """Une vue d'évaluation = une lentille pour comparer des pipelines.

    Répond à : « lequel des pipelines produit la meilleure sortie sous cet
    angle ? » Un pipeline ne produisant aucun artefact dans
    ``candidate_types`` est omis explicitement (pas de score factice).

    ``projection`` s'applique à tous les candidats ;
    ``projections_by_source_type`` permet une projection conditionnelle
    par type source. ``normalization_profile`` nomme le profil appliqué des
    deux côtés : omis, c'est :data:`DEFAULT_NORMALIZATION_PROFILE` (NFC,
    invisibles retirés, blancs écrasés) ; ``None`` **explicite** demande la
    comparaison brute (aucune normalisation). Le nom est toujours écrit dans
    le ``RunResult`` : un lecteur sait quelle convention a produit le chiffre.
    ``char_exclude`` filtre des caractères APRÈS
    ``normalization_profile``. ``ignored_dimensions`` est affiché pour
    signaler ce que la comparaison ne dit pas.

    ``target_step`` nomme l'**étape** dont la sortie est notée. ``None``
    (défaut) : l'étape la plus aval qui produit un type candidat — la règle
    d'avant, devenue explicite. Nommer une étape intermédiaire note un préfixe
    du pipeline **dans le même run**, sans le réexécuter (ablation : OCR seul /
    OCR + correction). Une étape inconnue d'un pipeline du run est refusée au
    chargement de la spec (``RunSpec``). Absente du JSON quand elle vaut
    ``None`` : le résultat d'une spec sans cible reste celui d'avant.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    candidate_types: frozenset[ArtifactType] = Field(...)
    projection: ProjectionSpec | None = None
    projections_by_source_type: dict[ArtifactType, ProjectionSpec] = Field(
        default_factory=dict,
    )
    normalization_profile: str | None = Field(
        default=DEFAULT_NORMALIZATION_PROFILE, max_length=128
    )
    char_exclude: str | None = Field(default=None, max_length=512)
    metric_names: tuple[str, ...] = Field(default_factory=tuple)
    ignored_dimensions: tuple[str, ...] = Field(default_factory=tuple)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    target_step: str | None = Field(default=None, min_length=1, max_length=128)

    @field_validator("candidate_types")
    @classmethod
    def _native_response_is_never_scored(
        cls, value: frozenset[ArtifactType]
    ) -> frozenset[ArtifactType]:
        """``NATIVE_JSON`` n'est pas une transcription : il n'est jamais candidat.

        C'est la réponse brute d'une API, dont le texte noté n'est qu'une
        lecture ; la noter comparerait du JSON à une vérité terrain. Le refus
        vaut au chargement, avant qu'une vue vide ne coûte un run.
        """
        if ArtifactType.NATIVE_JSON in value:
            raise CinocError(
                "'candidate_types' ne peut pas contenir 'native_json' : la réponse "
                "native d'un moteur n'est pas une sortie à noter (c'est sa "
                "lecture en texte qui l'est)."
            )
        return value

    @field_serializer("candidate_types", when_used="json")
    def _candidates_sorted(
        self, value: frozenset[ArtifactType]
    ) -> list[ArtifactType]:
        """Triés par valeur : l'ordre d'un ``frozenset`` suit le hachage des
        chaînes, randomisé par processus — deux runs de la même spec sortaient
        ``[raw_text, corrected_text]`` puis l'inverse (invariant §12)."""
        return sorted(value, key=lambda t: t.value)

    @model_serializer(mode="wrap")
    def _omit_default_target(
        self, handler: SerializerFunctionWrapHandler
    ) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.target_step is None:
            data.pop("target_step", None)
        return data

    def accepts(self, artifact_type: ArtifactType) -> bool:
        """Vrai si cette vue peut consommer un artefact du type donné."""
        return artifact_type in self.candidate_types

    def projection_for(
        self, source_type: ArtifactType,
    ) -> ProjectionSpec | None:
        """Projection à appliquer pour un artefact source donné.

        1. ``projections_by_source_type[source_type]`` si présent ;
        2. ``projection`` si son ``source_type`` matche ;
        3. ``None`` (artefact comparé tel quel).
        """
        if source_type in self.projections_by_source_type:
            return self.projections_by_source_type[source_type]
        if (
            self.projection is not None
            and self.projection.source_type == source_type
        ):
            return self.projection
        return None


#: Ce que devient une unité en échec dans les agrégats (cf. ``EvaluationSpec``).
FailurePolicy = Literal["exclude", "max_error"]


class EvaluationSpec(BaseModel):
    """Container de N ``EvaluationView`` qu'un benchmark applique.

    ``analyses`` déclare les **analyses** voulues, par leur ``kind`` — un
    registre les résout, comme ``metric_names`` pour les métriques.

    ===================  ==========================================
    valeur               effet
    ===================  ==========================================
    ``None`` (défaut)    **mode rapide** : les métriques déclarées
                         et leurs tests inter-moteurs (payload
                         ``inference`` sans IC bootstrap), rien d'autre
    ``"toutes"``         mode détaillé : toutes les analyses
    ``("diagnostics",)`` seulement celles nommées
    ``()``               aucune (identique au défaut, explicite)
    ===================  ==========================================

    **Pourquoi le défaut est le mode rapide.** Une spec qui déclare six
    métriques faisait produire **trente-quatre analyses**, et celles-ci
    pesaient 98,6 % du temps : 13 secondes de métriques contre 15 minutes
    d'analyses, sur trente unités déjà exécutées. Produire par défaut ce que
    personne n'a demandé, puis offrir le moyen de l'éteindre, est l'ordre
    inverse du bon — d'autant que le rapport qui en résulte pèse des dizaines
    de méga-octets et devient illisible.

    Le mode détaillé reste **entier** : c'est un choix au lancement, pas une
    version dégradée. Les **tests** (Wilcoxon/Friedman, Holm, Nemenyi) ne sont
    pas une option : leur coût est négligeable, et un rapport qui se tait sur
    la significativité laisse lire un écart comme un verdict. L'analyse
    ``inference`` ajoute l'IC bootstrap, qui, lui, coûte.

    ``failure_policy`` dit ce que devient une unité **en échec** (aucune sortie)
    dans les agrégats. ``"exclude"`` (défaut) : elle sort de la moyenne, et
    chaque agrégat porte « n notés / n attendus » pour le montrer.
    ``"max_error"`` : elle est notée à l'erreur maximale — 1 pour un taux
    d'erreur, 0 pour un score —, pondérée par sa référence, comme une page
    rendue vide. Ni l'une ni l'autre ne touche aux cas « vérité terrain absente »
    ou « métrique inapplicable », qui restent non notés (``None``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    views: tuple[EvaluationView, ...] = Field(default_factory=tuple)
    analyses: tuple[str, ...] | Literal["toutes"] | None = None
    failure_policy: FailurePolicy = "exclude"


__all__ = [
    "DEFAULT_NORMALIZATION_PROFILE",
    "EvaluationSpec",
    "EvaluationView",
    "FailurePolicy",
    "MetricCategory",
    "MetricSpec",
    "MetricUnit",
]

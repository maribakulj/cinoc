"""Canal « analyses » du ``RunResult`` — résultats **non scalaires** (couche 3).

Contrat E2 (``PLAN_PARITE.md`` §1) : les scalaires ``MetricScore`` restent la
seule monnaie de classement/historique ; ``analyses`` porte le **contexte
structuré** (inférentiel, diagnostics…), calculé dans ``evaluation/`` et
seulement **lu** par les rapports. Chaque famille ajoute son payload Pydantic
figé ici, discriminé par ``kind``, dans le même commit que son calcul et son
consommateur (garde-fou « pas de consommateur = supprimé »).

Familles : ``inference`` (verdict statistique corrigé multi-comparaisons),
``economics`` (coûts, débit, Pareto), ``diagnostics`` (confusions, pires
lignes, documents difficiles), ``calibration`` (ECE/MCE), ``taxonomy``
(classes d'erreurs par règles pures — quelles erreurs, pas seulement combien).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class PipelineRank(BaseModel):
    """Rang moyen d'un pipeline sur les cas complets (petit = meilleur)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    mean_rank: float = Field(ge=1)


class PipelineInterval(BaseModel):
    """IC bootstrap (percentile, graine fixe) de la moyenne d'un pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    mean: float
    lower: float
    upper: float
    #: Nombre de documents valides du pipeline (marginal, ≠ cas complets).
    n_documents: int = Field(ge=1)


class PairwiseDifference(BaseModel):
    """Verdict Nemenyi d'une paire : écart de rangs vs distance critique."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(min_length=1, max_length=128)
    b: str = Field(min_length=1, max_length=128)
    rank_gap: float = Field(ge=0)
    significant: bool


class InferencePayload(BaseModel):
    """Inférentiel d'une (vue × métrique) : rangs, Nemenyi, IC bootstrap.

    ``critical_distance``/``tied_groups``/``pairwise`` ne sont renseignés qu'à
    **k ≥ 3 pipelines** (le post-hoc corrige les comparaisons multiples après
    Friedman) ; à k = 2 le scalaire ``significance_p`` (Wilcoxon) reste le
    verdict, et seuls rangs + intervalles sont portés.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["inference"] = "inference"
    metric: str = Field(min_length=1, max_length=128)
    alpha: float = Field(gt=0, lt=1)
    #: Cas complets (documents où tous les pipelines ont une valeur).
    n_documents: int = Field(ge=0)
    critical_distance: float | None = Field(default=None, ge=0)
    q_alpha: float | None = Field(default=None, ge=0)
    #: Transparence : q_α extrapolé au-delà de la table (k > 50).
    q_alpha_extrapolated: bool = False
    #: Triés par (rang, pipeline) croissants — ordre déterministe.
    mean_ranks: tuple[PipelineRank, ...] = ()
    #: Groupes maximaux d'indiscernables (fenêtre ≤ CD sur les rangs triés).
    tied_groups: tuple[tuple[str, ...], ...] = ()
    #: Paires triées (a < b par nom).
    pairwise: tuple[PairwiseDifference, ...] = ()
    #: Triés par pipeline — ordre déterministe.
    intervals: tuple[PipelineInterval, ...] = ()


class PipelineEconomics(BaseModel):
    """Ressources et coût estimé d'un pipeline sur le run (par vue : CER joint).

    ``cost_eur`` est **indicatif** : temps machine (durée mesurée × taux
    horaire) + jetons cloud au tarif de la table ; ``None`` si un étage cloud
    a un modèle absent de la table (jamais un zéro silencieux — ``basis`` le
    dit). Tous les nombres sont des fonctions auditables des mesures E1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_documents: int = Field(ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    tokens_in: int | None = Field(default=None, ge=0)
    tokens_out: int | None = Field(default=None, ge=0)
    cost_eur: float | None = Field(default=None, ge=0)
    #: « machine » · « machine+jetons » · « tarif inconnu : <kind:model> ».
    basis: str = Field(min_length=1, max_length=256)
    cer: float | None = None
    #: Erreurs estimées sur la vue : Σ (cer_doc × poids_doc) — auditable.
    estimated_errors: float | None = Field(default=None, ge=0)
    pages_per_hour: float | None = Field(default=None, ge=0)
    #: Débit corrigé du temps de correction des erreurs résiduelles.
    pages_per_hour_effective: float | None = Field(default=None, ge=0)


class MarginalCost(BaseModel):
    """Coût marginal d'un pipeline vs le moins cher : € par erreur évitée."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    baseline: str = Field(min_length=1, max_length=128)
    cost_delta_eur: float
    errors_avoided: float
    #: ``None`` si le surcoût n'évite aucune erreur (dominé).
    eur_per_avoided_error: float | None = Field(default=None, ge=0)


class EconomicsPayload(BaseModel):
    """Économie d'un run sous une vue : coûts, débits, fronts de Pareto.

    La péremption de la table de tarifs est évaluée contre ``completed_at``
    du manifeste (déterministe — pas d'horloge au rendu).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["economics"] = "economics"
    #: Axe qualité des fronts de Pareto (la métrique phare de la vue).
    metric: str = Field(min_length=1, max_length=128)
    currency: str = Field(min_length=1, max_length=8)
    hourly_rate_eur: float = Field(ge=0)
    time_per_error_seconds: float = Field(ge=0)
    pricing_valid_until: str = Field(min_length=1, max_length=32)
    pricing_stale: bool
    pipelines: tuple[PipelineEconomics, ...] = ()
    #: Non-dominés sur (métrique, coût) puis (métrique, durée) — tri stable.
    pareto_cost: tuple[str, ...] = ()
    pareto_speed: tuple[str, ...] = ()
    marginal: tuple[MarginalCost, ...] = ()


class CharConfusion(BaseModel):
    """Substitution récurrente : caractère attendu → caractère produit."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    expected: str = Field(min_length=1, max_length=8)
    observed: str = Field(min_length=1, max_length=8)
    count: int = Field(ge=1)


class PipelineConfusions(BaseModel):
    """Top des confusions d'un pipeline sur le corpus (tri : -count, paire)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    pairs: tuple[CharConfusion, ...] = ()


class WorstLine(BaseModel):
    """Une des pires lignes du corpus : où ça casse, texte à l'appui.

    Les extraits sont **verbatim** (tronqués) des représentations normalisées
    déjà chargées pour le scoring — aucun re-calcul au rendu.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=256)
    line_index: int = Field(ge=0)
    cer: float = Field(ge=0)
    reference: str = Field(max_length=160)
    hypothesis: str = Field(max_length=160)


class HardDocument(BaseModel):
    """Document le plus difficile : CER moyen sur les pipelines scorés."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    mean_cer: float = Field(ge=0)
    n_pipelines: int = Field(ge=1)


class DiagnosticsPayload(BaseModel):
    """Diagnostic d'erreurs d'une vue : confusions, pires lignes, difficulté."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["diagnostics"] = "diagnostics"
    metric: str = Field(min_length=1, max_length=128)
    confusions: tuple[PipelineConfusions, ...] = ()
    worst_lines: tuple[WorstLine, ...] = ()
    hardest_documents: tuple[HardDocument, ...] = ()


class CalibrationBin(BaseModel):
    """Bin de fiabilité : confiance moyenne vs exactitude observée."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lower: float = Field(ge=0, le=1)
    upper: float = Field(ge=0, le=1)
    mean_confidence: float = Field(ge=0, le=1)
    accuracy: float = Field(ge=0, le=1)
    count: int = Field(ge=1)


class PipelineCalibration(BaseModel):
    """Calibration des confidences d'un pipeline sur le corpus.

    ECE = Σ (n_b/N)·|acc_b − conf_b| ; MCE = max |acc_b − conf_b| sur les bins
    non vides. « Correct » = le mot du jeton apparaît (multi-ensemble, exact)
    dans la référence du document — proxy auditable, documenté.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_tokens: int = Field(ge=1)
    ece: float = Field(ge=0, le=1)
    mce: float = Field(ge=0, le=1)
    bins: tuple[CalibrationBin, ...] = ()


class CalibrationPayload(BaseModel):
    """Fiabilité des auto-estimations moteur, par pipeline (vue texte)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["calibration"] = "calibration"
    n_bins: int = Field(ge=2)
    pipelines: tuple[PipelineCalibration, ...] = ()


class TaxonomyCount(BaseModel):
    """Occurrences d'une classe d'erreur."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=1)


class PipelineTaxonomy(BaseModel):
    """Répartition des classes d'erreurs d'un pipeline sur le corpus."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    total_errors: int = Field(ge=1)
    #: Classes présentes seulement, dans l'ordre canonique de ``CLASSES``.
    counts: tuple[TaxonomyCount, ...] = ()


class TaxonomyPayload(BaseModel):
    """Taxonomie d'erreurs d'une vue (classification par règles pures)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["taxonomy"] = "taxonomy"
    #: Ordre canonique de rendu (vocabulaire fermé, cf. ``evaluation.taxonomy``).
    classes: tuple[str, ...] = ()
    pipelines: tuple[PipelineTaxonomy, ...] = ()


class HallucinatedBlock(BaseModel):
    """Segment contigu de la sortie sans correspondance dans le GT (mots ajoutés)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    start_token: int = Field(ge=0)
    end_token: int = Field(ge=0)
    text: str = Field(min_length=1, max_length=4000)


class PipelineHallucination(BaseModel):
    """Détection d'hallucination d'un pipeline sur **un document**.

    ``anchor_score`` = part des trigrammes de la sortie présents dans le GT (haut
    = ancré) ; ``length_ratio`` = caractères sortie / GT (>1,2 = signal) ;
    ``net_insertion_rate`` = mots de la sortie absents du GT / mots sortie ;
    ``blocks`` = segments inventés affichés. ``is_hallucinating`` = ancrage faible
    **ou** longueur anormale (seuils = conventions, cf. ``document_hallucination``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    anchor_score: float = Field(ge=0, le=1)
    length_ratio: float = Field(ge=0)
    net_insertion_rate: float = Field(ge=0, le=1)
    gt_words: int = Field(ge=0)
    hyp_words: int = Field(ge=0)
    is_hallucinating: bool
    blocks: tuple[HallucinatedBlock, ...] = ()


class DocumentHallucination(BaseModel):
    """Analyse d'hallucination **d'un document**, par pipeline."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    pipelines: tuple[PipelineHallucination, ...] = ()


class DocumentHallucinationPayload(BaseModel):
    """Hallucinations **par document** : ancrage + blocs inventés du détail document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["document_hallucination"] = "document_hallucination"
    documents: tuple[DocumentHallucination, ...] = ()


#: Plafond de caractères par texte embarqué (borne de sûreté ; une page dense
#: tient largement dessous — au-delà, tronqué). Le payload porte **tous** les
#: documents scorés (cf. ``DocumentTextsCollector``), pas seulement les pires.
_MAX_TEXT_CHARS = 40000


class DocumentTexts(BaseModel):
    """Textes complets d'**un** document (vérité-terrain + sortie par moteur).

    Embarqués pour **tous les documents scorés** (ordre pires-d'abord), chaque
    texte borné à ``_MAX_TEXT_CHARS`` (sûreté). Normalisés (mêmes représentations
    que le scoring) → le diff côte à côte reflète ce qui est mesuré.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    reference: str = Field(max_length=_MAX_TEXT_CHARS)
    #: ``(pipeline, hypothèse)`` ordonnés — pour le sélecteur de moteur du diff.
    hypotheses: tuple[tuple[str, str], ...] = ()


class DocumentTextsPayload(BaseModel):
    """Textes complets des pires documents d'une vue (diff pleine page, borné)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["document_texts"] = "document_texts"
    documents: tuple[DocumentTexts, ...] = ()


class DocumentLines(BaseModel):
    """CER **par ligne** d'un document, par pipeline (heatmap recentrée sur le doc).

    ``pipelines`` = ``(pipeline, CER de chaque ligne GT)`` ordonnés par pipeline
    (déterminisme). Les CER par ligne viennent de l'alignement Levenshtein des
    lignes (``aligned_line_cers``) — mêmes lignes que le scoring.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    pipelines: tuple[tuple[str, tuple[float, ...]], ...] = ()


class DocumentLinesPayload(BaseModel):
    """CER par ligne **par document** : heatmap positionnelle du détail document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["document_lines"] = "document_lines"
    documents: tuple[DocumentLines, ...] = ()


class PipelineConformity(BaseModel):
    """Scores de conformité HIPE d'un pipeline (vue ``hipe``).

    ``cmer``/``wmer`` micro = somme des comptes puis ratio ; macro = moyenne des
    scores par-document (``None``-exclus) — les deux conventions du scorer
    (SPEC_HIPE §4.1). ``delta_norm = cmer(raw) − cmer(hipe)`` : part d'erreur
    imputable à casse/ponctuation/formes mappées ; ``delta_heritage =
    cmer(heritage) − cmer(hipe)`` : part des seuls mappings patrimoniaux.
    ``n_missing`` = documents sans sortie scorée sur la vue ``hipe`` — exposé
    (jamais un silence) ; leur matérialisation « sortie vide = erreur max »
    (R-1.8) arrive avec le bilan de correction (les textes y sont disponibles).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    cmer_micro: float | None = None
    cmer_macro: float | None = None
    wmer_micro: float | None = None
    wmer_macro: float | None = None
    delta_norm: float | None = None
    delta_heritage: float | None = None
    n_missing: int = Field(default=0, ge=0)


class ConformityPayload(BaseModel):
    """Conformité HIPE d'un run : scores officiels + deltas de normalisation.

    Les noms exportés (``cmer_micro``…) suivent le scorer ; les vues sources
    sont nommées — chaque nombre a son profil (SPEC_HIPE §7.2).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["hipe"] = "hipe"
    hipe_view: str = Field(min_length=1, max_length=128)
    raw_view: str | None = Field(default=None, max_length=128)
    heritage_view: str | None = Field(default=None, max_length=128)
    pipelines: tuple[PipelineConformity, ...] = ()


class RegressionSample(BaseModel):
    """Une régression de correction : le LLM a dégradé ce document."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    cmer_raw: float = Field(ge=0, le=1)
    cmer_corrected: float = Field(ge=0, le=1)
    delta: float


class OverNormalizedWord(BaseModel):
    """Un mot juste à l'OCR, dégradé par le correcteur (``∅`` = supprimé)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    reference: str = Field(max_length=64)
    corrected: str = Field(max_length=64)


class PipelineCorrection(BaseModel):
    """Bilan de correction d'un pipeline 2 étages (brut → corrigé), une vue.

    Tous les nombres dérivent de ``cmer`` par document sur les paires
    (GT, brut) et (GT, corrigé) — mêmes textes préparés que le scoring.
    R-1.8 : un étage absent est **matérialisé vide** (erreur maximale) et
    compté (``n_missing_*``) — jamais une exclusion silencieuse. Les taux
    valent ``None`` quand leur dénominateur est nul (jamais un faux zéro).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_documents: int = Field(ge=1)
    n_missing_raw: int = Field(default=0, ge=0)
    n_missing_corrected: int = Field(default=0, ge=0)
    #: Triplet de non-régression (Σ = 1) + pref = improvement − regression.
    improvement_rate: float = Field(ge=0, le=1)
    regression_rate: float = Field(ge=0, le=1)
    no_change_rate: float = Field(ge=0, le=1)
    pref_score: float = Field(ge=-1, le=1)
    n_catastrophic: int = Field(default=0, ge=0)
    catastrophic_rate: float = Field(ge=0, le=1)
    #: pcis (SPEC §4.2) : non borné → macro accompagnée de la médiane robuste
    #: et du compte des valeurs extrêmes (|pcis| > 1).
    pcis_macro: float | None = None
    pcis_median: float | None = None
    n_pcis_extreme: int = Field(default=0, ge=0)
    #: Ampleur d'intervention (Koynov 2025) : CCR = MER(brut ↔ corrigé).
    ccr: float | None = None
    change_ratio: float | None = None
    length_ratio: float | None = None
    n_overedited: int = Field(default=0, ge=0)
    #: Volume de texte inséré vs GT (R-1.3) : I/(H+S+D+I) sur (GT, corrigé).
    char_ins_ratio: float | None = None
    n_hallucination_heavy: int = Field(default=0, ge=0)
    #: Absorption d'erreurs (multiset de mots GT) : flux corrigé vs introduit.
    errors_before: int = Field(default=0, ge=0)
    errors_after: int = Field(default=0, ge=0)
    corrected: int = Field(default=0, ge=0)
    introduced: int = Field(default=0, ge=0)
    kept_wrong: int = Field(default=0, ge=0)
    correction_rate: float | None = None
    introduction_rate: float | None = None
    net_improvement: int = 0
    corrected_samples: tuple[str, ...] = ()
    introduced_samples: tuple[str, ...] = ()
    #: Sur-normalisation (positionnelle) : mots OCR-justes dégradés.
    n_correct_ocr_words: int = Field(default=0, ge=0)
    n_over_normalized: int = Field(default=0, ge=0)
    over_normalization: float | None = None
    over_normalized_samples: tuple[OverNormalizedWord, ...] = ()
    #: Localité des modifications (R-2.6) : séquences d'éditions consécutives
    #: sur (GT, corrigé) — longues séquences = réécriture de passages.
    edit_run_median: float | None = None
    edit_run_max: int = Field(default=0, ge=0)
    edit_run_share: float | None = None
    worst_regressions: tuple[RegressionSample, ...] = ()


class CorrectionPayload(BaseModel):
    """Bilan de correction d'une vue : que vaut l'étage LLM des pipelines ?

    Présent seulement si la vue a scoré au moins un pipeline **2 étages**
    (un ``CORRECTED_TEXT`` produit) — un pipeline mono-étage n'a pas de
    « bilan de correction » (absence ≠ zéro muet). Les seuils sont portés
    par le payload : chaque drapeau est auditable.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["correction"] = "correction"
    metric: str = Field(min_length=1, max_length=128)
    catastrophic_threshold: float = Field(gt=0)
    overedit_threshold: float = Field(gt=0)
    insertion_threshold: float = Field(gt=0)
    edit_run_threshold: int = Field(gt=0)
    pipelines: tuple[PipelineCorrection, ...] = ()


class CategoryBreakdown(BaseModel):
    """Restitution d'une catégorie de séquences (années, folios, montants…)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    category: str = Field(min_length=1, max_length=32)
    n_total: int = Field(ge=1)
    n_strict: int = Field(ge=0)
    n_value: int = Field(ge=0)
    strict_score: float = Field(ge=0, le=1)
    value_score: float = Field(ge=0, le=1)
    #: Formes GT perdues (lentille *value*), échantillon borné.
    lost: tuple[str, ...] = ()


class PipelineStructuredData(BaseModel):
    """Séquences numériques restituées par un pipeline, par catégorie présente."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    #: Catégories **présentes dans la GT** seulement, ordre canonique.
    categories: tuple[CategoryBreakdown, ...] = ()


class StructuredDataPayload(BaseModel):
    """Données structurées d'une vue : la survie des dates/folios/montants.

    Absent si la GT du corpus ne porte aucune séquence (adaptatif — la
    famille ne pollue pas un corpus moderne sans signal).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["structured_data"] = "structured_data"
    pipelines: tuple[PipelineStructuredData, ...] = ()


class MarkerPreservation(BaseModel):
    """Préservation d'un signe (ou d'une catégorie) sur le corpus (micro).

    ``sign`` porte soit le signe abréviatif (familles containment/positional),
    soit le **nom de catégorie** (familles agrégées par catégorie : imprimé
    ancien, archives modernes — ex. ``typographic_punctuation``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    sign: str = Field(min_length=1, max_length=32)
    n_total: int = Field(ge=1)
    n_strict: int = Field(ge=0)
    n_expansion: int = Field(ge=0)


class PipelinePhilology(BaseModel):
    """Préservation d'une famille de marqueurs par un pipeline (signes présents).

    ``n_strict`` = forme exacte reproduite ; ``n_expansion`` = forme **ou**
    développement (``≥ n_strict``, borne optimiste — un mot courant peut compter
    comme développement, capé au total GT).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    family: str = Field(min_length=1, max_length=32)
    n_total: int = Field(ge=1)
    n_strict: int = Field(ge=0)
    n_expansion: int = Field(ge=0)
    markers: tuple[MarkerPreservation, ...] = ()


class PhilologyPayload(BaseModel):
    """Préservation des marqueurs philologiques d'une vue (diplomatique vs
    modernisant). Absent si la GT du corpus n'en porte aucun (adaptatif)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["philology"] = "philology"
    pipelines: tuple[PipelinePhilology, ...] = ()


class PipelineRomanNumerals(BaseModel):
    """Restitution des numéraux romains d'un pipeline en **5 statuts**.

    Un numéral de la GT est restitué selon le premier statut applicable :
    ``strict_preserved`` (forme exacte), ``case_changed`` (``xiv`` → ``XIV``),
    ``j_dropped`` (``viij`` → ``viii``), ``converted_to_arabic`` (``XIV`` → ``14``)
    ou ``lost``. Les 4 premiers **préservent la valeur** ; leur somme sur
    ``n_total`` = score *valeur*, ``strict_preserved / n_total`` = score *strict*
    (les deux scores du verdict 4a, dérivés ici sans double comptage — R1).
    Les 5 compteurs somment à ``n_total`` (invariant).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_total: int = Field(ge=1)
    strict_preserved: int = Field(ge=0)
    case_changed: int = Field(ge=0)
    j_dropped: int = Field(ge=0)
    converted_to_arabic: int = Field(ge=0)
    lost: int = Field(ge=0)
    #: Formes GT perdues (échantillon borné, verbatim).
    lost_samples: tuple[str, ...] = ()


class RomanNumeralsPayload(BaseModel):
    """Numéraux romains d'une vue : la valeur a-t-elle survécu, et sous quelle
    forme ? Absent si la GT du corpus n'en porte aucun (adaptatif).

    Payload **dédié** (≠ `PhilologyPayload`) : le modèle 5-statuts ne se mappe
    pas sur la lentille strict/expansion des marqueurs ; le forcer serait un
    hack. Rendu par la même section « Philologie ».
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["roman"] = "roman"
    pipelines: tuple[PipelineRomanNumerals, ...] = ()


class ModernizedVariant(BaseModel):
    """Forme produite par le moteur pour un token GT (``∅`` = mot supprimé)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    form: str = Field(min_length=1, max_length=64)
    count: int = Field(ge=1)


class ModernizedToken(BaseModel):
    """Un token GT et son taux de réécriture par un pipeline (corpus, micro).

    ``rate = n_modernized / n_total`` ∈ ]0,1] — seuls les tokens **réellement
    réécrits au moins une fois** sont embarqués (sinon la table déborderait du
    vocabulaire entier). ``variants`` = formes produites, triées (-count, forme).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(min_length=1, max_length=64)
    n_total: int = Field(ge=1)
    n_modernized: int = Field(ge=1)
    rate: float = Field(gt=0, le=1)
    variants: tuple[ModernizedVariant, ...] = ()


class PipelineTextualFidelity(BaseModel):
    """Fidélité textuelle d'un pipeline : tokens rares restitués + réécriture.

    ``rare_recall`` = Σ min(occ. GT, occ. hyp) / occurrences rares de la GT
    (multiset, borne le rappel par la multiplicité) ; ``None`` si la GT du
    pipeline ne porte aucun token rare (non applicable). ``missed`` = échantillon
    borné des tokens rares manqués (multiplicité incluse).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_rare_reference: int = Field(ge=0)
    n_rare_recalled: int = Field(ge=0)
    rare_recall: float | None = Field(default=None, ge=0, le=1)
    missed: tuple[str, ...] = ()
    modernization: tuple[ModernizedToken, ...] = ()


class TextualFidelityPayload(BaseModel):
    """Fidélité textuelle d'une vue : tokens rares + modernisation lexicale.

    Deux lectures complémentaires du même alignement mot-à-mot : le **rappel des
    tokens rares** (noms propres, toponymes — ce qui compte en prosopographie,
    invisible au CER global) et la **modernisation lexicale** (quelles formes
    historiques le moteur réécrit — diagnostic de prompt LLM). ``max_freq`` borne
    la rareté (≤ 2 = hapax + dis legomena), inscrit pour audit.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["textual_fidelity"] = "textual_fidelity"
    max_freq: int = Field(ge=1)
    pipelines: tuple[PipelineTextualFidelity, ...] = ()


class EngineTokenRecall(BaseModel):
    """Rappel multiset des tokens GT par un pipeline **seul** (corpus entier)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    recall: float = Field(ge=0, le=1)


class ComplementarityDocument(BaseModel):
    """Écart oracle − meilleur moteur sur un document (où l'ensemble gagnerait)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    oracle_recall: float = Field(ge=0, le=1)
    best_single_recall: float = Field(ge=0, le=1)
    absolute_gap: float = Field(ge=0, le=1)


class InterEngineComplementarity(BaseModel):
    """Oracle bag-of-words (union des moteurs) vs meilleur moteur seul.

    ``oracle_recall = Σ_token max_moteur(min(occ. GT, occ. moteur)) / Σ occ. GT``
    — **borne supérieure optimiste** : multiset (multiplicité respectée) mais
    **ordre ignoré** ; un vote séquentiel réel ferait au mieux autant, en
    général moins. ``relative_gap`` = part des erreurs du meilleur moteur
    qu'un ensemble pourrait théoriquement rattraper
    (``absolute_gap / (1 − best)``, clampé [0,1]). Les documents dont la GT ne
    porte aucun token sont **exclus** du dénominateur (R10 : jamais un rappel
    1.0 sur GT vide).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    n_documents: int = Field(ge=1)
    n_reference_tokens: int = Field(ge=1)
    oracle_recall: float = Field(ge=0, le=1)
    best_single_recall: float = Field(ge=0, le=1)
    best_engine: str = Field(min_length=1, max_length=128)
    absolute_gap: float = Field(ge=0, le=1)
    relative_gap: float = Field(ge=0, le=1)
    #: Triés par pipeline — ordre déterministe.
    per_engine_recall: tuple[EngineTokenRecall, ...] = ()
    #: Plus forts écarts oracle − meilleur (tri −gap puis doc), échantillon borné.
    per_document: tuple[ComplementarityDocument, ...] = ()


class TaxonomyDivergencePair(BaseModel):
    """JS-divergence (bits, [0,1]) entre les profils d'erreurs de deux pipelines."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    a: str = Field(min_length=1, max_length=128)
    b: str = Field(min_length=1, max_length=128)
    divergence: float = Field(ge=0, le=1)


class InterEngineDivergence(BaseModel):
    """Matrice de divergence taxonomique paire-à-paire (symétrique).

    ``pairs`` = triangle supérieur (``a < b`` par nom), diagonale (nulle)
    omise ; ``max_pair`` = la paire la plus divergente, ``None`` si toutes les
    paires sont à divergence nulle (profils identiques — aucune « paire la
    plus divergente » à nommer).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pairs: tuple[TaxonomyDivergencePair, ...]
    max_pair: TaxonomyDivergencePair | None = None


class InterEnginePayload(BaseModel):
    """Analyse inter-moteurs d'une vue : complémentarité + divergence.

    Deux lectures de « les moteurs se trompent-ils pareil ? » : l'**oracle**
    (que rattraperait un ensemble ?) sur les tokens GT, et la **divergence JS**
    sur les distributions de classes d'erreurs **déjà comptées** par la
    taxonomie de la même vue (zéro re-classification). Chaque bloc est ``None``
    quand son préalable manque (< 2 pipelines, GT sans token, taxonomie
    absente) — jamais un zéro muet.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["inter_engine"] = "inter_engine"
    complementarity: InterEngineComplementarity | None = None
    taxonomy_divergence: InterEngineDivergence | None = None


class LinePercentiles(BaseModel):
    """Percentiles de la distribution des CER par ligne (interpolation linéaire)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    p50: float = Field(ge=0)
    p75: float = Field(ge=0)
    p90: float = Field(ge=0)
    p95: float = Field(ge=0)
    p99: float = Field(ge=0)


class CatastrophicRate(BaseModel):
    """Part des lignes « catastrophiques » : CER **≥ seuil** (seuil inclus).

    Le seuil 1.0 compte les lignes totalement perdues (CER plafonné à 1.0) —
    le ``>`` strict de la source le laissait à zéro pour toujours.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    threshold: float = Field(gt=0)
    count: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)


class PipelineLines(BaseModel):
    """Distribution du CER par ligne d'un pipeline (lignes GT du corpus poolées).

    Lignes appariées par alignement Levenshtein **sur les listes de lignes**
    (une insertion/suppression ne décale pas les suivantes) ; ligne GT sans
    correspondance → CER 1.0 ; lignes hypothèse en trop ignorées. Agrégat
    **micro** : toutes les lignes du corpus dans une seule distribution (pas
    une moyenne de statistiques par document). ``gini`` : 0 = erreurs
    uniformes, 1 = concentrées sur quelques lignes. ``heatmap`` = CER moyen
    par tranche de position relative dans le document (``None`` = tranche
    sans ligne, jamais un faux zéro).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    line_count: int = Field(ge=1)
    mean_cer: float = Field(ge=0)
    gini: float = Field(ge=0, le=1)
    percentiles: LinePercentiles
    catastrophic: tuple[CatastrophicRate, ...] = ()
    heatmap: tuple[float | None, ...] = ()


class LinesPayload(BaseModel):
    """Distribution des erreurs par ligne d'une vue.

    Le CER document noie la répartition : 5 % d'erreurs uniformes (correction
    rapide partout) et 5 % concentrées en lignes détruites (re-saisie locale)
    ne se relisent pas pareil. **Absent si la normalisation de la vue écrase
    les sauts de ligne** (profil « à plat ») — une distribution par ligne d'un
    texte aplati serait un chiffre trompeur, pas une mesure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["lines"] = "lines"
    heatmap_bins: int = Field(ge=2)
    pipelines: tuple[PipelineLines, ...] = ()


class EntityCategoryScore(BaseModel):
    """Précision/rappel/F1 d'une catégorie d'entité (PER, LOC, DATE…)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=32)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    #: Entités GT de la catégorie (TP + FN) — l'assiette du rappel.
    support: int = Field(ge=1)


class EntityMention(BaseModel):
    """Une entité non appariée (manquée côté GT, ou hallucinée côté sortie)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1, max_length=32)
    text: str = Field(max_length=128)


class PipelineNer(BaseModel):
    """Précision sur entités nommées d'un pipeline (micro global + par catégorie).

    Appariement IoU ≥ seuil sur des spans **reprojetés en coordonnées GT**
    (R14 — sans quoi le F1 mesurerait le profil d'insertion/délétion de l'OCR
    amont, pas la survie des entités). ``hallucinated`` = entités produites
    sans correspondance GT (utile pour les VLM/LLM qui inventent) ; ``missed``
    = entités GT non retrouvées. La métrique mesure **conjointement** OCR + NER
    (le modèle d'extraction faillit aussi) — limite documentée dans la section.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_reference: int = Field(ge=1)
    true_positives: int = Field(ge=0)
    false_positives: int = Field(ge=0)
    false_negatives: int = Field(ge=0)
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1: float = Field(ge=0, le=1)
    #: Catégories présentes (TP+FN+FP > 0), ordre alphabétique.
    per_category: tuple[EntityCategoryScore, ...] = ()
    missed: tuple[EntityMention, ...] = ()
    hallucinated: tuple[EntityMention, ...] = ()


class NerPayload(BaseModel):
    """Précision sur entités nommées d'une vue : la survie des noms propres.

    Présent seulement si au moins un pipeline a une GT entités **et** une
    sortie entités (vue déclarant ``ner_f1``). Absent sinon (adaptatif — pas
    de colonne vide sur un corpus sans entités).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["ner"] = "ner"
    iou_threshold: float = Field(gt=0, le=1)
    pipelines: tuple[PipelineNer, ...] = ()


class EngineWordError(BaseModel):
    """Échecs d'un pipeline sur un mot GT : compte + forme produite dominante.

    ``count`` = occurrences où ce pipeline n'a **pas** restitué le mot GT (tags
    ``replace``/``delete`` de l'alignement mot-à-mot). ``variant`` = forme produite
    **dominante** *verbatim* (``∅`` = mot supprimé) : la matière de la confusion,
    embarquée pour le graphe « mot → variante produite » (incrément ultérieur,
    même payload). Rien d'inventé — la variante sort de la sortie du moteur (D-094).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    count: int = Field(ge=1)
    variant: str = Field(min_length=1, max_length=64)


class WordError(BaseModel):
    """Un mot GT raté par ≥ 1 pipeline : total, détail par moteur, regroupement.

    ``word`` = mot **verbatim** de la GT (minuscule — tokenisation partagée de la
    couche). ``per_engine`` est **creux** : seuls les moteurs qui ratent le mot y
    figurent (un moteur absent = 0 raté). ``group`` classe le recoupement
    inter-moteurs : ``universal`` (tous les pipelines observés ratent le mot —
    difficulté de la *matière*), ``engine_specific`` (un seul — faiblesse *moteur*),
    ``partial`` (un sous-ensemble).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    word: str = Field(min_length=1, max_length=64)
    total_errors: int = Field(ge=1)
    per_engine: tuple[EngineWordError, ...] = ()
    group: Literal["universal", "engine_specific", "partial"]


class WordErrorPayload(BaseModel):
    """Carte des mots d'une vue : quels mots GT chaque moteur ne restitue pas.

    Le CER dit *combien* d'erreurs, pas *lesquelles*. Ici l'alignement mot-à-mot
    (même mécanique que ``textual_fidelity``) est **croisé** sur les pipelines :
    par mot GT, le nombre d'échecs **par moteur** + une signature de regroupement.
    ``pipelines`` = moteurs ayant produit du texte (base du croisement, ≥ 2) ;
    ``words`` triés (-total, mot) et **capés** aux plus durs. Absent si < 2
    pipelines ou aucune erreur (jamais une carte vide). L'appariement dépend de la
    **normalisation de la vue** ; une fusion/scission de mots est une limite de
    l'alignement (documentée dans la section).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["word_errors"] = "word_errors"
    pipelines: tuple[str, ...] = Field(min_length=2)
    words: tuple[WordError, ...] = ()


#: Union des payloads, discriminée par ``kind`` — s'élargit d'un membre par
#: famille, dans le même commit que le calcul et le consommateur.
#: Extrait d'une ligne montrée au rapport. Court : ce qu'on lit d'un coup d'œil.
_MAX_LINE_CHARS = 300

#: Lignes montrées en exemple par pipeline. Un rapport n'est pas un journal :
#: au-delà, on ne lit plus, on fait défiler.
_MAX_DECISION_SAMPLES = 40


class DecisionReasonCount(BaseModel):
    """Combien de lignes portent un motif de refus ou de relecture."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    n: int = Field(ge=0)


class DecisionReviewReason(BaseModel):
    """Motif de relecture transmis par le correcteur, sans le réinterpréter."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1, max_length=128)
    detail: str | None = Field(default=None, max_length=_MAX_LINE_CHARS)


class DecisionSample(BaseModel):
    """Une ligne, son avant, son après, et le motif s'il y en a un."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    document_id: str = Field(min_length=1, max_length=256)
    page_id: str = Field(min_length=1, max_length=256)
    line_id: str = Field(min_length=1, max_length=256)
    status: str = Field(min_length=1, max_length=64)
    source_text: str = Field(max_length=_MAX_LINE_CHARS)
    final_text: str = Field(max_length=_MAX_LINE_CHARS)
    reason_code: str | None = Field(default=None, max_length=128)
    reason_detail: str | None = Field(default=None, max_length=_MAX_LINE_CHARS)
    review_reasons: tuple[DecisionReviewReason, ...] = ()


class PipelineDecisions(BaseModel):
    """Bilan des décisions d'un pipeline correcteur.

    ``kept`` n'est pas ``n_lines - changed`` : une ligne peut être **refusée
    par une garde** après qu'un modèle a proposé autre chose. Confondre les deux
    ferait passer un refus pour une absence de proposition.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    pipeline: str = Field(min_length=1, max_length=128)
    n_lines: int = Field(ge=0)
    changed: int = Field(ge=0)
    #: Lignes où le modèle a proposé un changement que l'application a refusé.
    refused: int = Field(ge=0)
    #: Lignes qu'aucune proposition n'a touchées.
    untouched: int = Field(ge=0)
    #: Indépendant du changement : le texte retenu peut encore exiger un jugement.
    #: Une archive sans ce champ ne permet pas de conclure qu'il valait zéro.
    review_required: int | None = Field(default=None, ge=0)
    reasons: tuple[DecisionReasonCount, ...] = ()
    review_reasons: tuple[DecisionReasonCount, ...] = ()
    samples: tuple[DecisionSample, ...] = ()


class DecisionsPayload(BaseModel):
    """Ce qu'un correcteur a changé, refusé de changer, et pourquoi."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: Literal["decisions"] = "decisions"
    pipelines: tuple[PipelineDecisions, ...] = ()


AnalysisPayload = Annotated[
    InferencePayload
    | EconomicsPayload
    | DiagnosticsPayload
    | CalibrationPayload
    | TaxonomyPayload
    | DocumentHallucinationPayload
    | DocumentTextsPayload
    | DocumentLinesPayload
    | ConformityPayload
    | CorrectionPayload
    | StructuredDataPayload
    | PhilologyPayload
    | RomanNumeralsPayload
    | TextualFidelityPayload
    | InterEnginePayload
    | LinesPayload
    | NerPayload
    | WordErrorPayload
    | DecisionsPayload,
    Field(discriminator="kind"),
]


class Analysis(BaseModel):
    """Une analyse adressée : portée + vue (+ pipeline/document si local)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    scope: Literal["corpus", "pipeline", "document"]
    view: str = Field(min_length=1, max_length=128)
    pipeline: str | None = Field(default=None, max_length=128)
    document_id: str | None = Field(default=None, max_length=256)
    payload: AnalysisPayload


__all__ = [
    "Analysis",
    "AnalysisPayload",
    "CalibrationBin",
    "CalibrationPayload",
    "CatastrophicRate",
    "CategoryBreakdown",
    "CharConfusion",
    "ComplementarityDocument",
    "ConformityPayload",
    "CorrectionPayload",
    "DecisionReasonCount",
    "DecisionReviewReason",
    "DecisionSample",
    "DecisionsPayload",
    "DiagnosticsPayload",
    "EconomicsPayload",
    "EngineTokenRecall",
    "EngineWordError",
    "EntityCategoryScore",
    "EntityMention",
    "HardDocument",
    "InferencePayload",
    "InterEngineComplementarity",
    "InterEngineDivergence",
    "InterEnginePayload",
    "LinePercentiles",
    "LinesPayload",
    "MarginalCost",
    "MarkerPreservation",
    "ModernizedToken",
    "ModernizedVariant",
    "NerPayload",
    "OverNormalizedWord",
    "PairwiseDifference",
    "PhilologyPayload",
    "PipelineDecisions",
    "PipelineCalibration",
    "PipelineConformity",
    "PipelineConfusions",
    "PipelineCorrection",
    "PipelineEconomics",
    "PipelineInterval",
    "PipelineLines",
    "PipelineNer",
    "PipelinePhilology",
    "PipelineRank",
    "PipelineRomanNumerals",
    "PipelineStructuredData",
    "PipelineTaxonomy",
    "PipelineTextualFidelity",
    "RegressionSample",
    "RomanNumeralsPayload",
    "StructuredDataPayload",
    "TaxonomyCount",
    "TaxonomyDivergencePair",
    "TaxonomyPayload",
    "TextualFidelityPayload",
    "WordError",
    "WordErrorPayload",
    "WorstLine",
]

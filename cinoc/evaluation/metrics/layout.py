"""Métriques de structure par bloc (couche 3) — ``region_cer`` + ``region_detection``.

- ``region_cer`` : texte **région par région** (apparié par ``id``), micro-agrégé
  page (Σ erreurs / Σ caractères).
- ``region_detection`` : qualité de la **segmentation géométrique** — F1 des
  régions appariées par **IoU de boîte** (≥ 0.5), en coordonnées **relatives à la
  page** (donc robuste aux unités : mm10 ALTO vs pixels). Pas de ``shapely`` :
  IoU de boîtes (boîte dérivée du polygone pour PAGE) ; l'IoU polygonal exact est
  un épaississement (aucun consommateur ne l'exige encore).

Convention métier (CLAUDE.md §3) : **niveau absent → métrique non applicable
(``None``)**. ``region_cer`` : pas de niveau texte → ``None``. ``region_detection`` :
aucune région géo-localisable côté référence → ``None``.
"""

from __future__ import annotations

from collections.abc import Iterator

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.layout import CanonicalLayout, Region
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.errors import EvaluationError
from cinoc.evaluation.metric import DocumentMetric, Observation, document_metric
from cinoc.evaluation.metrics.text import _edit_distance
from cinoc.evaluation.reading_order import kendall_distance, order_coverage

_MISSING = ""

#: Seuil d'IoU standard pour qu'une région hypothèse compte comme détectée.
_IOU_THRESHOLD = 0.5

#: Boîte en coordonnées relatives ``(x0, y0, x1, y1)`` ∈ [0, 1].
_RelBox = tuple[float, float, float, float]


def _walk(regions: tuple[Region, ...]) -> list[Region]:
    """Aplati les régions imbriquées en parcours profondeur d'abord."""
    flat: list[Region] = []
    for region in regions:
        flat.append(region)
        flat.extend(_walk(region.regions))
    return flat


def _region_texts(layout: CanonicalLayout) -> dict[str, str]:
    """``{region_id: texte}`` (lignes jointes) sur toutes les pages."""
    texts: dict[str, str] = {}
    for page in layout.pages:
        for region in _walk(page.regions):
            texts[region.id] = "\n".join(line.text for line in region.lines)
    return texts


def _has_text_level(layout: CanonicalLayout) -> bool:
    """Vrai si au moins une région porte une ligne (≠ segmentation-seule)."""
    return any(
        region.lines
        for page in layout.pages
        for region in _walk(page.regions)
    )


def _layout_pair(ctx: DocContext) -> tuple[CanonicalLayout, CanonicalLayout]:
    if not isinstance(ctx.reference, CanonicalLayout) or not isinstance(
        ctx.hypothesis, CanonicalLayout
    ):
        raise EvaluationError(
            "métrique structure : reference et hypothesis doivent être des "
            "CanonicalLayout."
        )
    return ctx.reference, ctx.hypothesis


@document_metric(
    name="region_cer",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description="CER par région agrégé à la page (micro) sur le CanonicalLayout.",
    higher_is_better=False,
    tags=frozenset({"structure", "edit_distance", "layout"}),
)
def region_cer(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _layout_pair(ctx)
    if not _has_text_level(hypothesis) or not _has_text_level(reference):
        return None
    ref_texts = _region_texts(reference)
    hyp_texts = _region_texts(hypothesis)
    # Par identifiant quand ils sont partagés, par géométrie sinon : sans ça,
    # deux systèmes différents ne s'apparient jamais et le CER par région vaut
    # 1,0 pour une transcription parfaite (cf. ``correspondance``).
    paires = correspondance(reference, hypothesis)
    total_edits = 0
    total_chars = 0
    for region_id, ref_text in ref_texts.items():
        # Une région non appariée reste comptée comme **absente**, donc en
        # suppression intégrale : c'est le comportement d'origine, et la
        # détection a sa propre métrique pour dire *pourquoi* elle manque.
        hyp_text = hyp_texts.get(paires.get(region_id, ""), _MISSING)
        total_edits += _edit_distance(ref_text, hyp_text)
        total_chars += len(ref_text)
    if total_chars == 0:
        return None
    return Observation(value=total_edits / total_chars, weight=total_chars)


def _leaf_regions(regions: tuple[Region, ...]) -> Iterator[Region]:
    """Régions **atomiques** (sans sous-région) — la granularité segmentée."""
    for region in regions:
        if region.regions:
            yield from _leaf_regions(region.regions)
        else:
            yield region


def _abs_bbox(region: Region) -> tuple[int, int, int, int] | None:
    """Boîte absolue ``(x0, y0, x1, y1)`` depuis la bbox, sinon le polygone."""
    geometry = region.geometry
    if geometry is None:
        return None
    if geometry.bbox is not None:
        b = geometry.bbox
        return b.x, b.y, b.x + b.width, b.y + b.height
    if geometry.polygon:
        xs = [p[0] for p in geometry.polygon]
        ys = [p[1] for p in geometry.polygon]
        return min(xs), min(ys), max(xs), max(ys)
    return None


def _detection_boxes(layout: CanonicalLayout) -> list[_RelBox]:
    """Boîtes des régions atomiques, **relatives** à la page (unités neutralisées).

    Une page sans dimensions est ignorée (normalisation impossible).
    """
    boxes: list[_RelBox] = []
    for page in layout.pages:
        width, height = page.width, page.height
        if not width or not height:
            continue
        for region in _leaf_regions(page.regions):
            bbox = _abs_bbox(region)
            if bbox is None:
                continue
            x0, y0, x1, y1 = bbox
            boxes.append((x0 / width, y0 / height, x1 / width, y1 / height))
    return boxes


def _iou(a: _RelBox, b: _RelBox) -> float:
    ix0, iy0 = max(a[0], b[0]), max(a[1], b[1])
    ix1, iy1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix1 - ix0) * max(0.0, iy1 - iy0)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def _greedy_pairs(
    ref: list[_RelBox], hyp: list[_RelBox], threshold: float
) -> list[tuple[int, int]]:
    """Appariement glouton déterministe : chaque réf prend sa meilleure hyp libre.

    Rend les **couples d'indices**, et non leur seul compte : c'est le même
    appariement qui sert à la détection (combien de régions retrouvées) et à
    tout ce qui doit ensuite comparer deux régions entre elles — leur texte,
    leur rang de lecture. Un second appariement, écrit ailleurs, divergerait.
    """
    used: set[int] = set()
    pairs: list[tuple[int, int]] = []
    for ref_index, ref_box in enumerate(ref):
        best_iou, best_idx = threshold, -1
        for index, hyp_box in enumerate(hyp):
            if index in used:
                continue
            value = _iou(ref_box, hyp_box)
            if value >= best_iou:
                best_iou, best_idx = value, index
        if best_idx >= 0:
            used.add(best_idx)
            pairs.append((ref_index, best_idx))
    return pairs


def _true_positives(ref: list[_RelBox], hyp: list[_RelBox], threshold: float) -> int:
    return len(_greedy_pairs(ref, hyp, threshold))


def _identified_boxes(layout: CanonicalLayout) -> list[tuple[str, _RelBox]]:
    """``(id, boîte relative)`` des régions atomiques — l'entrée de l'appariement."""
    out: list[tuple[str, _RelBox]] = []
    for page in layout.pages:
        width, height = page.width, page.height
        if not width or not height:
            continue
        for region in _leaf_regions(page.regions):
            bbox = _abs_bbox(region)
            if bbox is None:
                continue
            x0, y0, x1, y1 = bbox
            out.append(
                (region.id, (x0 / width, y0 / height, x1 / width, y1 / height))
            )
    return out


def _ids_partages(
    reference: CanonicalLayout, hypothesis: CanonicalLayout
) -> set[str]:
    """Identifiants de région présents des **deux** côtés.

    Vide = deux systèmes qui ne se nomment pas pareil.
    """
    ref_ids = {r.id for page in reference.pages for r in _walk(page.regions)}
    hyp_ids = {r.id for page in hypothesis.pages for r in _walk(page.regions)}
    return ref_ids & hyp_ids


def correspondance(
    reference: CanonicalLayout, hypothesis: CanonicalLayout
) -> dict[str, str]:
    """``{id de référence: id d'hypothèse}`` — par identifiant, sinon par géométrie.

    **Le problème que ça résout.** Cinq des six métriques de structure
    appariaient les blocs par identifiant. Or deux systèmes différents ne
    partagent jamais les leurs : la BnF numérote ``r_10_1``, un détecteur ``r1``.
    Ces métriques étaient donc inutilisables dès qu'on comparait autre chose
    qu'un pipeline à lui-même — et ``region_cer``, silencieusement, annonçait
    **1,0** (le pire score possible) pour une transcription parfaite. Un faux
    négatif muet, qui classe dernier un système irréprochable.

    **L'ordre des deux stratégies n'est pas arbitraire.** L'identifiant d'abord :
    quand il est partagé, il est exact, il ne dépend d'aucun seuil, et toutes les
    valeurs déjà publiées restent identiques. La géométrie **ensuite**, et
    seulement si aucun identifiant ne se recoupe — c'est le cas inter-systèmes,
    celui qui ne rendait rien d'exploitable.

    Un appariement **vide** est rendu tel quel : les métriques le lisent comme
    « non applicable », ce qui est la vérité. Fabriquer un appariement de
    repli serait inventer une correspondance que rien n'établit.
    """
    communs = _ids_partages(reference, hypothesis)
    if communs:
        return {region_id: region_id for region_id in communs}
    ref_boxes = _identified_boxes(reference)
    hyp_boxes = _identified_boxes(hypothesis)
    return {
        ref_boxes[i][0]: hyp_boxes[j][0]
        for i, j in _greedy_pairs(
            [b for _, b in ref_boxes], [b for _, b in hyp_boxes], _IOU_THRESHOLD
        )
    }


@document_metric(
    name="region_detection",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description="F1 des régions appariées par IoU de boîte (≥0.5), coords relatives.",
    higher_is_better=True,
    tags=frozenset({"structure", "layout", "geometry", "detection"}),
)
def region_detection(ctx: DocContext) -> Observation | None:
    reference, hypothesis = _layout_pair(ctx)
    ref_boxes = _detection_boxes(reference)
    if not ref_boxes:
        return None  # rien de géo-localisable côté référence → non applicable
    hyp_boxes = _detection_boxes(hypothesis)
    tp = _true_positives(ref_boxes, hyp_boxes, _IOU_THRESHOLD)
    precision = tp / len(hyp_boxes) if hyp_boxes else 0.0
    recall = tp / len(ref_boxes)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return Observation(value=f1, weight=len(ref_boxes))


#: Socle de métriques de structure, collecté explicitement par le registre.
def _lines_by_id(layout: CanonicalLayout) -> dict[str, str]:
    """``{line_id: texte}``. Les lignes sans identifiant sont **ignorées** : sans
    identité, elles n'ont rien à quoi être appariées."""
    return {
        line.id: line.text
        for page in layout.pages
        for region in _walk(page.regions)
        for line in region.lines
        if line.id
    }


@document_metric(
    name="line_identity_cer",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description="CER par ligne appariée par IDENTITÉ (et non par alignement).",
    higher_is_better=False,
    tags=frozenset({"structure", "edit_distance", "layout", "identity"}),
)
def line_identity_cer(ctx: DocContext) -> Observation | None:
    """CER par ligne, lignes appariées par leur **identifiant**.

    Le banc apparie sinon les lignes par un alignement de Levenshtein sur des
    *listes de lignes* — une devinette, nécessaire quand tout est du texte plat.
    Quand les deux côtés portent des identifiants, l'appariement est **connu**.

    Ce que coûte la devinette, mesuré sur ``corpus/37-GT-BNL`` (522 lignes) :
    elle diverge de l'identité sur **57 lignes** et porte le CER moyen par ligne
    de 0,1188 à 0,1879. Elle se trompe presque toujours dans le même sens —
    **51 lignes sur-notées contre 6 sous-notées** — et pour **14** d'entre elles
    elle conclut « aucune correspondance » (CER 1,0) alors qu'un jumeau existe
    sous le même identifiant. Le déclencheur est une ligne vide côté hypothèse :
    absente du texte aplati, elle décale les blocs d'opcodes, et des lignes
    voisines quasi parfaites se retrouvent déclarées non appariées.

    Une ligne de référence absente de l'hypothèse compte comme **entièrement
    fausse** — c'est une ligne perdue, pas une ligne à ignorer.
    """
    reference, hypothesis = _layout_pair(ctx)
    ref_lines = _lines_by_id(reference)
    if not ref_lines or not _lines_by_id(hypothesis):
        return None
    hyp_lines = _lines_by_id(hypothesis)
    total_edits = 0
    total_chars = 0
    for line_id, ref_text in ref_lines.items():
        total_edits += _edit_distance(ref_text, hyp_lines.get(line_id, _MISSING))
        total_chars += len(ref_text)
    if total_chars == 0:
        return None
    return Observation(value=total_edits / total_chars, weight=total_chars)


@document_metric(
    name="line_identity_coverage",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description="Part des lignes de référence retrouvées par identifiant.",
    higher_is_better=True,
    tags=frozenset({"structure", "layout", "identity", "coverage"}),
)
def line_identity_coverage(ctx: DocContext) -> Observation | None:
    """Part des lignes de référence que l'hypothèse porte **sous le même id**.

    Une étape qui perd des lignes, en fusionne, ou leur réattribue un
    identifiant fait chuter ce chiffre — et c'est invisible dans un CER, qui
    n'a aucun moyen de signaler qu'une ligne a disparu plutôt que d'être mal
    transcrite.
    """
    reference, hypothesis = _layout_pair(ctx)
    ref_lines = _lines_by_id(reference)
    if not ref_lines:
        return None
    hyp_ids = set(_lines_by_id(hypothesis))
    retrouvees = sum(1 for line_id in ref_lines if line_id in hyp_ids)
    return Observation(value=retrouvees / len(ref_lines), weight=len(ref_lines))


def _ordres(ctx: DocContext) -> tuple[list[str], list[str]]:
    """Ordres de lecture (référence, hypothèse), toutes pages concaténées.

    L'ordre de l'hypothèse est rendu **dans les identifiants de la référence** :
    comparer deux suites d'identifiants étrangers ne mesurerait rien, et c'est
    ce qui rendait l'ordre de lecture inévaluable entre deux systèmes.
    """
    reference, hypothesis = _layout_pair(ctx)
    ref = [rid for page in reference.pages for rid in page.reading_order]
    brut = [rid for page in hypothesis.pages for rid in page.reading_order]
    if _ids_partages(reference, hypothesis):
        # Les deux côtés se nomment pareil : rien à traduire, et surtout rien à
        # filtrer. Un ordre de lecture peut citer un identifiant qui n'existe
        # pas comme région — la VT BnF le fait pour 34 de ses 416 renvois —, et
        # les écarter changerait une couverture déjà publiée.
        return ref, brut
    vers_reference = {
        hyp_id: ref_id
        for ref_id, hyp_id in correspondance(reference, hypothesis).items()
    }
    return ref, [vers_reference[rid] for rid in brut if rid in vers_reference]


@document_metric(
    name="reading_order_tau",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description=(
        "Désaccord d'ordre de lecture (Kendall normalisé) : part des paires de "
        "blocs rangées dans l'ordre inverse de la référence."
    ),
    higher_is_better=False,
    tags=frozenset({"structure", "layout", "reading_order"}),
)
def reading_order_tau(ctx: DocContext) -> Observation | None:
    """Attribue à l'**ordonnancement** ce que le CER attribuerait à la lecture.

    Un texte projeté dans le mauvais ordre a un CER catastrophique, mais ce CER
    ne dit pas où est la faute. Celle-ci ne mesure que l'ordre — et seulement
    sur les blocs présents des deux côtés, la détection ayant sa propre métrique.
    """
    reference, hypothese = _ordres(ctx)
    valeur = kendall_distance(reference, hypothese)
    if valeur is None:
        return None
    communs = len(set(reference) & set(hypothese))
    return Observation(value=valeur, weight=communs)


@document_metric(
    name="reading_order_coverage",
    input_types=(ArtifactType.LAYOUT, ArtifactType.LAYOUT),
    description="Part des blocs de la référence que l'hypothèse a ordonnés.",
    higher_is_better=True,
    tags=frozenset({"structure", "layout", "reading_order"}),
)
def reading_order_coverage(ctx: DocContext) -> Observation | None:
    """Le compagnon obligatoire du désaccord.

    Un ordre parfait sur deux blocs trouvés sur trente n'est pas un bon
    résultat, et la distance seule le dirait excellent.
    """
    reference, hypothese = _ordres(ctx)
    valeur = order_coverage(reference, hypothese)
    if valeur is None:
        return None
    return Observation(value=valeur, weight=len(set(reference)))



LAYOUT_METRICS: tuple[DocumentMetric, ...] = (
    region_cer,
    region_detection,
    line_identity_cer,
    line_identity_coverage,
    reading_order_tau,
    reading_order_coverage,
)


__all__ = [
    "LAYOUT_METRICS",
    "line_identity_cer",
    "line_identity_coverage",
    "reading_order_coverage",
    "reading_order_tau",
    "region_cer",
    "region_detection",
]

"""``ReadingOrderModule`` — ``LAYOUT → LAYOUT`` : remettre les blocs dans l'ordre.

Toutes les références traitent l'ordre de lecture comme une **étape**, pas comme
un sous-produit de la segmentation : eScriptorium et Transkribus le détectent
puis le donnent à corriger à la main, PP-Structure en fait un module dédié qui
reconstruit la logique d'un document multi-colonnes.

La raison est concrète. Sur une page de presse, un segmenteur trouve les blocs
sans savoir dans quel ordre les lire ; pris de haut en bas, ils entrelacent les
colonnes et le texte devient inexploitable — pour un lecteur comme pour une
recherche plein texte. Le taux d'erreur par caractère, lui, chute d'un coup :
c'est donc **mesurable**, à condition d'avoir l'étape qui le produit.

``layout_to_text`` projette déjà selon ``reading_order`` : changer l'ordre change
le texte, et le banc peut départager deux stratégies sur le même corpus.
"""

from __future__ import annotations

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

#: 2.0 : ``columns`` = ordre de Breuel (D-287) ; 1.0 regroupait par recouvrement
#: et entrelaçait deux colonnes sous un titre large.
_VERSION = "2.0"

#: Stratégies d'ordonnancement. ``topdown`` est la ligne de base — celle qu'on
#: veut battre ; ``columns`` suit l'ordre de Breuel (titres, colonnes, filets).
STRATEGIES: tuple[str, ...] = ("topdown", "columns")


def _boite(region: Region) -> tuple[int, int, int, int] | None:
    """``(x, y, largeur, hauteur)`` d'une région, ou ``None`` sans géométrie."""
    if region.geometry is None or region.geometry.bbox is None:
        return None
    boite = region.geometry.bbox
    return (boite.x, boite.y, boite.width, boite.height)


def _feuilles(regions: tuple[Region, ...]) -> list[Region]:
    """Régions atomiques : un bloc composé porte ses lignes dans ses enfants."""
    sorties: list[Region] = []
    for region in regions:
        if region.regions:
            sorties.extend(_feuilles(region.regions))
        else:
            sorties.append(region)
    return sorties


def ordonner_topdown(regions: list[Region]) -> list[str]:
    """De haut en bas, puis de gauche à droite. La ligne de base.

    Sur une page à une colonne, c'est le bon ordre. Sur deux colonnes, c'est
    exactement l'erreur qu'on cherche à mesurer : les lignes s'entrelacent.
    """
    avec = [(r, _boite(r)) for r in regions]
    return [
        r.id or ""
        for r, b in sorted(
            avec, key=lambda rb: (rb[1][1], rb[1][0]) if rb[1] else (0, 0)
        )
        if r.id
    ]


def ordonner_colonnes(regions: list[Region]) -> list[str]:
    """Ordre de lecture de Breuel : tri topologique sous contraintes de colonnes.

    Portage de l'algorithme de T. M. Breuel (« Two geometric algorithms for
    layout analysis », DAS 2002, §4 ; repris d'ocropus par kraken,
    ``kraken.lib.segmentation._reading_order`` et ``topsort``, Apache-2.0), en
    écriture gauche → droite. Un bloc ``u`` précède ``v`` :

    - s'ils se recouvrent horizontalement, quand ``u`` commence plus haut ;
    - sinon, quand ``u`` est entièrement à gauche de ``v`` **et** qu'aucun
      troisième bloc ne les sépare — un bloc qui chevauche verticalement
      l'étendue des deux et franchit horizontalement l'intervalle entre eux
      (un titre, un filet pleine largeur).

    Ces contraintes forment un ordre partiel ; un parcours en profondeur qui
    place chaque bloc après ses prédécesseurs le complète. Un titre large se lit
    donc avant ses deux colonnes, chacune entière, et un bloc pleine largeur au
    milieu de la page ferme les colonnes du haut avant d'ouvrir celles du bas.

    Seul écart à kraken : le parcours visite les blocs de haut en bas puis de
    gauche à droite, et non dans l'ordre où le segmenteur les déclare — ce qui
    reste libre entre deux blocs suit donc la ligne de base, et le résultat ne
    lit que la géométrie. Coût en O(n³) sur le nombre de blocs de la page.

    Sans géométrie, on ne devine pas : l'ordre déclaré est rendu tel quel.
    """
    boites = [_boite(r) for r in regions]
    if any(b is None for b in boites):
        return [r.id or "" for r in regions if r.id]
    rects = sorted(
        (
            (b[1], b[0], b[0] + b[2], b[1] + b[3], region)
            for b, region in zip(boites, regions, strict=True)
            if b is not None
        ),
        key=lambda r: (r[0], r[1]),
    )
    # (y0, x0, x1, y1) de chaque bloc, dans l'ordre de visite.
    cadres = [(y0, x0, x1, y1) for y0, x0, x1, y1, _r in rects]
    avant: list[list[int]] = [
        [i for i in range(len(cadres)) if i != j and _precede(cadres, i, j)]
        for j in range(len(cadres))
    ]
    return [
        rects[k][4].id or "" for k in _tri_topologique(avant) if rects[k][4].id
    ]


def _precede(cadres: list[tuple[int, int, int, int]], i: int, j: int) -> bool:
    """Le bloc ``i`` précède-t-il ``j`` (contrainte de Breuel) ?"""
    uy0, ux0, ux1, _uy1 = cadres[i]
    vy0, vx0, vx1, _vy1 = cadres[j]
    if ux0 < vx1 and ux1 > vx0:
        return uy0 < vy0
    if not ux1 < vx0:
        return False
    return not any(
        _separe(cadres[k], cadres[i], cadres[j])
        for k in range(len(cadres))
        if k not in (i, j)
    )


def _separe(
    w: tuple[int, int, int, int],
    u: tuple[int, int, int, int],
    v: tuple[int, int, int, int],
) -> bool:
    """``w`` s'interpose-t-il entre ``u`` (à gauche) et ``v`` (à droite) ?"""
    if w[3] < min(u[0], v[0]) or w[0] > max(u[3], v[3]):
        return False
    return w[1] < u[2] and w[2] > v[1]


def _tri_topologique(avant: list[list[int]]) -> list[int]:
    """Chaque bloc après ses prédécesseurs (parcours en profondeur, itératif)."""
    vu = [False] * len(avant)
    ordre: list[int] = []
    for depart in range(len(avant)):
        if vu[depart]:
            continue
        vu[depart] = True
        pile = [(depart, iter(avant[depart]))]
        while pile:
            noeud, suite = pile[-1]
            for precedent in suite:
                if not vu[precedent]:
                    vu[precedent] = True
                    pile.append((precedent, iter(avant[precedent])))
                    break
            else:
                pile.pop()
                ordre.append(noeud)
    return ordre


class ReadingOrderModule:
    """Calcule l'ordre de lecture d'une mise en page, sans la modifier autrement."""

    def __init__(self, *, label: str, strategy: str = "columns") -> None:
        if strategy not in STRATEGIES:
            raise AdapterStepError(
                f"reading_order : stratégie {strategy!r} inconnue "
                f"(attendu parmi {list(STRATEGIES)})."
            )
        self._label = label
        self._strategy = strategy

    @property
    def name(self) -> str:
        return f"reading_order:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.LAYOUT})

    @property
    def strategy(self) -> str:
        return self._strategy

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        entree = inputs.get(ArtifactType.LAYOUT)
        if entree is None or entree.uri is None:
            raise AdapterStepError(
                f"{self.name} : artefact LAYOUT manquant ou sans URI."
            )
        from pathlib import Path  # noqa: PLC0415

        source = Path(entree.uri)
        try:
            layout = CanonicalLayout.model_validate_json(source.read_bytes())
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : mise en page illisible ({source.name}) — {exc}"
            ) from exc

        pages = tuple(self._ordonner(page) for page in layout.pages)
        ordonnee = layout.model_copy(update={"pages": pages})

        payload = ordonnee.model_dump_json().encode("utf-8")
        cible = (
            workspace_artifact_path(
                context.workspace_uri, context.document_id, self._label, "layout.json"
            )
            if context.workspace_uri
            else source.with_name(f"{source.stem}.{self._label}.layout.json")
        )
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id=f"{context.document_id}:{self._label}:layout",
                    document_id=context.document_id,
                    type=ArtifactType.LAYOUT,
                    uri=str(cible),
                    content_hash=compute_content_hash(payload),
                    produced_by_step=self._label,
                )
            }
        )

    def _ordonner(self, page: LayoutPage) -> LayoutPage:
        feuilles = list(page.leaf_regions())
        if not feuilles:
            return page
        ordre = (
            ordonner_topdown(feuilles)
            if self._strategy == "topdown"
            else ordonner_colonnes(feuilles)
        )
        return page.model_copy(update={"reading_order": tuple(ordre)})


__all__ = [
    "STRATEGIES",
    "ReadingOrderModule",
    "ordonner_colonnes",
    "ordonner_topdown",
]

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

_VERSION = "1.0"

#: Stratégies d'ordonnancement. ``topdown`` est la ligne de base — celle qu'on
#: veut battre ; ``columns`` regroupe d'abord en colonnes.
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


def ordonner_colonnes(regions: list[Region], *, tolerance: float = 0.5) -> list[str]:
    """Colonnes d'abord, de gauche à droite ; blocs de haut en bas dans chacune.

    Deux blocs appartiennent à la même colonne si leurs intervalles horizontaux
    se recouvrent d'au moins ``tolerance`` fois la largeur du plus étroit. Le
    recouvrement **relatif** est ce qui permet de traiter pareil une manchette
    large et un filet étroit ; un seuil en pixels dépendrait de la résolution du
    scan, ce qui ne veut rien dire d'une page à l'autre.

    Sans géométrie, on ne devine pas : l'ordre déclaré est rendu tel quel.
    """
    boites = [(r, _boite(r)) for r in regions]
    if any(b is None for _r, b in boites):
        return [r.id or "" for r in regions if r.id]

    colonnes: list[list[tuple[Region, tuple[int, int, int, int]]]] = []
    # Blocs traités de gauche à droite : une colonne se construit en rencontrant
    # d'abord son bloc le plus à gauche.
    for region, boite in sorted(boites, key=lambda rb: rb[1][0]):  # type: ignore[index,arg-type]
        assert boite is not None
        place = False
        for colonne in colonnes:
            if any(_recouvre(boite, autre, tolerance) for _r, autre in colonne):
                colonne.append((region, boite))
                place = True
                break
        if not place:
            colonnes.append([(region, boite)])

    colonnes.sort(key=lambda c: min(b[0] for _r, b in c))
    ordre: list[str] = []
    for colonne in colonnes:
        for region, _b in sorted(colonne, key=lambda rb: (rb[1][1], rb[1][0])):
            if region.id:
                ordre.append(region.id)
    return ordre


def _recouvre(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int], tolerance: float
) -> bool:
    """Les intervalles horizontaux se recouvrent-ils assez pour être une colonne ?"""
    gauche = max(a[0], b[0])
    droite = min(a[0] + a[2], b[0] + b[2])
    commun = max(0, droite - gauche)
    etroit = max(1, min(a[2], b[2]))
    return commun / etroit >= tolerance


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
        feuilles = _feuilles(page.regions)
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

"""Outillage des tests de la revue indépendante de 1a + 1b (``test_ce_revue_1ab``).

Les défauts D1 à D14 et les questions Q1 à Q9 (``CONTRATS.md``, « Précisions
tranchées le 28/11 après la validation finale de 1a + 1b ») ont chacun un
contre-exemple exécutable. Ce module porte ce qu'ils partagent :

- ``BriqueOctets`` : une brique tierce qui écrit des **octets** (une sortie non
  UTF-8, un JSON de mise en page invalide), ce que ``TextBrick`` ne peut pas ;
- ``vue_layout`` : la vue « texte » projetée depuis une mise en page ;
- ``texte_visible`` / ``affiche`` : lire un rapport HTML **comme un lecteur** (ni
  ``<script>`` ni ``<style>``, dont l'île de données qui contient tout le
  ``RunResult``), pour vérifier qu'une valeur est *affichée* ;
- ``recalcule`` : l'oracle **indépendant** de la validation sémantique (somme des
  statistiques sérialisées, ``Fraction``), qui n'importe rien de
  ``cinoc.evaluation.aggregation``.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from cinoc.adapters.extension import (
    AdapterStepError,
    Artifact,
    ArtifactType,
    RunContext,
    RunControl,
    StepOutput,
    compute_content_hash,
    workspace_artifact_path,
)
from cinoc.domain.evaluation import EvaluationView
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Line, Region
from cinoc.domain.projection import ProjectionSpec
from cinoc.evaluation.result import RunResult

from . import test_ce_saknussemm_issues as sak
from ._kit import corpus, execute, pipeline, registry_with, spec, step, text_view

T = ArtifactType

#: Octets qui ne sont pas de l'UTF-8 (``0xff`` ne s'y rencontre jamais).
NON_UTF8 = b"\xff\xfe\x00garbage"
#: Une mise en page dont le JSON est invalide : lisible nulle part.
LAYOUT_ILLISIBLE = b'{"pages": [ oops'


@dataclass
class BriqueOctets:
    """Brique ``in_type → out_type`` qui écrit **telle quelle** sa sortie.

    ``sorties[document]`` : les octets à écrire, ou l'``AdapterStepError`` à
    lever. ``partial`` : documents dont l'étape se déclare partielle ;
    ``truncate`` : documents dont la sortie est coupée (``max_tokens``).
    ``calls`` compte les appels (un refus **avant** l'exécution n'en laisse
    aucun).
    """

    name: str
    sorties: Mapping[str, bytes | AdapterStepError]
    in_type: ArtifactType = T.IMAGE
    out_type: ArtifactType = T.RAW_TEXT
    partial: frozenset[str] = frozenset()
    truncate: frozenset[str] = frozenset()
    calls: list[str] = field(default_factory=list)
    version: str = "1.0"

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({self.in_type})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({self.out_type})

    def execute(
        self,
        inputs: Mapping[ArtifactType, Artifact],
        params: Mapping[str, object],
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        document = context.document_id
        self.calls.append(document)
        produced = self.sorties[document]
        if isinstance(produced, AdapterStepError):
            raise produced
        assert context.workspace_uri is not None
        path = workspace_artifact_path(
            context.workspace_uri, document, self.name.replace(":", "_"), "txt"
        )
        path.write_bytes(produced)
        artifact = Artifact(
            id=f"{document}:{self.name}:{self.out_type.value}",
            document_id=document,
            type=self.out_type,
            uri=str(path),
            content_hash=compute_content_hash(produced),
        )
        output = StepOutput(
            artifacts={self.out_type: artifact},
            truncation="max_tokens" if document in self.truncate else None,
        )
        if document in self.partial:
            output = dataclasses.replace(output, partial="ce_perte")  # type: ignore[call-arg]
        return output


def layout_octets(texte: str) -> bytes:
    """Une mise en page à une région dont chaque ligne de ``texte`` est une ligne
    (``""`` : une page sans région, c'est-à-dire une sortie vide valide)."""
    lignes = tuple(Line(text=ligne) for ligne in texte.split("\n")) if texte else ()
    regions = (Region(id="r1", lines=lignes),) if lignes else ()
    return (
        CanonicalLayout(pages=(LayoutPage(regions=regions),)).model_dump_json().encode()
    )


def vue_layout(
    name: str = "texte", metrics: tuple[str, ...] = ("cer",)
) -> EvaluationView:
    """La vue qui note le texte **projeté** d'une mise en page (``layout_to_text``)."""
    return EvaluationView(
        name=name,
        candidate_types=frozenset({T.LAYOUT}),
        metric_names=metrics,
        projection=ProjectionSpec(
            source_type=T.LAYOUT,
            target_type=T.RAW_TEXT,
            projector_name="layout_to_text",
        ),
    )


# --------------------------------------------------------------------------
# Lire un rapport comme un lecteur.
# --------------------------------------------------------------------------


class _Visible(HTMLParser):
    """Texte des nœuds du document, sans ``<script>`` ni ``<style>``. Le contenu
    d'un ``<template>`` (fiches détail, inertes jusqu'au clic) en fait partie :
    il est dans le fichier et le lecteur le déplie."""

    def __init__(self) -> None:
        super().__init__()
        self._sauter = 0
        self.morceaux: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style"):
            self._sauter += 1
        self.morceaux.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self._sauter -= 1
        self.morceaux.append(" ")

    def handle_data(self, data: str) -> None:
        if not self._sauter:
            self.morceaux.append(data)


def texte_visible(html: str) -> str:
    """Le texte lu d'un fragment ou d'un document HTML, espaces normalisés."""
    lecteur = _Visible()
    lecteur.feed(html)
    lecteur.close()
    texte = "".join(lecteur.morceaux).replace(" ", " ").replace("\xa0", " ")
    return re.sub(r"\s+", " ", texte).strip()


def _nombres(texte: str) -> list[str]:
    """Les jetons numériques du texte, virgule décimale ramenée au point et
    espace avant ``%`` retirée (« 12,5 % » → « 12.5% »)."""
    normal = re.sub(r"(?<=\d),(?=\d)", ".", texte)
    normal = re.sub(r"\s+%", "%", normal)
    return re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?%?", normal)


def affiche(texte: str, valeur: float) -> bool:
    """``valeur`` figure dans ``texte`` à la précision où le rapport l'écrit :
    un décimal à au moins trois chiffres (``0,0375``), ou un pourcentage à au
    moins un chiffre (``3,8 %``). Un entier ne prouve rien : il se trouve partout.
    """
    for jeton in _nombres(texte):
        if jeton.endswith("%"):
            corps = jeton[:-1]
            chiffres = len(corps.split(".")[1]) if "." in corps else 0
            if chiffres >= 1 and f"{valeur * 100:.{chiffres}f}" == corps:
                return True
        elif "." in jeton:
            chiffres = len(jeton.split(".")[1])
            if chiffres >= 3 and f"{valeur:.{chiffres}f}" == jeton:
                return True
    return False


def entier_affiche(texte: str, valeur: int) -> bool:
    """``valeur`` figure dans ``texte`` comme un entier isolé (ni partie d'un
    décimal, ni d'un identifiant). À réserver à des valeurs peu banales."""
    return re.search(rf"(?<![\w.,]){valeur}(?![\w]|[.,]\d)", texte) is not None


# --------------------------------------------------------------------------
# L'oracle indépendant : recalculer un agrégat depuis le seul JSON.
# --------------------------------------------------------------------------

#: Composantes sérialisées d'une statistique d'édition (``CONTRATS.md`` § 2.1 a).
_COMPOSANTES = ("substitutions", "deletions", "insertions", "reference_length")


def _stat(valeur: object) -> dict[str, int] | None:
    if isinstance(valeur, dict) and "reference_length" in valeur:
        return {nom: int(valeur[nom] or 0) for nom in _COMPOSANTES}
    return None


def _erreurs(stat: Mapping[str, int]) -> int:
    return stat["substitutions"] + stat["deletions"] + stat["insertions"]


def _somme(stats: list[dict[str, int]]) -> dict[str, int]:
    return {nom: sum(s[nom] for s in stats) for nom in _COMPOSANTES}


def grappe_serialisee(data: Mapping[str, Any], document: str) -> str:
    """La grappe de ``document`` **lue dans le JSON** (``CONTRATS.md`` D4, nom
    fixé le 28/11 : champ ``cluster`` de l'entrée ``documents``).

    Correction du 28/11 : la version précédente cherchait une valeur parmi des
    grappes « déclarées » qu'aucun appelant ne fournissait — l'ensemble était
    vide et la recherche échouait quel que soit le JSON.
    """
    for entree in data.get("documents", ()):
        if entree.get("document_id") == document:
            grappe = entree.get("cluster")
            assert isinstance(grappe, str) and grappe, (
                f"la grappe du document {document!r} est absente du JSON "
                "(champ « cluster » de l'entrée documents, CONTRATS.md D4)"
            )
            return grappe
    raise AssertionError(f"le document {document!r} est absent du JSON")

def _contributions(
    data: Mapping[str, Any],
    pipeline: str,
    view: str,
    references: Mapping[str, str],
    qualite: str,
) -> list[tuple[str, dict[str, int]]]:
    """``(document, statistique)`` qui entrent dans la qualité ``qualite``
    (``conditionnelle`` ou ``operationnelle``), lues dans les observations."""
    entrees: list[tuple[str, dict[str, int]]] = []
    for document in data["documents"]:
        if (document["pipeline"], document["view"]) != (pipeline, view):
            continue
        score = document["scores"][0]
        if score["applicability"] != "applicable":
            continue
        identifiant = document["document_id"]
        vert = score["availability"] == "available"
        if qualite == "conditionnelle":
            stat = _stat(score["stat"])
            if vert and score["validity"] == "valid" and stat is not None:
                entrees.append((identifiant, stat))
            continue
        if score["availability"] == "gt_unreadable":
            continue
        if vert:
            brute = (
                score["stat"]
                if score["validity"] == "valid"
                else score["stat_partielle"]
            )
            stat = _stat(brute)
            if stat is None:
                raise AssertionError(
                    f"{identifiant} : observation {score['validity']} sans statistique "
                    "dans le JSON (CONTRATS.md § 2.1 f)"
                )
            entrees.append((identifiant, stat))
            continue
        # Une unité sans sortie exploitable est notée comme une sortie vide : sa
        # statistique « sortie vide » est dans le JSON (D3), sous un nom que le
        # contrat ne fixe pas — on prend toute statistique de l'observation
        # hors ``stat_partielle``, la première non nulle.
        candidates = [
            s
            for nom, valeur in score.items()
            if nom != "stat_partielle" and (s := _stat(valeur)) is not None
        ]
        if not candidates:
            raise AssertionError(
                f"{identifiant} ({score['availability']}) : aucune statistique "
                "« sortie vide » sérialisée dans le JSON — l'opérationnel n'est pas "
                "recalculable (CONTRATS.md D3)"
            )
        vide = candidates[0]
        attendu = {
            "substitutions": 0,
            "deletions": len(references[identifiant]),
            "insertions": 0,
            "reference_length": len(references[identifiant]),
        }
        assert vide == attendu, (
            f"{identifiant} : la statistique « sortie vide » sérialisée est {vide}, "
            f"une sortie vide donnerait {attendu}"
        )
        entrees.append((identifiant, vide))
    return entrees


def recalcule(
    data: Mapping[str, Any],
    pipeline: str,
    view: str,
    references: Mapping[str, str],
    qualite: str,
    ponderation: str,
    grappes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Recalcule, **sans** ``cinoc.evaluation.aggregation``, l'agrégat CER d'une
    qualité à partir des seules observations sérialisées (somme des statistiques,
    ``Fraction``). ``grappes`` (document → grappe) n'est lu dans le JSON que si la
    pondération est « par grappe » et que l'appelant n'en donne pas.
    """
    contributions = _contributions(data, pipeline, view, references, qualite)
    somme = _somme([stat for _, stat in contributions])
    n = somme["reference_length"]
    macro_exact: Fraction | None = None
    scalaires = [
        (document, Fraction(_erreurs(stat), stat["reference_length"]))
        for document, stat in contributions
        if stat["reference_length"] > 0
    ]
    if scalaires:
        if ponderation == "cluster":
            par_grappe: dict[str, list[Fraction]] = {}
            for document, scalaire in scalaires:
                cle = (
                    grappes[document]
                    if grappes
                    else grappe_serialisee(data, document)
                )
                par_grappe.setdefault(cle, []).append(scalaire)
            moyennes = [sum(g) / len(g) for g in par_grappe.values()]
            macro_exact = sum(moyennes) / len(moyennes)
        else:
            macro_exact = sum(s for _, s in scalaires) / len(scalaires)
    return {
        "stat": somme if contributions else None,
        "value": None if n == 0 else _erreurs(somme) / n,
        "support": len(contributions),
        "macro": macro_exact,
        "macro_support": len(scalaires),
    }


def agregat_json(
    data: Mapping[str, Any], pipeline: str, view: str, qualite: str
) -> Mapping[str, Any]:
    """L'agrégat CER publié (JSON) d'une qualité pour (pipeline, vue)."""
    cle = (
        "conditional_aggregate"
        if qualite == "conditionnelle"
        else "operational_aggregate"
    )
    for entree in data["pipelines"]:
        if (entree["pipeline"], entree["view"]) == (pipeline, view):
            for score in entree[cle]:
                if score["metric"] == "cer":
                    return score  # type: ignore[no-any-return]
    raise AssertionError(f"({pipeline!r}, {view!r}) absent du JSON")


def verifie_agregat(
    data: Mapping[str, Any],
    pipeline: str,
    view: str,
    references: Mapping[str, str],
    qualite: str,
    ponderation: str,
    grappes: Mapping[str, str] | None = None,
) -> None:
    """Le publié égale le recalculé : statistique, micro (exact), supports, macro
    (à l'arrondi flottant près : l'exactitude de la conversion est D5)."""
    attendu = recalcule(data, pipeline, view, references, qualite, ponderation, grappes)
    publie = agregat_json(data, pipeline, view, qualite)
    nom = f"{pipeline}/{qualite}"
    stat = _stat(publie["stat"])
    assert stat == attendu["stat"], (
        f"{nom} : statistique {stat} ≠ recalculée {attendu['stat']}"
    )
    assert publie["value"] == attendu["value"], (
        f"{nom} : micro {publie['value']!r} ≠ recalculé {attendu['value']!r}"
    )
    assert publie["support"] == attendu["support"], f"{nom} : support"
    assert publie["macro_support"] == attendu["macro_support"], f"{nom} : support macro"
    if attendu["macro"] is None:
        assert publie["macro"] is None, f"{nom} : macro publié sans observation"
    else:
        assert publie["macro"] is not None, f"{nom} : macro absent"
        assert abs(Fraction(publie["macro"]) - attendu["macro"]) <= Fraction(
            1, 10**12
        ), f"{nom} : macro {publie['macro']!r} ≠ recalculé {float(attendu['macro'])!r}"


def run_decisions(
    tmp_path: Path, analyses: Sequence[str] | None = ("decisions",)
) -> RunResult:
    """``c09`` : le correcteur **réel** (client scripté) sur les cinq documents de
    ``test_ce_saknussemm_issues``, avec l'analyse des décisions (``analyses=None`` :
    les analyses par défaut, sans elle)."""
    chaine = pipeline(
        "p",
        step("seg", "ce_pages", out_type=T.LAYOUT),
        step("corr", "ce_sak", in_type=T.LAYOUT, out_type=T.CORRECTED_TEXT),
    )
    return execute(
        spec(
            corpus(tmp_path, dict.fromkeys(sak.LAYOUTS, sak.REFERENCE)),
            [chaine],
            [text_view(candidates=(T.CORRECTED_TEXT,))],
            analyses=None if analyses is None else list(analyses),
        ),
        registry_with(sak._Pages(), sak._corrector(sak._ScriptedClient(sak._script()))),
    )

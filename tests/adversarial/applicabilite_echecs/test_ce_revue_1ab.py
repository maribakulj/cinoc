"""Tranche 1b — la revue indépendante de la validation finale de 1a + 1b.

Révision n° 7 de ``CONTRATS.md``, « Précisions tranchées le 28/11 après la
validation finale de 1a + 1b » (défauts D1 à D15, questions Q1 à Q9). Chaque
test traduit **une** précision, citée en docstring avec son défaut ; chacun a un
contre-exemple exécutable dans ``rapports/revue-1ab/`` (scripts ``cNN``), dont
les corpus et les pipelines sont repris ici.

Les points qui se lisent **dans le rapport** (D6 affiché, D7, D8 rendu, D11
libellés, Q9 côté consommateur) sont dans
``tests/adversarial/rapports/test_ce_revue_1ab_rapport.py``.

Les noms que le contrat ne fixe pas (le champ qui porte la statistique « sortie
vide », celui qui porte la grappe d'un document, le statut exploratoire de
``significance_p``, la forme d'un ensemble d'issues) ne sont **pas** inventés
ici : les tests les cherchent par leur structure et disent ce qui manque.
"""

from __future__ import annotations

import ast
import json
import math
import tempfile
from collections.abc import Mapping, Sequence
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from cinoc.adapters.extension import AdapterStepError
from cinoc.adapters.storage.history_store import HistoryRecord
from cinoc.app.history import series_insight
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.evaluation.analysis import PairwiseDifference
from cinoc.evaluation.calibration import calibration_from_pairs
from cinoc.evaluation.result import SCHEMA_VERSION, RunResult
from tests.adversarial._contrat import (
    COMPTES_ENTIERS,
    COMPTES_PAR_CODE,
    agregat_operationnel,
    composante,
    corpus_declare,
    document_en_grappe,
    politique_empty_page,
)
from tests.adversarial._hypothese import DETERMINISTE

from ._kit import (
    T,
    corpus,
    execute,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)
from ._kit_revue import (
    LAYOUT_ILLISIBLE,
    NON_UTF8,
    BriqueOctets,
    layout_octets,
    run_decisions,
    verifie_agregat,
    vue_layout,
)

pytestmark = pytest.mark.tranche("1b")

POLITIQUES = ("exclude", "empty_page")
REF = "abcdefghij"
RACINE = Path(__file__).resolve().parents[3]


def _json(result: RunResult) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(result.model_dump_json())
    return data


def _payloads(result: RunResult, kind: str) -> list[Any]:
    return [a.payload for a in result.analyses if a.payload.kind == kind]


# --------------------------------------------------------------------------
# D1 : « not_in_view » est une propriété du pipeline, jamais de ses échecs.
# --------------------------------------------------------------------------


def _hors_vue(tmp_path: Path, politique: str) -> RunResult:
    """``c23`` : la vue « corrige » ne voit que ``CORRECTED_TEXT``. ``P`` (un OCR
    seul, ``RAW_TEXT``) ne la voit pas et échoue sur ``d1`` ; ``Q`` (OCR puis
    correction) la voit et réussit partout."""
    refs = {"d1": REF, "d2": REF, "d3": REF}
    p = BriqueOctets(
        "ce_ocr_p",
        {"d1": AdapterStepError("panne"), "d2": REF.encode(), "d3": REF.encode()},
    )
    q_ocr = BriqueOctets("ce_ocr_q", dict.fromkeys(refs, b"abcdefghiX"))
    q_corr = BriqueOctets(
        "ce_corr_q",
        dict.fromkeys(refs, REF.encode()),
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    chaine_q = pipeline(
        "Q",
        step("ocr", "ce_ocr_q"),
        step("corr", "ce_corr_q", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT),
    )
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline("P", step("ocr", "ce_ocr_p")), chaine_q],
            [text_view("corrige", candidates=(T.CORRECTED_TEXT,))],
            failure_policy=politique,
        ),
        registry_with(p, q_ocr, q_corr),
    )


@pytest.mark.parametrize("politique", POLITIQUES)
def test_d1__un_pipeline_hors_vue_l_est_sur_tous_ses_documents_echecs_compris(
    tmp_path: Path, politique: str
) -> None:
    """D1 (§ 2.1 b ; « ``not_in_view`` est une propriété du pipeline ») : il se lit
    sur les types de sortie **déclarés** par les étapes, jamais sur ce qu'une
    unité a produit. ``P`` ne déclare aucun type candidat de la vue : ``d2`` et
    ``d3`` sont ``not_in_view`` — et ``d1`` aussi, quoiqu'il ait échoué (axe 1,
    non axe 2). ``c23`` : ``d1`` restait ``applicable`` + ``step_failed``."""
    result = _hors_vue(tmp_path, politique)
    axe1 = {
        d.document_id: d.scores[0].applicability
        for d in result.documents
        if d.pipeline == "P"
    }
    assert axe1 == dict.fromkeys(("d1", "d2", "d3"), "not_in_view"), axe1


@pytest.mark.parametrize("politique", POLITIQUES)
def test_d1__un_pipeline_hors_vue_ne_recoit_aucun_agregat_dans_cette_vue(
    tmp_path: Path, politique: str
) -> None:
    """D1 : « un pipeline hors vue n'entre ni dans la famille F de cette vue, ni
    dans ses supports, ni dans son tri ». Il ne reçoit donc **aucun agrégat** dans
    cette vue : pas d'entrée, ou des agrégats sans valeur, sans statistique, sans
    attendu ni support. ``c23`` : ``P`` recevait ``0/1 attendu`` (son échec) sous
    ``exclude`` et une valeur **1,0** sous ``empty_page``."""
    data = _json(_hors_vue(tmp_path, politique))
    for entree in data["pipelines"]:
        if entree["pipeline"] != "P":
            continue
        scores = [
            score
            for valeur in entree.values()
            if isinstance(valeur, list)
            for score in valeur
            if isinstance(score, dict) and "metric" in score
        ]
        for score in scores:
            assert (
                score["value"] is None
                and score["stat"] is None
                and not score["support"]
                and not score["expected"]
            ), f"le pipeline hors vue P reçoit l'agrégat {score}"


@pytest.mark.parametrize("politique", POLITIQUES)
def test_d1__un_pipeline_hors_vue_n_entre_ni_dans_les_supports_ni_dans_le_tri(
    tmp_path: Path, politique: str
) -> None:
    """D1 : ni dans les supports (apparié, global), ni dans le tri. ``c23`` : la
    paire (``P``, ``Q``) existait, avec un support vide."""
    result = _hors_vue(tmp_path, politique)
    for comparaison in _payloads(result, "comparison"):
        for paire_ in comparaison.pairs:
            assert "P" not in (paire_.a, paire_.b), (paire_.a, paire_.b)
        support = comparaison.global_support
        assert "P" not in support.ranking
        assert "P" not in support.micro and "P" not in support.macro


def _famille_a_b_c(tmp_path: Path, c_echoue: bool) -> RunResult:
    """``c24`` : ``A`` et ``B`` (OCR puis correction) sont vus par la vue
    « corrige » ; ``C`` (OCR seul) ne l'est pas, et échoue ou non sur ``d0``."""
    refs = {f"d{i}": REF for i in range(4)}

    def chaine(nom: str, corrige: bytes) -> tuple[Any, Any, Any]:
        ocr = BriqueOctets(f"ce_o{nom}", dict.fromkeys(refs, b"x"))
        corr = BriqueOctets(
            f"ce_c{nom}",
            dict.fromkeys(refs, corrige),
            in_type=T.RAW_TEXT,
            out_type=T.CORRECTED_TEXT,
        )
        return (
            ocr,
            corr,
            pipeline(
                nom,
                step("ocr", f"ce_o{nom}"),
                step(
                    "corr", f"ce_c{nom}", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT
                ),
            ),
        )

    oa, ca, pa = chaine("A", b"abcdefghiX")
    ob, cb, pb = chaine("B", b"abcdefghXX")
    oc = BriqueOctets(
        "ce_oC",
        {
            d: AdapterStepError("panne") if (c_echoue and d == "d0") else REF.encode()
            for d in refs
        },
    )
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pa, pb, pipeline("C", step("ocr", "ce_oC"))],
            [text_view("corrige", candidates=(T.CORRECTED_TEXT,))],
        ),
        registry_with(oa, ca, ob, cb, oc),
    )


def test_d1__les_echecs_d_un_pipeline_hors_vue_ne_changent_le_support_de_personne(
    tmp_path: Path,
) -> None:
    """D1 (« ses échecs ne changent le support de personne ») : que ``C``, hors
    vue, échoue sur ``d0`` ou non, le support global de la famille (``A``, ``B``)
    reste ``d0`` à ``d3`` et le tri reste (``A``, ``B``). ``c24`` : avec l'échec
    de ``C``, le support global devenait **vide**, et le tri aussi."""
    publie = {}
    for c_echoue in (False, True):
        (tmp_path / str(c_echoue)).mkdir()
        result = _famille_a_b_c(tmp_path / str(c_echoue), c_echoue)
        (comparaison,) = _payloads(result, "comparison")
        publie[c_echoue] = (
            comparaison.global_support.micro_documents,
            comparaison.global_support.ranking,
            sorted(sorted((p.a, p.b)) for p in comparaison.pairs),
        )
    assert publie[False] == (("d0", "d1", "d2", "d3"), ("A", "B"), [["A", "B"]])
    assert publie[True] == publie[False], (
        "l'échec de C, hors vue, a changé les supports"
    )


# --------------------------------------------------------------------------
# D2, Q1 : une sortie illisible est notée comme une sortie vide.
# --------------------------------------------------------------------------

REFS_D2 = {
    "d1": "abcdefghij",
    "d2": "klmnopqrst",
    "d3": "uvwxyz0123",
    "d4": "ABCDEFGHIJ",
}


def _illisible(tmp_path: Path, politique: str) -> tuple[RunResult, dict[str, str]]:
    """``c06`` : trois pipelines sur quatre pages (mise en page projetée en texte).
    ``A`` : ``d2`` **illisible**, ``d3`` en échec moteur, ``d4`` partielle
    (``ABCDE``). ``C`` : comme ``A``, mais ``d2`` est une page **vide** honnête
    (rien de lu). ``B`` : ``d2`` vide, ``d4`` tronquée."""
    ref = REFS_D2
    sorties_a = {
        "d1": layout_octets(ref["d1"]),
        "d2": LAYOUT_ILLISIBLE,
        "d3": AdapterStepError("panne"),
        "d4": layout_octets("ABCDE"),
    }
    a = BriqueOctets("ce_a", sorties_a, partial=frozenset({"d4"}), out_type=T.LAYOUT)
    c = BriqueOctets(
        "ce_c",
        {**sorties_a, "d2": layout_octets("")},
        partial=frozenset({"d4"}),
        out_type=T.LAYOUT,
    )
    b = BriqueOctets(
        "ce_b",
        {
            "d1": layout_octets(ref["d1"]),
            "d2": layout_octets(""),
            "d3": layout_octets(ref["d3"]),
            "d4": layout_octets("ABCDEFG"),
        },
        truncate=frozenset({"d4"}),
        out_type=T.LAYOUT,
    )
    run_spec = spec(
        corpus(tmp_path, ref),
        [
            pipeline(nom, step("ocr", brique, out_type=T.LAYOUT))
            for nom, brique in (("A", "ce_a"), ("B", "ce_b"), ("C", "ce_c"))
        ],
        [vue_layout()],
        failure_policy=politique,
    )
    return execute(run_spec, registry_with(a, b, c)), ref


@pytest.mark.parametrize("politique", POLITIQUES)
def test_d2__une_sortie_illisible_est_notee_comme_une_sortie_vide_dans_l_operationnel(
    tmp_path: Path, politique: str
) -> None:
    """D2, Q1 (§ 2.1 c, « Sensibilité ``empty_page`` » ; § 2.1 f) :
    ``output_unreadable`` est un échec de production, noté comme une sortie vide
    dans la qualité opérationnelle, exactement comme ``step_failed``. ``A``
    (``d1`` exacte, ``d2`` illisible, ``d3`` en échec, ``d4`` partielle à 5
    erreurs) : 0 + 10 + 10 + 5 = **25 erreurs sur 40** caractères de référence,
    soit 0,625. ``c06`` : 15 sur 30 — ``d2`` n'y entrait pas, l'agrégat était
    **meilleur** (0,5) qu'avec une sortie vide."""
    result, _ = _illisible(tmp_path, politique)
    operationnel = agregat_operationnel(result, "A", "cer")
    erreurs = sum(
        composante(operationnel, nom)
        for nom in ("substitutions", "deletions", "insertions")
    )
    assert (erreurs, composante(operationnel, "reference_length")) == (25, 40)
    assert operationnel.value == 0.625


@pytest.mark.parametrize("politique", POLITIQUES)
def test_d2__une_sortie_illisible_n_est_jamais_mieux_notee_qu_une_sortie_vide(
    tmp_path: Path, politique: str
) -> None:
    """D2 (« une sortie inexploitable n'est jamais mieux notée qu'une sortie vide
    honnête ») : ``A`` et ``C`` ne diffèrent que par ``d2`` (illisible contre page
    vide) ; leurs qualités opérationnelles sont **égales** (``25/40``)."""
    result, _ = _illisible(tmp_path, politique)
    a = agregat_operationnel(result, "A", "cer")
    c = agregat_operationnel(result, "C", "cer")
    assert a.stat == c.stat, f"A (illisible) {a.stat} ≠ C (vide honnête) {c.stat}"


def test_d2__sous_empty_page_l_illisible_est_note_vide_comme_l_echec_moteur(
    tmp_path: Path,
) -> None:
    """D2 (« noté comme une sortie vide … sous ``empty_page``, exactement comme
    ``step_failed`` ») : sous la politique ``empty_page``, l'observation de ``d2``
    (illisible) porte la statistique d'une page vide (10 suppressions sur 10
    caractères de référence), comme ``d3`` (échec moteur). ``c06`` : ``d2`` n'en
    portait aucune."""
    politique_empty_page()
    result, _ = _illisible(tmp_path, "empty_page")
    data = _json(result)
    vides = {}
    for document in data["documents"]:
        if document["pipeline"] == "A" and document["document_id"] in ("d2", "d3"):
            score = document["scores"][0]
            vides[document["document_id"]] = [
                valeur
                for nom, valeur in score.items()
                if nom != "stat_partielle"
                and isinstance(valeur, dict)
                and "reference_length" in valeur
            ]
    assert vides["d3"], "contrôle : l'échec moteur porte sa statistique vide"
    assert vides["d2"] == vides["d3"], (
        f"d2 (illisible) {vides['d2']} ≠ d3 (échec moteur) {vides['d3']}"
    )


# --------------------------------------------------------------------------
# D3, D4 : tout agrégat publié se recalcule depuis le seul JSON.
# --------------------------------------------------------------------------


REFS_D3 = {
    "d1": "abcdefghij",
    "d2": "klmnopqrst",
    "d3": "uvwxyz0123",
    "d4": "ABCDEFGHIJ",
}


def _echecs_et_partielles(tmp_path: Path, politique: str) -> RunResult:
    """``A`` : ``d2`` en échec moteur, ``d3`` partielle (``uvwxy``), ``d4`` tronquée
    (``ABCDEFG``) ; ``B`` : ``d2`` vide, ``d3`` bruitée. Aucune sortie illisible
    (c'est D2) : seul l'échec moteur, noté vide, est en jeu."""
    ref = REFS_D3
    a = BriqueOctets(
        "ce_a",
        {
            "d1": layout_octets(ref["d1"]),
            "d2": AdapterStepError("panne"),
            "d3": layout_octets("uvwxy"),
            "d4": layout_octets("ABCDEFG"),
        },
        partial=frozenset({"d3"}),
        truncate=frozenset({"d4"}),
        out_type=T.LAYOUT,
    )
    b = BriqueOctets(
        "ce_b",
        {
            "d1": layout_octets(ref["d1"]),
            "d2": layout_octets(""),
            "d3": layout_octets("uvwxyz01##"),
            "d4": layout_octets(ref["d4"]),
        },
        out_type=T.LAYOUT,
    )
    return execute(
        spec(
            corpus(tmp_path, ref),
            [
                pipeline(nom, step("ocr", brique, out_type=T.LAYOUT))
                for nom, brique in (("A", "ce_a"), ("B", "ce_b"))
            ],
            [vue_layout()],
            failure_policy=politique,
        ),
        registry_with(a, b),
    )


def test_d3__le_conditionnel_et_l_operationnel_se_recalculent_depuis_le_json(
    tmp_path: Path,
) -> None:
    """D3 (« l'archive porte, pour chaque unité notée vide, la statistique
    « sortie vide » qui entre dans l'opérationnel ») : la somme des statistiques
    **sérialisées** (oracle indépendant, ``Fraction``, sans
    ``evaluation.aggregation``) redonne le conditionnel et l'opérationnel de
    chaque pipeline, sous les deux politiques. ``c06`` : l'unité en échec n'a, sous
    ``exclude``, aucune statistique dans le JSON : l'opérationnel de ``A``
    (``d1`` exacte, ``d2`` vide, ``d3`` et ``d4`` telles que produites) ne se
    recalcule pas."""
    for politique in POLITIQUES:
        (tmp_path / politique).mkdir()
        result = _echecs_et_partielles(tmp_path / politique, politique)
        data = _json(result)
        for nom in ("A", "B"):
            for qualite in ("conditionnelle", "operationnelle"):
                try:
                    verifie_agregat(data, nom, "texte", REFS_D3, qualite, "document")
                except AssertionError as exc:
                    raise AssertionError(f"[{politique}] {exc}") from exc


GRAPPES = {"a1": "g-nord", "a2": "g-nord", "a3": "g-nord", "b1": "g-sud", "b2": "g-sud"}
REFS_GRAPPES = dict.fromkeys(GRAPPES, "abcdefghijklmnopqrst")


def _en_grappes(tmp_path: Path) -> CorpusSpec:
    base = corpus(tmp_path, REFS_GRAPPES)
    documents = tuple(document_en_grappe(d, GRAPPES[d.id]) for d in base.documents)
    return corpus_declare(
        CorpusSpec(name="ce", documents=documents),
        target_population="volumes du fonds Nord et du fonds Sud",
        cluster_weighting="cluster",
    )


def test_d4__le_macro_par_grappe_se_recalcule_depuis_le_json(tmp_path: Path) -> None:
    """D4 (« l'archive porte, pour chaque document, sa grappe » ; B3) : le macro
    par grappe publié se recalcule depuis le seul JSON, grappe de chaque document
    comprise. Trois documents de la grappe « nord », deux de « sud » (un document
    fautif) : le macro par grappe diffère du macro par document. ``c21`` : aucun
    document du JSON ne porte sa grappe, le macro (0,25) n'est pas recalculable
    (0,125 par document)."""
    sorties = {d: b"abcdefghijklmnopqrst" for d in REFS_GRAPPES} | {
        "b1": b"abcdefghij##########"
    }
    brique = BriqueOctets("ce_g", sorties)
    result = execute(
        spec(
            _en_grappes(tmp_path),
            [pipeline("A", step("ocr", "ce_g"))],
            [text_view()],
        ),
        registry_with(brique),
    )
    data = _json(result)
    assert data["pipelines"][0]["cluster_weighting"] == "cluster"
    for qualite in ("conditionnelle", "operationnelle"):
        verifie_agregat(data, "A", "texte", REFS_GRAPPES, qualite, "cluster")


#: Ce qu'un document peut devenir : exact, bruité (k substitutions), échec
#: moteur, sortie illisible, partielle ou tronquée (préfixe, k manquants), vide.
_DESTINS = ("exact", "bruit", "echec", "illisible", "partielle", "tronquee", "vide")
_ALPHABET = "abcdefghijklmnopqrstuvwxyz"


@st.composite
def _scenarios(draw: st.DrawFn) -> dict[str, Any]:
    n = draw(st.integers(min_value=3, max_value=6))
    documents = []
    for i in range(n):
        documents.append(
            {
                "id": f"d{i}",
                "longueur": draw(st.integers(min_value=6, max_value=24)),
                "destin": draw(st.sampled_from(_DESTINS)),
                "k": draw(st.integers(min_value=1, max_value=5)),
                "grappe": draw(st.sampled_from(("g-un", "g-deux", "g-trois"))),
            }
        )
    return {
        "documents": documents,
        "ponderation": draw(st.sampled_from(("document", "cluster"))),
        "politique": draw(st.sampled_from(POLITIQUES)),
    }


def _sortie(document: Mapping[str, Any]) -> bytes | AdapterStepError:
    ref = _ALPHABET[: document["longueur"]]
    k = document["k"]
    return {
        "exact": lambda: layout_octets(ref),
        "bruit": lambda: layout_octets("#" * k + ref[k:]),
        "echec": lambda: AdapterStepError("panne"),
        "illisible": lambda: LAYOUT_ILLISIBLE,
        "partielle": lambda: layout_octets(ref[:-k]),
        "tronquee": lambda: layout_octets(ref[:-k]),
        "vide": lambda: layout_octets(""),
    }[document["destin"]]()


@settings(DETERMINISTE, max_examples=25)
@given(scenario=_scenarios())
def test_d3_d4__propriete_tout_agregat_publie_se_recalcule_depuis_le_json(
    scenario: dict[str, Any],
) -> None:
    """D3, D4 (invariant I) : pour tout corpus de 3 à 6 pages à destins variés
    (exacte, bruitée, en échec, illisible, partielle, tronquée, vide), à grappes
    quelconques, sous chaque politique et chaque pondération, **chaque** agrégat
    publié — conditionnel, opérationnel, micro, macro par document et par grappe —
    se recalcule depuis le seul JSON avec un oracle indépendant."""
    documents = scenario["documents"]
    refs = {d["id"]: _ALPHABET[: d["longueur"]] for d in documents}
    grappes = {d["id"]: d["grappe"] for d in documents}
    brique = BriqueOctets(
        "ce_prop",
        {d["id"]: _sortie(d) for d in documents},
        partial=frozenset(d["id"] for d in documents if d["destin"] == "partielle"),
        truncate=frozenset(d["id"] for d in documents if d["destin"] == "tronquee"),
        out_type=T.LAYOUT,
    )
    with tempfile.TemporaryDirectory() as tmp:
        base = corpus(Path(tmp), refs)
        corpus_ = corpus_declare(
            CorpusSpec(
                name="ce",
                documents=tuple(
                    document_en_grappe(d, grappes[d.id]) for d in base.documents
                ),
            ),
            target_population="population de test",
            cluster_weighting=scenario["ponderation"],
        )
        result = execute(
            spec(
                corpus_,
                [pipeline("P", step("ocr", "ce_prop", out_type=T.LAYOUT))],
                [vue_layout()],
                failure_policy=scenario["politique"],
            ),
            registry_with(brique),
        )
    data = _json(result)
    for qualite in ("conditionnelle", "operationnelle"):
        verifie_agregat(data, "P", "texte", refs, qualite, scenario["ponderation"])


# --------------------------------------------------------------------------
# D5 : le macro est exact.
# --------------------------------------------------------------------------


def _macro_publie(
    couples: Sequence[tuple[int, int]], ponderation: str, grappes: Sequence[str]
) -> tuple[float | None, Fraction]:
    """Le macro CER publié de ``couples`` ``(erreurs, longueur)`` — une page par
    couple, ``erreurs`` substitutions exactement —, et sa valeur **exacte**."""
    refs = {f"d{i}": "a" * n for i, (_, n) in enumerate(couples)}
    sorties = {
        f"d{i}": ("b" * e + "a" * (n - e)).encode() for i, (e, n) in enumerate(couples)
    }
    brique = BriqueOctets("ce_macro", sorties)
    with tempfile.TemporaryDirectory() as tmp:
        base = corpus(Path(tmp), refs)
        corpus_ = corpus_declare(
            CorpusSpec(
                name="ce",
                documents=tuple(
                    document_en_grappe(d, grappes[i])
                    for i, d in enumerate(base.documents)
                ),
            ),
            target_population="population de test",
            cluster_weighting=ponderation,
        )
        result = execute(
            spec(corpus_, [pipeline("P", step("ocr", "ce_macro"))], [text_view()]),
            registry_with(brique),
        )
    publie = result.pipelines[0].conditional_aggregate[0].macro
    scalaires = [Fraction(e, n) for e, n in couples]
    if ponderation == "cluster":
        groupes: dict[str, list[Fraction]] = {}
        for scalaire, grappe in zip(scalaires, grappes, strict=True):
            groupes.setdefault(grappe, []).append(scalaire)
        moyennes = [sum(g) / len(g) for g in groupes.values()]
        return publie, sum(moyennes) / len(moyennes)
    return publie, sum(scalaires) / len(scalaires)


@settings(DETERMINISTE, max_examples=40)
@example(couples=[(409, 591), (46, 227)], ponderation="document")
@example(couples=[(409, 591), (46, 227), (3, 7)], ponderation="cluster")
@given(
    couples=st.lists(
        st.integers(min_value=1, max_value=60).flatmap(
            lambda n: st.tuples(st.integers(min_value=0, max_value=n), st.just(n))
        ),
        min_size=2,
        max_size=5,
    ),
    ponderation=st.sampled_from(("document", "cluster")),
)
def test_d5__le_macro_est_la_moyenne_exacte_des_scalaires_exacts(
    couples: list[tuple[int, int]], ponderation: str
) -> None:
    """D5 (§ 2.1 a, R1) : le macro est la moyenne, en ``Fraction``, des scalaires
    exacts par document (puis par grappe, selon la pondération), **une seule**
    conversion flottante à la finalisation : le flottant publié égale
    ``float(moyenne exacte)``, sans écart d'un ulp. ``c02`` : ``fsum`` de
    scalaires déjà arrondis, puis une division — 671 écarts sur 3000 tirages ;
    (409/591, 46/227) donne 0.4473452745663663 au lieu de 0.44734527456636625."""
    grappes = [("g-pair", "g-impair")[i % 2] for i in range(len(couples))]
    publie, exact = _macro_publie(couples, ponderation, grappes)
    assert publie == float(exact), (publie, float(exact), couples, ponderation)


# --------------------------------------------------------------------------
# D10, Q2 : les comparaisons portent sur les observations du principal.
# --------------------------------------------------------------------------

_PAGES = {f"d{i}": f"texte de la page {i:02d} " * 3 for i in range(10)}


def _bruit(texte: str, k: int) -> bytes:
    return (texte[:-k] + "#" * k).encode()


def _paire_a_b(tmp_path: Path, politique: str) -> RunResult:
    """``c07`` : ``A`` échoue sur ``d0``-``d3`` et se déclare partielle sur ``d4`` ;
    ``B`` termine tout, avec trois erreurs par page."""
    a = BriqueOctets(
        "ce_a",
        {
            d: AdapterStepError("panne") if i < 4 else _bruit(t, 1)
            for i, (d, t) in enumerate(_PAGES.items())
        },
        partial=frozenset({"d4"}),
    )
    b = BriqueOctets("ce_b", {d: _bruit(t, 3) for d, t in _PAGES.items()})
    return execute(
        spec(
            corpus(tmp_path, _PAGES),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view()],
            failure_policy=politique,
        ),
        registry_with(a, b),
    )


#: Par politique : le support commun attendu, et le tri qu'il donne.
_SUPPORTS_D10 = (
    # observations complètes (d5-d9) : A (1 erreur par page) devant B (3).
    ("exclude", tuple(f"d{i}" for i in range(5, 10)), ("A", "B")),
    # observations opérationnelles (d0-d9) : A, vide sur 4 pages, derrière B.
    ("empty_page", tuple(f"d{i}" for i in range(10)), ("B", "A")),
)


def test_d10__test_delta_et_tri_portent_sur_les_memes_observations(
    tmp_path: Path,
) -> None:
    """D10, Q2 (« un test et le Δ qu'il accompagne ont toujours le même
    support » ; § 2.1 c) : le support du test exploratoire de la paire, celui du
    Δ de ``comparison`` et celui du tri global sont **les mêmes**. Sous
    ``exclude``, ce sont les observations complètes (``d5``-``d9``) ; sous
    ``empty_page``, les observations opérationnelles (les dix pages : échecs notés
    vides, partielle telle que produite), et le tri suit ces mêmes valeurs.
    ``c07`` : sous ``empty_page``, le test portait sur 10 pages, le Δ et le tri
    sur 5."""
    for politique, documents, tri in _SUPPORTS_D10:
        (tmp_path / politique).mkdir()
        result = _paire_a_b(tmp_path / politique, politique)
        (comparaison,) = _payloads(result, "comparison")
        (une_paire,) = comparaison.pairs
        etape = f"[{politique}]"
        assert une_paire.micro_documents == documents, f"{etape} support du Δ"
        assert comparaison.global_support.micro_documents == documents, (
            f"{etape} support global"
        )
        assert comparaison.global_support.ranking == tri, f"{etape} tri global"
        (inference,) = _payloads(result, "inference")
        assert inference.n_documents == len(documents), (
            f"{etape} support du test exploratoire : {inference.n_documents} pages, "
            f"le Δ en porte {len(documents)}"
        )
        (p,) = [s for s in result.cross_engine if s.metric.endswith("significance_p")]
        assert p.support == len(documents), f"{etape} support de la p publiée"
        if politique == "empty_page":
            # Le Δ est celui des agrégats opérationnels, sur les mêmes dix pages.
            for nom in ("A", "B"):
                operationnel = agregat_operationnel(result, nom, "cer").value
                assert une_paire.micro[nom] == operationnel, (nom, une_paire.micro)


# --------------------------------------------------------------------------
# D9 : sortie non UTF-8, vérité terrain non UTF-8.
# --------------------------------------------------------------------------


def test_d9__une_sortie_non_utf8_est_illisible_et_le_run_continue(
    tmp_path: Path,
) -> None:
    """D9 (« un octet non UTF-8 dans une sortie donne ``output_unreadable``, jamais
    une exception qui perd le run ») : ``A`` rend des octets non UTF-8 pour ``d2``,
    ``B`` termine. Le run n'est pas perdu : ``d2`` est ``output_unreadable`` pour
    ``A``, ``d1`` est noté, ``B`` est noté partout. ``c04`` : ``UnicodeDecodeError``
    qui emportait le run."""
    refs = {"d1": REF, "d2": "klmnopqrst"}
    a = BriqueOctets("ce_a", {"d1": REF.encode(), "d2": NON_UTF8})
    b = BriqueOctets("ce_b", {"d1": b"abcdefghiX", "d2": b"klmnopqrsX"})
    run_spec = spec(
        corpus(tmp_path, refs),
        [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
        [text_view()],
    )
    try:
        result = execute(run_spec, registry_with(a, b))
    except Exception as exc:  # noqa: BLE001 - on rapporte la perte du run
        pytest.fail(f"le run est perdu : {type(exc).__name__} : {exc}")
    axes = {
        (d.pipeline, d.document_id): (d.scores[0].availability, d.scores[0].value)
        for d in result.documents
    }
    assert axes[("A", "d2")][0] == "output_unreadable"
    assert axes[("A", "d1")] == ("available", 0.0)
    assert axes[("B", "d2")][0] == "available"


def test_d9__une_verite_terrain_non_utf8_refuse_le_run_avant_tout_appel(
    tmp_path: Path,
) -> None:
    """D9 (F8 ; « ``gt_unreadable`` … est refusé **avant tout appel** : la VT est
    décodée et hachée à la validation ») : une vérité terrain présente mais non
    UTF-8 refuse le run, par une erreur typée, avant le premier appel de moteur
    (zéro appel compté). ``c05`` : ``UnicodeDecodeError`` à l'évaluation, après
    deux appels payés."""
    refs = {"d1": "abc", "d2": "def"}
    corpus_ = corpus(tmp_path, refs)
    Path(corpus_.documents[1].ground_truths[0].uri).write_bytes(b"\xff\xfedef")
    brique = BriqueOctets("ce_a", {"d1": b"abc", "d2": b"def"})
    run_spec = spec(corpus_, [pipeline("A", step("ocr", "ce_a"))], [text_view()])
    try:
        execute(run_spec, registry_with(brique))
    except CinocError:
        pass
    except Exception as exc:  # noqa: BLE001 - on rapporte le type reçu
        pytest.fail(
            f"{type(exc).__name__} au lieu d'un refus typé (CinocError) ; "
            f"moteurs déjà exécutés : {brique.calls}"
        )
    else:
        pytest.fail(f"run noté malgré une VT illisible ; appels : {brique.calls}")
    assert brique.calls == [], f"refus **après** l'exécution de {brique.calls}"


# --------------------------------------------------------------------------
# D12, Q4 : unité tronquée et partielle.
# --------------------------------------------------------------------------


def test_d12__une_unite_tronquee_et_partielle_garde_les_deux_issues_de_son_etape(
    tmp_path: Path,
) -> None:
    """D12, Q4 (« la troncature reste typée à côté de ``partial``, et pas
    seulement dans ``message`` ») : ``step_issues`` associe à l'étape l'**ensemble
    trié** de ses issues, ici {``partial``, ``truncated``}. ``c10`` :
    ``{'ocr': 'partial'}`` — la troncature n'était que dans le message. La forme de
    l'ensemble (liste triée, ``frozenset``…) n'est pas fixée : seul son contenu et
    son ordre le sont."""
    brique = BriqueOctets(
        "ce_a",
        {"d1": b"abcde"},
        partial=frozenset({"d1"}),
        truncate=frozenset({"d1"}),
    )
    result = execute(
        spec(
            corpus(tmp_path, {"d1": REF}),
            [pipeline("A", step("ocr", "ce_a"))],
            [text_view()],
        ),
        registry_with(brique),
    )
    (unite,) = result.usage
    assert unite.outcome == "partial"
    issues = unite.step_issues["ocr"]
    contenu = [issues] if isinstance(issues, str) else list(issues)
    assert sorted(set(contenu)) == ["partial", "truncated"], (
        f"issues de l'étape : {issues!r}"
    )
    if isinstance(issues, list | tuple):
        assert contenu == sorted(contenu), f"l'ensemble n'est pas trié : {contenu}"
    rejoue = RunResult.model_validate_json(result.model_dump_json())
    assert rejoue.usage[0].step_issues == unite.step_issues


# --------------------------------------------------------------------------
# D14 : classe de calibration exacte.
# --------------------------------------------------------------------------


def test_d14__0_8999999999999999_tombe_dans_la_classe_0_8_0_9() -> None:
    """D14 (M6 ; « la classe se calcule sur ``Fraction(c)``, valeur exacte du
    binaire ») : 0,8999999999999999 est strictement inférieur à 0,9, donc dans
    [0,8 ; 0,9[. Le flottant juste au-dessous de chaque dixième tombe dans la
    classe qui le précède (oracle ``floor(Fraction(c) * 10)``). ``c03`` :
    ``int(c * 10)`` arrondit ``0.8999999999999999 * 10`` à 9,0 et le range dans
    [0,9 ; 1,0]."""
    _, _, bins = calibration_from_pairs([(0.8999999999999999, True)])
    assert [(b.lower, b.upper) for b in bins] == [(0.8, 0.9)], bins
    for k in range(1, 10):
        sous = math.nextafter(k / 10, 0.0)
        classe = math.floor(Fraction(sous) * 10)
        _, _, (cellule,) = calibration_from_pairs([(sous, True)])
        assert (cellule.lower, cellule.upper) == (classe / 10, (classe + 1) / 10), sous


# --------------------------------------------------------------------------
# Q8 : Pettitt sur une série sans variation.
# --------------------------------------------------------------------------


def _serie(valeurs: Sequence[float]) -> list[HistoryRecord]:
    return [
        HistoryRecord(
            run_id=f"r{i}",
            completed_at=f"2026-11-{i + 1:02d}T00:00:00+00:00",
            corpus_name="c",
            normalization_profile=None,
            code_version="x",
            pipeline="p",
            view="v",
            metric="cer",
            value=v,
        )
        for i, v in enumerate(valeurs)
    ]


def test_q8__une_serie_constante_ne_publie_aucune_rupture() -> None:
    """Q8 (« si max |U_t| = 0, la position de rupture n'est pas définie : rien
    n'est publié, pas une « rupture » à p = 1 ») : une série constante de trois
    runs ou plus n'a ni rupture ni run de rupture. Une série qui varie, elle, en
    publie une dès trois runs (le test n'est pas retiré). ``c13`` :
    ``rupture=('r1', 1.0)`` sur ``[0.1, 0.1, 0.1]``."""
    for longueur in (3, 5, 8):
        insight = series_insight(_serie([0.1] * longueur))
        assert insight.rupture is None, f"{longueur} runs constants : {insight.rupture}"
        assert insight.rupture_run_id is None
    assert series_insight(_serie([0.1, 0.3, 0.2, 0.25, 0.15])).rupture is not None


# --------------------------------------------------------------------------
# D13 : schéma v7.
# --------------------------------------------------------------------------


def test_v7__le_run_est_au_schema_7_et_les_versions_anterieures_sont_refusees(
    tmp_path: Path,
) -> None:
    """D13, Q5 (« ``RunResult`` passe en v7, v1 à v6 refusés avec le message de
    re-notation depuis l'archive ») : ``schema_version == 7`` ; un JSON qui se
    déclare v1 à v6 est refusé, pas relu ni converti, avec un message qui dit
    la version reçue et renvoie à la re-notation depuis l'archive. ``c22`` : deux
    « v6 » de sémantiques différentes étaient acceptés sans distinction."""
    brique = BriqueOctets("ce_a", {"d1": REF.encode()})
    result = execute(
        spec(
            corpus(tmp_path, {"d1": REF}),
            [pipeline("A", step("ocr", "ce_a"))],
            [text_view()],
        ),
        registry_with(brique),
    )
    assert SCHEMA_VERSION == 7
    assert result.schema_version == 7
    for ancienne in range(1, 7):
        data = _json(result) | {"schema_version": ancienne}
        try:
            RunResult.model_validate(data)
        except ValueError as exc:
            message = str(exc)
            assert f"v{ancienne}" in message and "archive" in message, message
        else:
            pytest.fail(f"un JSON v{ancienne} est accepté par un code en v7")


# --------------------------------------------------------------------------
# Q9 : une seule représentation de l'agrégat principal.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("politique", POLITIQUES)
def test_q9__le_json_ne_stocke_pas_une_troisieme_copie_de_l_agregat_principal(
    tmp_path: Path, politique: str
) -> None:
    """Q9 (règle 1 de ``CLAUDE.md`` § 5 ; « ``RunResult`` stocke les agrégats
    conditionnel et opérationnel ; le principal est **dérivé** de
    ``failure_policy`` par un accesseur, jamais stocké une seconde fois ») : le
    JSON de chaque pipeline porte les deux qualités et **aucune clé**
    ``aggregate``. Le nom de l'accesseur n'est pas fixé par le contrat : il se
    teste par ce que lit le rapport (``test_ce_revue_1ab_rapport``)."""
    brique = BriqueOctets("ce_a", {"d1": REF.encode(), "d2": b"abcdefghiX"})
    result = execute(
        spec(
            corpus(tmp_path, {"d1": REF, "d2": REF}),
            [pipeline("A", step("ocr", "ce_a"))],
            [text_view()],
            failure_policy=politique,
        ),
        registry_with(brique),
    )
    for entree in _json(result)["pipelines"]:
        assert "conditional_aggregate" in entree and "operational_aggregate" in entree
        assert "aggregate" not in entree, (
            "l'agrégat principal est stocké : troisième copie des agrégats "
            f"(clés : {sorted(entree)})"
        )


# --------------------------------------------------------------------------
# D11 : restes de verdict dans le RunResult.
# --------------------------------------------------------------------------


def _trois_pipelines(tmp_path: Path) -> RunResult:
    """``c11`` : trois pipelines nettement différents sur 14 pages (Friedman
    rejeté, post-hoc de Nemenyi)."""
    refs = {f"d{i:02d}": "abcdefghijklmnopqrst" for i in range(14)}

    def sorties(k: int) -> dict[str, bytes]:
        return {
            d: ("abcdefghijklmnopqrst"[: 20 - k - i % 3] + "#" * (k + i % 3)).encode()
            for i, d in enumerate(refs)
        }

    briques = [
        BriqueOctets(f"ce_{n}", sorties(k)) for n, k in (("a", 0), ("b", 3), ("c", 7))
    ]
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline(n.upper(), step("ocr", f"ce_{n}")) for n in "abc"],
            [text_view()],
            analyses="toutes",
        ),
        registry_with(*briques),
    )


def test_d11__significance_p_porte_le_statut_exploratoire_dans_le_json(
    tmp_path: Path,
) -> None:
    """D11 (« tout scalaire issu de l'ancienne inférence, ``significance_p``
    compris, porte le statut exploratoire ») : chaque ``significance_p`` de
    ``cross_engine`` dit, dans le JSON, qu'il est ``exploratory``. Le nom du champ
    n'est pas fixé : on cherche la valeur dans l'entrée sérialisée. ``c11`` :
    seul le payload ``inference`` portait le statut."""
    data = _json(_trois_pipelines(tmp_path))
    entrees = [
        e for e in data["cross_engine"] if e["metric"].endswith("significance_p")
    ]
    assert entrees, "contrôle : le run publie des significance_p"
    for entree in entrees:
        assert "exploratory" in json.dumps(entree), (
            f"{entree['metric']} ne porte pas le statut exploratoire : {entree}"
        )


def test_d11__une_paire_n_a_plus_de_verdict_booleen(tmp_path: Path) -> None:
    """D11 (« ``PairwiseDifference.significant`` (un verdict booléen) est
    retiré ») : ni le modèle ni le JSON d'une paire du post-hoc ne portent de
    champ ``significant``. ``c11`` : trois paires à ``significant=True``."""
    assert "significant" not in PairwiseDifference.model_fields
    (inference,) = [
        p for p in _payloads(_trois_pipelines(tmp_path), "inference") if p.pairwise
    ]
    assert inference.pairwise, "contrôle : le post-hoc publie ses paires"
    for paire_ in inference.pairwise:
        assert "significant" not in paire_.model_dump(), paire_


# --------------------------------------------------------------------------
# D6 : les classes de lignes sont déclarées, jamais reconstruites.
# --------------------------------------------------------------------------

#: Ce que l'adaptateur déclare sur le corpus de ``test_ce_saknussemm_issues``.
_DECLARE = {
    "corrected": 3,
    "review_required": 1,
    "abstained": 3,
    "refused": {"absorbs_next_line": 1, "too_different_from_source": 2},
    "fallback": {"chunk_error_absorbed": 4},
}


def _chercher(noeud: object, nom: str) -> object:
    """La valeur de la clé ``nom`` n'importe où dans ``noeud`` (absente : ``None``)."""
    if isinstance(noeud, dict):
        if nom in noeud:
            return noeud[nom]
        for valeur in noeud.values():
            trouve = _chercher(valeur, nom)
            if trouve is not None:
                return trouve
    elif isinstance(noeud, list):
        for element in noeud:
            trouve = _chercher(element, nom)
            if trouve is not None:
                return trouve
    return None


def _par_code(valeur: object) -> dict[str, int] | None:
    """Un compte par code : ``{code: n}`` ou ``[{code, n}, …]`` (sinon ``None``)."""
    if isinstance(valeur, dict) and all(isinstance(n, int) for n in valeur.values()):
        return dict(valeur)
    if isinstance(valeur, list) and all(
        isinstance(i, dict) and {"code", "n"} <= set(i) for i in valeur
    ):
        return {i["code"]: i["n"] for i in valeur}
    return None


def test_d6__l_analyse_des_decisions_publie_les_classes_declarees(
    tmp_path: Path,
) -> None:
    """D6 (« l'adaptateur déclare la classe de **chaque** ligne ; l'exécuteur la
    porte ; l'analyse des décisions et le rapport la lisent ») : sur l'adaptateur
    réel, le payload ``decisions`` du pipeline publie exactement les classes
    déclarées — corrigées 3, ``review_required`` 1, abstentions 3, refus par code
    (``too_different_from_source`` 2, ``absorbs_next_line`` 1), replis par code
    (``chunk_error_absorbed`` 4) —, classes **disjointes**. Les noms des
    compteurs sont ceux de ``_contrat.COMPTES_*`` ; le contrat ne fixe pas ceux du
    payload. ``c09`` : « Changées 4 » (corrigées + à revoir), « Refusées 7 » (refus
    + replis), « Intactes 3 »."""
    result = run_decisions(tmp_path)
    declare = result.pipelines[0].line_outcomes
    assert declare is not None
    assert {n: getattr(declare, n) for n in COMPTES_ENTIERS} == {
        n: _DECLARE[n] for n in COMPTES_ENTIERS
    }, "contrôle : ce que l'adaptateur déclare"
    (payload,) = _payloads(result, "decisions")
    (ligne,) = payload.pipelines
    brut = ligne.model_dump(mode="json")
    publie: dict[str, Any] = {}
    for nom in COMPTES_ENTIERS:
        valeur = _chercher(brut, nom)
        assert isinstance(valeur, int), (
            f"l'analyse des décisions ne publie pas le compte « {nom} » "
            f"(clés : {sorted(brut)})"
        )
        publie[nom] = valeur
    for nom in COMPTES_PAR_CODE:
        valeur = _par_code(_chercher(brut, nom))
        assert valeur is not None, (
            f"l'analyse des décisions ne publie pas les « {nom} » par code "
            f"(clés : {sorted(brut)})"
        )
        publie[nom] = valeur
    assert publie == _DECLARE


# --------------------------------------------------------------------------
# D6 (garde) : aucune classe n'est recalculée en couche evaluation.
# --------------------------------------------------------------------------

_ORIGINES = {
    "source_text": "source",
    "final_text": "final",
    "proposed_text": "proposed",
}


def _origines(noeud: ast.AST, prises: Mapping[str, set[str]]) -> set[str]:
    trouvees: set[str] = set()
    for sous in ast.walk(noeud):
        if isinstance(sous, ast.Constant) and sous.value in _ORIGINES:
            trouvees.add(_ORIGINES[sous.value])
        elif isinstance(sous, ast.Attribute) and sous.attr in _ORIGINES:
            trouvees.add(_ORIGINES[sous.attr])
        elif isinstance(sous, ast.Name):
            trouvees |= prises.get(sous.id, set())
    return trouvees


def _comparaisons_de_textes(source: str) -> list[int]:
    """Les lignes où une fonction **compare** un texte final ou proposé à un texte
    source. Un nom hérite des origines (``source_text``, ``final_text``,
    ``proposed_text``) de l'expression qui l'a affecté, par propagation."""
    arbre = ast.parse(source)
    portees: list[ast.AST] = [arbre] + [
        n
        for n in ast.walk(arbre)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    lignes: list[int] = []
    for portee in portees:
        prises: dict[str, set[str]] = {}
        affectations = sorted(
            (
                n
                for n in ast.walk(portee)
                if isinstance(n, ast.Assign | ast.AnnAssign | ast.NamedExpr)
            ),
            key=lambda n: n.lineno,
        )
        for _ in range(2):
            for noeud in affectations:
                cibles = (
                    noeud.targets if isinstance(noeud, ast.Assign) else [noeud.target]
                )
                valeur = noeud.value
                if valeur is None:
                    continue
                origines = _origines(valeur, prises)
                for cible in cibles:
                    if isinstance(cible, ast.Name):
                        prises.setdefault(cible.id, set()).update(origines)
        for noeud in ast.walk(portee):
            if isinstance(noeud, ast.Compare):
                origines = _origines(noeud, prises)
                if "source" in origines and origines & {"final", "proposed"}:
                    lignes.append(noeud.lineno)
    return sorted(set(lignes))


def test_d6__aucune_fonction_d_evaluation_ne_compare_des_textes_pour_classer() -> None:
    """D6, Q6 (« aucune classe n'est recalculée en couche ``evaluation`` ; dans
    l'adaptateur, la seule comparaison de textes permise est l'égalité exacte
    ``final_text == source_text`` ») : aucune fonction de ``cinoc/evaluation``
    ne compare un texte final ou proposé à un texte source. Garde par AST, avec
    propagation des affectations (``final = ligne.get("final_text")``).
    ``c09`` : ``decisions.py`` rangeait chaque ligne en « changée / refusée /
    intacte » par ``final != source`` et ``str(propose) != source``."""
    controle = (
        "def f(ligne):\n"
        "    source = ligne.get('source_text')\n"
        "    final = ligne.get('final_text')\n"
        "    return final != source\n"
    )
    assert _comparaisons_de_textes(controle) == [4], "contrôle : le garde détecte"
    assert _comparaisons_de_textes("def g(a, b):\n    return a != b\n") == []
    fautifs = {
        str(chemin.relative_to(RACINE)): lignes
        for chemin in sorted((RACINE / "cinoc" / "evaluation").rglob("*.py"))
        if (lignes := _comparaisons_de_textes(chemin.read_text(encoding="utf-8")))
    }
    assert not fautifs, f"classes reconstruites par comparaison de textes : {fautifs}"

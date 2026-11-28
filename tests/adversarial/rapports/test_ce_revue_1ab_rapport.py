"""Tranche 1b — la revue indépendante de 1a + 1b, côté **rapport** (``CONTRATS.md``,
« Précisions tranchées le 28/11 après la validation finale de 1a + 1b »).

Règle de ``CLAUDE.md`` § 5.3, reprise par D7 : « publié » veut dire **affiché** ;
un champ de ``RunResult`` sans lecteur dans le rapport n'est pas publié. Ces tests
lisent le HTML rendu **comme un lecteur** — texte des nœuds, sans ``<script>`` ni
``<style>`` (l'île de données du rapport contient tout le ``RunResult`` : y
trouver une valeur ne prouve rien) — et cherchent des **valeurs**, pas des
libellés. Le contrat ne fixe ni les libellés ni la mise en page : on ne les devine
pas.

Rendus lus ici : D6 (classes de lignes), D7 (deux qualités, tri global, supports
appariés, invention hors référence, comptes de lignes, population cible), D8
(chemin d'alignement et phrases de décomposition), D11 (mot « verdict »), Q9
(l'agrégat principal côté consommateur).
"""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.extension import AdapterStepError
from cinoc.domain.corpus import CorpusSpec
from cinoc.evaluation.result import RunResult
from cinoc.reports import default_report_renderer
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.by_engine import EngineSection
from cinoc.reports.sections.correction import CorrectionSection
from cinoc.reports.sections.decisions import DecisionsSection
from cinoc.reports.sections.diagnostics import DiagnosticsSection
from cinoc.reports.sections.document_detail import DocumentDetailSection
from cinoc.reports.sections.taxonomy import TaxonomySection
from cinoc.reports.sections.textual_fidelity import TextualFidelitySection
from cinoc.reports.sections.word_errors import WordErrorsSection
from tests.adversarial._contrat import (
    agregat_operationnel,
    comparaison,
    corpus_declare,
    document_en_grappe,
    invention,
    paire,
)
from tests.adversarial.applicabilite_echecs._kit import (
    T,
    corpus,
    execute,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)
from tests.adversarial.applicabilite_echecs._kit_revue import (
    BriqueOctets,
    affiche,
    entier_affiche,
    run_decisions,
    texte_visible,
)

pytestmark = pytest.mark.tranche("1b")

RACINE = Path(__file__).resolve().parents[3]
LANGUES = ("fr", "en")


def _json(result: RunResult) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(result.model_dump_json())
    return data


def _rendu(result: RunResult, lang: str) -> str:
    """Le texte lu du rapport complet."""
    return texte_visible(default_report_renderer().render(result, lang=lang))


# --------------------------------------------------------------------------
# D7 : le tableau « Comparaison des moteurs » suit le tri global publié.
# --------------------------------------------------------------------------


class _Lignes(HTMLParser):
    """Première cellule de chaque ligne du **premier** tableau d'un fragment."""

    def __init__(self) -> None:
        super().__init__()
        self._tableaux = 0
        self._cellule = False
        self._ligne_vue = False
        self.premieres: list[str] = []
        self._courant: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self._tableaux += 1
        elif tag == "tr" and self._tableaux == 1:
            self._ligne_vue = False
        elif tag == "td" and self._tableaux == 1 and not self._ligne_vue:
            self._cellule, self._courant = True, []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cellule:
            self._cellule, self._ligne_vue = False, True
            self.premieres.append("".join(self._courant).strip())

    def handle_data(self, data: str) -> None:
        if self._cellule:
            self._courant.append(data)


def test_d7__le_tableau_des_moteurs_est_ordonne_selon_le_tri_global_publie(
    tmp_path: Path,
) -> None:
    """D7, Q3 (§ 2.1 c, A6/B7 : « seul le support global trie » ; « le rapport
    affiche … le tri sur le support global, et non sur les supports propres ») : le
    tableau « Comparaison des moteurs » est ordonné selon
    ``global_support.ranking``. ``alpha`` échoue sur ses quatre pages difficiles
    où ``bravo`` fait beaucoup d'erreurs ; sur les six pages communes, ``bravo``
    est meilleur (5 % contre 10 %), mais sur son propre support ``alpha`` paraît
    meilleur (10 % contre 23 %). ``c08`` : le tableau mettait ``alpha`` en tête,
    contre le tri publié (``bravo``, ``alpha``)."""
    refs = {f"d{i}": "abcdefghijklmnopqrst" for i in range(10)}
    alpha = BriqueOctets(
        "ce_alpha",
        {
            d: AdapterStepError("x") if i < 4 else b"abcdefghijklmnopqr##"
            for i, d in enumerate(refs)
        },
    )
    bravo = BriqueOctets(
        "ce_bravo",
        {
            d: b"##########klmnopqrst" if i < 4 else b"abcdefghijklmnopqrs#"
            for i, d in enumerate(refs)
        },
    )
    result = execute(
        spec(
            corpus(tmp_path, refs),
            [
                pipeline("alpha", step("ocr", "ce_alpha")),
                pipeline("bravo", step("ocr", "ce_bravo")),
            ],
            [text_view()],
        ),
        registry_with(alpha, bravo),
    )
    tri = comparaison(result, "texte", "cer").global_support.ranking
    assert tri == ("bravo", "alpha"), "contrôle : le tri global publié"
    html = EngineSection().render(result, SectionContext())
    assert html is not None
    lecteur = _Lignes()
    lecteur.feed(html)
    ordre = [
        nom
        for cellule in lecteur.premieres
        for nom in ("alpha", "bravo")
        if cellule.endswith(nom)
    ]
    assert tuple(ordre) == tri, f"tableau : {ordre}, tri global publié : {tri}"


# --------------------------------------------------------------------------
# D7 : les deux qualités, la comparaison, l'invention, la population cible.
# --------------------------------------------------------------------------

#: Onze documents de 40 caractères et deux pages blanches (sans référence), en deux
#: grappes. ``A`` : une page en échec, une partielle, une tronquée ; ``B`` : une
#: page en échec. Chaque pipeline invente du texte sur la page blanche ``b1``.
_REF40 = "abcdefghij" * 4
_GRAPPES = {
    **{f"t{i}": "fonds-nord" for i in range(1, 5)},
    **{f"t{i}": "fonds-sud" for i in range(5, 9)},
    "b1": "fonds-nord",
    "b2": "fonds-sud",
}
_POPULATION = "registres paroissiaux du diocèse de Lisieux, 1650-1790"
_INVENTE_A, _INVENTE_B = 37, 41


def _bruit(erreurs: int) -> bytes:
    return ("#" * erreurs + _REF40[erreurs:]).encode()


def _campagne(tmp_path: Path) -> RunResult:
    refs = {f"t{i}": _REF40 for i in range(1, 9)} | {"b1": "", "b2": ""}
    sorties_a: dict[str, bytes | AdapterStepError] = {
        "t1": _REF40.encode(),
        "t2": _bruit(1),
        "t3": AdapterStepError("panne"),
        "t4": _REF40[:30].encode(),
        "t5": _REF40[:36].encode(),
        "t6": _bruit(2),
        "t7": _REF40.encode(),
        "t8": _bruit(3),
        "b1": b"x" * _INVENTE_A,
        "b2": b"",
    }
    sorties_b: dict[str, bytes | AdapterStepError] = {
        **{f"t{i}": _bruit(2) for i in range(1, 8)},
        "t8": AdapterStepError("panne"),
        "b1": b"y" * _INVENTE_B,
        "b2": b"",
    }
    a = BriqueOctets(
        "ce_a", sorties_a, partial=frozenset({"t4"}), truncate=frozenset({"t5"})
    )
    b = BriqueOctets("ce_b", sorties_b)
    base = corpus(tmp_path, refs)
    declare = corpus_declare(
        CorpusSpec(
            name="ce",
            documents=tuple(
                document_en_grappe(d, _GRAPPES[d.id]) for d in base.documents
            ),
        ),
        target_population=_POPULATION,
        cluster_weighting="cluster",
    )
    return execute(
        spec(
            declare,
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view()],
        ),
        registry_with(a, b),
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_d7__le_rapport_affiche_la_qualite_conditionnelle_et_l_operationnelle(
    tmp_path: Path, lang: str
) -> None:
    """D7, Q3 (« le rapport affiche : les deux qualités avec la couverture ») :
    sur ``A`` (une page en échec, une partielle, une tronquée), la valeur
    conditionnelle (43 erreurs sur 200 caractères, 0,215) **et** la valeur
    opérationnelle (97 sur 320, 0,3031) sont écrites dans le texte du rapport, à
    côté de la couverture (7 notés sur 10 attendus). Le rapport n'affichait que
    l'agrégat principal, soit la seule qualité conditionnelle."""
    result = _campagne(tmp_path)
    data = _json(result)
    texte = _rendu(result, lang)
    (entree,) = (p for p in data["pipelines"] if p["pipeline"] == "A")
    conditionnelle = entree["conditional_aggregate"][0]
    operationnelle = entree["operational_aggregate"][0]
    assert (conditionnelle["support"], conditionnelle["expected"]) == (7, 10)
    assert conditionnelle["value"] != operationnelle["value"], "contrôle du banc"
    assert affiche(texte, conditionnelle["value"]), "qualité conditionnelle absente"
    assert affiche(texte, operationnelle["value"]), (
        f"qualité opérationnelle ({operationnelle['value']!r}) absente du texte "
        "visible du rapport"
    )
    assert re.search(r"\b7\s*/\s*10\b", texte), "couverture 7/10 absente"


@pytest.mark.parametrize("lang", LANGUES)
def test_d7__le_rapport_affiche_le_support_apparie_de_la_comparaison(
    tmp_path: Path, lang: str
) -> None:
    """D7, Q3 (« le rapport affiche … ``comparison`` ») : les valeurs de la paire
    (``A``, ``B``) **sur leur support apparié** (``t1``, ``t2``, ``t6``, ``t7`` et
    les deux pages blanches : 0,25 contre 0,30625) sont écrites dans le rapport.
    Ce ne sont ni l'un ni l'autre des agrégats propres des pipelines. Aucune
    section ne lisait ``comparison``."""
    result = _campagne(tmp_path)
    paire_ab = paire(comparaison(result, "texte", "cer"), "A", "B")
    propres = {
        s.value
        for p in result.pipelines
        for s in (*p.conditional_aggregate, *p.operational_aggregate)
    }
    texte = _rendu(result, lang)
    for nom in ("A", "B"):
        valeur = paire_ab.micro[nom]
        assert valeur not in propres, "contrôle du banc : valeur propre au support"
        assert affiche(texte, valeur), f"micro de {nom} sur le support apparié absent"


@pytest.mark.parametrize("lang", LANGUES)
def test_d7__le_rapport_affiche_l_invention_hors_reference(
    tmp_path: Path, lang: str
) -> None:
    """D7, Q3 (« le rapport affiche … l'invention hors référence » ; § 2.1 c, N3,
    C5) : sur les pages sans référence, ``A`` invente 37 caractères et ``B`` 41 ;
    les deux nombres sont écrits dans le rapport. Aucune section ne lisait
    ``invention_outside_reference``."""
    result = _campagne(tmp_path)
    payload = invention(result, "texte", "cer")
    inventes = paire(payload, "A", "B").invented
    assert dict(inventes) == {"A": _INVENTE_A, "B": _INVENTE_B}, "contrôle du banc"
    texte = _rendu(result, lang)
    for nom, valeur in inventes.items():
        assert entier_affiche(texte, valeur), (
            f"les {valeur} caractères inventés par {nom} ne sont pas affichés"
        )


@pytest.mark.parametrize("lang", LANGUES)
def test_d7__le_rapport_affiche_la_population_cible_et_la_ponderation(
    tmp_path: Path, lang: str
) -> None:
    """D7, Q3, B3 (« le rapport affiche … la population cible et la pondération des
    grappes ») : la population cible déclarée par le corpus est écrite telle quelle
    dans le rapport, et la pondération « par grappe » y est dite. Aucune section ne
    lisait ``target_population`` ni ``cluster_weighting``."""
    texte = _rendu(_campagne(tmp_path), lang)
    assert _POPULATION in texte, "population cible absente du rapport"
    mot = r"\bgrappes?\b" if lang == "fr" else r"\bclusters?\b"
    assert re.search(mot, texte, re.IGNORECASE), "pondération par grappe non dite"


@pytest.mark.parametrize("lang", LANGUES)
def test_d7__le_rapport_affiche_les_comptes_de_lignes_declares(
    tmp_path: Path, lang: str
) -> None:
    """D7, Q3 (« le rapport affiche … les comptes de lignes déclarés ») : le
    rapport complet d'un run de correction structurée écrit chaque code de refus
    et de repli avec son compte déclaré (refus : ``too_different_from_source`` 2,
    ``absorbs_next_line`` 1 ; repli : ``chunk_error_absorbed`` 4). Le run ne
    demande **aucune** analyse : ``PipelineResult.line_outcomes`` est un champ du
    ``RunResult``, déclaré par l'adaptateur, et le rapport le lit — il ne dépend
    pas d'une analyse facultative. Sans l'analyse ``decisions``, le rapport ne
    disait rien des lignes."""
    texte = _rendu(run_decisions(tmp_path, analyses=None), lang)
    attendus = {
        "too_different_from_source": 2,
        "absorbs_next_line": 1,
        "chunk_error_absorbed": 4,
    }
    for code, compte in attendus.items():
        assert re.search(rf"{code}\W{{1,6}}{compte}\b", texte), (
            f"« {code} » n'est pas écrit avec son compte {compte}"
        )


# --------------------------------------------------------------------------
# D6 : l'analyse des décisions affiche les classes déclarées.
# --------------------------------------------------------------------------


def _listes(html: str) -> list[str]:
    return re.findall(r"<ul>(.*?)</ul>", html, re.DOTALL)


@pytest.mark.parametrize("lang", LANGUES)
def test_d6__un_repli_n_est_jamais_affiche_comme_un_refus(
    tmp_path: Path, lang: str
) -> None:
    """D6, Q6 (« un repli n'est jamais affiché comme refus » ; § 2.1 f : le repli
    est un incident d'exécution, le refus une décision valide) : dans la section
    des décisions, ``chunk_error_absorbed`` (repli, 4) n'est pas dans la liste qui
    porte les refus (``too_different_from_source`` 2, ``absorbs_next_line`` 1), et
    il y a sa propre liste, avec son compte. ``c09`` : les quatre replis étaient
    comptés « Refusées » (7 au lieu de 3) et listés avec les motifs de refus."""
    html = DecisionsSection().render(run_decisions(tmp_path), SectionContext(lang=lang))
    assert html is not None
    listes = _listes(html)
    (refus,) = [liste for liste in listes if "too_different_from_source" in liste]
    assert "absorbs_next_line" in refus
    assert "chunk_error_absorbed" not in refus, "un repli est listé parmi les refus"
    (repli,) = [liste for liste in listes if "chunk_error_absorbed" in liste]
    assert re.search(r"chunk_error_absorbed</code>\s*—\s*4\b", repli)


@pytest.mark.parametrize("lang", LANGUES)
def test_d6__la_ligne_du_pipeline_affiche_les_comptes_disjoints_des_classes(
    tmp_path: Path, lang: str
) -> None:
    """D6 (§ 2.1 f : « ces classes sont **disjointes** : ``corrected`` n'inclut pas
    ``review_required`` ») : la ligne du pipeline porte les comptes des classes,
    corrigées 3, ``review_required`` 1, abstentions 3 : deux cellules à 3 et une à
    1 au moins (les libellés ne sont pas fixés par le contrat). ``c09`` : la
    ligne portait 14, 4 (corrigées + à revoir), 7 (refus + replis), 3, 1."""
    html = DecisionsSection().render(run_decisions(tmp_path), SectionContext(lang=lang))
    assert html is not None
    (ligne,) = re.findall(r'<tr><td class="eng-cell">.*?</tr>', html, re.DOTALL)
    cellules = re.findall(r"<td[^>]*>(.*?)</td>", ligne, re.DOTALL)[1:]
    entiers = Counter(
        int(m.group(1))
        for c in cellules
        if (m := re.match(r"\s*(\d+)", texte_visible(c)))
    )
    assert entiers[3] >= 2 and entiers[1] >= 1, (
        f"comptes de la ligne : {sorted(entiers.elements())} — corrigées (3), "
        "abstentions (3) et à revoir (1) attendus"
    )


# --------------------------------------------------------------------------
# D8, Q7 : chemin d'alignement affiché, phrases de décomposition.
# --------------------------------------------------------------------------


def _alignement(tmp_path: Path) -> RunResult:
    """Un OCR corrigé par un correcteur, et un OCR seul, sur deux pages dont la
    première a des ex æquo d'alignement (« ab un deux » → « ba deux un »)."""
    refs = {"d1": "ab un deux trois", "d2": "abc quatre cinq"}
    ocr_p = BriqueOctets(
        "ce_ocr_p", {"d1": b"ba deux un trois", "d2": b"abc quatre cinq"}
    )
    corr = BriqueOctets(
        "ce_corr",
        {"d1": b"ab un deux troys", "d2": b"abd quatre cinq"},
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    ocr_q = BriqueOctets(
        "ce_ocr_q", {"d1": b"ab un deux trois", "d2": b"abc quatre cinc"}
    )
    return execute(
        spec(
            corpus(tmp_path, refs),
            [
                pipeline(
                    "P",
                    step("ocr", "ce_ocr_p"),
                    step(
                        "corr", "ce_corr", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT
                    ),
                ),
                pipeline("Q", step("ocr", "ce_ocr_q")),
            ],
            [text_view("brut", metrics=("cer", "wer"))],
            analyses="toutes",
        ),
        registry_with(ocr_p, corr, ocr_q),
    )


_SECTIONS_ALIGNEMENT = (
    ("diagnostics", DiagnosticsSection),
    ("taxonomy", TaxonomySection),
    ("word_errors", WordErrorsSection),
    ("textual_fidelity", TextualFidelitySection),
    ("correction", CorrectionSection),
    ("document_texts", DocumentDetailSection),
)


def test_d8__word_errors_fidelity_et_correction_portent_leur_chemin_d_alignement(
    tmp_path: Path,
) -> None:
    """D8, Q7 (arbitrage n° 1 du 28/11 ; « ``word_errors``, ``textual_fidelity``, les
    séquences d'éditions de ``correction`` et le diff portent ``alignment_path`` ») :
    chaque payload qui nomme des éditions porte son chemin, ``"rapidfuzz"`` ou
    ``"canonical"``. ``c19``/``c20`` : ``word_errors``, ``textual_fidelity`` et
    ``correction`` n'en portaient pas."""
    result = _alignement(tmp_path)
    sans = {}
    for analyse in result.analyses:
        kind = analyse.payload.kind
        if kind not in {k for k, _ in _SECTIONS_ALIGNEMENT}:
            continue
        chemin = getattr(analyse.payload, "alignment_path", None)
        if chemin not in ("rapidfuzz", "canonical"):
            sans[kind] = chemin
    assert not sans, f"payloads sans chemin d'alignement : {sorted(sans)}"
    assert {a.payload.kind for a in result.analyses} >= {
        k for k, _ in _SECTIONS_ALIGNEMENT
    }, "contrôle du banc : tous les payloads existent"


@pytest.mark.parametrize("lang", LANGUES)
def test_d8__le_rendu_affiche_le_chemin_d_alignement(tmp_path: Path, lang: str) -> None:
    """D8 (« …portent ``alignment_path``, **et le rendu l'affiche** » ; § 2.1 f,
    « diff surligné ») : la section de chacune des analyses qui nomment des
    éditions écrit le chemin d'alignement de son payload (``rapidfuzz``). Seule
    la liste des dépendances du manifeste le nommait."""
    result = _alignement(tmp_path)
    ctx = SectionContext(lang=lang)
    muets = []
    for kind, section in _SECTIONS_ALIGNEMENT:
        (payload,) = [a.payload for a in result.analyses if a.payload.kind == kind][:1]
        chemin = getattr(payload, "alignment_path", "rapidfuzz")
        html = section().render(result, ctx)
        assert html is not None, f"{kind} : section absente"
        if chemin.lower() not in texte_visible(html).lower():
            muets.append(kind)
    assert not muets, f"sections qui n'affichent pas leur chemin d'alignement : {muets}"


def _un_document(tmp_path: Path, reference: str, hypothese: str) -> RunResult:
    brique = BriqueOctets("ce_a", {"d": hypothese.encode()})
    return execute(
        spec(
            corpus(tmp_path, {"d": reference}),
            [pipeline("A", step("ocr", "ce_a"))],
            [text_view(metrics=("cer", "wer"))],
            analyses="toutes",
        ),
        registry_with(brique),
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_d8__sans_concordance_aucune_phrase_ne_decompose_les_comptes_canoniques(
    tmp_path: Path, lang: str
) -> None:
    """D8, Q7 (« quand ``matches_canonical_counts`` est faux, aucune phrase du
    rapport ne présente ces éditions comme la décomposition des comptes
    canoniques ») : « ab » → « ba » rend les confusions non concordantes (les
    comptes canoniques sont (2, 0, 0), l'alignement RapidFuzz (0, 1, 1)) : la
    section ne dit plus « ce sont les substitutions que compte le CER, ni plus ni
    moins » ; « a b » → « b a » rend la taxonomie non concordante : elle ne dit
    plus « les omissions sont ses suppressions » (ni leurs équivalents anglais).
    ``c20`` : ces deux phrases étaient affichées."""
    interdit = {
        "diagnostics": {
            "fr": "ni plus ni moins",
            "en": "exactly the substitutions the CER counts",
        },
        "taxonomy": {
            "fr": "les omissions sont ses suppressions",
            "en": "omissions are its deletions",
        },
    }
    cas = (
        ("diagnostics", DiagnosticsSection, "ab xyz", "ba xyw"),
        ("taxonomy", TaxonomySection, "a b", "b a"),
    )
    ctx = SectionContext(lang=lang)
    presentes = []
    for sous, (kind, section, reference, hypothese) in enumerate(cas):
        dossier = tmp_path / str(sous)
        dossier.mkdir()
        result = _un_document(dossier, reference, hypothese)
        (payload,) = [a.payload for a in result.analyses if a.payload.kind == kind]
        assert payload.matches_canonical_counts is False, "contrôle du banc"
        html = section().render(result, ctx)
        assert html is not None
        if interdit[kind][lang] in texte_visible(html):
            presentes.append(f"{kind} : « {interdit[kind][lang]} »")
    assert not presentes, (
        "phrases qui présentent des éditions comme la décomposition des comptes "
        f"canoniques, alors que matches_canonical_counts est faux : {presentes}"
    )


# --------------------------------------------------------------------------
# D11 : plus de « verdict » dans les textes livrés.
# --------------------------------------------------------------------------

_VERDICT = re.compile(r"\bverdicts?\b", re.IGNORECASE)
_ATTRIBUT_CLASSE = re.compile(r"""class=(?:"[^"]*"|'[^']*')""")


def _litteraux(chemin: Path) -> list[tuple[int, str]]:
    """Les littéraux de chaîne d'un module, **hors docstrings** (un docstring
    n'est lu par personne à l'exécution)."""
    arbre = ast.parse(chemin.read_text(encoding="utf-8"))
    docstrings = {
        id(noeud.body[0].value)
        for noeud in ast.walk(arbre)
        if isinstance(
            noeud, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
        )
        and noeud.body
        and isinstance(noeud.body[0], ast.Expr)
        and isinstance(noeud.body[0].value, ast.Constant)
        and isinstance(noeud.body[0].value.value, str)
    }
    return [
        (noeud.lineno, noeud.value)
        for noeud in ast.walk(arbre)
        if isinstance(noeud, ast.Constant)
        and isinstance(noeud.value, str)
        and id(noeud) not in docstrings
    ]


def test_d11__aucun_texte_livre_ne_parle_de_verdict() -> None:
    """D11 (« les textes livrés qui parlent de « verdict », rendus ou non, sont
    reformulés ou retirés » ; révision n° 7, « Wording des sections » : « résultat
    (exploratoire) ») : ni les glossaires (``cinoc/**/*.yaml``), ni les textes de
    l'interface web (``i18n``), ni les littéraux des sections du rapport ne
    contiennent le mot. Les identifiants et les classes CSS (``class="verdict"``)
    ne sont pas des textes. ``c11``, ``c12`` : « un verdict ne vaut que pour sa vue
    » (mesures clés), « le verdict lit la p-valeur » (glossaire)."""
    trouves: list[str] = []
    for chemin in sorted((RACINE / "cinoc").rglob("*.yaml")):
        for numero, ligne in enumerate(
            chemin.read_text(encoding="utf-8").splitlines(), 1
        ):
            if _VERDICT.search(ligne):
                trouves.append(f"{chemin.relative_to(RACINE)}:{numero}")
    modules = [
        *sorted((RACINE / "cinoc" / "reports" / "sections").glob("*.py")),
        RACINE / "cinoc" / "interfaces" / "web" / "i18n.py",
    ]
    for chemin in modules:
        for numero, texte in _litteraux(chemin):
            if _VERDICT.search(_ATTRIBUT_CLASSE.sub("", texte)):
                trouves.append(f"{chemin.relative_to(RACINE)}:{numero}")
    assert not trouves, f"textes livrés qui parlent de verdict : {trouves}"


# --------------------------------------------------------------------------
# Q9 : le consommateur dérive le principal de la politique d'échec.
# --------------------------------------------------------------------------


def _principal(tmp_path: Path, politique: str) -> RunResult:
    refs = {f"d{i}": "abcdefghijklmnopqrst" for i in range(4)}
    a = BriqueOctets(
        "ce_a",
        {
            "d0": AdapterStepError("panne"),
            "d1": b"abcdefghijklmnopqrs#",
            "d2": b"abcdefghijklmnopqrst",
            "d3": b"abcdefghijklmnopqr##",
        },
    )
    b = BriqueOctets("ce_b", {d: b"abcdefghijklmnopqrs#" for d in refs})
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view()],
            failure_policy=politique,
        ),
        registry_with(a, b),
    )


@pytest.mark.parametrize("politique", ["exclude", "empty_page"])
def test_q9__le_rapport_lit_le_principal_derive_de_la_politique_pas_une_copie_stockee(
    tmp_path: Path, politique: str
) -> None:
    """Q9 (« le principal est **dérivé** de ``failure_policy`` par un accesseur,
    jamais stocké une seconde fois ») : le contrat ne nomme pas l'accesseur ; on le
    teste par ce que lit le consommateur. Un ``RunResult`` rechargé d'un JSON
    **sans** clé ``aggregate`` rend le même tableau des moteurs que l'original, et
    celui-ci écrit la valeur du principal de la politique (conditionnelle sous
    ``exclude``, opérationnelle sous ``empty_page``). Avec une copie stockée,
    retirer la clé vide le tableau."""
    result = _principal(tmp_path, politique)
    data = _json(result)
    for entree in data["pipelines"]:
        entree.pop("aggregate", None)
    recharge = RunResult.model_validate(data)
    contexte = SectionContext()
    original = EngineSection().render(result, contexte)
    sans_copie = EngineSection().render(recharge, contexte)
    assert sans_copie is not None, (
        "sans la copie stockée de l'agrégat principal, le rapport n'a plus rien "
        "à lire : il ne le dérive pas de la politique"
    )
    assert sans_copie == original
    qualite = (
        "conditional_aggregate" if politique == "exclude" else "operational_aggregate"
    )
    (a,) = (p for p in data["pipelines"] if p["pipeline"] == "A")
    assert affiche(texte_visible(sans_copie), a[qualite][0]["value"])
    assert (
        agregat_operationnel(recharge, "A", "cer").value
        == a["operational_aggregate"][0]["value"]
    )

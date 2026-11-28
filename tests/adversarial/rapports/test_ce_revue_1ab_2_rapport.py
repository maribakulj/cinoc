"""Tranche 1b — la seconde revue de 1a + 1b, côté **rapport** (``CONTRATS.md``,
« Précisions tranchées le 28/11 après la seconde validation », défauts N1 à N12,
questions 1 à 10 ; contre-exemples ``r01`` à ``r11`` de ``revue-1ab-2/``).

Mêmes règles que ``test_ce_revue_1ab_rapport`` : « publié » veut dire **affiché**
(``CLAUDE.md`` § 5.3) ; le HTML est lu **comme un lecteur** (texte des nœuds, sans
``<script>`` ni ``<style>``, l'île de données du rapport contenant tout le
``RunResult``) et on y cherche des **valeurs**. Le contrat ne fixe pas les
libellés qu'il ne cite pas : on ne les devine pas. Quand un libellé n'est fixé
qu'en français, l'équivalent anglais se cherche par sa **structure** (un nombre à
côté d'un mot, l'absence d'un libellé français ou d'un ancien terme) et le test le
dit.

Couvre : N3 (classes non déclarées, affiché), N4 et question 5 (le texte suit le
support), N7 (liste de confusions tronquée), N8 (flèche de tri), N9 (l'autre
qualité à côté de l'agrégat principal), N10/N11 (comparateur), question 7 (titres),
question 8 (pipeline hors vue dans les tableaux par document), question 9 (CSV).
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.extension import AdapterStepError
from cinoc.evaluation.result import RunResult
from cinoc.reports import default_report_renderer
from cinoc.reports.compare import render_comparison
from cinoc.reports.compare_widget import compare_widget
from cinoc.reports.csv_export import run_result_csv
from cinoc.reports.section import SectionContext
from cinoc.reports.sections.by_engine import EngineSection
from cinoc.reports.sections.composition import CompositionSection
from cinoc.reports.sections.decisions import DecisionsSection
from cinoc.reports.sections.diagnostics import DiagnosticsSection
from cinoc.reports.sections.document_detail import DocumentDetailSection
from cinoc.reports.sections.documents import DocumentsSection
from cinoc.reports.sections.economics import EconomicsSection
from cinoc.reports.sections.engine_duel import EngineDuelSection
from cinoc.reports.sections.engine_profile import EngineProfileSection
from cinoc.reports.sections.key_measures import KeyMeasuresSection
from cinoc.reports.sections.overview import OverviewSection
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
    micro_sur_support,
    run_archive_sans_classes,
    texte_visible,
)

pytestmark = pytest.mark.tranche("1b")

RACINE = Path(__file__).resolve().parents[3]
LANGUES = ("fr", "en")
POLITIQUES = ("exclude", "empty_page")


def _json(result: RunResult) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(result.model_dump_json())
    return data


def _rendu(result: RunResult, lang: str) -> str:
    """Le texte lu du rapport complet."""
    return texte_visible(default_report_renderer().render(result, lang=lang))


def _section(section: Any, result: RunResult, lang: str) -> str:
    """Le texte lu d'une section (vide si la section ne se rend pas)."""
    html = section.render(result, SectionContext(lang=lang))
    return "" if html is None else texte_visible(html)


# --------------------------------------------------------------------------
# N3 : « classes non déclarées par l'archive », jamais un zéro.
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lang", LANGUES)
def test_n3__le_rapport_ne_chiffre_pas_des_classes_non_declarees(
    tmp_path: Path, lang: str
) -> None:
    """N3 (« un sidecar sans ``line_class`` ne produit aucun compte … le rapport
    écrit « classes non déclarées par l'archive ». Jamais un zéro ») : la ligne du
    pipeline de la section des décisions ne porte **aucun nombre** (ni ``0`` ni
    ``0 (—)``). En français, la section écrit « classes non déclarées par
    l'archive ». L'équivalent anglais n'est pas fixé par le contrat : on vérifie
    sa structure (aucun chiffre dans la ligne, aucune phrase française). ``c09``,
    ``dresden.toutes`` : « 0 · 0 (—) · 0 (—) … » sur 40 pages corrigées."""
    result = run_archive_sans_classes(tmp_path)
    html = DecisionsSection().render(result, SectionContext(lang=lang))
    assert html is not None
    (ligne,) = re.findall(r'<tr><td class="eng-cell">.*?</tr>', html, re.DOTALL)
    cellules = re.findall(r"<td[^>]*>(.*?)</td>", ligne, re.DOTALL)[1:]
    lues = texte_visible(" ".join(cellules))
    assert not re.search(r"\d", lues), f"la ligne du pipeline chiffre : {lues!r}"
    texte = texte_visible(html)
    phrase = re.compile(r"classes\s+non\s+déclarées\s+par\s+l.archive", re.IGNORECASE)
    if lang == "fr":
        assert phrase.search(texte), "« classes non déclarées par l'archive » absent"
    else:
        assert not phrase.search(texte), "la phrase française fuit dans le rapport EN"


# --------------------------------------------------------------------------
# N4, question 5 : le texte suit le support.
# --------------------------------------------------------------------------

_ALPHABET = "abcdefghijklmnopqrstuvwxyz"
#: Dix documents de longueurs différentes (20 à 47 caractères) : aucune valeur
#: micro ne tombe sur un chiffre rond, qu'un hasard d'affichage confondrait avec
#: une autre.
REFS_N4 = {f"d{i}": (_ALPHABET * 3)[: 20 + 3 * i] for i in range(10)}


def _bruit(document: str, k: int) -> bytes:
    reference = REFS_N4[document]
    return ("#" * k + reference[k:]).encode()


def _supports_differents(tmp_path: Path, politique: str) -> RunResult:
    """Trois pipelines. ``A`` : ``d0`` en échec, ``d1`` partielle (dix premiers
    caractères), trois erreurs ailleurs. ``B`` et ``C`` : complets partout, mais
    leurs deux premiers documents sont bien plus fautifs que les autres. Sous
    ``exclude``, le support du test est celui des **huit** documents complets de
    ``A`` : le CER de ``B`` et de ``C`` sur leur propre support (dix documents)
    n'est pas celui qu'ils ont sur ce support."""
    a = {d: _bruit(d, 3) for d in REFS_N4}
    a["d0"] = AdapterStepError("panne")  # type: ignore[assignment]
    a["d1"] = REFS_N4["d1"][:10].encode()
    b = {d: _bruit(d, 1) for d in REFS_N4} | {
        "d0": _bruit("d0", 9),
        "d1": _bruit("d1", 7),
    }
    c = {d: _bruit(d, 2) for d in REFS_N4} | {
        "d0": _bruit("d0", 6),
        "d1": _bruit("d1", 6),
    }
    briques = [
        BriqueOctets("ce_a", a, partial=frozenset({"d1"})),
        BriqueOctets("ce_b", b),
        BriqueOctets("ce_c", c),
    ]
    return execute(
        spec(
            corpus(tmp_path, REFS_N4),
            [pipeline(nom, step("ocr", f"ce_{nom.lower()}")) for nom in "ABC"],
            [text_view()],
            failure_policy=politique,
        ),
        registry_with(*briques),
    )


def _support_du_test(data: dict[str, Any], politique: str) -> frozenset[str]:
    """Les documents du support du test : ceux de l'agrégat principal que **tous**
    les pipelines ont notés (complets sous ``exclude``, tous les attendus à vérité
    disponible sous ``empty_page``)."""
    par_document: dict[str, list[dict[str, Any]]] = {}
    for entree in data["documents"]:
        par_document.setdefault(entree["document_id"], []).append(entree["scores"][0])
    gardes = set()
    for document, scores in par_document.items():
        if politique == "exclude":
            ok = all(
                s["availability"] == "available" and s["validity"] == "valid"
                for s in scores
            )
        else:
            ok = all(s["availability"] != "gt_unreadable" for s in scores)
        if ok:
            gardes.add(document)
    return frozenset(gardes)


def _paragraphe_du_test(html: str) -> str:
    """Le paragraphe des mesures clés qui écrit le résultat du test (« … p = … »)."""
    for fragment in re.findall(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
        texte = texte_visible(fragment)
        if re.search(r"\bp = ", texte):
            return texte
    raise AssertionError("aucun paragraphe de test dans les mesures clés")


def _valeur_principale(data: dict[str, Any], nom: str, politique: str) -> float:
    cle = "conditional_aggregate" if politique == "exclude" else "operational_aggregate"
    (entree,) = (p for p in data["pipelines"] if p["pipeline"] == nom)
    return float(entree[cle][0]["value"])


@pytest.mark.parametrize("lang", LANGUES)
@pytest.mark.parametrize("politique", POLITIQUES)
def test_n4__les_valeurs_a_cote_du_test_sont_celles_de_son_support(
    tmp_path: Path, politique: str, lang: str
) -> None:
    """N4, question 5 (« un test et le Δ qu'il accompagne ont toujours le même
    support » ; « les valeurs affichées à côté d'un test sont calculées sur le
    support de ce test, avec sa taille ») : les mesures clés écrivent, pour chaque
    pipeline, le CER micro **recalculé sur le support du test** (huit documents
    sous ``exclude`` ; dix sous ``empty_page``), et la taille de ce support à côté
    du mot « observations ». Sous ``exclude``, ces valeurs diffèrent de celles du
    support propre de ``B`` et de ``C`` (dix documents) : un tableau qui n'affiche
    que ces dernières ne dit pas ce que le test a comparé. ``r03`` : le texte du
    test ne disait que « 9 cas complets », et les valeurs voisines venaient du
    support propre de chaque pipeline."""
    result = _supports_differents(tmp_path, politique)
    data = _json(result)
    support = _support_du_test(data, politique)
    qualite = "conditionnelle" if politique == "exclude" else "operationnelle"
    attendues = {
        nom: micro_sur_support(data, nom, "texte", REFS_N4, qualite, support)
        for nom in "ABC"
    }
    propres = {nom: _valeur_principale(data, nom, politique) for nom in "ABC"}
    assert len(support) == (8 if politique == "exclude" else 10), "contrôle du banc"
    if politique == "exclude":
        assert attendues["B"] != propres["B"] and attendues["C"] != propres["C"], (
            "contrôle du banc : le support du test n'est pas le support propre"
        )
    valeurs = [v for v in (*attendues.values(), *propres.values()) if v is not None]
    assert len({f"{v:.4f}" for v in valeurs}) == len(set(valeurs)), "contrôle du banc"
    html = KeyMeasuresSection().render(result, SectionContext(lang=lang))
    assert html is not None
    texte = texte_visible(html)
    absentes = [
        f"{nom} ({attendues[nom]:.4f})"
        for nom in "ABC"
        if attendues[nom] is None or not affiche(texte, attendues[nom])  # type: ignore[arg-type]
    ]
    assert not absentes, f"valeurs du support du test absentes : {absentes}"
    n = len(support)
    assert re.search(
        rf"\b{n}\b[^.]{{0,60}}\bobservations?\b|\bobservations?\b[^.]{{0,60}}\b{n}\b",
        _paragraphe_du_test(html),
    ), f"la taille du support ({n}) n'est pas écrite à côté du test"


@pytest.mark.parametrize("lang", LANGUES)
@pytest.mark.parametrize("politique", POLITIQUES)
def test_n4__le_texte_du_test_nomme_les_observations_qu_il_a_comparees(
    tmp_path: Path, politique: str, lang: str
) -> None:
    """N4, question 5 (« sous ``exclude`` : « observations complètes » ; sous
    ``empty_page`` : « observations opérationnelles (échecs notés comme une sortie
    vide) » ») : le paragraphe du test dit, en français, « observations complètes »
    sous ``exclude`` ; « observations opérationnelles » et « échecs notés comme une
    sortie vide » sous ``empty_page`` — jamais l'autre. Aucun texte du rapport ne dit
    plus « cas complets » (FR) ni « complete cases » (EN). En anglais, le contrat ne
    fixe pas la phrase : on cherche « complete observations » sous ``exclude`` et
    « operational » (et « observations ») sous ``empty_page``, les termes que
    l'aperçu des deux qualités emploie déjà. ``r03`` : « (9 cas complets) » sous
    ``empty_page``, où les échecs sont notés vides et donc comptés."""
    result = _supports_differents(tmp_path, politique)
    html = KeyMeasuresSection().render(result, SectionContext(lang=lang))
    assert html is not None
    paragraphe = _paragraphe_du_test(html)
    ancien = r"cas complets" if lang == "fr" else r"complete cases"
    assert not re.search(ancien, _rendu(result, lang), re.IGNORECASE), (
        f"le rapport ({lang}) dit encore « {ancien} »"
    )
    if lang == "fr":
        if politique == "exclude":
            assert "observations complètes" in paragraphe, paragraphe
            assert "opérationnelles" not in paragraphe, paragraphe
        else:
            assert "observations opérationnelles" in paragraphe, paragraphe
            assert "échecs notés comme une sortie vide" in paragraphe, paragraphe
            assert "observations complètes" not in paragraphe, paragraphe
    elif politique == "exclude":
        assert re.search(r"\bcomplete observations\b", paragraphe), paragraphe
        assert not re.search(r"\boperational\b", paragraphe), paragraphe
    else:
        assert re.search(r"\boperational\b", paragraphe), paragraphe
        assert re.search(r"\bobservations\b", paragraphe), paragraphe
        assert not re.search(r"\bcomplete observations\b", paragraphe), paragraphe


def _sans_test(tmp_path: Path, politique: str, cas: str) -> RunResult:
    """Deux pipelines dont le test n'est pas calculé : ``insuffisant`` (quatre
    documents, moins que le minimum) ou ``identiques`` (dix documents, mêmes
    sorties : aucune différence)."""
    nombre = 4 if cas == "insuffisant" else 10
    refs = {d: r for d, r in REFS_N4.items() if int(d[1:]) < nombre}
    sortie_b = {d: _bruit(d, 1 if cas == "identiques" else 2) for d in refs}
    briques = [
        BriqueOctets("ce_a", {d: _bruit(d, 1) for d in refs}),
        BriqueOctets("ce_b", sortie_b),
    ]
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline(nom, step("ocr", f"ce_{nom.lower()}")) for nom in "AB"],
            [text_view()],
            failure_policy=politique,
        ),
        registry_with(*briques),
    )


@pytest.mark.parametrize("lang", LANGUES)
@pytest.mark.parametrize("politique", POLITIQUES)
@pytest.mark.parametrize("cas", ["insuffisant", "identiques"])
def test_n4__les_motifs_de_non_calcul_ne_parlent_plus_de_cas_complets(
    tmp_path: Path, cas: str, politique: str, lang: str
) -> None:
    """N4, question 5 : les phrases qui disent **pourquoi** le test n'est pas
    calculé (« n cas complets, il en faut au moins 6 », « aucune différence entre
    pipelines sur les n cas complets ») suivent le même support que le test : elles
    nomment des observations, complètes (``exclude``) ou opérationnelles
    (``empty_page``), et ne disent plus « cas complets » / « complete cases ». La
    taille n du support reste écrite."""
    result = _sans_test(tmp_path, politique, cas)
    texte = _section(KeyMeasuresSection(), result, lang)
    assert re.search(r"non calculé|not computed", texte), (
        "contrôle : le test est motivé"
    )
    ancien = r"cas complets" if lang == "fr" else r"complete cases"
    assert not re.search(ancien, texte, re.IGNORECASE), f"« {ancien} » : {texte[-300:]}"
    nombre = 4 if cas == "insuffisant" else 10
    mot = (
        ("complètes" if politique == "exclude" else "opérationnelles")
        if lang == "fr"
        else ("complete" if politique == "exclude" else "operational")
    )
    assert re.search(
        rf"\b{nombre}\b[^.]{{0,60}}\b{mot}\b|\b{mot}\b[^.]{{0,60}}\b{nombre}\b", texte
    ), f"le motif ne nomme pas {nombre} observations « {mot} »"


# --------------------------------------------------------------------------
# N7 : « ni plus ni moins » seulement pour une liste complète.
# --------------------------------------------------------------------------

_ALPHA = "abcdefghijklmnopqrstuvwxyz"


def _confusions(tmp_path: Path, n_substitutions: int) -> RunResult:
    """``A`` substitue ``n_substitutions`` lettres, **toutes différentes** (chaque
    paire attendu → produit n'a lieu qu'une fois : le nombre de confusions
    distinctes égale celui des substitutions, ce qui ne laisse aucune ambiguïté sur
    « N ») ; ``B`` est exact. Aucune ambiguïté d'alignement : les comptes de
    l'analyse sont ceux des comptes canoniques (``matches_canonical_counts``)."""
    hypothese = _ALPHA[:n_substitutions].upper() + _ALPHA[n_substitutions:]
    return execute(
        spec(
            corpus(tmp_path, {"d1": _ALPHA}),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view()],
            analyses="toutes",
        ),
        registry_with(
            BriqueOctets("ce_a", {"d1": hypothese.encode()}),
            BriqueOctets("ce_b", {"d1": _ALPHA.encode()}),
        ),
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_n7__une_liste_tronquee_ne_se_presente_pas_comme_la_decomposition_des_comptes(
    tmp_path: Path, lang: str
) -> None:
    """N7 (« ``ni plus ni moins`` seulement pour une liste complète ; arbitrage
    n° 1 ; si la liste des confusions est tronquée, le texte dit « les k plus
    fréquentes sur N », et ne présente pas la liste comme la décomposition des
    comptes ») : douze substitutions distinctes, la liste publiée en garde dix, et
    la concordance avec les comptes canoniques est vraie. La section n'écrit ni
    « ni plus ni moins » ni « exactly the substitutions the CER counts », et dit
    « les 10 plus fréquentes sur 12 ». L'anglais n'est pas fixé par le contrat : on
    cherche les deux nombres 10 et 12 à proximité l'un de l'autre. ``r06`` : la
    phrase de décomposition était affichée à côté d'une liste de dix paires, sur
    douze."""
    result = _confusions(tmp_path, 12)
    (payload,) = [a.payload for a in result.analyses if a.payload.kind == "diagnostics"]
    (pairs,) = [p.pairs for p in payload.confusions if p.pipeline == "A"]
    assert payload.matches_canonical_counts is True and len(pairs) == 10, "banc"
    texte = _section(DiagnosticsSection(), result, lang)
    assert texte, "la section diagnostic est rendue"
    decompose = "ni plus ni moins" if lang == "fr" else "exactly the substitutions"
    assert decompose not in texte, "une liste tronquée est présentée comme complète"
    if lang == "fr":
        assert re.search(r"les\s+10\s+plus\s+fréquentes\s+sur\s+12\b", texte), (
            "« les 10 plus fréquentes sur 12 » absent"
        )
    else:
        assert re.search(r"\b10\b.{0,80}\b12\b|\b12\b.{0,80}\b10\b", texte), (
            "les nombres 10 (affichées) et 12 (distinctes) ne sont pas écrits ensemble"
        )


# --------------------------------------------------------------------------
# N8 : la flèche de tri suit higher_is_better et la légende.
# --------------------------------------------------------------------------


def _tri(tmp_path: Path, metriques: tuple[str, ...]) -> RunResult:
    refs = {f"d{i}": _ALPHA[:20] for i in range(4)}
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view(metrics=metriques)],
        ),
        registry_with(
            BriqueOctets("ce_a", {d: _ALPHA[:19].encode() + b"#" for d in refs}),
            BriqueOctets("ce_b", {d: _ALPHA[:18].encode() + b"##" for d in refs}),
        ),
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_n8__la_fleche_de_tri_suit_le_sens_de_la_metrique_et_la_legende(
    tmp_path: Path, lang: str
) -> None:
    """N8 (« la flèche de tri dépend de ``higher_is_better`` et suit la légende ») :
    la légende des mesures clés dit « ↓ = plus bas est meilleur · ↑ = plus haut est
    meilleur » ; la phrase qui annonce le tri de la comparaison des moteurs écrit,
    après le nom de la métrique de tri, ↓ si elle est un taux d'erreur (``cer``)
    et ↑ si plus haut est meilleur (``char_accuracy``, exactitude : la métrique de
    tri est la première de la vue quand elle n'a pas de ``cer``). ``r07`` : « cer ↑ »
    — l'inverse de la légende — quelle que soit la métrique."""
    (tmp_path / "legende").mkdir()
    legende = _section(
        KeyMeasuresSection(), _tri(tmp_path / "legende", ("cer", "wer")), lang
    )
    plus_bas = "plus bas est meilleur" if lang == "fr" else "lower is better"
    plus_haut = "plus haut est meilleur" if lang == "fr" else "higher is better"
    assert f"↓ = {plus_bas}" in legende and f"↑ = {plus_haut}" in legende, "légende"
    problemes: list[str] = []
    cas = (
        (("cer", "wer"), "cer", "↓"),
        (("char_accuracy", "wer"), "char_accuracy", "↑"),
    )
    for metriques, tri, fleche in cas:
        dossier = tmp_path / tri
        dossier.mkdir()
        texte = _section(EngineSection(), _tri(dossier, metriques), lang)
        trouvees = re.findall(rf"\b{re.escape(tri)}\s*([↑↓])", texte)
        if not trouvees:
            problemes.append(f"aucune flèche de tri après « {tri} »")
        elif trouvees[0] != fleche:
            problemes.append(
                f"« {tri} {trouvees[0]} » : la légende veut « {tri} {fleche} »"
            )
    assert not problemes, problemes


# --------------------------------------------------------------------------
# N9, question 10 : l'autre qualité à côté de l'agrégat principal.
# --------------------------------------------------------------------------

_MOTS = "le ſoleil luit sur la seine et les ponts de paris"
REFS_N9 = {f"d{i}": _MOTS for i in range(8)}
METRIQUES_N9 = ("cer", "wer", "mer", "cer_diplo", "ins_rate", "char_accuracy")
_VARIANTES_A = (
    "le soleil luit sur la seine et les ponts de paris",
    "le ſoleil luit sur sur la seine et les ponts de pari",
    "le ſoleil luit sur la seine et les pont de paris encore",
)
_VARIANTES_B = (
    "le ſoleil luit sur la seine et les ponts de paris",
    "le ſoleil luit sur la seine et ses ponts de paris",
    "le ſoleil luit sur la sein et les ponts de paris x",
)


def _deux_qualites(tmp_path: Path, politique: str) -> RunResult:
    """``A`` : ``d0`` en échec, ``d1`` partielle, les autres plus ou moins fautives ;
    ``B`` complète. Pour **chaque** métrique de la vue (établies, adaptée,
    exploratoire, et ``mer`` qui n'est pas rendue dans les tableaux), la qualité
    conditionnelle de ``A`` diffère de l'opérationnelle."""
    a = {d: _VARIANTES_A[i % 3].encode() for i, d in enumerate(REFS_N9)}
    a["d0"] = AdapterStepError("panne")  # type: ignore[assignment]
    a["d1"] = "le ſoleil luit".encode()
    b = {d: _VARIANTES_B[i % 3].encode() for i, d in enumerate(REFS_N9)}
    return execute(
        spec(
            corpus(tmp_path, REFS_N9),
            [pipeline("A", step("ocr", "ce_a")), pipeline("B", step("ocr", "ce_b"))],
            [text_view(metrics=METRIQUES_N9)],
            failure_policy=politique,
        ),
        registry_with(
            BriqueOctets("ce_a", a, partial=frozenset({"d1"})), BriqueOctets("ce_b", b)
        ),
    )


def _agregats(data: dict[str, Any], nom: str, metrique: str) -> tuple[Any, Any]:
    (entree,) = (p for p in data["pipelines"] if p["pipeline"] == nom)
    conditionnel = next(
        s for s in entree["conditional_aggregate"] if s["metric"] == metrique
    )
    operationnel = next(
        s for s in entree["operational_aggregate"] if s["metric"] == metrique
    )
    return conditionnel, operationnel


@pytest.mark.parametrize("lang", LANGUES)
@pytest.mark.parametrize("politique", POLITIQUES)
def test_n9__partout_ou_l_agregat_principal_est_affiche_l_autre_qualite_l_est_aussi(
    tmp_path: Path, politique: str, lang: str
) -> None:
    """N9, question 10 (« partout où le rapport affiche l'agrégat principal d'une
    métrique, l'autre qualité est affichée à côté, avec sa couverture » ; « publié
    veut dire affiché ») : sur les surfaces qui écrivent l'agrégat d'un pipeline par
    métrique (mesures clés, vue d'ensemble, comparaison des moteurs, profil moteur),
    si la valeur de l'agrégat principal de ``A`` est écrite pour une métrique, la
    valeur de **l'autre** qualité l'est aussi, avec sa couverture « notées /
    attendues ». Six métriques où la conditionnelle diffère de l'opérationnelle : les
    établies ``cer``, ``wer`` ; ``mer`` (établie, masquée des tableaux) ; l'adaptée
    ``cer_diplo`` et ``ins_rate`` ; l'adaptée ``char_accuracy``. ``r03``/``n9`` : seules
    ``cer`` et ``wer``, dans la vue d'ensemble, étaient accompagnées de l'autre
    qualité ; la comparaison, le profil et les mesures clés n'écrivaient que le
    principal."""
    result = _deux_qualites(tmp_path, politique)
    data = _json(result)
    surfaces = {
        "key_measures": KeyMeasuresSection(),
        "overview": OverviewSection(),
        "by_engine": EngineSection(),
        "engine_profiles": EngineProfileSection(),
    }
    textes = {nom: _section(section, result, lang) for nom, section in surfaces.items()}
    principales: dict[str, float] = {}
    autres: dict[str, float] = {}
    couvertures: dict[str, str] = {}
    for metrique in METRIQUES_N9:
        conditionnel, operationnel = _agregats(data, "A", metrique)
        principal, autre = (
            (conditionnel, operationnel)
            if politique == "exclude"
            else (operationnel, conditionnel)
        )
        assert principal["value"] != autre["value"], f"banc : {metrique}"
        principales[metrique], autres[metrique] = principal["value"], autre["value"]
        couvertures[metrique] = f"{autre['support']}/{autre['expected']}"
    valeurs = [*principales.values(), *autres.values()]
    assert len({f"{100 * v:.1f}" for v in valeurs}) == len(valeurs), "banc : collisions"
    jamais_vues = [
        m
        for m in METRIQUES_N9
        if not any(affiche(t, principales[m]) for t in textes.values())
    ]
    assert not jamais_vues, (
        f"banc : l'agrégat principal n'est affiché nulle part : {jamais_vues}"
    )
    manques: list[str] = []
    for surface, texte in textes.items():
        for metrique in METRIQUES_N9:
            if not affiche(texte, principales[metrique]):
                continue
            if not affiche(texte, autres[metrique]):
                manques.append(f"{surface}/{metrique} : autre qualité absente")
            elif not re.search(
                rf"\b{couvertures[metrique]}\b".replace("/", r"\s*/\s*"), texte
            ):
                manques.append(
                    f"{surface}/{metrique} : couverture {couvertures[metrique]}"
                )
    assert not manques, "\n".join(manques)


# --------------------------------------------------------------------------
# N10, N11 : le comparateur.
# --------------------------------------------------------------------------


def _paires_proches(texte: str, premier: str, second: str, distance: int = 80) -> bool:
    """``premier`` et ``second`` s'écrivent à moins de ``distance`` caractères
    l'un de l'autre (la politique et la qualité qui l'accompagne)."""
    return any(
        abs(m.start() - n.start()) <= distance
        for m in re.finditer(re.escape(premier), texte)
        for n in re.finditer(re.escape(second), texte, re.IGNORECASE)
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_n11__deux_runs_de_politiques_differentes_sont_compares_en_le_disant(
    tmp_path: Path, lang: str
) -> None:
    """N11 (« deux runs sous des politiques différentes sont comparés en le disant
    (qualité et politique de chaque run) ») : le rapport de comparaison d'un run
    sous ``exclude`` et d'un run sous ``empty_page`` écrit la politique de chaque
    run et, à côté, la qualité que son agrégat principal mesure (conditionnelle /
    opérationnelle ; « conditional » / « operational »). Sans cela, le Δ d'un CER
    conditionnel avec un CER opérationnel passe pour un écart de pipeline.
    ``r09`` : le rapport de comparaison ne disait rien des politiques."""
    runs = []
    for politique in POLITIQUES:
        (tmp_path / politique).mkdir()
        runs.append(_supports_differents(tmp_path / politique, politique))
    texte = texte_visible(render_comparison(runs[0], runs[1], lang=lang))
    conditionnelle, operationnelle = (
        ("conditionnelle", "opérationnelle")
        if lang == "fr"
        else ("conditional", "operational")
    )
    assert _paires_proches(texte, "exclude", conditionnelle), (
        f"la politique exclude et sa qualité ({conditionnelle}) ne sont pas dites"
    )
    assert _paires_proches(texte, "empty_page", operationnelle), (
        f"la politique empty_page et sa qualité ({operationnelle}) ne sont pas dites"
    )


def _donnees_du_widget(html: str) -> Any:
    (brut,) = re.findall(
        r'<script id="cinoc-compare-data" type="application/json">(.*?)</script>',
        html,
        re.DOTALL,
    )
    return json.loads(brut)


def _valeurs(noeud: Any) -> list[Any]:
    if isinstance(noeud, dict):
        return [v for x in noeud.values() for v in _valeurs(x)]
    if isinstance(noeud, list):
        return [v for x in noeud for v in _valeurs(x)]
    return [noeud]


def test_n11__le_widget_porte_la_politique_du_run_courant(tmp_path: Path) -> None:
    """N11 (« qualité et politique de chaque run ») : le widget « comparer un run »
    ne peut nommer la politique du run courant que s'il l'embarque. Le nom du champ
    n'est pas fixé par le contrat : on cherche la **valeur** (``exclude`` ou
    ``empty_page``) parmi celles du bloc de données inerte. ``compare_widget`` ne
    portait que le CER par pipeline."""
    manques = []
    for politique in POLITIQUES:
        (tmp_path / politique).mkdir()
        result = _supports_differents(tmp_path / politique, politique)
        valeurs = _valeurs(_donnees_du_widget(compare_widget(result)))
        if politique not in valeurs:
            manques.append(politique)
    assert not manques, f"politique(s) absente(s) des données du widget : {manques}"


def test_n10__compare_js_refuse_un_run_sans_version_ou_anterieur_a_7() -> None:
    """N10 (« ``compare.js`` et le chargeur refusent un JSON de schéma antérieur à 7,
    ou sans ``schema_version``, avec le message de re-notation »). **Limite** : le
    dépôt n'a aucun test d'exécution de ``compare.js`` (``test_compare_widget`` ne
    fait que ``node --check``, et saute sans ``node``) ; ce test ne l'exécute donc
    pas non plus. Il vérifie ce que le source doit porter : il lit
    ``schema_version`` du JSON chargé, le compare à 7, et contient le message de
    re-notation depuis l'archive (``--resume-dir``, ``--offline``). Le comportement
    se prouve côté Python par ``test_n10`` de ``test_ce_revue_1ab_2`` (le chargeur)
    et par un test d'exécution sous ``node`` que la tranche peut ajouter."""
    from cinoc.reports.embedded import asset_text

    source = asset_text("compare.js")
    manques = []
    if "schema_version" not in source:
        manques.append("le script ne lit pas schema_version")
    elif not re.search(
        r"schema_version[^;]{0,120}\b7\b|\b7\b[^;]{0,120}schema_version", source
    ):
        manques.append("le script ne compare pas schema_version à 7")
    for jeton in ("--resume-dir", "--offline"):
        if jeton not in source:
            manques.append(f"le message de re-notation ne dit pas « {jeton} »")
    assert not manques, manques


# --------------------------------------------------------------------------
# Question 7 : « Significativité » n'est plus un titre.
# --------------------------------------------------------------------------

_ANCIENS_TITRES = (
    "Significativité inter-moteurs",
    "Significativité & recouvrement",
    "Inter-engine significance",
    "Significance & overlap",
)
_NOUVEAUX_TITRES = {
    "fr": (
        "Tests inter-moteurs (exploratoires)",
        "Tests et recouvrement (exploratoires)",
    ),
    "en": ("Inter-engine tests (exploratory)", "Tests and overlap (exploratory)"),
}
_TEXTES_LIVRES = {
    ".py",
    ".yaml",
    ".yml",
    ".js",
    ".json",
    ".html",
    ".css",
    ".md",
    ".txt",
}


def test_q7__aucun_texte_livre_ne_porte_un_ancien_titre_de_significativite() -> None:
    """Question 7 (« « Significativité inter-moteurs », « Significativité &
    recouvrement » et leurs équivalents anglais deviennent « Tests inter-moteurs
    (exploratoires) », « Tests et recouvrement (exploratoires) », « Inter-engine
    tests (exploratory) », « Tests and overlap (exploratory) » » ; « jamais présenté
    comme significatif ») : aucun fichier de ``cinoc/`` ne contient plus un des
    quatre anciens titres. ``cross_engine.py`` et ``renderer.py`` les portaient."""
    trouves = []
    for chemin in sorted((RACINE / "cinoc").rglob("*")):
        if chemin.suffix not in _TEXTES_LIVRES or "__pycache__" in chemin.parts:
            continue
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        for titre in _ANCIENS_TITRES:
            if titre in texte:
                trouves.append(f"{chemin.relative_to(RACINE)} : « {titre} »")
    assert not trouves, trouves


@pytest.mark.parametrize("lang", LANGUES)
def test_q7__le_rapport_rendu_porte_les_nouveaux_titres_et_aucun_ancien(
    tmp_path: Path, lang: str
) -> None:
    """Question 7 : le rapport rendu (trois moteurs, donc la section des tests
    inter-moteurs) ne contient aucun ancien titre, et contient les deux nouveaux
    (le titre de la section et celui du groupe du sommaire)."""
    texte = _rendu(_supports_differents(tmp_path, "exclude"), lang)
    anciens = [titre for titre in _ANCIENS_TITRES if titre in texte]
    assert not anciens, f"anciens titres rendus : {anciens}"
    absents = [titre for titre in _NOUVEAUX_TITRES[lang] if titre not in texte]
    assert not absents, f"titres du contrat absents du rapport : {absents}"


# --------------------------------------------------------------------------
# Question 8 : un pipeline hors vue n'a aucune ligne dans les tableaux par document.
# --------------------------------------------------------------------------

REF_Q8 = "abcdefghij"
#: Les sections qui portent les faits d'exécution (issues d'unité, coûts, montage).
_SECTIONS_D_EXECUTION = (EconomicsSection(), CompositionSection())


def _hors_vue(tmp_path: Path) -> RunResult:
    """``Phors`` (un OCR seul, ``RAW_TEXT``) ne produit aucun type que la vue
    « corrige » note, et échoue sur ``d1`` ; ``Qdans`` (OCR puis correction) est vu."""
    refs = {"d1": REF_Q8, "d2": REF_Q8, "d3": REF_Q8}
    p = BriqueOctets(
        "ce_ocr_p",
        {"d1": AdapterStepError("panne"), "d2": REF_Q8.encode(), "d3": REF_Q8.encode()},
    )
    q_ocr = BriqueOctets("ce_ocr_q", dict.fromkeys(refs, b"abcdefghiX"))
    q_corr = BriqueOctets(
        "ce_corr_q",
        dict.fromkeys(refs, REF_Q8.encode()),
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    chaine = pipeline(
        "Qdans",
        step("ocr", "ce_ocr_q"),
        step("corr", "ce_corr_q", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT),
    )
    return execute(
        spec(
            corpus(tmp_path, refs),
            [pipeline("Phors", step("ocr", "ce_ocr_p")), chaine],
            [text_view("corrige", candidates=(T.CORRECTED_TEXT,))],
        ),
        registry_with(p, q_ocr, q_corr),
    )


@pytest.mark.parametrize("lang", LANGUES)
def test_q8__un_pipeline_hors_vue_n_a_aucune_ligne_dans_les_tableaux_par_document(
    tmp_path: Path, lang: str
) -> None:
    """Question 8 (« un pipeline hors vue n'a aucune ligne dans les tableaux d'une
    vue où il est hors vue ; les faits d'exécution (issues d'unité, coûts) restent
    dans les sections d'exécution » ; D1) : ``Phors`` ne produit pas de texte
    corrigé, la vue « corrige » ne le voit pas. Les sections par document (le
    tableau et la galerie des documents, les fiches de détail, le duel) ne le
    nomment pas, alors que son échec sur ``d1`` reste lisible dans le reste du
    rapport. ``q8`` : ses trois documents étaient listés, avec le CER vide."""
    result = _hors_vue(tmp_path)
    nomme = [
        nom
        for nom, section in (
            ("documents", DocumentsSection()),
            ("document_details", DocumentDetailSection()),
            ("engine_duel", EngineDuelSection()),
        )
        if re.search(r"\bPhors\b", _section(section, result, lang))
    ]
    assert not nomme, f"« Phors », hors vue, est nommé dans : {nomme}"
    execution = " ".join(
        _section(section, result, lang)
        for section in (OverviewSection(), *_SECTIONS_D_EXECUTION)
    )
    assert re.search(r"\bPhors\b[^.]{0,80}\bd1\b[^.]{0,80}\bpanne\b", execution), (
        "l'échec de Phors sur d1 n'est plus lisible dans les sections d'exécution"
    )


# --------------------------------------------------------------------------
# Question 9 : le CSV exporte les deux qualités.
# --------------------------------------------------------------------------


def _lignes_agregat(
    texte: str, pipeline_nom: str, metrique: str
) -> list[dict[str, str]]:
    return [
        ligne
        for ligne in csv.DictReader(io.StringIO(texte))
        if ligne["pipeline"] == pipeline_nom
        and ligne["metric"] == metrique
        and not ligne["document_id"]
        and ligne["scope"] not in {"document", "usage"}
    ]


def _qualite_nommee(ligne: dict[str, str]) -> str | None:
    """Ce que le CSV dit de la qualité de la ligne : ``conditional`` ou
    ``operational`` quelque part dans ses cellules (les noms de champ du contrat,
    ``conditional_aggregate`` et ``operational_aggregate``)."""
    noms = {
        m.group(0).lower()
        for cellule in ligne.values()
        for m in re.finditer(r"conditional|operational", cellule or "", re.IGNORECASE)
    }
    return noms.pop() if len(noms) == 1 else None


def _marquee_principale(ligne: dict[str, str]) -> bool:
    for nom, cellule in ligne.items():
        valeur = (cellule or "").strip().lower()
        if re.search(r"principal|primary", valeur):
            return True
        if re.search(r"principal|primary", nom or "", re.IGNORECASE) and valeur in {
            "1",
            "true",
            "yes",
            "oui",
            "x",
        }:
            return True
    return False


@pytest.mark.parametrize("politique", POLITIQUES)
def test_q9__le_csv_exporte_les_deux_qualites_et_marque_la_principale(
    tmp_path: Path, politique: str
) -> None:
    """Question 9 (« le CSV exporte les deux qualités, chacune nommée, et marque
    laquelle est principale ») : pour le CER de ``A`` (une page en échec, une
    partielle : les deux qualités diffèrent), le CSV a une ligne d'agrégat par
    qualité, qui se nomme (« conditional » / « operational », les noms des champs
    stockés), porte la valeur exacte de sa qualité, et **une seule** est marquée
    principale — la conditionnelle sous ``exclude``, l'opérationnelle sous
    ``empty_page``. Les noms de colonne ne sont pas fixés par le contrat : on lit les
    cellules. ``csv_export`` n'écrivait que l'agrégat principal, sans le dire."""
    result = _supports_differents(tmp_path, politique)
    data = _json(result)
    conditionnel, operationnel = _agregats(data, "A", "cer")
    assert conditionnel["value"] != operationnel["value"], "contrôle du banc"
    lignes = _lignes_agregat(run_result_csv(result), "A", "cer")
    par_qualite = {_qualite_nommee(ligne): ligne for ligne in lignes}
    assert set(par_qualite) == {"conditional", "operational"}, (
        f"qualités nommées dans le CSV : {sorted(map(str, par_qualite))}"
    )
    assert float(par_qualite["conditional"]["value"]) == conditionnel["value"]
    assert float(par_qualite["operational"]["value"]) == operationnel["value"]
    marquees = sorted(
        q for q, ligne in par_qualite.items() if _marquee_principale(ligne)
    )
    principale = "conditional" if politique == "exclude" else "operational"
    assert marquees == [principale], f"qualité(s) marquée(s) principale(s) : {marquees}"

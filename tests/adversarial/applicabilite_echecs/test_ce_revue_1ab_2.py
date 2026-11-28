"""Tranche 1b — la seconde revue indépendante de 1a + 1b.

Révision n° 7 de ``CONTRATS.md``, « Précisions tranchées le 28/11 après la seconde
validation » (défauts N1 à N12, questions 1 à 10 ; contre-exemples ``r01`` à
``r11`` de ``revue-1ab-2/``). Chaque test traduit **une** précision, citée en
docstring avec son défaut. Les points qui se lisent **dans le rapport**
(N3 affiché, N4, N7, N8, N9, N10/N11 côté comparateur, questions 5, 7, 8, 9) sont
dans ``tests/adversarial/rapports/test_ce_revue_1ab_2_rapport.py``.

Ce module couvre : N1 (une étape déclare ses types de sortie), N2 (provenance des
archives S30), N3 (classes non déclarées, côté données), N5 (``stat_partielle`` a un
seul sens), N6 (grappe implicite sans collision), N10 (le chargeur refuse un JSON
sans version ou antérieur à 7).

Les noms que le contrat ne fixe pas (le champ qui porte le statut ``not_declared``
d'une ligne de décisions, la forme des comptes absents) ne sont **pas** inventés :
les tests les cherchent par leur structure et disent ce qui manque.

N12 : le test ``test_decision_counts_use_complete_text_not_the_display_excerpt``
de ``tests/evaluation/test_decisions_review.py`` est **réécrit** (il était
tautologique), et les commentaires de ``tests/adversarial/_contrat.py`` qui citaient
``PipelineResult.aggregate`` sont corrigés.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from cinoc.app import load_run_spec
from cinoc.app.results import RunResultError, load_run_result
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.errors import CinocError
from cinoc.domain.run import RunManifest
from cinoc.evaluation.result import RunResult
from cinoc.interfaces import cli
from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER
from tests.adversarial._contrat import corpus_declare, document_en_grappe

from ._kit import T, corpus, execute, pipeline, registry_with, spec, step, text_view
from ._kit_revue import (
    LAYOUT_ILLISIBLE,
    BriqueOctets,
    layout_octets,
    run_archive_sans_classes,
    verifie_agregat,
    vue_layout,
)

pytestmark = pytest.mark.tranche("1b")

POLITIQUES = ("exclude", "empty_page")
RACINE = Path(__file__).resolve().parents[3]


def _json(result: RunResult) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(result.model_dump_json())
    return data


# --------------------------------------------------------------------------
# N1 : une étape déclare ses types de sortie.
# --------------------------------------------------------------------------

ETAPE_MUETTE = "etape_muette"


def _spec_yaml(avec_sorties: bool) -> dict[str, Any]:
    """Une spec de rejeu dont l'étape ``etape_muette`` déclare, ou non, ses types
    de sortie. ``r01``/``d1yaml`` : la seconde étape de l'exemple de la revue."""
    etape: dict[str, Any] = {
        "id": ETAPE_MUETTE,
        "kind": "ocr",
        "adapter_name": "precomputed:ocr",
        "input_types": ["image"],
    }
    if avec_sorties:
        etape["output_types"] = ["raw_text"]
    return {
        "pipelines": [{"name": "rejeu", "initial_inputs": ["image"], "steps": [etape]}],
        "evaluation": {
            "views": [
                {
                    "name": "texte",
                    "candidate_types": ["raw_text"],
                    "metric_names": ["cer"],
                }
            ]
        },
        "adapter_kwargs": {"precomputed:ocr": {"source_label": "ocr"}},
    }


def _config(dossier: Path, avec_sorties: bool) -> Path:
    """Un fichier de run complet (corpus d'un document + rejeu), lisible par la CLI."""
    (dossier / "d1.png").write_bytes(b"\x89PNG stub")
    (dossier / "d1.gt.txt").write_text("le soleil", encoding="utf-8")
    (dossier / "d1.ocr.txt").write_text("le so1eil", encoding="utf-8")
    contenu = {
        "corpus": {
            "name": "ce",
            "documents": [
                {
                    "id": "d1",
                    "image_uri": "d1.png",
                    "ground_truths": [{"type": "raw_text", "uri": "d1.gt.txt"}],
                }
            ],
        },
        **_spec_yaml(avec_sorties),
        "run_id": "n1",
    }
    chemin = dossier / "config.yaml"
    chemin.write_text(yaml.safe_dump(contenu, allow_unicode=True), encoding="utf-8")
    return chemin


def test_n1__une_etape_sans_types_de_sortie_est_refusee_au_chargement(
    tmp_path: Path,
) -> None:
    """N1 (« une ``RunSpec`` dont une étape a ``output_types`` vide est refusée au
    chargement, avec le nom de l'étape » ; F8, « jamais un défaut muet ») :
    ``load_run_spec`` refuse la spec par une erreur typée (``CinocError``) qui
    nomme l'étape. Contrôle : la même spec, avec ``output_types``, se charge.
    ``d1yaml`` : l'étape sans sortie était chargée, puis ignorée par la vue."""
    (tmp_path / "ok").mkdir()
    assert load_run_spec(_config(tmp_path / "ok", True)).pipelines, "contrôle"
    (tmp_path / "ko").mkdir()
    chemin = _config(tmp_path / "ko", False)
    with pytest.raises(CinocError) as erreur:
        load_run_spec(chemin)
    assert ETAPE_MUETTE in str(erreur.value), (
        f"le refus ne nomme pas l'étape : {erreur.value}"
    )


def test_n1__le_check_de_la_cli_refuse_l_etape_sans_types_de_sortie(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """N1 (« refusée au chargement (``--check``, CLI) ») : ``cinoc run --check``
    sort en erreur (code 1), nomme l'étape sur la sortie d'erreur, et n'écrit pas
    « Spec valide ». Contrôle : la même spec avec ``output_types`` passe le
    ``--check``. ``d1yaml`` : ``--check`` répondait « Spec valide »."""
    (tmp_path / "ok").mkdir()
    assert cli.main(["run", str(_config(tmp_path / "ok", True)), "--check"]) == 0
    capsys.readouterr()
    (tmp_path / "ko").mkdir()
    code = cli.main(["run", str(_config(tmp_path / "ko", False)), "--check"])
    sortie = capsys.readouterr()
    assert code == 1, f"--check a accepté la spec (code {code})"
    assert ETAPE_MUETTE in sortie.err, f"stderr : {sortie.err!r}"
    assert "Spec valide" not in sortie.out


def test_n1__le_run_de_la_cli_refuse_avant_toute_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """N1 (« aucune exécution ») : sans ``--check``, la CLI refuse la même spec
    **avant** d'appeler l'orchestrateur et n'écrit aucun rapport."""
    exécutions: list[str] = []

    def _interdit(*args: object, **kwargs: object) -> RunResult:
        exécutions.append("orchestrateur")
        raise AssertionError("l'orchestrateur a été appelé sur une spec refusée")

    monkeypatch.setattr(cli, "run_orchestrator", _interdit)
    chemin = _config(tmp_path, False)
    rapport = tmp_path / "rapport.html"
    code = cli.main(["run", str(chemin), "-o", str(rapport)])
    erreur = capsys.readouterr().err
    assert not exécutions, "une exécution a eu lieu"
    assert code == 1, f"le run a accepté la spec (code {code})"
    assert ETAPE_MUETTE in erreur, f"stderr : {erreur!r}"
    assert not rapport.exists()


def test_n1__le_depot_web_refuse_l_etape_sans_types_de_sortie(tmp_path: Path) -> None:
    """N1 (« refusée au chargement (…, dépôt web) ») : ``POST /api/runs/spec``
    répond 422 et nomme l'étape ; aucun job n'est lancé. Contrôle : la même spec
    avec ``output_types`` est acceptée (201)."""
    client = TestClient(create_app(reports_dir=tmp_path, rate_limit=1000))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("p1.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        zf.writestr("p1.gt.txt", "le soleil")
        zf.writestr("p1.ocr.txt", "le so1eil")
    corpus_id = client.post(
        "/api/corpus",
        files={"file": ("c.zip", archive.getvalue(), "application/zip")},
        headers={CSRF_HEADER: "1"},
    ).json()["corpus_id"]

    def deposer(avec_sorties: bool) -> Any:
        return client.post(
            "/api/runs/spec",
            headers={CSRF_HEADER: "1"},
            json={
                "corpus_id": corpus_id,
                "spec": yaml.safe_dump(_spec_yaml(avec_sorties), allow_unicode=True),
            },
        )

    assert deposer(True).status_code == 201, "contrôle : la spec complète est acceptée"
    refus = deposer(False)
    assert refus.status_code == 422, (refus.status_code, refus.text)
    assert ETAPE_MUETTE in refus.text, f"le refus ne nomme pas l'étape : {refus.text}"


# --------------------------------------------------------------------------
# N2 : la provenance des archives S30 dit leurs replis.
# --------------------------------------------------------------------------

PROVENANCE = RACINE / "campaigns" / "2026-11-26-reference" / "v7" / "PROVENANCE.md"


def _sections(texte: str) -> list[str]:
    """Les sections d'un document Markdown, découpées à chaque titre."""
    return [bloc for bloc in re.split(r"(?m)^#{1,6}\s", texte) if bloc.strip()]


def test_n2__la_provenance_v7_dit_les_replis_et_la_non_conformite_de_e3_et_e4() -> None:
    """N2 (« ``PROVENANCE.md`` le dit avec ces comptes ; la qualité conditionnelle
    v7 de E3 et E4 y est déclarée **non conforme au § 2.1 f** et ne doit pas être
    citée ») : une même section de ``campaigns/2026-11-26-reference/v7/PROVENANCE.md``
    nomme E3 et E4, le code de repli ``all_attempts_exhausted``, les comptes de
    Dresden (129 lignes sur 132, 10 unités sur 10) et de BNL (110 sur 218,
    39 sur 74), déclare la qualité conditionnelle non conforme au § 2.1 f et
    interdit de la citer. Le fichier ne disait rien de ces replis : il présentait la
    qualité conditionnelle de E3 et E4 comme un résultat."""
    texte = PROVENANCE.read_text(encoding="utf-8")
    paire = r"{a}\s*(?:/|sur)\s*{b}"
    attendus = {
        "Dresden, 129 lignes sur 132": paire.format(a=129, b=132),
        "Dresden, 10 unités sur 10": paire.format(a=10, b=10),
        "BNL, 110 lignes sur 218": paire.format(a=110, b=218),
        "BNL, 39 unités sur 74": paire.format(a=39, b=74),
    }
    candidates = [
        section
        for section in _sections(texte)
        if "all_attempts_exhausted" in section and re.search(r"\bE3\b", section)
    ]
    assert candidates, (
        "aucune section de PROVENANCE.md ne nomme E3 et le repli all_attempts_exhausted"
    )
    section = "\n\n".join(candidates)
    manques = [
        libelle for libelle, motif in attendus.items() if not re.search(motif, section)
    ]
    assert not manques, f"comptes de replis absents de la provenance : {manques}"
    assert re.search(r"\bE4\b", section), "E4 n'est pas nommé avec les replis"
    assert re.search(r"non\s+conforme", section), (
        "la qualité conditionnelle de E3 et E4 n'est pas déclarée non conforme"
    )
    assert re.search(r"2\.1\s*f", section), "la non-conformité ne cite pas le § 2.1 f"
    assert re.search(
        r"ne\s+(?:doit|peut)\s+pas\s+être\s+cité|ne\s+pas\s+(?:la\s+)?cite", section
    ), "la provenance n'interdit pas de citer cette qualité"


# --------------------------------------------------------------------------
# N3 : un sidecar sans classe déclarée ne produit aucun compte.
# --------------------------------------------------------------------------

_COMPTES_ENTIERS = ("n_lines", "corrected", "review_required", "abstained")


def _ligne_pipeline(result: RunResult) -> dict[str, Any]:
    data = _json(result)
    (decisions,) = [
        a["payload"] for a in data["analyses"] if a["payload"]["kind"] == "decisions"
    ]
    (ligne,) = decisions["pipelines"]
    assert isinstance(ligne, dict)
    return ligne


def test_n3__un_sidecar_sans_line_class_donne_un_statut_not_declared_sans_aucun_compte(
    tmp_path: Path,
) -> None:
    """N3 (« non-mesure typée, K2 » ; « un sidecar sans ``line_class`` ne produit
    aucun compte : la ligne du pipeline porte le statut ``not_declared``, sans
    compte. Jamais un zéro ») : le correcteur rend trois lignes (une corrigée
    d'après son texte, une intacte, une en repli d'après son statut), aucune ne
    déclare sa classe. La ligne du pipeline porte le statut ``not_declared`` — le
    champ qui le porte n'est pas fixé par le contrat, on cherche la valeur — et
    aucun compte entier (``None`` ou absent, jamais ``0``), ni refus ni repli.
    ``c09``/``dresden.toutes`` : ``n_lines`` 0, ``corrected`` 0… quatre zéros qui
    disent « ce correcteur n'a rien fait »."""
    ligne = _ligne_pipeline(run_archive_sans_classes(tmp_path))
    statuts = [nom for nom, valeur in ligne.items() if valeur == "not_declared"]
    assert statuts, (
        "aucun champ de la ligne du pipeline ne vaut « not_declared » "
        f"(CONTRATS.md N3) : {sorted(ligne)}"
    )
    comptes = {nom: ligne.get(nom) for nom in _COMPTES_ENTIERS}
    assert all(valeur is None for valeur in comptes.values()), (
        f"comptes publiés pour des classes non déclarées : {comptes}"
    )
    assert not ligne.get("refused") and not ligne.get("fallback"), (
        ligne.get("refused"),
        ligne.get("fallback"),
    )
    assert not ligne.get("samples"), "des lignes sont montrées sans classe déclarée"


# --------------------------------------------------------------------------
# N5 : stat_partielle a un seul sens.
# --------------------------------------------------------------------------

REFS_N5 = {
    "d1": "abcdefghij",
    "d2": "klmnopqrst",
    "d3": "uvwxyz0123",
    "d4": "ABCDEFGHIJ",
}
#: Une sortie illisible n'a rien produit de lisible : la statistique « sortie
#: vide » d'une page de dix caractères de référence.
VIDE_DIX = {
    "substitutions": 0,
    "deletions": 10,
    "insertions": 0,
    "reference_length": 10,
}


def _illisibles(tmp_path: Path, politique: str) -> RunResult:
    """``r02`` (V3) : ``d2`` illisible **et** partielle, ``d3`` illisible **et**
    tronquée, ``d4`` illisible seule ; ``d1`` exacte."""
    a = BriqueOctets(
        "ce_a",
        {
            "d1": layout_octets(REFS_N5["d1"]),
            "d2": LAYOUT_ILLISIBLE,
            "d3": LAYOUT_ILLISIBLE,
            "d4": LAYOUT_ILLISIBLE,
        },
        partial=frozenset({"d2"}),
        truncate=frozenset({"d3"}),
        out_type=T.LAYOUT,
    )
    return execute(
        spec(
            corpus(tmp_path, REFS_N5),
            [pipeline("A", step("ocr", "ce_a", out_type=T.LAYOUT))],
            [vue_layout()],
            failure_policy=politique,
        ),
        registry_with(a),
    )


def test_n5__une_sortie_illisible_n_a_pas_de_stat_partielle_sous_aucune_politique(
    tmp_path: Path,
) -> None:
    """N5, question 6 (« ``stat_partielle`` porte ce qui a été produit et lu ; une
    sortie illisible n'a rien produit de lisible : ``stat_partielle`` = ``None``
    sous les deux politiques, la statistique vide va dans ``stat_vide`` ») : pour
    ``d2`` (illisible + partielle), ``d3`` (illisible + tronquée) et ``d4``
    (illisible seule), sous ``exclude`` comme sous ``empty_page``,
    ``stat_partielle`` est ``None`` et ``stat_vide`` porte la page vide (dix
    suppressions). ``r02`` (V3) : sous ``empty_page``, ``stat_partielle`` recopiait
    la statistique vide — elle disait « partielle » d'une sortie qui n'a rien
    donné."""
    for politique in POLITIQUES:
        (tmp_path / politique).mkdir()
        data = _json(_illisibles(tmp_path / politique, politique))
        scores = {
            d["document_id"]: d["scores"][0]
            for d in data["documents"]
            if d["pipeline"] == "A"
        }
        for document in ("d2", "d3", "d4"):
            score = scores[document]
            assert score["availability"] == "output_unreadable", "contrôle du banc"
            assert score["stat_partielle"] is None, (
                f"[{politique}] {document} : stat_partielle = {score['stat_partielle']}"
                " pour une sortie illisible"
            )
            vide = score["stat_vide"]
            assert (
                vide is not None and {nom: vide[nom] for nom in VIDE_DIX} == VIDE_DIX
            ), f"[{politique}] {document} : stat_vide = {vide}"


# --------------------------------------------------------------------------
# N6 : une grappe implicite ne se confond avec aucune grappe déclarée.
# --------------------------------------------------------------------------

REFS_N6 = {"g": "abcdefghij", "x1": "abcdefghij", "x2": "abcdefghij"}
GRAPPES_N6 = {"x1": "g", "x2": "g"}  # « g » est aussi l'id d'un document sans grappe


def _collision(tmp_path: Path) -> RunResult:
    """``r08`` : le document ``g`` n'a pas de grappe et son identifiant égale le nom
    de la grappe déclarée ``g`` (``x1``, ``x2``). ``g`` est faux, ``x1`` et ``x2``
    exacts."""
    base = corpus(tmp_path, REFS_N6)
    documents = tuple(
        document_en_grappe(d, GRAPPES_N6[d.id]) if d.id in GRAPPES_N6 else d
        for d in base.documents
    )
    declare = corpus_declare(
        CorpusSpec(name="ce", documents=documents),
        target_population="population de test",
        cluster_weighting="cluster",
    )
    brique = BriqueOctets(
        "ce_g", {"g": b"##########", "x1": b"abcdefghij", "x2": b"abcdefghij"}
    )
    return execute(
        spec(declare, [pipeline("A", step("ocr", "ce_g"))], [text_view()]),
        registry_with(brique),
    )


@pytest.mark.parametrize("qualite", ["conditionnelle", "operationnelle"])
def test_n6__le_macro_par_grappe_distingue_le_singleton_de_la_grappe_declaree(
    tmp_path: Path, qualite: str
) -> None:
    """N6 (« la clé de regroupement distingue « déclarée » de « singleton » ») :
    le document ``g`` (CER 1) forme **sa** grappe, distincte de la grappe déclarée
    ``g`` (``x1``, ``x2``, CER 0) : le macro par grappe est (1 + 0) / 2 = **0,5**
    — pas 1/3, la moyenne des trois documents que donne la fusion dans la grappe
    « g ». Le champ ``cluster`` du document sans grappe est ``null`` dans le JSON
    (``x1`` et ``x2`` portent ``g``), et le macro se recalcule depuis le JSON avec
    la clé « déclarée / singleton » (``recalcule(..., implicites=True)``). ``r08`` :
    macro publié 0,3333."""
    data = _json(_collision(tmp_path))
    grappes = {d["document_id"]: d.get("cluster", "ABSENT") for d in data["documents"]}
    assert grappes == {"g": None, "x1": "g", "x2": "g"}, (
        f"contrôle : « cluster » est null pour le document sans grappe : {grappes}"
    )
    cle = (
        "conditional_aggregate"
        if qualite == "conditionnelle"
        else "operational_aggregate"
    )
    publie = data["pipelines"][0][cle][0]["macro"]
    assert publie == 0.5, f"macro par grappe {publie!r} (attendu 0,5 : singleton)"
    verifie_agregat(data, "A", "texte", REFS_N6, qualite, "cluster", implicites=True)


# --------------------------------------------------------------------------
# N10 : le chargeur refuse un JSON sans version ou antérieur à 7.
# --------------------------------------------------------------------------


def _json_de_run(tmp_path: Path) -> dict[str, Any]:
    from datetime import UTC, datetime

    instant = datetime(2026, 11, 28, tzinfo=UTC)
    resultat = RunResult(
        manifest=RunManifest(
            run_id="r",
            corpus_name="c",
            n_documents=1,
            code_version="1.0",
            started_at=instant,
            completed_at=instant,
        )
    )
    data: dict[str, Any] = json.loads(resultat.model_dump_json())
    assert data["schema_version"] == 7, "contrôle : le schéma courant"
    return data


def test_n10__le_chargeur_refuse_sans_version_ou_en_v6_avec_la_renotation(
    tmp_path: Path,
) -> None:
    """N10 (« ``compare.js`` et le chargeur refusent un JSON de schéma antérieur à
    7, ou sans ``schema_version``, avec le message de re-notation » ; rupture
    explicite, arbitrage n° 3 du 28/11) : ``load_run_result`` lève ``RunResultError``
    pour un JSON **sans** ``schema_version`` et pour un JSON en **v6**, et le message
    donne la re-notation depuis l'archive (``--resume-dir``, ``--offline``). Contrôle :
    le même JSON en v7 se charge. ``r09`` : un JSON sans version était lu comme
    courant — ses agrégats, de sens antérieur, passaient pour des v7."""
    data = _json_de_run(tmp_path)
    ok = tmp_path / "v7.json"
    ok.write_text(json.dumps(data), encoding="utf-8")
    assert load_run_result(ok).schema_version == 7, "contrôle"
    cas = {
        "sans schema_version": {k: v for k, v in data.items() if k != "schema_version"},
        "schema_version 6": {**data, "schema_version": 6},
    }
    problemes: list[str] = []
    for nom, contenu in cas.items():
        chemin = tmp_path / f"{nom.replace(' ', '_')}.json"
        chemin.write_text(json.dumps(contenu), encoding="utf-8")
        try:
            load_run_result(chemin)
        except RunResultError as exc:
            message = str(exc)
            for attendu in ("--resume-dir", "--offline"):
                if attendu not in message:
                    problemes.append(f"{nom} : le message ne dit pas « {attendu} »")
        else:
            problemes.append(f"{nom} : le JSON a été chargé")
    assert not problemes, problemes

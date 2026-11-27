"""``cinoc correct`` — l'assemblage, pas seulement ses pièces.

Le planificateur avait ses tests, l'adapter les siens ; ce qui les **compose**
n'en avait aucun. C'est pourtant là que vit la commande telle qu'un utilisateur
la tape : un dossier d'ALTO en entrée, un rapport HTML en sortie, et — quand on
répète — une fourchette écrite à côté.

Producteur ``rules`` partout : déterministe, hors ligne. Ce qui est vérifié est
le **chemin**, pas la qualité d'un correcteur.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from cinoc.app.variance import MetricSpread, VarianceSummary
from cinoc.interfaces._correction_command import run_correction, write_variance

_needs_saknussemm = pytest.mark.skipif(
    importlib.util.find_spec("saknussemm") is None,
    reason="saknussemm absent — la correction structurée passe par lui.",
)

_NS = 'xmlns="http://www.loc.gov/standards/alto/ns-v4#"'

#: Le ``ſ`` long est l'une des substitutions des règles françaises par défaut :
#: sans lui, le test ne distinguerait pas « rien à corriger » de « la chaîne ne
#: corrige rien ».
_ALTO = (
    f'<alto {_NS}><Layout><Page ID="P1" WIDTH="600" HEIGHT="400"><PrintSpace>'
    '<TextBlock ID="B1">'
    '<TextLine ID="L1" HPOS="10" VPOS="10" WIDTH="300" HEIGHT="30">'
    '<String CONTENT="le" WC="0.9"/><SP/><String CONTENT="ſoleil"/></TextLine>'
    '<TextLine ID="L2" HPOS="10" VPOS="50" WIDTH="300" HEIGHT="30">'
    '<String CONTENT="rien"/><SP/><String CONTENT="ici"/></TextLine>'
    "</TextBlock></PrintSpace></Page></Layout></alto>"
).encode()


@pytest.fixture
def dossier_alto(tmp_path: Path) -> Path:
    source = tmp_path / "alto"
    source.mkdir()
    for nom in ("page1", "page2"):
        (source / f"{nom}.xml").write_bytes(_ALTO)
        # Pas une vraie image : la chaîne lit l'ALTO, et les vignettes se
        # dégradent gracieusement quand l'octet n'est pas décodable.
        (source / f"{nom}.png").write_bytes(b"pas une vraie image")
    return source


def _spread(metric: str, spread: float | None) -> MetricSpread:
    return MetricSpread(
        pipeline="alto→rules",
        view="texte",
        metric=metric,
        n=3,
        minimum=0.10,
        median_value=0.20,
        maximum=0.10 + (spread or 0.0),
        spread=spread,
    )


# --------------------------------------------------------------------------- #
# La fourchette écrite à côté du rapport
# --------------------------------------------------------------------------- #


def test_the_spread_is_written_next_to_the_report_and_printed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Écrite **et** affichée : un fichier qu'on ne regarde pas ne protège de
    rien, et c'est la fourchette la plus large qui borne ce qu'on a le droit
    d'affirmer."""
    sortie = tmp_path / "rapport.html"
    resume = VarianceSummary(
        runs=3,
        corpus="alto",
        spreads=(_spread("cer", 0.25), _spread("wer", 0.05)),
    )

    write_variance(sortie, resume)

    ecrit = sortie.with_suffix(".html.variance.json")
    assert ecrit.exists(), "la fourchette doit voisiner le rapport, pas le remplacer"
    relu = json.loads(ecrit.read_text(encoding="utf-8"))
    assert relu["runs"] == 3
    assert [s["metric"] for s in relu["spreads"]] == ["cer", "wer"]

    affiche = capsys.readouterr().out
    assert "Variance sur 3 runs (alto)" in affiche
    # La plus instable d'abord : c'est elle qui borne les comparaisons.
    assert affiche.index("cer") < affiche.index("wer")
    assert "est du bruit" in affiche


def test_each_range_names_its_view_and_where_it_lives(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """S34b, n° 12 : ``cer : 0.0051 – 0.0051`` deux fois — une par vue — sans
    dire laquelle ; et rien ne disait que la fourchette n'est pas au rapport."""
    lignes = (
        _spread("cer", 0.25),
        _spread("cer", 0.25).model_copy(update={"view": "texte (lignes)"}),
    )
    write_variance(
        tmp_path / "r.html", VarianceSummary(runs=3, corpus="c", spreads=lignes)
    )
    affiche = capsys.readouterr().out
    assert "alto→rules · texte · cer :" in affiche
    assert "alto→rules · texte (lignes) · cer :" in affiche
    assert "le rapport HTML porte le dernier run" in affiche


def test_without_a_measurable_spread_the_summary_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Aucune métrique applicable → le dire. Une section vide se lirait
    « stable »."""
    write_variance(
        tmp_path / "r.html",
        VarianceSummary(runs=2, corpus="alto", spreads=(_spread("cer", None),)),
    )
    affiche = capsys.readouterr().out
    assert "aucune métrique applicable" in affiche
    assert "est du bruit" not in affiche


# --------------------------------------------------------------------------- #
# La commande entière
# --------------------------------------------------------------------------- #


@_needs_saknussemm
def test_a_folder_of_alto_becomes_a_report(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le parcours que tape un utilisateur : un dossier d'ALTO, un rapport."""
    sortie = tmp_path / "rapport.html"

    code = run_correction(
        str(dossier_alto),
        str(sortie),
        producer="rules",
        model="",
        host="http://localhost:11434",
        ocr_sidecar="",
        ground_truth=True,
        repeat=1,
    )

    assert code == 0
    html = sortie.read_text(encoding="utf-8")
    assert html.startswith("<!DOCTYPE html>")
    assert "alto" in html
    assert "2 document(s) corrigé(s)" in capsys.readouterr().out
    # Un seul run : pas de fourchette — elle n'en serait pas une.
    assert not sortie.with_suffix(".html.variance.json").exists()


@_needs_saknussemm
def test_repeating_the_run_writes_a_spread_beside_the_report(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--repeat`` existe pour ne jamais publier une décimale isolée."""
    sortie = tmp_path / "rapport.html"

    code = run_correction(
        str(dossier_alto),
        str(sortie),
        producer="rules",
        model="",
        host="http://localhost:11434",
        ocr_sidecar="",
        ground_truth=True,
        repeat=2,
    )

    assert code == 0
    assert sortie.exists()
    fourchette = sortie.with_suffix(".html.variance.json")
    assert json.loads(fourchette.read_text(encoding="utf-8"))["runs"] == 2
    affiche = capsys.readouterr().out
    assert "run 1/2" in affiche and "run 2/2" in affiche


@_needs_saknussemm
def test_an_ocr_alto_is_not_treated_as_a_reference(
    dossier_alto: Path, tmp_path: Path
) -> None:
    """``--no-ground-truth`` : comparer un ALTO d'OCR à lui-même donnerait un
    CER nul **par construction**, qui ressemble à un excellent résultat."""
    sortie = tmp_path / "rapport.html"

    code = run_correction(
        str(dossier_alto),
        str(sortie),
        producer="rules",
        model="",
        host="http://localhost:11434",
        ocr_sidecar="",
        ground_truth=False,
        repeat=1,
    )

    assert code == 0
    assert sortie.exists()


@_needs_saknussemm
def test_failed_units_end_with_the_same_summary_and_code_as_run(
    dossier_alto: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reste de S10b (D-282) : ``cinoc correct`` sortait en code 0 sans bilan
    quand des unités échouaient — même défaut que D2. Même bilan et même code
    3 que ``cinoc run``, rapport écrit quand même."""
    from cinoc.adapters.layout.saknussemm_correct import SaknussemmCorrector
    from cinoc.domain.errors import AdapterStepError
    from cinoc.interfaces._run_summary import EXIT_UNITS_FAILED

    original = SaknussemmCorrector.execute

    def flaky(self, inputs, params, context, control):  # noqa: ANN001, ANN202
        if context.document_id == "page2":
            raise AdapterStepError("correcteur injoignable")
        return original(self, inputs, params, context, control)

    monkeypatch.setattr(SaknussemmCorrector, "execute", flaky)
    sortie = tmp_path / "rapport.html"
    code = run_correction(
        str(dossier_alto),
        str(sortie),
        producer="rules",
        model="",
        host="http://localhost:11434",
        ocr_sidecar="",
        ground_truth=True,
        repeat=1,
    )
    assert code == EXIT_UNITS_FAILED == 3
    assert sortie.exists()
    err = capsys.readouterr().err
    assert "Bilan : 1 unité(s) en échec / 2 (moteur : 1)" in err


@_needs_saknussemm
def test_a_clean_correction_says_so(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_correction(
        str(dossier_alto),
        str(tmp_path / "r.html"),
        producer="rules",
        model="",
        host="http://localhost:11434",
        ocr_sidecar="",
        ground_truth=True,
        repeat=1,
    )
    assert code == 0
    assert "Bilan : 2 unité(s), aucune en échec." in capsys.readouterr().out


# --------------------------------------------------------------------------- #
# Ce que mesurent les chiffres (D-307)
# --------------------------------------------------------------------------- #


def _correct(dossier: Path, sortie: Path, *extra: str) -> int:
    from cinoc.interfaces.cli import main

    return main(["correct", str(dossier), "-o", str(sortie), *extra])


@_needs_saknussemm
def test_an_ocr_alto_no_longer_scores_against_itself(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le testeur : ``F1 RÉG. 1,0000 · CER RÉG. 0,0000`` sur un ALTO d'OCR, sans
    un mot — la sortie comparée à sa propre entrée."""
    sortie = tmp_path / "r.html"
    assert _correct(dossier_alto, sortie) == 0
    html = sortie.read_text(encoding="utf-8")
    assert 'title="line_identity_cer"' not in html
    assert "Rien n&#x27;est noté dans cette vue" in html or (
        "Rien n'est noté dans cette vue" in html
    )
    assert "rien n'est noté" in capsys.readouterr().out


@_needs_saknussemm
def test_a_transcription_beside_the_alto_gives_a_real_cer(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for nom in ("page1", "page2"):
        (dossier_alto / f"{nom}.gt.txt").write_text(
            "le soleil\nrien ici", encoding="utf-8"
        )
    sortie = tmp_path / "r.html"
    assert _correct(dossier_alto, sortie) == 0
    assert 'title="cer"' in sortie.read_text(encoding="utf-8")
    assert "Vérité terrain texte : 2/2" in capsys.readouterr().out


@_needs_saknussemm
def test_no_ground_truth_says_why_the_table_is_empty(
    dossier_alto: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (dossier_alto / "page1.gt.txt").write_text("le soleil", encoding="utf-8")
    sortie = tmp_path / "r.html"
    assert _correct(dossier_alto, sortie, "--no-ground-truth") == 0
    assert 'title="cer"' not in sortie.read_text(encoding="utf-8")
    assert "rien n'est noté" in capsys.readouterr().out


@_needs_saknussemm
def test_the_alto_of_a_cinoc_run_is_corrected_with_its_pipeline(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """``cinoc hybrid`` / ``--alto-dir`` écrivent ``<doc>.<pipeline>.alto.xml`` :
    ``cinoc correct`` le lisait pas (« aucune paire »)."""
    dossier = tmp_path / "hybrid"
    dossier.mkdir()
    (dossier / "page1.ocr_simple_tesseract.alto.xml").write_bytes(_ALTO)
    (dossier / "page1.png").write_bytes(b"pas une vraie image")
    sortie = tmp_path / "r.html"
    assert _correct(dossier, sortie) == 1
    assert "--pipeline (ocr_simple_tesseract)" in capsys.readouterr().err
    assert _correct(dossier, sortie, "--pipeline", "ocr_simple_tesseract") == 0
    assert "1 document(s) corrigé(s)" in capsys.readouterr().out

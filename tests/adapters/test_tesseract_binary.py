"""Le binaire ``tesseract`` lancé par Cinoc : un appel par page, environnement
de l'enfant, délai et arrêt, données de langue (D-300).

Un **faux binaire** (``sh``) posé en tête du ``PATH`` tient lieu de Tesseract :
il journalise chaque appel, écrit ce qu'il lit de ``OMP_THREAD_LIMIT`` à la
place du texte, et sait dormir (délai, arrêt) ou ignorer ``SIGTERM``.
"""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

import pytest

from cinoc.adapters.ocr import _tesseract_cli as cli
from cinoc.adapters.ocr.tesseract import TesseractAdapter, tsv_confidences
from cinoc.domain.artifacts import Artifact, ArtifactType
from cinoc.domain.errors import AdapterStepError, DeadlineExceeded, RunCancelledError
from cinoc.pipeline.executor import failure_reason
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="faux binaire en sh")

_TSV = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
    "\tleft\ttop\twidth\theight\tconf\ttext\n"
    "1\t1\t0\t0\t0\t0\t0\t0\t10\t10\t-1\t\n"
    "5\t1\t1\t1\t1\t1\t0\t0\t5\t5\t96.7\tmot\n"
)

_FAKE = """#!/bin/sh
case "$1" in
  --version) echo "tesseract 5.9.9"; exit 0 ;;
  --list-langs)
    echo "List of available languages in \\"$FAKE_TESSDATA/\\" (2):"
    echo deu; echo fra; exit 0 ;;
esac
echo "$*" >> "$FAKE_TESS_LOG"
echo $$ > "$FAKE_TESS_PID"
case "${FAKE_TESS_MODE:-ok}" in
  sleep) exec sleep 30 ;;
  stubborn) trap '' TERM; exec sleep 30 ;;
  fail) echo "Error opening data file grc.traineddata" >&2; exit 1 ;;
esac
printf '%s' "${OMP_THREAD_LIMIT:-absent}" > "$2.txt"
printf '%s' "$FAKE_TSV" > "$2.tsv"
printf '<alto/>' > "$2.xml"
"""


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Le faux binaire en tête du ``PATH`` ; rend le dossier de travail."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    script = bindir / "tesseract"
    script.write_text(_FAKE, encoding="utf-8")
    script.chmod(0o755)
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    (tessdata / "fra.traineddata").write_bytes(b"fra v1")
    (tessdata / "deu.traineddata").write_bytes(b"deu v1")
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
    monkeypatch.setenv("FAKE_TESS_LOG", str(tmp_path / "calls.log"))
    monkeypatch.setenv("FAKE_TESS_PID", str(tmp_path / "pid"))
    monkeypatch.setenv("FAKE_TESSDATA", str(tessdata))
    monkeypatch.setenv("FAKE_TSV", _TSV)
    monkeypatch.delenv("TESSDATA_PREFIX", raising=False)
    # set puis del : absente au départ, elle l'est encore après le test.
    monkeypatch.setenv("OMP_THREAD_LIMIT", "x")
    monkeypatch.delenv("OMP_THREAD_LIMIT")
    work = tmp_path / "ws"
    work.mkdir()
    (tmp_path / "page.png").write_bytes(b"")
    return tmp_path


def _execute(
    root: Path, control: RunControl | None = None, **kwargs: object
) -> dict[ArtifactType, Artifact]:
    image = Artifact(
        id="d:img", document_id="d", type=ArtifactType.IMAGE,
        uri=str(root / "page.png"),
    )
    context = RunContext(
        document_id="d", code_version="t", pipeline_name="p",
        workspace_uri=str(root / "ws"),
    )
    module = TesseractAdapter(label="t", lang="fra", **kwargs)  # type: ignore[arg-type]
    output = module.execute(
        {ArtifactType.IMAGE: image}, {}, context, control or RunControl()
    )
    return output.artifacts


def _calls(root: Path) -> list[str]:
    log = root / "calls.log"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def test_one_binary_call_per_page_for_all_outputs(fake: Path) -> None:
    """Texte, confidences et ALTO sortaient de **trois** passes d'OCR."""
    artifacts = _execute(fake, alto=True)
    assert len(_calls(fake)) == 1, _calls(fake)
    alto = artifacts[ArtifactType.ALTO_XML].uri
    assert alto is not None and Path(alto).read_bytes() == b"<alto/>"
    conf = artifacts[ArtifactType.CONFIDENCES].uri
    assert conf is not None
    assert Path(conf).read_text(encoding="utf-8") == (
        '[{"text": "mot", "confidence": 0.96}]'
    )
    # Le dossier temporaire du workspace ne survit pas à l'appel.
    assert sorted(p.name for p in (fake / "ws").iterdir()) == [
        "d.t.alto.xml", "d.t.confidences.json", "d.t.txt",
    ]


def test_command_line_is_the_one_pytesseract_composed(fake: Path) -> None:
    _execute(fake, dpi=300, alto=True)
    (call,) = _calls(fake)
    image, _outbase, *options = call.split(" ")
    assert image == os.path.realpath(fake / "page.png")
    assert options == [
        "-l", "fra", "--oem", "3", "--psm", "6", "--dpi", "300",
        "-c", "tessedit_create_txt=1", "-c", "tessedit_create_tsv=1",
        "-c", "tessedit_create_alto=1",
    ]


def test_openmp_bound_for_the_child_only(fake: Path) -> None:
    """``OMP_THREAD_LIMIT=1`` est donné **au binaire** ; le parent n'est plus
    modifié (D-282 le posait dans ``os.environ``, faute d'autre prise)."""
    artifacts = _execute(fake)
    text = artifacts[ArtifactType.RAW_TEXT].uri
    assert text is not None and Path(text).read_text(encoding="utf-8") == "1"
    assert "OMP_THREAD_LIMIT" not in os.environ


def test_explicit_openmp_limit_is_kept(
    fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMP_THREAD_LIMIT", "3")
    text = _execute(fake)[ArtifactType.RAW_TEXT].uri
    assert text is not None and Path(text).read_text(encoding="utf-8") == "3"


def _gone(pid: int) -> bool:
    """Le processus n'existe plus — **ni zombie** : un zombie répond à
    ``kill(pid, 0)`` tant que son parent ne l'a pas attendu."""
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    return False


def test_stop_cuts_the_binary_in_flight(
    fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """« Arrêter » attendait la fin de la page (jusqu'au délai de l'étape)."""
    monkeypatch.setenv("FAKE_TESS_MODE", "sleep")
    control = RunControl()
    threading.Timer(0.3, control.trigger_cancel).start()
    started = time.monotonic()
    with pytest.raises(RunCancelledError):
        _execute(fake, control, timeout=20)
    assert time.monotonic() - started < 3.0
    assert _gone(int((fake / "pid").read_text(encoding="utf-8")))


def test_step_timeout_kills_and_is_a_deadline(
    fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_TESS_MODE", "sleep")
    started = time.monotonic()
    with pytest.raises(DeadlineExceeded) as raised:
        _execute(fake, timeout=0.5)
    assert time.monotonic() - started < 3.0
    assert failure_reason(raised.value) == "cancelled"  # « arrêtée (délai) »
    assert _gone(int((fake / "pid").read_text(encoding="utf-8")))


def test_a_binary_deaf_to_terminate_is_killed(
    fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_TESS_MODE", "stubborn")
    monkeypatch.setattr(cli, "_GRACE_SECONDS", 0.2)
    with pytest.raises(DeadlineExceeded):
        _execute(fake, timeout=0.5)
    assert _gone(int((fake / "pid").read_text(encoding="utf-8")))


def test_a_binary_failure_is_an_engine_fault_with_its_message(
    fake: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_TESS_MODE", "fail")
    with pytest.raises(AdapterStepError) as raised:
        _execute(fake)
    assert failure_reason(raised.value) == "engine"
    assert "a échoué sur" in str(raised.value)
    assert "grc.traineddata" in str(raised.value)


def test_a_missing_binary_is_named(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    (tmp_path / "ws").mkdir()
    with pytest.raises(AdapterStepError, match="introuvable"):
        _execute(tmp_path)


# --- D19 : les données de langue au manifeste et dans la clé ------------------


def test_traineddata_enter_the_provenance(fake: Path) -> None:
    """Seule la version du binaire était tracée : changer ``fra.traineddata``
    changeait la sortie sans invalider l'archive (D19 du pilote)."""
    from cinoc.domain.pipeline import PipelineStep
    from cinoc.pipeline.fingerprint import ModuleIdentity, step_fingerprint

    module = TesseractAdapter(label="t", lang="fra+deu")
    before = module.system_binaries()
    tessdata = str(fake / "tessdata")
    assert before["tesseract"] == "tesseract 5.9.9"
    assert before["tesseract:tessdata"] == tessdata
    assert set(before) == {
        "tesseract", "tesseract:tessdata",
        "tesseract:deu.traineddata", "tesseract:fra.traineddata",
    }
    assert before["tesseract:fra.traineddata"].startswith("sha256:")
    (fake / "tessdata" / "fra.traineddata").write_bytes(b"fra v2")
    after = module.system_binaries()
    assert after["tesseract:fra.traineddata"] != before["tesseract:fra.traineddata"]
    assert after["tesseract:deu.traineddata"] == before["tesseract:deu.traineddata"]
    step = PipelineStep(
        id="ocr", kind="ocr", adapter_name="tesseract:t",
        input_types=(ArtifactType.IMAGE,), output_types=(ArtifactType.RAW_TEXT,),
    )
    assert step_fingerprint(step, ModuleIdentity("1.0", binaries=before)) != (
        step_fingerprint(step, ModuleIdentity("1.0", binaries=after))
    ), "un autre traineddata est une autre unité"


def test_osd_is_traced_when_the_psm_reads_it(fake: Path) -> None:
    (fake / "tessdata" / "osd.traineddata").write_bytes(b"osd")
    default = TesseractAdapter(label="t").system_binaries()
    assert "tesseract:osd.traineddata" not in default
    found = TesseractAdapter(label="t", psm=1).system_binaries()
    assert found["tesseract:osd.traineddata"].startswith("sha256:")


def test_the_segmenter_traces_its_traineddata_too(fake: Path) -> None:
    from cinoc.adapters.layout.tesseract_layout import TesseractLayoutSegmenter

    found = TesseractLayoutSegmenter(lang="deu").system_binaries()
    assert found["tesseract:deu.traineddata"].startswith("sha256:")
    assert "tesseract:osd.traineddata" not in found  # psm 3 : pas d'OSD
    assert "tesseract:fra.traineddata" not in found


def test_list_langs_of_tesseract_4_falls_back_on_tessdata_prefix() -> None:
    sortie = "List of available languages (2):\neng\nfra\n"
    assert cli.parse_list_langs(sortie, {"TESSDATA_PREFIX": "/opt/td/"}) == (
        cli.Tessdata(directory=str(Path("/opt/td")), languages=("eng", "fra"))
    )
    assert cli.parse_list_langs(sortie, {}).directory is None


def test_list_langs_of_tesseract_5_names_its_directory() -> None:
    sortie = 'List of available languages in "/usr/share/td/" (2):\nFraktur\nfra\n'
    listing = cli.parse_list_langs(sortie, {"TESSDATA_PREFIX": "/ailleurs"})
    assert listing == cli.Tessdata(
        directory=str(Path("/usr/share/td")), languages=("Fraktur", "fra")
    )
    assert cli.missing_languages("fra+grc+frm", listing) == ("grc", "frm")


# --- Lecture du TSV : celle de pytesseract, à l'octet ---------------------------


def test_tsv_reading_truncates_like_pytesseract() -> None:
    tsv = (
        "level\tconf\ttext\n"
        "1\t-1\t\n"
        "5\t96.7\tmot\n"
        "5\t12.0\t  \n"
        "5\t100\tfin"
    )
    assert [(t.text, t.confidence) for t in tsv_confidences(tsv)] == [
        ("mot", 0.96), ("fin", 1.0),
    ]
    assert tsv_confidences("") == []
    with pytest.raises(ValueError):
        tsv_confidences("level\tconf\ttext\n5\tx\tmot\n")

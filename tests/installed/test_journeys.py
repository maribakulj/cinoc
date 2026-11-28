"""Les parcours d'une personne extérieure, sur le **paquet installé** (P5i 2, D-305).

Le reste de la suite importe ``cinoc`` depuis l'arbre de sources, installé en
éditable avec ``[dev]`` — qui tire des dépendances que la base n'a pas. C'est
ainsi que ``cinoc --help`` a planté en installation nue pendant trois mois avec
une CI verte (D-260). Ici, rien n'importe ``cinoc`` : chaque pas lance
l'exécutable ``cinoc`` d'un venv où **la roue** a été installée, dans un
dossier hors du dépôt, comme le ferait quelqu'un qui découvre l'outil.

Les trois parcours de ``PLAN_FIN_MIGRATION.md`` (P5i 2), et ce qu'il faut pour
les commencer :

1. **noter des sorties existantes, sans moteur** — ``cinoc demo``, puis
   ``cinoc run`` sur l'exemple livré (``precomputed``) ;
2. **comparer des moteurs sur son corpus** — un ZIP d'images et de
   transcriptions, ``cinoc corpus import zip``, un premier vrai OCR Tesseract,
   son rapport ; puis ``cinoc serve --reports-dir`` qui sert ce rapport **avec
   ses images** (D-282), et un run lancé depuis la page sur le même ZIP ;
3. **corriger un ALTO existant** — ``cinoc correct --pipeline`` sur l'ALTO
   que le parcours 2 a produit à côté de ses images.

Opt-in : ``CINOC_INSTALLED_VENV`` nomme le venv à éprouver (job CI
``install-bare``). Sans lui, ces tests sautent — ils ne jugent pas l'arbre de
sources, que le reste de la suite couvre. Les parcours qui exigent un extra
(``[serve]``, ``[images]``, ``[saknussemm]``) sautent si le venv ne l'a pas,
sauf sous ``CINOC_INSTALLED_EXTRAS=1`` où son absence est un échec : une
installation ratée ne doit pas passer pour un saut. Tesseract, lui, est exigé
dès que le venv est nommé : c'est le premier vrai OCR.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from tests.installed._score_alto import guide_spec, pages_zip

VENV_ENV = "CINOC_INSTALLED_VENV"
EXTRAS_ENV = "CINOC_INSTALLED_EXTRAS"

ROOT = Path(__file__).resolve().parents[2]
FIRST_CORPUS = ROOT / "tests" / "fixtures" / "first_corpus"
EXAMPLES = ROOT / "examples"

installed = pytest.mark.skipif(
    not os.environ.get(VENV_ENV),
    reason=f"{VENV_ENV} non posée : parcours du paquet installé (job install-bare)",
)


def test_the_ci_runs_these_journeys() -> None:
    """Des tests opt-in que rien ne lance sont verts sur rien : le job
    ``install-bare`` doit les lancer, sur la base **et** avec les extras."""
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    job = ci[ci.index("  install-bare:") :]
    job = job[: job.index("\n  # ")]  # jusqu'au job suivant
    assert job.count("tests/installed") >= 2, job
    assert f"{VENV_ENV}:" in job and f'{EXTRAS_ENV}: "1"' in job, job
    assert "tesseract-ocr" in job, job


def _bin(name: str) -> Path:
    venv = Path(os.environ[VENV_ENV])
    scripts = venv / ("Scripts" if sys.platform == "win32" else "bin")
    suffix = ".exe" if sys.platform == "win32" else ""
    return scripts / f"{name}{suffix}"


def _env(tmp: Path) -> dict[str, str]:
    """L'environnement d'une personne extérieure : ni l'arbre de sources sur
    le chemin d'import, ni le dossier de données d'un autre run."""
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["CINOC_DATA_DIR"] = str(tmp / "donnees")
    env["PYTHONIOENCODING"] = env.get("PYTHONIOENCODING", "utf-8")
    return env


def cinoc(*args: str, cwd: Path, expect: int = 0) -> subprocess.CompletedProcess[str]:
    """Lance ``cinoc`` **installé** ; échoue en citant sa sortie s'il ne rend
    pas ``expect``."""
    done = subprocess.run(
        [str(_bin("cinoc")), *args],
        cwd=cwd,
        env=_env(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    assert done.returncode == expect, (
        f"cinoc {' '.join(args)} → {done.returncode} (attendu {expect})\n"
        f"--- stdout\n{done.stdout}\n--- stderr\n{done.stderr}"
    )
    return done


def _has(module: str) -> bool:
    found = subprocess.run(
        [str(_bin("python")), "-c", f"import {module}"],
        capture_output=True,
    ).returncode == 0
    if not found and os.environ.get(EXTRAS_ENV) == "1":
        pytest.fail(f"{EXTRAS_ENV}=1 mais `{module}` est absent du venv installé")
    return found


def _need(*modules: str) -> None:
    missing = [m for m in modules if not _has(m)]
    if missing:
        pytest.skip(f"extra absent du venv installé : {', '.join(missing)}")


def _pages_zip(dest: Path) -> Path:
    """Le ZIP qu'on dépose : des images et leurs transcriptions, à plat."""
    archive = dest / "pages.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for path in sorted(FIRST_CORPUS.iterdir()):
            if path.suffix in (".png", ".txt"):
                zf.write(path, path.name)
    return archive


# --- parcours 1 : noter des sorties existantes, sans moteur ----------------


@installed
def test_a_bare_install_scores_existing_outputs(tmp_path: Path) -> None:
    cinoc("--help", cwd=tmp_path)
    assert cinoc("--version", cwd=tmp_path).stdout.startswith("cinoc ")
    cinoc("list", "engines", cwd=tmp_path)
    cinoc("demo", "--output", "demo.html", cwd=tmp_path)
    shutil.copytree(EXAMPLES, tmp_path / "examples")
    cinoc("run", "examples/config.yaml", "-o", "run.html",
          "--json", "examples/run.json", cwd=tmp_path)
    for written in ("demo.html", "run.html"):
        assert (tmp_path / written).read_text(encoding="utf-8").startswith(
            "<!DOCTYPE html>"
        )
    run_json = tmp_path / "examples" / "run.json"
    result = json.loads(run_json.read_text(encoding="utf-8"))
    assert {p["pipeline"] for p in result["pipelines"]} == {"tesseract", "pero"}


@installed
def test_a_bare_install_scores_an_existing_alto(tmp_path: Path) -> None:
    """Un ALTO d'un autre outil, noté sans moteur par la spec du guide (D-307) ;
    sans transcription à côté, le run est refusé — jamais un zéro par
    construction."""
    for avec, attendu in ((True, 0), (False, 1)):
        work = tmp_path / ("avec" if avec else "sans")
        work.mkdir()
        pages_zip(work, transcriptions=avec)
        cinoc("corpus", "import", "zip", "pages.zip", "--dest", "corpus", cwd=work)
        fichier = work / "corpus" / "corpus.yaml"
        fichier.write_text(
            fichier.read_text(encoding="utf-8") + guide_spec(), encoding="utf-8"
        )
        done = cinoc("run", "corpus/corpus.yaml", "-o", "r.html", "--json",
                     "corpus/run.json", cwd=work, expect=attendu)
        if not avec:
            assert "propre ALTO" in done.stderr
            continue
        result = json.loads((work / "corpus" / "run.json").read_text(encoding="utf-8"))
        (texte,) = [p for p in result["pipelines"] if p["view"] == "texte"]
        cer = next(
            s["value"] for s in texte["conditional_aggregate"] if s["metric"] == "cer"
        )
        assert cer == 0


@installed
def test_serve_without_its_extra_says_how_to_get_it(tmp_path: Path) -> None:
    if _has("uvicorn"):
        pytest.skip("[serve] installé : le message d'extra absent ne s'applique pas")
    done = cinoc("serve", cwd=tmp_path, expect=1)
    assert "cinoc[serve]" in done.stderr


# --- parcours 2 : un premier vrai OCR sur son corpus ------------------------


@pytest.fixture(scope="module")
def first_run(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """ZIP → ``corpus import`` → Tesseract → rapport, JSON à côté de la spec,
    ALTO gardé. Renvoie le dossier de travail."""
    if shutil.which("tesseract") is None:
        pytest.fail(
            f"{VENV_ENV} posée mais aucun binaire `tesseract` : le premier vrai "
            "OCR ne peut pas tourner (apt install tesseract-ocr)."
        )
    work = tmp_path_factory.mktemp("premier")
    _pages_zip(work)
    done = cinoc("corpus", "import", "zip", "pages.zip", "--dest", "corpus", cwd=work)
    assert "corpus/corpus.yaml" in done.stdout.replace("\\", "/")
    texte = (work / "corpus" / "corpus.yaml").read_text(encoding="utf-8")
    assert str(work) not in texte, "corpus.yaml cite un chemin de la machine"
    cinoc("run", "corpus/corpus.yaml", "--recipe", "ocr_simple",
          "--set", "ocr.lang=eng", "--set", "ocr.alto=true",
          "-o", "rapport.html", "--json", "corpus/premier.json",
          "--alto-dir", "corpus", cwd=work)
    return work


@installed
def test_a_first_tesseract_run_reads_the_pages(first_run: Path) -> None:
    assert (first_run / "rapport.html").read_text(encoding="utf-8").startswith(
        "<!DOCTYPE html>"
    )
    result = json.loads(
        (first_run / "corpus" / "premier.json").read_text(encoding="utf-8")
    )
    assert str(first_run) not in json.dumps(result)
    documents = {d["document_id"]: d for d in result["documents"]}
    assert set(documents) == {"page_001", "page_002"}
    for document in documents.values():
        assert document["image_ref"] == f"{document['document_id']}.png"
        cer = next(s["value"] for s in document["scores"] if s["metric"] == "cer")
        # Deux lignes nettes en 34 px : un vrai OCR les lit presque sans faute
        # (0,0 avec Tesseract 5.3.4). Le seuil dit « il a lu », pas « il est bon ».
        assert cer is not None and cer < 0.1, document
    # À côté des images, sous le nom que ``cinoc correct --pipeline`` relit.
    assert sorted(p.name for p in (first_run / "corpus").glob("*.alto.xml")) == [
        "page_001.ocr_simple_tesseract.alto.xml",
        "page_002.ocr_simple_tesseract.alto.xml",
    ]


# --- parcours 3 : corriger un ALTO existant ---------------------------------


@installed
def test_an_existing_alto_is_corrected(first_run: Path, tmp_path: Path) -> None:
    """L'ALTO que le parcours 2 a écrit, corrigé **là où il est** — ni copie,
    ni renommage (D-307) ; les transcriptions du corpus en sont la vérité."""
    _need("saknussemm")
    rapport = tmp_path / "correction.html"
    sans = cinoc("correct", "corpus", "-o", str(rapport), cwd=first_run, expect=1)
    assert "--pipeline (ocr_simple_tesseract)" in sans.stderr
    done = cinoc("correct", "corpus", "--pipeline", "ocr_simple_tesseract",
                 "-o", str(rapport), cwd=first_run)
    assert "Vérité terrain texte : 2/2" in done.stdout
    assert "aucune en échec" in done.stdout
    assert rapport.read_text(encoding="utf-8").startswith("<!DOCTYPE html>")


# --- parcours 2, suite : la page ---------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _Server:
    def __init__(self, base: str, process: subprocess.Popen[bytes], log: Path) -> None:
        self.base = base
        self.process = process
        self.log = log

    def get(self, path: str) -> tuple[int, bytes]:
        try:
            with urllib.request.urlopen(self.base + path, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()

    def post(self, path: str, body: bytes, content_type: str) -> tuple[int, object]:
        request = urllib.request.Request(
            self.base + path,
            data=body,
            method="POST",
            headers={"Content-Type": content_type, "X-Cinoc-CSRF": "1"},
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as resp:
                return resp.status, json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", "replace")


@pytest.fixture
def server(first_run: Path, tmp_path: Path) -> Iterator[_Server]:
    """``cinoc serve --reports-dir`` sur le dossier où ``cinoc run --json`` a
    écrit son rapport — le dossier de la spec."""
    _need("uvicorn", "fastapi", "multipart", "PIL")
    port = _free_port()
    log = tmp_path / "serve.log"
    with log.open("wb") as sink:
        process = subprocess.Popen(
            [str(_bin("cinoc")), "serve", "--port", str(port),
             "--reports-dir", str(first_run / "corpus")],
            cwd=tmp_path,
            env=_env(tmp_path),
            stdout=sink,
            stderr=subprocess.STDOUT,
        )
    live = _Server(f"http://127.0.0.1:{port}", process, log)
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                if live.get("/health")[0] == 200:
                    break
            except OSError:
                pass
            if process.poll() is not None or time.monotonic() > deadline:
                pytest.fail(f"le serveur ne répond pas :\n{log.read_text('utf-8')}")
            time.sleep(0.3)
        yield live
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()


def _assert_served_with_images(server: _Server, name: str, document: str) -> None:
    status, html = server.get(f"/reports/{name}")
    assert status == 200, html[:500]
    assert f"/reports/{name}/image/{document}".encode() in html, (
        "le rapport servi retombe sur l'aperçu synthétique"
    )
    status, image = server.get(f"/reports/{name}/image/{document}")
    assert status == 200, f"image de {name}/{document} : {status}\n" + (
        server.log.read_text("utf-8")
    )
    assert image.startswith(b"\xff\xd8\xff")


@installed
def test_a_cli_report_is_served_with_its_images(server: _Server) -> None:
    """Reste de S10b (D-282) : le rapport de ``cinoc run --json`` relu par la
    vitrine retrouve ses images au lieu de l'aperçu synthétique."""
    status, home = server.get("/")
    assert status == 200 and b"premier" in home
    _assert_served_with_images(server, "premier", "page_001")


@installed
def test_a_run_launched_from_the_page(server: _Server, tmp_path: Path) -> None:
    """Ce que fait la page : déposer le ZIP en Bibliothèque, lancer une recette
    sur ce corpus, suivre le job, ouvrir son rapport."""
    archive = _pages_zip(tmp_path).read_bytes()
    boundary = "cinoc-parcours"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"pages.zip\"\r\nContent-Type: application/zip\r\n\r\n"
    ).encode() + archive + f"\r\n--{boundary}--\r\n".encode()
    status, corpus = server.post(
        "/api/corpus", body, f"multipart/form-data; boundary={boundary}"
    )
    assert status == 201, corpus
    assert isinstance(corpus, dict) and corpus["n_documents"] == 2

    launch = {
        "corpus_id": corpus["corpus_id"],
        "entries": [{"recipe": "ocr_simple", "params": {"ocr": {"lang": "eng"}}}],
    }
    status, job = server.post(
        "/api/runs", json.dumps(launch).encode(), "application/json"
    )
    assert status == 201, job
    assert isinstance(job, dict)

    deadline = time.monotonic() + 300
    while True:
        status, raw = server.get(f"/api/runs/{job['job_id']}")
        state = json.loads(raw)
        if state["state"] in ("done", "failed", "cancelled"):
            break
        assert time.monotonic() < deadline, state
        time.sleep(0.5)
    assert state["state"] == "done", state
    _assert_served_with_images(server, state["report_name"], "page_001")

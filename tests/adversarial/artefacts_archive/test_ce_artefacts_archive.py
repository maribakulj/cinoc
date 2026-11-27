"""Contre-expertise — intégrité des artefacts (affirmation 5) et archive (7).

Tout passe par les API publiques : un module tiers écrit son fichier par
``cinoc.adapters.extension.workspace_artifact_path`` (l'usage documenté), le run
par ``cinoc.app.run`` avec un ``ResumeStore`` (= ``--resume-dir``) puis
``offline=True`` (= ``--offline``). Seules les pannes et les altérations
externes sont simulées : un octet changé dans l'archive, un lien symbolique
planté, un SDK absent, un serveur d'images.

Références indépendantes : le CER attendu est calculé à la main (distance
d'édition comptée sur des chaînes choisies pour que le compte soit trivial), et
les empreintes avec ``hashlib.sha256`` directement.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.extension import (
    Artifact,
    ArtifactType,
    StepOutput,
    compute_content_hash,
    workspace_artifact_path,
)
from cinoc.app import run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.resume import ResumeStore
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.errors import CinocError
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult

#: Vérité terrain : dix caractères distincts. Une sortie identique a un CER de
#: 0 ; une sortie de dix ``z`` en a un de 10 substitutions / 10 = 1,0 ; une sortie
#: où seul le dernier caractère diffère en a un de 1 / 10 = 0,1.
GT = "abcdefghij"
TEXT_A = GT  # CER 0,0 à la main
TEXT_B = "zzzzzzzzzz"  # CER 1,0 à la main
TEXT_ONE_ERROR = "abcdefghiX"  # CER 0,1 à la main


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# Un module tiers écrit comme le documente ``cinoc.adapters.extension``
# --------------------------------------------------------------------------- #


class StampModule:
    """Module tiers : écrit ``params["text"]`` dans son fichier de workspace.

    Le nom de fichier est celui que fixe l'API publique
    ``workspace_artifact_path(workspace, document, label=self.name, suffixe)``.
    """

    version = "1.0.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls = 0

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        control.raise_if_cancelled()
        self.calls += 1
        text = str(params["text"])
        assert context.workspace_uri is not None
        path = workspace_artifact_path(
            context.workspace_uri, context.document_id, self.name, "txt"
        )
        path.write_text(text, encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(text.encode("utf-8")),
                )
            }
        )


def _registry(*names: str, explode: bool = False) -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    for name in names:

        def build(_kwargs: Mapping[str, Any], _name: str = name) -> StampModule:
            module = StampModule(_name)
            if explode:
                module.execute = _explode  # type: ignore[method-assign]
            return module

        registry.register_builder(name, build)
    return registry


def _explode(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("un module a été exécuté pendant une relecture hors ligne")


def _corpus(folder: Path, image_uri: str | None = None) -> CorpusSpec:
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "folio.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"folio-pixels")
    gt = folder / "folio.gt.txt"
    gt.write_text(GT, encoding="utf-8")
    return CorpusSpec(
        name="ce-corpus",
        documents=(
            DocumentRef(
                id="folio",
                image_uri=image_uri if image_uri is not None else str(image),
                ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),),
            ),
        ),
    )


def _step(step_id: str, adapter: str, text: str, *, initial: bool) -> PipelineStep:
    return PipelineStep(
        id=step_id,
        kind="ocr",
        adapter_name=adapter,
        params={"text": text},
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
        inputs_from={ArtifactType.IMAGE: "__initial__"} if initial else {},
    )


def _view(name: str, target: str | None) -> EvaluationView:
    return EvaluationView(
        name=name,
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
        target_step=target,
    )


def _two_step_spec(tmp_path: Path, adapter_a: str, adapter_b: str) -> RunSpec:
    """Deux étapes, deux sorties différentes ; une vue nomme chaque étape."""
    pipeline = PipelineSpec(
        name="deux_passes",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            _step("a", adapter_a, TEXT_A, initial=False),
            _step("b", adapter_b, TEXT_B, initial=True),
        ),
    )
    return RunSpec(
        corpus=_corpus(tmp_path / "corpus"),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(_view("va", "a"), _view("vb", "b"))),
    )


def _one_step_spec(corpus: CorpusSpec) -> RunSpec:
    pipeline = PipelineSpec(
        name="une_passe",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(_step("ocr", "stamp", TEXT_ONE_ERROR, initial=False),),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(_view("texte", None),)),
    )


def _cer(result: RunResult, view: str) -> float | None:
    (doc,) = [d for d in result.documents if d.view == view]
    return next(s.value for s in doc.scores if s.metric == "cer")


def _unit_dirs(archive: Path) -> list[Path]:
    return sorted(p.parent for p in archive.glob("*/index.json"))


def _index(unit: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((unit / "index.json").read_text("utf-8"))
    return data


def _raw_text_entries(unit: Path) -> dict[str, dict[str, Any]]:
    return {
        entry["step"]: entry["artifacts"]["raw_text"]
        for entry in _index(unit)["steps"]
        if "raw_text" in entry["artifacts"]
    }


class _Sink:
    """``artifact_sink`` : lit chaque fichier **pendant** que le workspace vit."""

    def __init__(self) -> None:
        self.files: dict[str, tuple[str, str | None, str]] = {}

    def __call__(self, outputs: Mapping[str, Any], _manifest: object) -> None:
        for per_doc in outputs.values():
            for by_step in per_doc.values():
                for step_id, arts in by_step.items():
                    art = arts.get(ArtifactType.RAW_TEXT)
                    if art is not None and art.uri is not None:
                        data = Path(art.uri).read_bytes()
                        self.files[step_id] = (art.uri, art.content_hash, _sha(data))


# =========================================================================== #
# Affirmation 5 — deux étapes du même adaptateur, même label
# =========================================================================== #


@pytest.mark.valide
def test_a5_meme_adaptateur_deux_etapes__fichier_de_chaque_etape_conserve(
    tmp_path: Path,
) -> None:
    """Deux étapes ``stamp`` (textes A puis B) : le fichier de l'étape a, lu après
    le run, doit encore avoir l'empreinte que l'artefact a enregistre."""
    sink = _Sink()
    run(
        _two_step_spec(tmp_path, "stamp", "stamp"),
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        artifact_sink=sink,
    )
    uri_a, hash_a, disk_a = sink.files["a"]
    uri_b, hash_b, disk_b = sink.files["b"]
    assert hash_a == _sha(TEXT_A.encode())  # l'artefact a dit « A »
    assert uri_a != uri_b, f"les deux étapes désignent le même fichier : {uri_a}"
    assert disk_a == hash_a, "le fichier de l'étape a porte le contenu de b"


@pytest.mark.valide
def test_a5_meme_adaptateur_deux_etapes__chaque_vue_notee_sur_sa_sortie(
    tmp_path: Path,
) -> None:
    """Sans archive : la vue ciblant a (texte = GT) doit valoir CER 0,0 et celle
    ciblant b (dix ``z``) CER 1,0 — calcul à la main."""
    result = run(
        _two_step_spec(tmp_path, "stamp", "stamp"),
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
    )
    assert _cer(result, "vb") == pytest.approx(1.0)
    assert _cer(result, "va") == pytest.approx(0.0)


def test_a5_temoin_deux_adaptateurs_distincts__aucun_ecrasement(tmp_path: Path) -> None:
    """Témoin : mêmes deux sorties produites par deux noms d'adaptateur distincts
    — chaque vue doit être notée sur sa propre sortie (0,0 et 1,0)."""
    sink = _Sink()
    result = run(
        _two_step_spec(tmp_path, "stamp1", "stamp2"),
        registry=_registry("stamp1", "stamp2"),
        code_version="ce",
        max_workers=1,
        artifact_sink=sink,
    )
    assert _cer(result, "va") == pytest.approx(0.0)
    assert _cer(result, "vb") == pytest.approx(1.0)
    assert sink.files["a"][1] == sink.files["a"][2]


@pytest.mark.valide
def test_a5_archive__empreinte_de_chaque_fichier_archive_egale_hash_enregistre(
    tmp_path: Path,
) -> None:
    """Après ``--resume-dir`` : pour chaque étape, le SHA-256 du fichier archivé
    doit égaler le ``content_hash`` inscrit dans ``index.json``."""
    archive = tmp_path / "archive"
    run(
        _two_step_spec(tmp_path, "stamp", "stamp"),
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    (unit,) = _unit_dirs(archive)
    entries = _raw_text_entries(unit)
    assert set(entries) == {"a", "b"}
    mismatches = {
        step: (entry["content_hash"], _sha((unit / entry["uri"]).read_bytes()))
        for step, entry in entries.items()
        if _sha((unit / entry["uri"]).read_bytes()) != entry["content_hash"]
    }
    assert not mismatches, f"empreinte enregistrée ≠ fichier archivé : {mismatches}"


@pytest.mark.valide
def test_a5_relecture_offline__chaque_etape_relit_son_propre_fichier(
    tmp_path: Path,
) -> None:
    """Archive puis ``--offline`` : la vue de a doit relire le texte A (CER 0,0),
    celle de b le texte B (CER 1,0), sans rien exécuter."""
    archive = tmp_path / "archive"
    spec = _two_step_spec(tmp_path, "stamp", "stamp")
    run(
        spec,
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    replay = run(
        spec,
        registry=_registry("stamp", explode=True),
        code_version="ce",
        resume_store=ResumeStore(archive),
        offline=True,
    )
    assert _cer(replay, "vb") == pytest.approx(1.0)
    assert _cer(replay, "va") == pytest.approx(0.0)


# =========================================================================== #
# Affirmation 7 — l'archive : vérifiable, portable, immuable, réévaluable
# =========================================================================== #


@pytest.fixture
def archived(tmp_path: Path) -> tuple[RunSpec, Path, RunResult]:
    """Une passe ``stamp`` (une erreur sur dix → CER 0,1), archivée."""
    spec = _one_step_spec(_corpus(tmp_path / "corpus"))
    archive = tmp_path / "archive"
    first = run(
        spec,
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    assert _cer(first, "texte") == pytest.approx(0.1)
    return spec, archive, first


def _replay(spec: RunSpec, archive: Path, **kwargs: Any) -> RunResult:
    return run(
        spec,
        registry=_registry("stamp", explode=True),
        code_version="ce",
        resume_store=ResumeStore(archive),
        offline=True,
        **kwargs,
    )


def test_a7_temoin_relecture_intacte__meme_score(
    archived: tuple[RunSpec, Path, RunResult],
) -> None:
    """Témoin : une archive intacte, relue hors ligne, redonne CER 0,1."""
    spec, archive, _ = archived
    assert _cer(_replay(spec, archive), "texte") == pytest.approx(0.1)


@pytest.mark.discutable("C14-archive-scellee")
def test_a7_octet_change_dans_une_sortie__corruption_detectee(
    archived: tuple[RunSpec, Path, RunResult],
) -> None:
    """Un octet changé dans le texte archivé (``X`` → ``j``, sortie = GT) : la
    relecture doit refuser l'unité au lieu de la noter CER 0,0."""
    spec, archive, _ = archived
    (unit,) = _unit_dirs(archive)
    path = unit / _raw_text_entries(unit)["ocr"]["uri"]
    path.write_bytes(path.read_bytes().replace(b"X", b"j"))
    try:
        replay = _replay(spec, archive)
    except CinocError:
        return  # détectée : comportement attendu
    pytest.fail(
        "corruption non détectée : l'unité est relue et notée CER "
        f"{_cer(replay, 'texte')} sur un contenu dont l'empreinte ne correspond "
        "plus à celle enregistrée"
    )


def test_a7_index_json_illisible__unite_refusee(
    archived: tuple[RunSpec, Path, RunResult],
) -> None:
    """``index.json`` tronqué d'un octet (JSON invalide) : la relecture doit
    refuser l'archive (``ArchiveIncompleteError``)."""
    spec, archive, _ = archived
    (unit,) = _unit_dirs(archive)
    index = unit / "index.json"
    index.write_bytes(index.read_bytes()[:-1])
    with pytest.raises(CinocError):
        _replay(spec, archive)


@pytest.mark.discutable("C14-archive-scellee")
def test_a7_index_json_valide_mais_altere__alteration_detectee(
    archived: tuple[RunSpec, Path, RunResult],
) -> None:
    """``index.json`` modifié en restant du JSON valide (durée mesurée ×1000,
    ``content_hash`` remplacé) : la relecture doit le détecter."""
    spec, archive, first = archived
    (unit,) = _unit_dirs(archive)
    data = _index(unit)
    entry = data["steps"][-1]
    entry["usage"]["duration_seconds"] = 1234.5
    entry["artifacts"]["raw_text"]["content_hash"] = "0" * 64
    (unit / "index.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        replay = _replay(spec, archive)
    except CinocError:
        return
    (usage,) = replay.usage
    pytest.fail(
        "altération non détectée : durée relue "
        f"{usage.usage.duration_seconds} s (au lieu de "
        f"{first.usage[0].usage.duration_seconds:.6f}), empreinte 0…0 acceptée"
    )


@pytest.mark.discutable("C14-archive-scellee")
def test_a7_image_partagee_corrompue__corruption_detectee(
    archived: tuple[RunSpec, Path, RunResult],
) -> None:
    """Un octet changé dans ``images/<sha256>.png`` : son nom *est* son empreinte,
    la relecture doit refuser une image qui ne la respecte plus."""
    spec, archive, _ = archived
    (image,) = sorted((archive / "images").iterdir())
    assert image.stem == _sha(image.read_bytes())
    image.write_bytes(image.read_bytes() + b"!")
    seen: dict[str, str] = {}

    def sink(outputs: Mapping[str, Any], _manifest: object) -> None:
        for per_doc in outputs.values():
            for by_step in per_doc.values():
                art = by_step["__initial__"][ArtifactType.IMAGE]
                seen[art.uri] = _sha(Path(art.uri).read_bytes())

    try:
        _replay(spec, archive, artifact_sink=sink)
    except CinocError:
        return
    pytest.fail(
        "image archivée corrompue relue sans contrôle ; artefact IMAGE servi au "
        f"run (uri → sha256 réel) : {seen}"
    )


def test_a7_archive__aucun_chemin_absolu_de_la_machine_d_origine(
    archived: tuple[RunSpec, Path, RunResult],
    tmp_path: Path,
) -> None:
    """Aucun fichier de l'archive ne doit contenir un chemin absolu de la
    machine qui l'a produite (ici, la racine ``tmp_path``)."""
    _, archive, _ = archived
    origin = str(tmp_path)
    leaks = [
        str(p.relative_to(archive))
        for p in archive.rglob("*")
        if p.is_file() and origin.encode() in p.read_bytes()
    ]
    assert not leaks, f"chemins absolus d'origine dans : {leaks}"


@pytest.mark.valide
def test_a7_uri_absolue_hors_archive__refusee(
    archived: tuple[RunSpec, Path, RunResult],
    tmp_path: Path,
) -> None:
    """Archive reçue dont ``index.json`` nomme un fichier par chemin **absolu**
    hors de l'archive : il ne doit pas être lu (comme un ``..``)."""
    spec, archive, _ = archived
    outside = tmp_path / "ailleurs.txt"
    outside.write_text(GT, encoding="utf-8")  # contenu « parfait » planté
    (unit,) = _unit_dirs(archive)
    data = _index(unit)
    data["steps"][-1]["artifacts"]["raw_text"]["uri"] = str(outside)
    (unit / "index.json").write_text(json.dumps(data), encoding="utf-8")
    try:
        replay = _replay(spec, archive)
    except CinocError:
        return
    pytest.fail(
        f"fichier hors archive lu par chemin absolu : CER {_cer(replay, 'texte')}"
    )


def test_a7_temoin_uri_relative_en_point_point__refusee(
    archived: tuple[RunSpec, Path, RunResult],
    tmp_path: Path,
) -> None:
    """Témoin D-304 : un nom relatif ``../../ailleurs.txt`` qui sort de l'archive
    doit être refusé (archive incomplète)."""
    spec, archive, _ = archived
    (tmp_path / "ailleurs.txt").write_text(GT, encoding="utf-8")
    (unit,) = _unit_dirs(archive)
    data = _index(unit)
    data["steps"][-1]["artifacts"]["raw_text"]["uri"] = "../../ailleurs.txt"
    (unit / "index.json").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CinocError):
        _replay(spec, archive)


@pytest.mark.valide
def test_a7_lien_symbolique_hors_archive__refuse(
    archived: tuple[RunSpec, Path, RunResult],
    tmp_path: Path,
) -> None:
    """Le fichier de sortie archivé est remplacé par un lien symbolique vers un
    fichier hors de l'archive : il ne doit pas être suivi."""
    spec, archive, _ = archived
    outside = tmp_path / "ailleurs.txt"
    outside.write_text(GT, encoding="utf-8")
    (unit,) = _unit_dirs(archive)
    path = unit / _raw_text_entries(unit)["ocr"]["uri"]
    path.unlink()
    os.symlink(outside, path)
    try:
        replay = _replay(spec, archive)
    except CinocError:
        return
    pytest.fail(
        "lien symbolique hors archive suivi : unité notée CER "
        f"{_cer(replay, 'texte')} sur {outside}"
    )


# --------------------------------------------------------------------------- #
# Réévaluable hors moteur : SDK absent, clé absente, réseau coupé
# --------------------------------------------------------------------------- #


def test_a7_reevaluation_sans_sdk_ni_cle_ni_reseau__scores_identiques(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Run 1 avec le moteur OpenAI servi par cassette ; run 2 hors ligne avec le
    SDK non importable, les clés retirées et le réseau coupé : mêmes scores."""
    from cinoc.app.recipe_queue import RecipeEntry, plan_recipe_run
    from tests.adapters._native_fakes import (
        KEY_ENV,
        cut_network,
        install_fake_http,
        install_fake_sdks,
        set_keys,
        wire,
    )

    set_keys(monkeypatch)
    queue = {"openai": lambda: wire("llm", "openai", "stop")}
    install_fake_sdks(monkeypatch, queue)
    install_fake_http(monkeypatch, queue)
    spec = plan_recipe_run(
        _corpus(tmp_path / "corpus"),
        (
            RecipeEntry(
                recipe="vlm_seul",
                choices={"vlm": "openai"},
                params={"vlm": {"model": "gpt-4o-mini"}},
            ),
        ),
        run_id="ce",
    )
    archive = tmp_path / "archive"
    first = run(
        spec,
        registry=_registry(),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    cut_network(monkeypatch)  # SDK → None dans sys.modules, httpx refuse tout
    for env in set(KEY_ENV.values()):
        monkeypatch.delenv(env, raising=False)
    assert sys.modules.get("openai") is None
    second = run(
        spec,
        registry=_registry(),
        code_version="ce",
        resume_store=ResumeStore(archive),
        offline=True,
    )
    scores = lambda r: {(d.view, s.metric): s.value for d in r.documents for s in d.scores}  # noqa: E731
    assert scores(first)
    assert scores(second) == scores(first)


# --------------------------------------------------------------------------- #
# Réévaluable hors réseau : image distante d'un corpus curé
# --------------------------------------------------------------------------- #

_REMOTE = "https://images.exemple.invalid/folio.png"
_PIXELS = b"\x89PNG\r\n\x1a\n" + b"remote-pixels"


def _remote_spec(tmp_path: Path) -> RunSpec:
    return _one_step_spec(_corpus(tmp_path / "corpus", image_uri=_REMOTE))


def _fake_server(monkeypatch: pytest.MonkeyPatch, *, up: bool) -> list[str]:
    """Serveur d'images simulé (panne externe) : compte les téléchargements."""
    from cinoc.adapters.corpus._http import HttpFetchError

    calls: list[str] = []

    def download(url: str, dest: Path, **_kwargs: object) -> None:
        calls.append(url)
        if not up:
            raise HttpFetchError(f"serveur injoignable : {url}")
        dest.write_bytes(_PIXELS)

    monkeypatch.setattr("cinoc.app.orchestrator.download", download)
    return calls


@pytest.mark.discutable("C15-archive-portable-images")
def test_a7_relecture_offline_image_distante__aucun_telechargement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corpus à image distante archivé, puis relu ``--offline`` : la relecture ne
    doit télécharger aucune image (l'archive garde ``images/<sha256>``)."""
    spec = _remote_spec(tmp_path)
    archive = tmp_path / "archive"
    calls = _fake_server(monkeypatch, up=True)
    run(
        spec,
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    assert calls == [_REMOTE]
    assert any((archive / "images").iterdir())
    calls.clear()
    _replay(spec, archive)
    assert calls == [], f"téléchargé pendant la relecture hors ligne : {calls}"


@pytest.mark.discutable("C15-archive-portable-images")
def test_a7_relecture_offline_serveur_d_images_eteint__unite_relue_de_l_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Même archive, serveur d'images éteint à la relecture : l'unité doit être
    relue de l'archive (CER 0,1), pas rendue « échouée » ni refusée."""
    spec = _remote_spec(tmp_path)
    archive = tmp_path / "archive"
    _fake_server(monkeypatch, up=True)
    run(
        spec,
        registry=_registry("stamp"),
        code_version="ce",
        max_workers=1,
        resume_store=ResumeStore(archive),
    )
    _fake_server(monkeypatch, up=False)
    replay = _replay(spec, archive)
    (usage,) = replay.usage
    assert usage.outcome == "ok", (
        f"unité {usage.outcome!r} ({usage.reason}) : {usage.message}"
    )
    assert _cer(replay, "texte") == pytest.approx(0.1)


# --------------------------------------------------------------------------- #
# Affirmation 5 sur le socle : tesseract deux fois (ablation du redressement)
# --------------------------------------------------------------------------- #


@pytest.mark.valide
@pytest.mark.skipif(
    __import__("shutil").which("tesseract") is None, reason="binaire tesseract absent"
)
def test_a5_socle_tesseract_avant_apres_redressement__chaque_etape_garde_son_fichier(
    tmp_path: Path,
) -> None:
    """Ablation dans un pipeline écrit à la main : ``tesseract:fra`` sur la page
    inclinée, ``preprocess`` (deskew), puis ``tesseract:fra`` sur la page
    redressée — le fichier de la 1re lecture doit garder son empreinte."""
    from PIL import Image, ImageDraw, ImageFont

    folder = tmp_path / "corpus"
    folder.mkdir()
    page = Image.new("L", (1400, 360), 255)
    draw = ImageDraw.Draw(page)
    font = ImageFont.load_default(size=44)
    draw.text((40, 60), "Le Petit Journal, douze mars 1894.", fill=0, font=font)
    draw.text((40, 180), "On annonce de Boulogne-sur-Mer que", fill=0, font=font)
    page = page.rotate(4.0, expand=True, fillcolor=255)
    image = folder / "folio.png"
    page.save(image)
    gt = folder / "folio.gt.txt"
    gt.write_text(
        "Le Petit Journal, douze mars 1894.\nOn annonce de Boulogne-sur-Mer que",
        encoding="utf-8",
    )
    corpus = CorpusSpec(
        name="ce",
        documents=(
            DocumentRef(
                id="folio",
                image_uri=str(image),
                ground_truths=(GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(gt)),),
            ),
        ),
    )
    ocr = dict(
        kind="ocr",
        adapter_name="tesseract:fra",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    pipeline = PipelineSpec(
        name="ablation_deskew",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(id="brut", **ocr),  # type: ignore[arg-type]
            PipelineStep(
                id="prep",
                kind="preprocess",
                adapter_name="preprocess:deskew",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.IMAGE,),
            ),
            PipelineStep(
                id="redresse",
                inputs_from={ArtifactType.IMAGE: "prep"},
                **ocr,  # type: ignore[arg-type]
            ),
        ),
    )
    spec = RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(
            views=(_view("v_brut", "brut"), _view("v_redresse", "redresse"))
        ),
        adapter_kwargs={
            "tesseract:fra": {"label": "fra", "lang": "fra", "psm": 6},
            "preprocess:deskew": {"label": "deskew", "operations": "deskew",
                                  "skew_amplitude_deg": 6.0},
        },
    )
    sink = _Sink()
    result = run(spec, registry=_registry(), code_version="ce", max_workers=1,
                 artifact_sink=sink)
    _, hash_brut, disk_brut = sink.files["brut"]
    _, hash_redresse, _ = sink.files["redresse"]
    if hash_brut == hash_redresse:
        pytest.skip("les deux lectures sont identiques : cas non discriminant")
    assert disk_brut == hash_brut, (
        "la lecture de la page inclinée a été écrasée par celle de la page "
        f"redressée : CER v_brut = {_cer(result, 'v_brut')}, "
        f"CER v_redresse = {_cer(result, 'v_redresse')}"
    )


@pytest.mark.discutable("C15-archive-portable-images")
def test_a7_archive_seule_sans_images_du_corpus__reevaluable(
    archived: tuple[RunSpec, Path, RunResult],
    tmp_path: Path,
) -> None:
    """L'archive garde ``images/<sha256>`` ; l'image du corpus est retirée (seule
    la VT reste) : la re-notation hors ligne doit fonctionner (CER 0,1)."""
    spec, archive, _ = archived
    (tmp_path / "corpus" / "folio.png").unlink()
    assert any((archive / "images").iterdir())
    assert _cer(_replay(spec, archive), "texte") == pytest.approx(0.1)


@pytest.mark.discutable("C14-archive-scellee")
def test_a7_archive_publiee__une_reprise_normale_ne_la_modifie_pas(
    tmp_path: Path,
) -> None:
    """Archive dont l'unité a échoué (motif archivé) ; un ``--resume-dir`` sans
    ``--offline`` sur ce dossier ne doit pas réécrire une unité déjà archivée."""
    from cinoc.domain.errors import AdapterStepError

    spec = _one_step_spec(_corpus(tmp_path / "corpus"))
    archive = tmp_path / "archive"

    def failing(*_args: object, **_kwargs: object) -> None:
        raise AdapterStepError("stamp : panne simulée du moteur")

    registry = ModuleRegistry()
    register_default_modules(registry)

    def build(_kwargs: Mapping[str, Any]) -> StampModule:
        module = StampModule("stamp")
        module.execute = failing  # type: ignore[method-assign]
        return module

    registry.register_builder("stamp", build)
    run(spec, registry=registry, code_version="ce", max_workers=1,
        resume_store=ResumeStore(archive))
    (unit,) = _unit_dirs(archive)
    published = (unit / "index.json").read_bytes()
    assert _index(unit)["outcome"] == "failed"

    run(spec, registry=_registry("stamp"), code_version="ce", max_workers=1,
        resume_store=ResumeStore(archive))
    after = (unit / "index.json").read_bytes()
    assert after == published, (
        "l'unité archivée a été réécrite en place sous la même clé : "
        f"issue {json.loads(published)['outcome']!r} → {json.loads(after)['outcome']!r}"
    )

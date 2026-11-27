"""Contre-expertise, affirmation 8 — provenance des données évaluées et des
sorties relues d'une archive.

Chaque test construit un contre-exemple minimal par les API publiques
(``orchestrator.run``, ``ResumeStore``, ``ModuleRegistry``) et affirme le
comportement scientifiquement attendu. Rouge = défaut confirmé.
"""

from __future__ import annotations

import json
import threading
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

import pytest

from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.orchestrator import run
from cinoc.app.resume import ResumeStore, declared_inputs, unit_key
from cinoc.app.run_manifest import module_identities
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec
from cinoc.evaluation.result import RunResult
from cinoc.pipeline.types import StepOutput

CAMPAGNE = (
    Path(__file__).resolve().parents[3] / "campaigns" / "2026-11-26-reference"
)

# --------------------------------------------------------------------------
# Briques factices (contrat ``Module`` public, aucun monkeypatch du produit)
# --------------------------------------------------------------------------


class _FixedOCR:
    """OCR factice : écrit ``text`` ; déclare ``version`` ; compte ses appels.

    ``served`` (optionnel) : modèle que le « fournisseur » dit avoir servi ;
    ``binaries`` (optionnel) : ce que le hook ``system_binaries`` déclare.
    """

    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.RAW_TEXT})

    def __init__(
        self,
        calls: list[str],
        *,
        text: str = "abcd",
        version: str = "1.0",
        served: dict[str, str] | None = None,
        binaries: dict[str, str] | None = None,
    ) -> None:
        self._calls = calls
        self._text = text
        self.version = version
        self._served = served
        self._binaries = binaries
        self.name = "fake:ocr"

    def system_binaries(self) -> dict[str, str]:
        return dict(self._binaries or {})

    def execute(self, inputs, params, context, control):  # noqa: ANN001, ANN201
        self._calls.append(context.document_id)
        path = Path(context.workspace_uri) / f"{context.document_id}.txt"
        path.write_text(self._text, encoding="utf-8")
        return StepOutput(
            artifacts={
                ArtifactType.RAW_TEXT: Artifact(
                    id=f"{context.document_id}:fake:raw_text",
                    document_id=context.document_id,
                    type=ArtifactType.RAW_TEXT,
                    uri=str(path),
                    content_hash=compute_content_hash(self._text.encode()),
                )
            },
            served_models=(
                (self._served["now"],) if self._served is not None else ()
            ),
        )


def _registry(**module_kwargs: Any) -> ModuleRegistry:
    registry = ModuleRegistry()
    registry.register_builder("fake", lambda kwargs: _FixedOCR(**module_kwargs))
    return registry


def _corpus(tmp_path: Path, ids: tuple[str, ...], gt: str = "abcd") -> CorpusSpec:
    documents = []
    for doc_id in ids:
        image = tmp_path / f"{doc_id}.png"
        if not image.exists():
            image.write_bytes(b"\x89PNG " + doc_id.encode())
        truth = tmp_path / f"{doc_id}.gt.txt"
        if not truth.exists():
            truth.write_text(gt, encoding="utf-8")
        documents.append(
            DocumentRef(
                id=doc_id,
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.RAW_TEXT, uri=str(truth)),
                ),
            )
        )
    return CorpusSpec(name="c", documents=tuple(documents))


def _spec(corpus: CorpusSpec, model: str | None = None) -> RunSpec:
    pipeline = PipelineSpec(
        name="p",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="lecture",
                kind="ocr",
                adapter_name="fake:ocr",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    view = EvaluationView(
        name="texte",
        candidate_types=frozenset({ArtifactType.RAW_TEXT}),
        metric_names=("cer",),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=(view,)),
        adapter_kwargs={"fake:ocr": {"model": model}} if model else {},
        run_id="provenance",
    )


def _manifest_sans_horloge(result: RunResult) -> dict[str, Any]:
    data = result.manifest.model_dump(mode="json")
    for volatile in ("started_at", "completed_at", "artifacts_dir"):
        data.pop(volatile, None)
    return data


def _cer(result: RunResult) -> float | None:
    (pipeline,) = result.pipelines
    return {s.metric: s.value for s in pipeline.aggregate}["cer"]


# --------------------------------------------------------------------------
# 8a. Identité du corpus et de chaque vérité terrain
# --------------------------------------------------------------------------


@pytest.mark.valide
def test_identite_gt__deux_gt_differentes_donnent_deux_manifestes(
    tmp_path: Path,
) -> None:
    """Même spec, même moteur, un seul ``.gt.txt`` modifié (abcd → abXd) : les
    manifestes doivent différer (empreinte de la GT), pas seulement les scores."""
    corpus = _corpus(tmp_path, ("d1", "d2"))
    spec = _spec(corpus)
    first = run(spec, registry=_registry(calls=[]), code_version="1.0")
    (tmp_path / "d2.gt.txt").write_text("abXd", encoding="utf-8")
    second = run(spec, registry=_registry(calls=[]), code_version="1.0")

    assert _cer(first) != _cer(second)  # les chiffres ont bougé…
    # … et le manifeste doit dire pourquoi : une GT différente a été lue.
    assert _manifest_sans_horloge(first) != _manifest_sans_horloge(second)


@pytest.mark.valide
def test_identite_gt__resultat_porte_empreinte_de_chaque_gt(tmp_path: Path) -> None:
    """Le ``RunResult`` doit contenir, pour chaque document, le SHA-256 du
    fichier de vérité terrain réellement noté (calculé ici par ``hashlib``)."""
    corpus = _corpus(tmp_path, ("d1",))
    result = run(_spec(corpus), registry=_registry(calls=[]), code_version="1.0")
    digest = sha256((tmp_path / "d1.gt.txt").read_bytes()).hexdigest()
    assert digest in result.model_dump_json()


@pytest.mark.valide
def test_identite_image__resultat_porte_empreinte_de_chaque_image(
    tmp_path: Path,
) -> None:
    """La clé d'unité hache l'image, mais le ``RunResult`` doit aussi porter ce
    SHA-256 (référence ``hashlib``) : sinon l'image évaluée n'est pas vérifiable."""
    corpus = _corpus(tmp_path, ("d1",))
    result = run(_spec(corpus), registry=_registry(calls=[]), code_version="1.0")
    digest = sha256((tmp_path / "d1.png").read_bytes()).hexdigest()
    assert digest in result.model_dump_json()


@pytest.mark.valide
def test_identite_gt__renotation_hors_ligne_contre_autre_gt_signalee(
    tmp_path: Path,
) -> None:
    """Archive produite, GT de ``d1`` remplacée, re-notation ``offline`` : le
    manifeste du second ``RunResult`` doit différer du premier (hors horloges)."""
    corpus = _corpus(tmp_path, ("d1",))
    spec = _spec(corpus)
    store = ResumeStore(tmp_path / "archive")
    original = run(
        spec, registry=_registry(calls=[]), code_version="1.0", resume_store=store
    )
    (tmp_path / "d1.gt.txt").write_text("wxyz", encoding="utf-8")
    renote = run(
        spec,
        registry=_registry(calls=[]),
        code_version="1.0",
        resume_store=store,
        offline=True,
    )
    assert _cer(original) == 0.0
    assert _cer(renote) == 1.0
    assert _manifest_sans_horloge(original) != _manifest_sans_horloge(renote)


@pytest.mark.valide
def test_identite_gt__run_result_publie_porte_les_gt_et_leurs_empreintes() -> None:
    """Le ``RunResult`` publié de la campagne (BNL, 37 pages) doit nommer chaque
    GT notée et son empreinte : on y cherche au moins un nom ``*.gt.txt``."""
    data = json.loads(
        (CAMPAGNE / "bnl-sans-cle.run_result.json").read_text(encoding="utf-8")
    )
    texte = json.dumps(data, ensure_ascii=False)
    assert ".gt.txt" in texte, "aucune GT nommée dans le RunResult publié"


# --------------------------------------------------------------------------
# 8b. Alias de modèles (``-latest``) et digest Ollama
# --------------------------------------------------------------------------


def test_alias_modele__manifeste_enregistre_le_modele_servi(tmp_path: Path) -> None:
    """Modèle demandé ``m-latest``, servi ``m-2506`` : le manifeste doit garder
    les deux (demandé dans ``adapter_kwargs``, servi dans ``served_models``)."""
    served = {"now": "m-2506"}
    corpus = _corpus(tmp_path, ("d1",))
    result = run(
        _spec(corpus, model="m-latest"),
        registry=_registry(calls=[], served=served),
        code_version="1.0",
    )
    assert result.manifest.adapter_kwargs["fake:ocr"]["model"] == "m-latest"
    assert result.manifest.served_models == {"fake:ocr": ("m-2506",)}


@pytest.mark.discutable("C18-provenance-par-unite")
def test_alias_modele__reprise_apres_bascule_attribue_le_modele_par_unite(
    tmp_path: Path,
) -> None:
    """L'alias bascule entre deux runs repris (d1 servi par m-2503, d2 par m-2506)
    : le ``RunResult`` doit dire quelle unité vient de quel modèle servi."""
    served = {"now": "m-2503"}
    store = ResumeStore(tmp_path / "archive")
    run(
        _spec(_corpus(tmp_path, ("d1",)), model="m-latest"),
        registry=_registry(calls=[], served=served),
        code_version="1.0",
        resume_store=store,
    )
    served["now"] = "m-2506"  # l'alias change de cible chez le fournisseur
    calls: list[str] = []
    final = run(
        _spec(_corpus(tmp_path, ("d1", "d2")), model="m-latest"),
        registry=_registry(calls=calls, served=served),
        code_version="1.0",
        resume_store=store,
    )
    assert calls == ["d2"]  # d1 relue de l'archive, sous l'ancien instantané
    # Le run-level voit le mélange (union) …
    assert final.manifest.served_models == {"fake:ocr": ("m-2503", "m-2506")}
    # … mais rien, par unité, ne dit laquelle a été produite par quel modèle.
    per_unit = {u["document_id"]: json.dumps(u) for u in final.model_dump(mode="json")["usage"]}
    assert "m-2503" in per_unit["d1"] and "m-2506" in per_unit["d2"], per_unit


class _TagsHandler(BaseHTTPRequestHandler):
    """Faux serveur Ollama local (boucle locale) : ``/api/tags`` avec digest."""

    digest = "a" * 64

    def do_GET(self) -> None:  # noqa: N802
        body = json.dumps(
            {"models": [{"name": "qwen2.5vl:3b", "digest": type(self).digest}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        return


@pytest.fixture
def ollama_local() -> Any:
    server = HTTPServer(("127.0.0.1", 0), _TagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_digest_ollama__un_tag_reaffecte_change_la_cle_d_unite(
    tmp_path: Path, ollama_local: HTTPServer
) -> None:
    """Le vrai ``OllamaAdapter`` sur un serveur local : le même tag ``qwen2.5vl:3b``
    sous deux digests doit donner deux clés d'unité et deux manifestes."""
    pytest.importorskip("httpx")
    host = f"http://127.0.0.1:{ollama_local.server_address[1]}"
    image = tmp_path / "d1.png"
    image.write_bytes(b"\x89PNG d1")
    document = DocumentRef(id="d1", image_uri=str(image))
    pipeline = PipelineSpec(
        name="vlm",
        initial_inputs=(ArtifactType.IMAGE,),
        steps=(
            PipelineStep(
                id="lecture",
                kind="zero_shot",
                adapter_name="ollama:qwen",
                input_types=(ArtifactType.IMAGE,),
                output_types=(ArtifactType.RAW_TEXT,),
            ),
        ),
    )
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=(document,)),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=()),
        adapter_kwargs={
            "ollama:qwen": {
                "label": "qwen",
                "model": "qwen2.5vl:3b",
                "host": host,
                "role": "zero_shot",
            }
        },
    )
    registry = ModuleRegistry()
    register_default_modules(registry)

    def identity_and_key() -> tuple[dict[str, str], str | None]:
        module = registry.build("ollama:qwen", spec.adapter_kwargs["ollama:qwen"])
        modules = {"ollama:qwen": module}
        identities = module_identities(spec, modules)
        key = unit_key(
            pipeline=pipeline,
            identities=identities,
            document=document,
            inputs=declared_inputs(pipeline, modules, document),
        )
        return dict(identities["ollama:qwen"].binaries), key

    binaries_a, key_a = identity_and_key()
    _TagsHandler.digest = "b" * 64  # ``ollama pull`` : le tag pointe ailleurs
    try:
        binaries_b, key_b = identity_and_key()
    finally:
        _TagsHandler.digest = "a" * 64
    assert binaries_a == {"ollama:qwen2.5vl:3b": "a" * 64}
    assert binaries_b == {"ollama:qwen2.5vl:3b": "b" * 64}
    assert key_a != key_b


def _saknussemm_identity(kwargs: dict[str, Any]) -> str:
    """L'identité hachée (version, réglages, binaires) du vrai module
    ``saknussemm`` construit par le registre du produit, en JSON."""
    pytest.importorskip("saknussemm")
    name = f"saknussemm:{kwargs['label']}"
    registry = ModuleRegistry()
    register_default_modules(registry)
    module = registry.build(name, kwargs)
    pipeline = PipelineSpec(
        name="p",
        initial_inputs=(ArtifactType.LAYOUT,),
        steps=(
            PipelineStep(
                id="correction",
                kind="structured_correction",
                adapter_name=name,
                input_types=(ArtifactType.LAYOUT,),
                output_types=(
                    ArtifactType.LAYOUT,
                    ArtifactType.CORRECTED_TEXT,
                    ArtifactType.DECISIONS,
                ),
            ),
        ),
    )
    spec = RunSpec(
        corpus=CorpusSpec(name="c", documents=()),
        pipelines=(pipeline,),
        evaluation=EvaluationSpec(views=()),
        adapter_kwargs={name: kwargs},
    )
    identity = module_identities(spec, {name: module})[name]
    return json.dumps(
        {
            "version": identity.version,
            "settings": dict(identity.settings),
            "binaries": dict(identity.binaries),
        },
        ensure_ascii=False,
    )


# --------------------------------------------------------------------------
# 8c. Versions de modules déclarées à la main
# --------------------------------------------------------------------------


@pytest.mark.discutable("C17-identite-etape")
def test_version_manuelle__brique_modifiee_sans_relever_sa_version_reexecutee(
    tmp_path: Path,
) -> None:
    """Brique ``1.0`` qui lit « abcd », puis corrigée (lit « abXd ») sans relever
    sa ``version`` : la reprise doit ré-exécuter, pas relire l'ancienne sortie."""
    spec = _spec(_corpus(tmp_path, ("d1",), gt="abXd"))
    store = ResumeStore(tmp_path / "archive")
    run(
        spec,
        registry=_registry(calls=[], text="abcd"),
        code_version="1.0",
        resume_store=store,
    )
    calls: list[str] = []
    after = run(
        spec,
        registry=_registry(calls=calls, text="abXd"),
        code_version="1.0",
        resume_store=store,
    )
    # La brique corrigée est parfaite sur cette GT : CER attendu 0.
    assert _cer(after) == 0.0, (
        f"sortie périmée relue (CER {_cer(after)}), brique appelée {calls}"
    )


@pytest.mark.valide
def test_version_manuelle__identite_saknussemm_porte_la_version_de_la_bibliotheque(
    tmp_path: Path,
) -> None:
    """``saknussemm`` est une bibliothèque tierce (règles, prompt, température
    vivent chez elle) : son ``__version__`` doit entrer dans l'identité hachée."""
    saknussemm = pytest.importorskip("saknussemm")
    hashed = _saknussemm_identity({"label": "regles", "producer": "rules"})
    assert saknussemm.__version__ in hashed, hashed


@pytest.mark.discutable("C17-identite-etape")
def test_identite_saknussemm__prompt_et_temperature_envoyes_au_llm_sont_traces() -> None:
    """``saknussemm:mistral`` (E3 de la campagne) : le prompt système et la
    température que la bibliothèque envoie à Mistral doivent figurer dans
    l'identité (manifeste + empreinte), comme pour ``mistral:correction``."""
    hashed = json.loads(
        _saknussemm_identity(
            {"label": "mistral", "producer": "mistral", "model": "mistral-small-latest"}
        )
    )
    assert {"prompt", "temperature"} <= set(hashed["settings"]), hashed


@pytest.mark.valide
def test_identite_saknussemm__poids_du_scoreur_qe_epingles() -> None:
    """``saknussemm:mistral_qe`` (E4) route par D'AlemBERT (``pjox/dalembert``,
    chargé sans révision) : une révision ou un digest des poids doit entrer
    dans l'identité, sinon deux runs E4 peuvent router avec deux modèles."""
    hashed = json.loads(
        _saknussemm_identity(
            {
                "label": "mistral_qe",
                "producer": "mistral",
                "model": "mistral-small-latest",
                "qe": "dalembert",
                "qe_skip": 0.5,
            }
        )
    )
    texte = json.dumps(hashed)
    assert "dalembert" in texte and ("revision" in texte or "sha" in texte), hashed


# --------------------------------------------------------------------------
# 8d. Reprise sous un autre environnement : provenance des unités relues
# --------------------------------------------------------------------------


@pytest.mark.discutable("C18-provenance-par-unite")
def test_reprise_autre_code__resultat_dit_la_version_de_chaque_unite(
    tmp_path: Path,
) -> None:
    """d1 produite sous ``code_version`` 1.0, d2 sous 2.0 (reprise de la même
    archive) : le ``RunResult`` doit attribuer 1.0 à d1 (ou signaler le mélange)."""
    store = ResumeStore(tmp_path / "archive")
    run(
        _spec(_corpus(tmp_path, ("d1",))),
        registry=_registry(calls=[]),
        code_version="1.0",
        resume_store=store,
    )
    final = run(
        _spec(_corpus(tmp_path, ("d1", "d2"))),
        registry=_registry(calls=[]),
        code_version="2.0",
        resume_store=store,
    )
    assert final.manifest.code_version == "2.0"
    assert [u.resumed for u in final.usage] == [True, False]
    assert '"1.0"' in json.dumps(
        [u.model_dump(mode="json") for u in final.usage]
    ) or '"1.0"' in json.dumps(final.manifest.metadata), (
        "d1 a été produite sous 1.0 ; le RunResult ne nomme que 2.0"
    )


def test_reprise_autres_binaires__unite_reexecutee_pas_melangee(
    tmp_path: Path,
) -> None:
    """d1 produite sous ``tool 5.3``, reprise sous ``tool 5.4`` : la clé hache
    les binaires, donc d1 doit être ré-exécutée et le manifeste ne dire que 5.4."""
    store = ResumeStore(tmp_path / "archive")
    spec = _spec(_corpus(tmp_path, ("d1",)))
    run(
        spec,
        registry=_registry(calls=[], binaries={"tool": "5.3"}),
        code_version="1.0",
        resume_store=store,
    )
    calls: list[str] = []
    final = run(
        spec,
        registry=_registry(calls=calls, binaries={"tool": "5.4"}),
        code_version="1.0",
        resume_store=store,
    )
    assert calls == ["d1"]
    assert [u.resumed for u in final.usage] == [False]
    assert final.manifest.system_binaries_lock == {"tool": "5.4"}


def test_reprise_hors_ligne_binaires_melanges__refus_pas_melange_silencieux(
    tmp_path: Path,
) -> None:
    """Archive où d1 vient de ``tool 5.3`` et d2 de ``tool 5.4`` : la relecture
    hors ligne ne doit pas rendre un run unique qui ne nommerait qu'une version."""
    from cinoc.app.orchestrator import ArchiveIncompleteError

    store = ResumeStore(tmp_path / "archive")
    run(
        _spec(_corpus(tmp_path, ("d1",))),
        registry=_registry(calls=[], binaries={"tool": "5.3"}),
        code_version="1.0",
        resume_store=store,
    )
    run(
        _spec(_corpus(tmp_path, ("d2",))),
        registry=_registry(calls=[], binaries={"tool": "5.4"}),
        code_version="1.0",
        resume_store=store,
    )
    with pytest.raises(ArchiveIncompleteError):
        run(
            _spec(_corpus(tmp_path, ("d1", "d2"))),
            registry=_registry(calls=[]),
            code_version="1.0",
            resume_store=store,
            offline=True,
        )

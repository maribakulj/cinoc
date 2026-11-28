"""Matérialisation des images **distantes** au run (corpus curé = références).

Un corpus curé (HF/IIIF) porte ``image_uri = URL épinglée`` ; les moteurs lisent
un **fichier local**. L'orchestrateur télécharge donc chaque image distante dans
le workspace (fetch durci : anti-SSRF, plafond, écriture atomique) avant
l'exécution. Ces tests verrouillent : (1) la chaîne complète URL → fichier local
→ module → score, (2) la **préservation de la référence** dans le ``RunResult``
(le rapport garde l'URL, pas le chemin temporaire), (3) l'échec **isolé** d'une
image injoignable, (4) le refus anti-SSRF d'une IP privée — sans réseau.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.adapters.corpus._http import HttpFetchError
from cinoc.app import orchestrator, run
from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.domain.evaluation import EvaluationSpec, EvaluationView
from cinoc.domain.pipeline import PipelineSpec, PipelineStep
from cinoc.domain.run_spec import RunSpec

_REMOTE_URL = "https://example.org/iiif/doc1/full/1600,/0/default.jpg"

TEXT_VIEW = EvaluationView(
    name="text",
    candidate_types=frozenset({ArtifactType.RAW_TEXT}),
    metric_names=("cer",),
)


def _registry() -> ModuleRegistry:
    registry = ModuleRegistry()
    register_default_modules(registry)
    return registry


def _spec(corpus: CorpusSpec) -> RunSpec:
    step = PipelineStep(
        id="ocr",
        kind="ocr",
        adapter_name="precomputed:eng",
        input_types=(ArtifactType.IMAGE,),
        output_types=(ArtifactType.RAW_TEXT,),
    )
    return RunSpec(
        corpus=corpus,
        pipelines=(
            PipelineSpec(
                name="eng", initial_inputs=(ArtifactType.IMAGE,), steps=(step,)
            ),
        ),
        evaluation=EvaluationSpec(views=(TEXT_VIEW,)),
        adapter_kwargs={"precomputed:eng": {"source_label": "eng"}},
    )


def _remote_document(tmp_path: Path, url: str = _REMOTE_URL) -> DocumentRef:
    (tmp_path / "doc1.gt.txt").write_text("abcd", encoding="utf-8")
    return DocumentRef(
        id="doc1",
        image_uri=url,
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "doc1.gt.txt")
            ),
        ),
    )


def test_remote_image_materialized_then_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    def fake_download(url: str, dest: Path, **_: object) -> None:
        seen["url"], seen["dest"] = url, dest
        dest.write_bytes(b"\x89PNG stub")
        # ``precomputed`` lit ``<stem>.<label>.txt`` à côté de l'image : le texte
        # rejoué doit suivre la copie matérialisée (c'est le point du test — le
        # module ne voit QUE le fichier local, jamais l'URL).
        dest.with_name(f"{dest.stem}.eng.txt").write_text("abxd", encoding="utf-8")

    monkeypatch.setattr(orchestrator, "download", fake_download)
    document = _remote_document(tmp_path)
    result = run(
        _spec(CorpusSpec(name="c", documents=(document,))),
        registry=_registry(),
        code_version="1.0",
    )
    # Le fetch durci a bien été appelé sur l'URL de référence, suffixe préservé.
    assert seen["url"] == _REMOTE_URL
    assert str(seen["dest"]).endswith(".jpg")
    # La chaîne aboutit à un vrai score (1 substitution / 4).
    aggregate = result.principal_aggregate(result.pipelines[0])[0]
    assert aggregate.metric == "cer"
    assert aggregate.value == pytest.approx(0.25)
    # La spec n'est PAS réécrite : le RunResult garde la **référence** distante
    # (saveur rapport « liens »), pas le chemin du workspace temporaire.
    assert result.documents[0].image_ref == _REMOTE_URL


def test_unreachable_remote_image_fails_unit_not_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Deux documents : un local sain + un distant injoignable → le run aboutit,
    # seul le document distant est en échec (philosophie « échec isolé »).
    def failing_download(url: str, dest: Path, **_: object) -> None:
        raise HttpFetchError("statut HTTP 404")

    monkeypatch.setattr(orchestrator, "download", failing_download)
    (tmp_path / "ok.png").write_bytes(b"\x89PNG stub")
    (tmp_path / "ok.eng.txt").write_text("abcd", encoding="utf-8")
    (tmp_path / "ok.gt.txt").write_text("abcd", encoding="utf-8")
    local = DocumentRef(
        id="ok",
        image_uri=str(tmp_path / "ok.png"),
        ground_truths=(
            GroundTruthRef(
                type=ArtifactType.RAW_TEXT, uri=str(tmp_path / "ok.gt.txt")
            ),
        ),
    )
    remote = _remote_document(tmp_path)
    result = run(
        _spec(CorpusSpec(name="c", documents=(local, remote))),
        registry=_registry(),
        code_version="1.0",
    )
    by_doc = {
        d.document_id: {s.metric: s.value for s in d.scores}
        for d in result.documents
    }
    assert by_doc["ok"]["cer"] == pytest.approx(0.0)  # le local est bien noté
    # L'injoignable est en échec **isolé** (score absent → None, jamais un 0
    # mensonger), sans abattre le run.
    assert by_doc["doc1"]["cer"] is None
    # … et l'échec est **enregistré** avec son motif, pas réduit à une absence.
    outcomes = {u.document_id: (u.outcome, u.reason) for u in result.usage}
    assert outcomes == {"ok": ("ok", None), "doc1": ("failed", "infrastructure")}
    failed = next(u for u in result.usage if u.document_id == "doc1")
    assert "statut HTTP 404" in (failed.message or "")
    assert (result.principal_aggregate(result.pipelines[0])[0].support,
            result.principal_aggregate(result.pipelines[0])[0].expected) == (1, 2)


def test_private_ip_reference_refused_by_ssrf_guard(tmp_path: Path) -> None:
    # IP privée littérale → ``assert_public_url`` refuse AVANT toute connexion
    # (aucun réseau en CI) : l'unité échoue, le run aboutit quand même.
    document = _remote_document(tmp_path, url="http://10.0.0.1/page.png")
    result = run(
        _spec(CorpusSpec(name="c", documents=(document,))),
        registry=_registry(),
        code_version="1.0",
    )
    # Unité échouée (score None), mais le run aboutit — le refus est silencieux
    # côté HTTP : aucune connexion n'a été tentée vers l'IP privée.
    scores = {s.metric: s.value for s in result.documents[0].scores}
    assert scores["cer"] is None

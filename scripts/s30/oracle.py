"""Oracle dinglehopper sur les sorties archivées d'un run (procédure D-290) — outil de session.

Pour chaque unité (pipeline × document) : le texte noté par la vue « texte
(lignes) » (sortie de l'étape notée, relue dans l'archive) et la GT ; puis
  - CER de Cinoc (vue texte (lignes)), recalculé par la chaîne d'écarts du
    golden (tests/evaluation/test_dinglehopper_golden.py) ;
  - CER de dinglehopper exécuté comme sa CLI (plain_extract + character_error_rate) ;
et l'on vérifie que le dernier maillon tombe exactement sur dinglehopper.

Usage (venv d'oracle) : python -I oracle.py <spec.yaml> <archive> <run_result.json> <sortie.json>
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path("/home/user/cinoc")
sys.path.insert(0, str(ROOT))

from cinoc.app.loader import load_run_spec  # noqa: E402
from cinoc.app.modules.registry import register_default_modules  # noqa: E402
from cinoc.app.modules.registry import ModuleRegistry  # noqa: E402, F811
from cinoc.app.orchestrator import _materialize_remote_images  # noqa: E402
from cinoc.app.run_manifest import module_identities  # noqa: E402
from cinoc.app.resume import ResumeStore, declared_inputs, unit_key  # noqa: E402
from cinoc.domain.run_spec import _scored_step  # noqa: E402
from tests.evaluation.test_dinglehopper_golden import (  # noqa: E402
    cinoc_side,
    dinglehopper_scores,
    oracle_side,
)


def main(spec_path: str, archive: str, result_path: str, out_path: str) -> None:
    spec = load_run_spec(spec_path)
    result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    cinoc_cer = {
        (d["pipeline"], d["document_id"]): next(
            s["value"] for s in d["scores"] if s["metric"] == "cer"
        )
        for d in result["documents"]
        if d["view"] == "texte (lignes)"
    }
    store = ResumeStore(Path(archive))
    registry = ModuleRegistry()
    register_default_modules(registry)
    view = next(v for v in spec.evaluation.views if v.name == "texte (lignes)")
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        documents, _unreachable = _materialize_remote_images(
            spec.corpus.documents, Path(tmp) / "images"
        )
        for pipeline in spec.pipelines:
            modules = {
                s.adapter_name: registry.build(
                    s.adapter_name, spec.adapter_kwargs.get(s.adapter_name, {})
                )
                for s in pipeline.steps
            }
            identities = module_identities(
                spec, modules, recorded_binaries=store.recorded_binaries()
            )
            step = _scored_step(view, pipeline)
            for doc in documents:
                key = unit_key(
                    pipeline=pipeline,
                    identities=identities,
                    document=doc,
                    inputs=declared_inputs(pipeline, modules, doc),
                )
                execution = store.load(key, failures=True) if key else None
                if execution is None or execution.outcome == "failed":
                    rows.append({"pipeline": pipeline.name, "document": doc.id,
                                 "status": "absent" if execution is None else "failed"})
                    continue
                outputs = execution.by_step[step.id]
                artifact = next(a for t, a in outputs.items() if t in view.candidate_types)
                hyp_path = Path(artifact.uri or "")
                gt_path = Path(doc.ground_truths[0].uri)
                reference = gt_path.read_text(encoding="utf-8")
                hypothesis = hyp_path.read_text(encoding="utf-8")
                chain = cinoc_side(reference, hypothesis)
                chain["cer"].update(oracle_side(reference, hypothesis)["cer"])
                # plain_extract veut des fichiers : copies UTF-8 exactes.
                g = Path(tmp) / "gt.txt"
                h = Path(tmp) / "hyp.txt"
                g.write_text(reference, encoding="utf-8")
                h.write_text(hypothesis, encoding="utf-8")
                dh = dinglehopper_scores(g, h)["cer"]
                rows.append({
                    "pipeline": pipeline.name,
                    "document": doc.id,
                    "status": "ok",
                    "cinoc_run_result": cinoc_cer.get((pipeline.name, doc.id)),
                    "chain": chain["cer"],
                    "dinglehopper": dh,
                })
    Path(out_path).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = [r for r in rows if r["status"] == "ok"]
    same_run = sum(
        1 for r in ok
        if r["cinoc_run_result"] is not None
        and abs(r["cinoc_run_result"] - r["chain"]["cinoc"]) < 1e-12
    )
    ends = sum(1 for r in ok if abs(r["chain"]["graphemes"] - r["dinglehopper"]) < 1e-12)
    exact = sum(1 for r in ok if abs(r["chain"]["cinoc"] - r["dinglehopper"]) < 1e-12)
    moved = {
        stage: sum(
            1 for r in ok
            if abs(r["chain"][stage] - r["chain"][prev]) > 1e-12
        )
        for prev, stage in zip(
            ("cinoc", "blancs", "invisibles", "sbb"),
            ("blancs", "invisibles", "sbb", "graphemes"),
        )
    }
    gap = sum(abs(r["chain"]["cinoc"] - r["dinglehopper"]) for r in ok) / max(len(ok), 1)
    print(f"unités notées : {len(ok)} / {len(rows)}")
    print(f"CER Cinoc du RunResult = maillon 'cinoc' : {same_run}/{len(ok)}")
    print(f"dernier maillon = dinglehopper : {ends}/{len(ok)}")
    print(f"Cinoc = dinglehopper sans pont : {exact}/{len(ok)} ; écart moyen absolu {gap:.4f}")
    print(f"unités que chaque maillon fait bouger : {moved}")
    for name in sorted({r['pipeline'] for r in ok}):
        mine = [r for r in ok if r["pipeline"] == name]
        mc = sum(r["chain"]["cinoc"] for r in mine) / len(mine)
        md = sum(r["dinglehopper"] for r in mine) / len(mine)
        print(f"  {name} : CER moyen par page Cinoc (lignes) {mc:.4f} · dinglehopper {md:.4f}")


if __name__ == "__main__":
    main(*sys.argv[1:5])

"""C22 — Deux « v6 » de sémantiques différentes, acceptés tous deux par le code de
HEAD sans distinction : le v6 commité (tranche 1a, abee7b5) et la réévaluation 1b
(HEAD) de la même archive S30 Dresden. Même schema_version, même clé ``aggregate``."""
import sys
from cinoc.evaluation.result import RunResult
a = RunResult.model_validate_json(open(sys.argv[1]).read())
b = RunResult.model_validate_json(open(sys.argv[2]).read())
for name, r in (("v6 commité (1a)", a), ("v6 réévalué (HEAD, 1b)", b)):
    p = next(p for p in r.pipelines if p.pipeline.startswith("E5") and p.view == "texte")
    s = next(s for s in p.aggregate if s.metric == "cer")
    print(f"{name:24s} schema_version={r.schema_version} E5/texte/cer aggregate={s.value:.4f} support={s.support}/{s.expected} "
          f"coverage={s.coverage} conditional_aggregate={'vide' if not p.conditional_aggregate else 'présent'} politique={r.manifest.failure_policy}")

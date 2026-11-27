"""Révision 4, C3 (§ 2.1 d) : « un rejet n'est possible que si n₀ ≥ 6 » ; « Avec les
10 pages Dresden, SF peut rejeter (n₀ ≥ 6) » ; B4 : famille de Holm par défaut =
toutes les paires × métriques établies × vues × {micro, macro publié}.

Holm multiplie la plus petite p par la taille m de la famille : un rejet exige
m·2^(1−n₀) ≤ α, soit n₀ ≥ 1 + log2(m/α), pas n₀ ≥ 6. On compte m sur la spec de la
campagne commitée `campaigns/2026-11-26-reference/dresden.yaml`.
"""
import math, yaml
from pathlib import Path
from cinoc.evaluation.registry import metric_specs
from cinoc.domain.evaluation import MetricCategory
root = Path("/tmp/claude-0/-home-user-cinoc/ba51ebd3-028f-5e81-8193-80881c86be9f/scratchpad/contre-expertise/campaigns/2026-11-26-reference")
spec = yaml.safe_load((root / "dresden.yaml").read_text())
specs = metric_specs(); established = {k for k, v in specs.items() if v.category == MetricCategory.ESTABLISHED}
k = len(spec["pipelines"]); pairs = k * (k - 1) // 2
cells = sum(len([m for m in v["metric_names"] if m in established]) for v in spec["evaluation"]["views"])
m = pairs * cells * 2
n_docs = len(spec["corpus"]["documents"]) if "documents" in spec.get("corpus", {}) else 10
print(f"pipelines {k}, paires {pairs}, (vue × métrique établie) {cells}, estimandes 2 -> famille m = {m}")
pmin = 2 ** (1 - n_docs)
print(f"n₀ ≤ {n_docs} : p minimale SF = {pmin:.5f} ; p minimale corrigée Holm = {min(1, m * pmin):.4f} (α = 0,05)")
need = math.ceil(1 + math.log2(m / 0.05))
print(f"rejet possible seulement si n₀ ≥ {need} unités")
assert m * pmin > 0.05

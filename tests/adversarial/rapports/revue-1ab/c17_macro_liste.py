"""C17 — Pour chaque métrique : macro publié ?, finalisation, statistique, et
critère D^M (reference_defines). Repère une métrique dont le dénominateur dépend de
l'hypothèse mais dont le macro est publié (§ 2.1 c)."""
from cinoc.evaluation.registry import MetricRegistry, register_default_metrics
reg = MetricRegistry(); register_default_metrics(reg)
for n in sorted(reg.names()):
    m = reg.document_metric(n)
    if m is None: continue
    print(f"{n:28s} macro={m.macro!s:5s} finalize={getattr(m.finalize,'__name__',m.finalize)!s:18s} in={m.input_types[0].value}/{m.input_types[1].value} cat={m.spec.category.value}")

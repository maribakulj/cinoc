"""C09 — Point 3 : l'évaluation reconstruit-elle les classes de saknussemm ?
Même run (adaptateur réel + vraie bibliothèque, client scripté du test adversarial) :
on compare les comptes **déclarés** par l'adaptateur (DocumentUsage.line_outcomes,
PipelineResult.line_outcomes) au payload ``decisions`` calculé en couche 3
(cinoc/evaluation/decisions.py) et rendu par la section « décisions »."""
import sys, tempfile
from pathlib import Path
from tests.adversarial.applicabilite_echecs import test_ce_saknussemm_issues as m
from tests.adversarial.applicabilite_echecs._kit import (T, corpus, execute, pipeline,
    registry_with, spec, step, text_view)
from cinoc.reports.sections.decisions import DecisionsSection
from cinoc.reports.section import SectionContext

with tempfile.TemporaryDirectory() as t:
    tmp = Path(t)
    docs = tuple(m.LAYOUTS)
    chain = pipeline("p", step("seg", "ce_pages", out_type=T.LAYOUT),
                     step("corr", "ce_sak", in_type=T.LAYOUT, out_type=T.CORRECTED_TEXT))
    r = execute(spec(corpus(tmp, dict.fromkeys(docs, m.REFERENCE)), [chain],
                     [text_view(candidates=(T.CORRECTED_TEXT,))], analyses=["decisions"]),
                registry_with(m._Pages(), m._corrector(m._ScriptedClient(m._script()))))
lo = r.pipelines[0].line_outcomes
print("DÉCLARÉ (adaptateur → exécuteur) :", lo.model_dump())
dec = next(a.payload for a in r.analyses if a.payload.kind == "decisions").pipelines[0]
print("LU (evaluation/decisions.py) : n_lines=%d corrected=%d review_required=%d abstained=%d refused=%s fallback=%s"
      % (dec.n_lines, dec.corrected, dec.review_required, dec.abstained,
         {x.code: x.n for x in dec.refused}, {x.code: x.n for x in dec.fallback}))
same = (dec.corrected, dec.review_required, dec.abstained, {x.code: x.n for x in dec.refused}, {x.code: x.n for x in dec.fallback}) == (lo.corrected, lo.review_required, lo.abstained, dict(lo.refused), dict(lo.fallback))
print("payload decisions == line_outcomes déclarés :", same)
# sidecar réel : chaque ligne porte line_class ; recompte indépendant
import json
from collections import Counter

total_decl = lo.corrected + lo.review_required + lo.abstained + sum(lo.refused.values()) + sum(lo.fallback.values())
print("somme des classes déclarées :", total_decl, "| n_lines :", dec.n_lines)
print("partial déclaré par unité :", {u.document_id: u.outcome for u in r.usage})
html = str(DecisionsSection().render(r, SectionContext()) or "")
import re
txt = re.sub(r"<[^>]+>", " ", html); txt = re.sub(r"\s+", " ", txt)
for mot in ("chunk_error_absorbed", "refus", "repli", "fallback"):
    i = txt.find(mot)
    if i >= 0: print(f"rapport [{mot}] … {txt[max(0,i-140):i+80]} …")

"""C06 — Qualité opérationnelle et recalcul des agrégats depuis le JSON v6.

Corpus 4 pages, vue texte projetée depuis une mise en page (layout_to_text).
  A : d1 exact ; d2 sortie **illisible** (JSON de layout invalide) ; d3 échec moteur ;
      d4 partielle déclarée (moitié du texte).
  B : d1 exact ; d2 mise en page **vide** (rien de lu) ; d3 exact ; d4 tronquée.
Attendu (§ 2.1 f) : l'opérationnel = toutes les unités attendues ; un échec ou une
sortie inexploitable notée comme une sortie vide. On vérifie aussi que chaque agrégat
publié se recalcule à partir des observations conservées dans le JSON (rév. 7, I)."""
import sys, tempfile, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError, ArtifactType as T
from cinoc.domain.layout import CanonicalLayout, LayoutPage, Region, Line
from cinoc.domain.projection import ProjectionSpec
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.result import RunResult
from cinoc.evaluation.statistics import combine, edit_rate
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, spec, execute)

def lay(text):
    lines = tuple(Line(text=t) for t in text.split("\n")) if text else ()
    return CanonicalLayout(pages=(LayoutPage(regions=(Region(id="r1", lines=lines),) if lines else ()),)).model_dump_json().encode()

REF = {"d1": "abcdefghij", "d2": "klmnopqrst", "d3": "uvwxyz0123", "d4": "ABCDEFGHIJ"}
policy = sys.argv[1] if len(sys.argv) > 1 else "exclude"
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), REF)
    a = RawBrick("brick_a", {"d1": lay(REF["d1"]), "d2": b'{"pages": [ oops', "d3": AdapterStepError("panne"),
                             "d4": lay("ABCDE")}, partial=frozenset({"d4"}), out_type=T.LAYOUT)
    b = RawBrick("brick_b", {"d1": lay(REF["d1"]), "d2": lay(""), "d3": lay(REF["d3"]), "d4": lay("ABCDEFG")},
                 truncate=frozenset({"d4"}), out_type=T.LAYOUT)
    view = EvaluationView(name="texte", candidate_types=frozenset({T.LAYOUT}), metric_names=("cer",),
        projection=ProjectionSpec(source_type=T.LAYOUT, target_type=T.RAW_TEXT, projector_name="layout_to_text"))
    s = spec(c, [pipeline("A", step("ocr", "brick_a", out_type=T.LAYOUT)),
                 pipeline("B", step("ocr", "brick_b", out_type=T.LAYOUT))], [view], failure_policy=policy)
    r = execute(s, registry_with(a, b))
raw = r.model_dump_json()
r2 = RunResult.model_validate_json(raw)
print("politique :", policy, "| aller-retour JSON identique :", r2 == r)
for p in r2.pipelines:
    for name, ag in (("conditionnel", p.conditional_aggregate[0]), ("opérationnel", p.operational_aggregate[0])):
        print(f"  {p.pipeline} {name:13s} valeur={ag.value} stat={None if ag.stat is None else (ag.stat.edits, ag.stat.reference_length)} support={ag.support}/{ag.expected} couverture={ag.coverage}")
print("  par document :")
for d in r2.documents:
    sc = d.scores[0]
    print(f"   {d.pipeline} {d.document_id} axes=({sc.applicability},{sc.availability},{sc.validity}) stat={None if sc.stat is None else (sc.stat.edits, sc.stat.reference_length)} stat_partielle={None if sc.stat_partielle is None else (sc.stat_partielle.edits, sc.stat_partielle.reference_length)}")
print("  recalcul depuis le JSON :")
for p in r2.pipelines:
    docs = [d.scores[0] for d in r2.documents if d.pipeline == p.pipeline]
    cond = combine([s.stat for s in docs if s.stat is not None and s.validity == "valid" and s.availability == "available"])
    # opérationnel : complètes + partielles telles que produites ; les échecs sans
    # statistique ne portent pas n_réf dans le JSON : on ne peut pas les « vider ».
    oper = combine([s.stat if s.stat is not None else s.stat_partielle for s in docs if (s.stat or s.stat_partielle) is not None])
    pub_c, pub_o = p.conditional_aggregate[0].stat, p.operational_aggregate[0].stat
    print(f"   {p.pipeline}: conditionnel recalculé == publié : {cond == pub_c} ; opérationnel recalculé {None if oper is None else (oper.edits, oper.reference_length)} == publié {(pub_o.edits, pub_o.reference_length)} : {oper == pub_o}")

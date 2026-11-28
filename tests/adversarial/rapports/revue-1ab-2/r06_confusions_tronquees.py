"""R06 — D8 : « Ce sont les substitutions que compte le CER, ni plus ni moins »
est affiché quand matches_canonical_counts est vrai ; la liste est tronquée à
_TOP_CONFUSIONS (10). 12 substitutions distinctes, aucune ambiguïté d'alignement."""
import tempfile, re
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step, pipeline, text_view, spec, execute, per_document)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets, texte_visible
from cinoc.reports.renderer import default_report_renderer
ref = "abcdefghijklmnopqrstuvwxyz"
hyp = "ABCDEFGHIJKLmnopqrstuvwxyz"  # 12 substitutions distinctes
with tempfile.TemporaryDirectory() as t:
    c = corpus(Path(t), {"d1": ref})
    r = execute(spec(c, [pipeline("A", step("ocr", "a")), pipeline("B", step("ocr", "b"))], [text_view()], analyses="toutes"),
                registry_with(BriqueOctets("a", {"d1": hyp.encode()}), BriqueOctets("b", {"d1": ref.encode()})))
diag = next(a.payload for a in r.analyses if a.payload.kind == "diagnostics")
print("matches_canonical_counts :", diag.matches_canonical_counts, "| paires publiées A :", sum(len(p.pairs) for p in diag.confusions if p.pipeline == "A"),
      "| S canonique A :", per_document(r, "A", "d1").stat.substitutions)
for lang in ("fr", "en"):
    txt = texte_visible(default_report_renderer().render(r, lang=lang))
    print(lang, "phrase de décomposition affichée :", ("ni plus ni moins" in txt) or ("exactly the substitutions" in txt))

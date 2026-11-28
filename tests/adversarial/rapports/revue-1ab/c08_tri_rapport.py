"""C08 — A6/B7 : « seul le support global trie ». Le tableau « Comparaison des
moteurs » du rapport (by_engine) et la synthèse ordonnent-ils sur le support global ?
A échoue sur les 4 pages difficiles où B fait beaucoup d'erreurs ; sur les 6 pages
communes, B est meilleur. Sur son propre support (D^μ_A), A paraît meilleur."""
import sys, tempfile, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from _brique import RawBrick
from cinoc.adapters.extension import AdapterStepError
from cinoc.reports.sections.by_engine import EngineSection
from cinoc.reports.section import SectionContext
from tests.adversarial.applicabilite_echecs._kit import (corpus, registry_with, step,
    pipeline, text_view, spec, execute)
REF = {f"d{i}": "abcdefghijklmnopqrst" for i in range(10)}
with tempfile.TemporaryDirectory() as tmp:
    c = corpus(Path(tmp), REF)
    a = RawBrick("brick_a", {d: (AdapterStepError("x") if i < 4 else ("abcdefghijklmnopqr##").encode()) for i, d in enumerate(REF)})
    b = RawBrick("brick_b", {d: (("##########klmnopqrst") if i < 4 else "abcdefghijklmnopqrs#").encode() for i, d in enumerate(REF)})
    s = spec(c, [pipeline("A", step("ocr", "brick_a")), pipeline("B", step("ocr", "brick_b"))], [text_view()])
    r = execute(s, registry_with(a, b))
comp = next(an.payload for an in r.analyses if an.payload.kind == "comparison")
print("support global :", comp.global_support.micro_documents, "micro", comp.global_support.micro, "→ tri publié", comp.global_support.ranking)
print("agrégats propres :", {p.pipeline: (p.aggregate[0].value, f"{p.aggregate[0].support}/{p.aggregate[0].expected}") for p in r.pipelines})
html = str(EngineSection().render(r, SectionContext()))
rows = re.findall(r'<tr><td class="eng-cell"><a href="#engine-\d+" title="Profil">(.*?)</a>', html)
names = [re.sub("<[^>]+>", "", x).strip() for x in rows]
print("ordre des lignes du tableau « Comparaison des moteurs » :", names)

"""R10 — D9 : sortie non UTF-8 (et JSON de mise en page invalide) sous TOUTES les
analyses (correction, diagnostics, taxonomie, word_errors, document_texts…),
chaîne OCR → correction, et rapport FR/EN : le run et le rapport survivent-ils ?"""
import tempfile
from pathlib import Path
from tests.adversarial.applicabilite_echecs._kit import (T, corpus, registry_with, step, pipeline, text_view, spec, execute, per_document)
from tests.adversarial.applicabilite_echecs._kit_revue import BriqueOctets
from cinoc.reports.renderer import default_report_renderer
REF = {f"d{i}": "le soleil luit sur la seine" for i in range(7)}
for pol in ("exclude", "empty_page"):
    with tempfile.TemporaryDirectory() as t:
        c = corpus(Path(t), REF)
        ocr = BriqueOctets("ocr", {d: b"le so1eil luit sur la seine" for d in REF})
        corr = BriqueOctets("corr", {d: (b"\xff\xfe\x00 garbage" if d == "d1" else b"le soleil luit sur la seine") for d in REF}, in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT)
        ocr2 = BriqueOctets("ocr2", {d: (b"\xc3\x28 bad" if d == "d2" else b"le soleil luit sur la scine") for d in REF})
        try:
            r = execute(spec(c, [pipeline("C", step("ocr", "ocr"), step("corr", "corr", in_type=T.RAW_TEXT, out_type=T.CORRECTED_TEXT)),
                                 pipeline("O", step("ocr", "ocr2"))],
                             [text_view("texte", metrics=("cer", "wer"), candidates=(T.RAW_TEXT, T.CORRECTED_TEXT))], analyses="toutes", failure_policy=pol),
                        registry_with(ocr, corr, ocr2))
        except Exception as e:
            print(pol, "RUN PERDU", type(e).__name__, str(e)[:300]); continue
    x = per_document(r, "C", "d1"); y = per_document(r, "O", "d2")
    print(pol, "C d1", x.availability, x.value, "| O d2", y.availability, y.value, "| analyses", sorted({a.payload.kind for a in r.analyses}))
    for lang in ("fr", "en"):
        try:
            h = default_report_renderer().render(r, lang=lang); print("  rapport", lang, len(h))
        except Exception as e:
            print("  RAPPORT PERDU", lang, type(e).__name__, str(e)[:200])

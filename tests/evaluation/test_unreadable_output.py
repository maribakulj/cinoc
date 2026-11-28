"""Une sortie illisible n'abat jamais le run, même sous toutes les analyses (D9).

Un octet non UTF-8 dans l'étage corrigé donne ``output_unreadable`` à son unité,
et le bilan de correction le compte comme un étage absent au lieu de lever.
"""

from __future__ import annotations

from pathlib import Path

from tests.adversarial.applicabilite_echecs._kit import (
    T,
    corpus,
    execute,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)
from tests.adversarial.applicabilite_echecs._kit_revue import NON_UTF8, BriqueOctets


def test_a_non_utf8_corrected_text_does_not_lose_the_run(tmp_path: Path) -> None:
    refs = {"d1": "abcdefghij", "d2": "abcdefghij"}
    ocr = BriqueOctets("ce_ocr", dict.fromkeys(refs, b"abcdefghiX"))
    corr = BriqueOctets(
        "ce_corr",
        {"d1": b"abcdefghij", "d2": NON_UTF8},
        in_type=T.RAW_TEXT,
        out_type=T.CORRECTED_TEXT,
    )
    result = execute(
        spec(
            corpus(tmp_path, refs),
            [
                pipeline(
                    "A",
                    step("ocr", "ce_ocr"),
                    step(
                        "corr",
                        "ce_corr",
                        in_type=T.RAW_TEXT,
                        out_type=T.CORRECTED_TEXT,
                    ),
                )
            ],
            [text_view("corrige", candidates=(T.CORRECTED_TEXT,))],
            analyses="toutes",
        ),
        registry_with(ocr, corr),
    )
    axes = {d.document_id: d.scores[0].availability for d in result.documents}
    assert axes == {"d1": "available", "d2": "output_unreadable"}
    assert "correction" in {a.payload.kind for a in result.analyses}

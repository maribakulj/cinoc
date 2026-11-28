"""Collecteur de **textes complets** de tous les documents scorés (couche 3).

Mirror de ``DiagnosticsCollector`` : observe (pipeline, doc, ref, hyp, CER) par
document scoré, puis ``build`` embarque **tous** les documents (ordonnés
pires-d'abord par CER moyen) avec leurs textes (bornés par sûreté) →
``DocumentTextsPayload``, qui alimente le **diff côte à côte** du détail document
(rapport). Tous les docs → la vue document montre la transcription complète de
chacun (pas seulement des pires). Déterministe.
"""

from __future__ import annotations

from statistics import fmean

from cinoc.evaluation._alignment import matches_canonical
from cinoc.evaluation.analysis import (
    _MAX_TEXT_CHARS,
    Analysis,
    DocumentTexts,
    DocumentTextsPayload,
)

#: Plafond de caractères par texte (borne de sûreté, = ``analysis._MAX_TEXT_CHARS``).
_MAX_CHARS = _MAX_TEXT_CHARS


class DocumentTextsCollector:
    """Accumule les textes par document, ``build`` borne aux pires (CER moyen)."""

    def __init__(self) -> None:
        self._reference: dict[str, str] = {}
        self._hyps: dict[str, dict[str, str]] = {}
        self._cers: dict[str, list[float]] = {}
        #: Le diff surligné suit l'alignement RapidFuzz : concorde-t-il, sur
        #: tous les documents, avec les comptes canoniques du CER ?
        self._concordant = True

    def observe(
        self,
        pipeline: str,
        document_id: str,
        reference: str,
        hypothesis: str,
        cer: float | None,
    ) -> None:
        self._concordant = self._concordant and matches_canonical(
            reference, hypothesis
        )
        self._reference.setdefault(document_id, reference[:_MAX_CHARS])
        self._hyps.setdefault(document_id, {})[pipeline] = hypothesis[:_MAX_CHARS]
        if cer is not None:
            self._cers.setdefault(document_id, []).append(cer)

    def build(self, view: str) -> Analysis | None:
        """Payload de **tous** les documents scorés (CER moyen ↓), ``None`` si rien."""
        if not self._reference:
            return None

        def _mean_cer(doc: str) -> float:
            values = self._cers.get(doc)
            return fmean(values) if values else 0.0

        ranked = sorted(self._reference, key=lambda d: (-_mean_cer(d), d))
        documents = tuple(
            DocumentTexts(
                document_id=doc,
                reference=self._reference[doc],
                # Hypothèses ordonnées (pipeline) — déterministe.
                hypotheses=tuple(sorted(self._hyps.get(doc, {}).items())),
            )
            for doc in ranked
        )
        return Analysis(
            scope="corpus",
            view=view,
            payload=DocumentTextsPayload(
                documents=documents, matches_canonical_counts=self._concordant
            ),
        )


__all__ = ["DocumentTextsCollector"]

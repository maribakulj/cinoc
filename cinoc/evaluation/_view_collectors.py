"""Cycle de vie des **collecteurs de vue** du runner (couche 3).

``evaluate_run`` instancie ~13 collecteurs stateful par vue, leur fait
``observe`` un par document × pipeline, puis ``build`` un payload d'analyse.
Cet enchaînement (instancier → observer → bâtir) est ici **regroupé** en un seul
objet cohésif : le runner n'a plus à câbler chaque collecteur à la main. Sortie
**identique** — pur déplacement de l'orchestration (les analyses sont triées en
aval, l'ordre d'ajout est sans effet).

Les analyses **autonomes** (calibration, économie, correction, conformité) ne
sont pas des collecteurs (elles lisent ``corpus``/``pipeline_outputs``/``usage``
directement) et restent dans ``evaluate_run``.

``actives`` restreint ce qui est **observé**, pas seulement ce qui est rendu :
c'est l'observation qui coûte. Un collecteur éteint ne voit aucun document,
donc ne bâtit rien — le filtre sur ``build`` n'est qu'une ceinture, gratuite
puisque rien n'a été accumulé.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.context import DocContext
from cinoc.evaluation.diagnostics import DiagnosticsCollector
from cinoc.evaluation.document_hallucination import DocumentHallucinationCollector
from cinoc.evaluation.document_lines import DocumentLinesCollector
from cinoc.evaluation.document_texts import DocumentTextsCollector
from cinoc.evaluation.inter_engine import InterEngineCollector
from cinoc.evaluation.lines import LinesCollector, newline_preserved
from cinoc.evaluation.markers import MarkerCollector
from cinoc.evaluation.ner import EntitiesCollector, EntitySet
from cinoc.evaluation.result import Analysis, MetricScore
from cinoc.evaluation.roman import RomanNumeralsCollector
from cinoc.evaluation.structured_data import StructuredDataCollector
from cinoc.evaluation.taxonomy import TaxonomyCollector
from cinoc.evaluation.textual_fidelity import TextualFidelityCollector
from cinoc.evaluation.word_errors import WordErrorCollector

#: ``attribut du collecteur -> kind de l'analyse qu'il produit``. C'est cette
#: table qui rend les analyses **déclarables** : sans elle, ``EvaluationSpec.
#: analyses`` ne saurait pas quoi éteindre. Elle est confrontée aux ``kind``
#: réellement produits par ``tests/evaluation/test_analyses_declarees.py`` —
#: une table qui dérive rendrait une analyse silencieusement inextinguible.
COLLECTEURS: Mapping[str, str] = {
    "diagnostics": "diagnostics",
    "taxonomy": "taxonomy",
    "doc_hallucination": "document_hallucination",
    "doc_texts": "document_texts",
    "structured": "structured_data",
    "markers": "philology",
    "roman": "roman",
    "textual_fidelity": "textual_fidelity",
    "inter_engine": "inter_engine",
    "word_errors": "word_errors",
    "entities": "ner",
    "lines": "lines",
    "doc_lines": "document_lines",
}


class ViewCollectors:
    """Les collecteurs stateful d'**une** vue : instancier → observer → bâtir.

    Une instance par vue. ``observe`` est appelé une fois par (pipeline,
    document) avec les contextes texte/entités déjà calculés par le runner ;
    ``build`` rend les payloads d'analyse non vides de la vue.
    """

    def __init__(
        self, view: EvaluationView, actives: frozenset[str] | None = None
    ) -> None:
        #: ``None`` = toutes (défaut historique). Sinon, les ``kind`` voulus.
        self._actives = actives
        self.diagnostics = DiagnosticsCollector()
        self.taxonomy = TaxonomyCollector()
        self.doc_hallucination = DocumentHallucinationCollector()
        self.doc_texts = DocumentTextsCollector()
        self.structured = StructuredDataCollector()
        self.markers = MarkerCollector()
        self.roman = RomanNumeralsCollector()
        self.textual_fidelity = TextualFidelityCollector()
        self.inter_engine = InterEngineCollector()
        self.word_errors = WordErrorCollector()
        self.entities = EntitiesCollector()
        # Distribution par ligne : applicable seulement si la normalisation de
        # la vue préserve les sauts de ligne (sonde comportementale).
        preserves_newlines = newline_preserved(view)
        self.lines = LinesCollector(enabled=preserves_newlines)
        self.doc_lines = DocumentLinesCollector(enabled=preserves_newlines)

    def _actif(self, attribut: str) -> bool:
        """Ce collecteur est-il demandé ? ``None`` = tous le sont."""
        return self._actives is None or COLLECTEURS[attribut] in self._actives

    def observe(
        self,
        pipeline_name: str,
        document_id: str,
        scores: Sequence[MetricScore],
        text_context: DocContext | None,
        entity_context: DocContext | None,
    ) -> None:
        """Diffuse un document à tous les collecteurs applicables (fan-out)."""
        if (
            entity_context is not None
            and isinstance(entity_context.reference, EntitySet)
            and isinstance(entity_context.hypothesis, EntitySet)
        ):
            if self._actif("entities"):
                self.entities.observe(
                    pipeline_name,
                    entity_context.reference,
                    entity_context.hypothesis,
                )
        if text_context is None:
            return
        ref = str(text_context.reference)
        hyp = str(text_context.hypothesis)
        if self._actif("diagnostics"):
            self.diagnostics.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("taxonomy"):
            self.taxonomy.observe(pipeline_name, ref, hyp)
        if self._actif("doc_hallucination"):
            self.doc_hallucination.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("structured"):
            self.structured.observe(pipeline_name, ref, hyp)
        if self._actif("markers"):
            self.markers.observe(pipeline_name, ref, hyp)
        if self._actif("roman"):
            self.roman.observe(pipeline_name, ref, hyp)
        if self._actif("lines"):
            self.lines.observe(pipeline_name, ref, hyp)
        if self._actif("doc_lines"):
            self.doc_lines.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("textual_fidelity"):
            self.textual_fidelity.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("inter_engine"):
            self.inter_engine.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("word_errors"):
            self.word_errors.observe(pipeline_name, document_id, ref, hyp)
        if self._actif("doc_texts"):
            cer = next((s.value for s in scores if s.metric == "cer"), None)
            self.doc_texts.observe(pipeline_name, document_id, ref, hyp, cer)

    def build(
        self,
        view_name: str,
        document_ids: Sequence[str],
        cer_series: Mapping[str, list[MetricScore]],
    ) -> list[Analysis]:
        """Payloads non vides de la vue (ordre indifférent : tri en aval)."""
        out: list[Analysis] = []
        diagnostic = self.diagnostics.build(
            view_name, "cer", list(document_ids), cer_series
        )
        taxonomy_analysis = self.taxonomy.build(view_name)
        # L'inter-moteurs lit les comptages taxonomy de la même vue (zéro
        # re-classification) — il doit donc être bâti après ``taxonomy``.
        inter_engine_analysis = self.inter_engine.build(view_name, taxonomy_analysis)
        candidates = [
            diagnostic,
            taxonomy_analysis,
            self.doc_hallucination.build(view_name),
            inter_engine_analysis,
            self.word_errors.build(view_name),
            self.structured.build(view_name),
            self.markers.build(view_name),
            self.roman.build(view_name),
            self.textual_fidelity.build(view_name),
            self.lines.build(view_name),
            self.doc_lines.build(view_name),
            self.entities.build(view_name),
            self.doc_texts.build(view_name),
        ]
        out.extend(
            analysis
            for analysis in candidates
            if analysis is not None
            and (self._actives is None or analysis.payload.kind in self._actives)
        )
        return out


__all__ = ["ViewCollectors"]

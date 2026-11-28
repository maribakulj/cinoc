"""``CorpusSpec`` — description immuable et déclarative d'un corpus.

Construit par un adapter de corpus, consommé par les services
applicatifs et le pipeline. Minimaliste : il décrit la structure (liste
de documents + métadonnées). Le chargement, le parsing et la détection
des patterns de nommage GT vivent ailleurs.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from cinoc.domain.documents import DocumentRef


class CorpusSpec(BaseModel):
    """Description immuable d'un corpus à benchmarker.

    Ne contient pas la racine du filesystem : les URIs des documents sont
    résolubles sans contexte, ce qui permet à un service de réécrire les
    chemins (sandbox, cache) sans muter le ``CorpusSpec``.

    Attributs
    ---------
    name:
        Nom court (rapports, cache, logs).
    documents:
        Liste ordonnée des ``DocumentRef`` ; ids uniques.
    metadata:
        Dictionnaire libre de contexte (``language``, ``period``,
        ``source``…). Pas de validation stricte sur les clés.
    target_population:
        Ce que l'échantillon de documents (ou de grappes) représente (B3) —
        publié avec chaque agrégat. ``None`` : non déclaré.
    cluster_weighting:
        Pondération du macro : ``document`` (moyenne par document, défaut) ou
        ``cluster`` (moyenne des moyennes par grappe ; un document sans grappe
        est sa propre grappe). Le micro, ratio de sommes, n'en dépend pas.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    documents: tuple[DocumentRef, ...] = Field(default_factory=tuple)
    metadata: dict[str, str] = Field(default_factory=dict)
    target_population: str | None = Field(default=None, min_length=1, max_length=512)
    cluster_weighting: Literal["document", "cluster"] = "document"

    @model_validator(mode="after")
    def _weighting_needs_clusters(self) -> Self:
        if self.cluster_weighting == "cluster" and not any(
            doc.cluster is not None for doc in self.documents
        ):
            from cinoc.domain.errors import CorpusSpecError

            raise CorpusSpecError(
                "pondération par grappe déclarée, mais aucun document ne porte "
                "de grappe (``DocumentRef.cluster``)."
            )
        return self

    @field_validator("documents")
    @classmethod
    def _validate_unique_doc_ids(
        cls, v: tuple[DocumentRef, ...],
    ) -> tuple[DocumentRef, ...]:
        seen: set[str] = set()
        for doc in v:
            if doc.id in seen:
                from cinoc.domain.errors import CorpusSpecError

                raise CorpusSpecError(
                    f"document id dupliqué : {doc.id!r}. Les id de DocumentRef "
                    "doivent être uniques au sein d'un CorpusSpec."
                )
            seen.add(doc.id)
        return v

    def __len__(self) -> int:
        return len(self.documents)

    def doc_by_id(self, doc_id: str) -> DocumentRef | None:
        """Retourne le ``DocumentRef`` correspondant ou ``None``."""
        for doc in self.documents:
            if doc.id == doc_id:
                return doc
        return None


__all__ = ["CorpusSpec"]

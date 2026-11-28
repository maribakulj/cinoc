"""Brique de contre-exemple : comme TextBrick, mais peut écrire des octets bruts."""
from __future__ import annotations
from dataclasses import dataclass, field
from cinoc.adapters.extension import (AdapterStepError, Artifact, ArtifactType,
    StepOutput, compute_content_hash, workspace_artifact_path)
import dataclasses

@dataclass
class RawBrick:
    name: str
    outputs: dict  # doc -> bytes | AdapterStepError
    partial: frozenset = frozenset()
    truncate: frozenset = frozenset()
    in_type: ArtifactType = ArtifactType.IMAGE
    out_type: ArtifactType = ArtifactType.RAW_TEXT
    version: str = "1.0"
    @property
    def input_types(self): return frozenset({self.in_type})
    @property
    def output_types(self): return frozenset({self.out_type})
    def execute(self, inputs, params, context, control):
        doc = context.document_id
        produced = self.outputs[doc]
        if isinstance(produced, AdapterStepError):
            raise produced
        path = workspace_artifact_path(context.workspace_uri, doc, self.name, "txt")
        path.write_bytes(produced)
        art = Artifact(id=f"{doc}:{self.name}", document_id=doc, type=self.out_type,
                       uri=str(path), content_hash=compute_content_hash(produced))
        out = StepOutput(artifacts={self.out_type: art},
                         truncation="max_tokens" if doc in self.truncate else None)
        if doc in self.partial:
            out = dataclasses.replace(out, partial="perte_region")
        return out

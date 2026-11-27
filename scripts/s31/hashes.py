"""SHA-256 des images et des vérités terrain des deux corpus — outil de session.

Image locale : hachée sur disque. Image distante (Dresden, IIIF servi par HF) :
le contenu que l'archive a rangé sous ``images/<sha256>`` — l'unité le nomme ;
on re-hache le fichier pour le vérifier. Sortie : tableau Markdown.

Usage : python hashes.py <spec.yaml> <archive>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(spec_path: str, archive: str) -> None:
    root = Path(spec_path).parent
    spec = yaml.safe_load(Path(spec_path).read_text(encoding="utf-8"))
    remote: dict[str, Path] = {}
    for index in Path(archive).glob("*/index.json"):
        data = json.loads(index.read_text(encoding="utf-8"))
        for step in data["steps"]:
            if step["step"] != "__initial__":
                continue
            image = step["artifacts"].get("image")
            if image and image["uri"]:
                remote[image["document_id"]] = (index.parent / image["uri"]).resolve()
    print("| document | image (SHA-256) | vérité terrain (SHA-256) |")
    print("|---|---|---|")
    for doc in spec["corpus"]["documents"]:
        uri = doc["image_uri"]
        if uri.startswith("http"):
            path = remote[doc["id"]]
            digest = sha(path)
            assert path.stem == digest, (doc["id"], path)
        else:
            digest = sha(root / uri)
        gt = sha(root / doc["ground_truths"][0]["uri"])
        print(f"| `{doc['id']}` | `{digest}` | `{gt}` |")


if __name__ == "__main__":
    main(*sys.argv[1:3])

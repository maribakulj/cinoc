"""``load_run_spec`` : YAML valide → ``RunSpec`` (chemins sécurisés) ; rejets."""

from __future__ import annotations

from pathlib import Path

import pytest

from cinoc.app.loader import RunSpecError, load_run_spec
from cinoc.app.security import PathSecurityError

_VALID = """
run_id: demo
corpus:
  name: my_corpus
  documents:
    - id: doc1
      image_uri: images/doc1.png
      ground_truths:
        - {type: raw_text, uri: gt/doc1.txt}
pipelines:
  - name: tess
    initial_inputs: [image]
    steps:
      - id: ocr
        kind: ocr
        adapter_name: "tesseract:fra"
        input_types: [image]
        output_types: [raw_text]
adapter_kwargs:
  "tesseract:fra": {label: fra, lang: fra}
evaluation:
  views:
    - {name: text, candidate_types: [raw_text], metric_names: [cer, wer]}
"""


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "run.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_valid_run_spec(tmp_path: Path) -> None:
    # la vérité-terrain doit exister (must_exist=True) ; l'image, non.
    (tmp_path / "gt").mkdir()
    (tmp_path / "gt" / "doc1.txt").write_text("réf", encoding="utf-8")
    spec = load_run_spec(_write(tmp_path, _VALID))
    assert spec.run_id == "demo"
    assert spec.corpus.name == "my_corpus"
    assert len(spec.pipelines) == 1
    assert spec.adapter_kwargs["tesseract:fra"]["lang"] == "fra"
    document = spec.corpus.documents[0]
    assert document.image_uri == str((tmp_path / "images/doc1.png").resolve())
    assert document.ground_truths[0].uri == str((tmp_path / "gt/doc1.txt").resolve())


def test_remote_image_reference_passes_through(tmp_path: Path) -> None:
    # Corpus curé : ``image_uri`` peut être une **référence** http(s) épinglée —
    # elle passe telle quelle (matérialisée au run par l'orchestrateur via le
    # fetch durci) ; seuls les chemins locaux passent par ``validated_path``.
    (tmp_path / "gt").mkdir()
    (tmp_path / "gt" / "doc1.txt").write_text("réf", encoding="utf-8")
    url = "https://huggingface.co/datasets/x/y/resolve/abc/iiif/doc1/full/max/0/default.jpg"
    spec = load_run_spec(_write(tmp_path, _VALID.replace("images/doc1.png", url)))
    assert spec.corpus.documents[0].image_uri == url


def test_path_traversal_rejected(tmp_path: Path) -> None:
    evil = _VALID.replace("images/doc1.png", "../../../etc/passwd")
    with pytest.raises(PathSecurityError):
        load_run_spec(_write(tmp_path, evil))


def test_missing_ground_truth_rejected(tmp_path: Path) -> None:
    # GT inexistante → erreur typée AU CHARGEMENT (pas un OSError opaque en run).
    # Le message dit contre quel dossier le chemin relatif a été cherché : un
    # bloc `corpus:` collé ailleurs échouait sans le dire (D-281, D21).
    with pytest.raises(PathSecurityError, match="dossier du fichier de run") as exc:
        load_run_spec(_write(tmp_path, _VALID))
    assert str(tmp_path) in str(exc.value)


def test_written_identifiers_are_always_quoted(tmp_path: Path) -> None:
    """``id: 0009`` nu se lit 9 en YAML 1.2 (pilote D-281, D21)."""
    import yaml

    from cinoc.app.loader import dump_corpus_spec
    from cinoc.domain.corpus import CorpusSpec
    from cinoc.domain.documents import DocumentRef

    spec = CorpusSpec(
        name="1850",
        documents=tuple(DocumentRef(id=i) for i in ("0003", "0009", "page_1")),
    )
    texte = dump_corpus_spec(spec, tmp_path / "corpus.yaml").read_text(
        encoding="utf-8"
    )
    for ident in ("0003", "0009", "page_1", "1850"):
        assert f"'{ident}'" in texte
    relu = yaml.safe_load(texte)["corpus"]
    assert [d["id"] for d in relu["documents"]] == ["0003", "0009", "page_1"]
    assert relu["name"] == "1850"


def test_malformed_yaml_rejected(tmp_path: Path) -> None:
    with pytest.raises(RunSpecError):
        load_run_spec(_write(tmp_path, "just a string"))


def test_unknown_field_rejected(tmp_path: Path) -> None:
    with pytest.raises(RunSpecError):
        load_run_spec(_write(tmp_path, _VALID + "\nbogus_field: 1\n"))

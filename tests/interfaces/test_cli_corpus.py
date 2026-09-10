"""``cinoc corpus`` : la capacité d'acquisition, côté ligne de commande.

Ce qui est vérifié est le **transport** — que la bonne source soit choisie, que
ses options traversent, et que le corpus matérialisé ressorte en un YAML
transportable. Les importeurs eux-mêmes ont leurs tests en couche ``adapters`` :
les rejouer ici mesurerait deux fois la même chose.

Aucun test ne touche le réseau : les importeurs sont remplacés par des sondes.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest
import yaml

from cinoc.app import corpus_import
from cinoc.app.loader import load_run_spec
from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.corpus import CorpusSpec
from cinoc.domain.documents import DocumentRef, GroundTruthRef
from cinoc.interfaces._cli_parser import build_parser
from cinoc.interfaces.cli import main

_PLAN = (
    "pipelines:\n  - name: p\n    initial_inputs: [image]\n    steps: []\n"
    "evaluation:\n  views: []\n"
)


def _faux_corpus(dest: Path, *, name: str) -> CorpusSpec:
    """Un corpus de deux pages **réellement matérialisé** sous ``dest``."""
    dest.mkdir(parents=True, exist_ok=True)
    documents = []
    for index in (1, 2):
        image = dest / f"page_{index}.png"
        image.write_bytes(b"\x89PNG stub")
        texte = dest / f"page_{index}.txt"
        texte.write_text(f"page {index}", encoding="utf-8")
        documents.append(
            DocumentRef(
                id=f"page_{index}",
                image_uri=str(image),
                ground_truths=(
                    GroundTruthRef(type=ArtifactType.REFERENCE_TEXT, uri=str(texte)),
                ),
            )
        )
    return CorpusSpec(name=name, documents=tuple(documents))


@pytest.fixture
def gallica(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    """Remplace l'importeur Gallica par une sonde qui matérialise pour de vrai."""
    vus: dict[str, object] = {}

    def _sonde(ark: str, dest: object, **kwargs: object) -> CorpusSpec:
        vus["ark"] = ark
        vus.update(kwargs)
        return _faux_corpus(Path(str(dest)), name=str(kwargs.get("name") or ark))

    monkeypatch.setattr(corpus_import, "import_gallica_corpus", _sonde)
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.import_gallica_corpus", _sonde
    )
    return vus


# --------------------------------------------------------------------------- #
# Importer
# --------------------------------------------------------------------------- #


def test_an_import_writes_a_corpus_that_cinoc_run_can_read(
    tmp_path: Path, gallica: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """Le livrable n'est pas un dossier d'images : c'est un corpus **relisible**."""
    dest = tmp_path / "corpus"

    code = main(
        ["corpus", "import", "gallica", "ark:/12148/bpt6k1", "--dest", str(dest)]
    )

    assert code == 0
    ecrit = dest / "corpus.yaml"
    assert ecrit.exists()
    # Le YAML porte la clé `corpus` : il se complète en fichier de run.
    charge = yaml.safe_load(ecrit.read_text(encoding="utf-8"))
    assert set(charge) == {"corpus"}
    (dest / "run.yaml").write_text(
        ecrit.read_text(encoding="utf-8") + _PLAN, encoding="utf-8"
    )
    spec = load_run_spec(dest / "run.yaml")
    assert [d.id for d in spec.corpus.documents] == ["page_1", "page_2"]
    assert "2 document(s)" in capsys.readouterr().out


def test_the_written_corpus_survives_being_moved(
    tmp_path: Path, gallica: dict[str, object]
) -> None:
    """Chemins **relatifs** : un corpus absolu serait intransportable, alors que
    c'est justement un dossier qu'on archive et qu'on déplace."""
    dest = tmp_path / "corpus"
    main(["corpus", "import", "gallica", "ark:/12148/x", "--dest", str(dest)])
    charge = yaml.safe_load((dest / "corpus.yaml").read_text(encoding="utf-8"))
    chemins = [d["image_uri"] for d in charge["corpus"]["documents"]]
    assert chemins == ["page_1.png", "page_2.png"], chemins

    ailleurs = tmp_path / "ailleurs"
    dest.rename(ailleurs)
    (ailleurs / "run.yaml").write_text(
        (ailleurs / "corpus.yaml").read_text(encoding="utf-8") + _PLAN,
        encoding="utf-8",
    )
    spec = load_run_spec(ailleurs / "run.yaml")
    assert Path(spec.corpus.documents[0].image_uri or "").exists()


def test_source_options_reach_the_importer(
    tmp_path: Path, gallica: dict[str, object]
) -> None:
    """Chaque source a ses options ; elles doivent traverser le transport."""
    main(
        [
            "corpus",
            "import",
            "gallica",
            "ark:/12148/y",
            "--dest",
            str(tmp_path / "c"),
            "--limit",
            "3",
            "--name",
            "presse",
            "--no-ocr",
        ]
    )
    assert gallica["ark"] == "ark:/12148/y"
    assert gallica["limit"] == 3
    assert gallica["name"] == "presse"
    # `--no-ocr` existe parce que l'OCR de Gallica n'est pas une transcription
    # vérifiée : l'importer en vérité terrain change la lecture des scores.
    assert gallica["include_ocr"] is False


def test_a_zip_corpus_needs_no_network(tmp_path: Path) -> None:
    """La source locale : une archive déjà en main."""
    archive = tmp_path / "corpus.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        # Vrais octets d'en-tête : l'extracteur refuse une image non reconnue.
        zf.writestr("page_1.png", b"\x89PNG\r\n\x1a\n stub")
        zf.writestr("page_1.txt", "bonjour")

    code = main(
        ["corpus", "import", "zip", str(archive), "--dest", str(tmp_path / "c")]
    )

    assert code == 0
    assert (tmp_path / "c" / "corpus.yaml").exists()


def test_a_populated_destination_is_refused(
    tmp_path: Path, gallica: dict[str, object], capsys: pytest.CaptureFixture[str]
) -> None:
    """Deux corpus dans un même dossier se mêleraient sans le dire."""
    dest = tmp_path / "c"
    dest.mkdir()
    (dest / "deja.png").write_bytes(b"x")

    code = main(["corpus", "import", "gallica", "ark:/12148/z", "--dest", str(dest)])

    assert code == 1
    assert "n'est pas vide" in capsys.readouterr().err


def test_a_failed_import_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Atomicité : un import qui casse en route ne laisse pas un demi-corpus.

    La garantie vient de ``materialize_corpus``, partagée avec le ``CorpusStore``
    du web — elle n'est pas ré-implémentée ici, elle est **vérifiée** ici.
    """

    def _casse(ark: str, dest: object, **kwargs: object) -> CorpusSpec:
        chemin = Path(str(dest))
        chemin.mkdir(parents=True, exist_ok=True)
        (chemin / "page_1.png").write_bytes(b"x")  # déjà téléchargé…
        raise OSError("le réseau lâche à la page 2")

    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.import_gallica_corpus", _casse
    )
    dest = tmp_path / "c"

    code = main(["corpus", "import", "gallica", "ark:/12148/w", "--dest", str(dest)])

    assert code == 1
    assert not dest.exists(), "le dossier partiel doit être nettoyé"


# --------------------------------------------------------------------------- #
# Chercher & découvrir
# --------------------------------------------------------------------------- #


def test_search_lists_catalogue_entries(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue

    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.fetch_catalogue",
        lambda: HTRUnitedCatalogue.from_demo(),
    )
    code = main(["corpus", "search", ""])
    assert code == 0
    assert capsys.readouterr().out.strip()


def test_discover_without_an_account_says_how_to_name_one(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Anti-silence : sans compte résolu, on nomme les trois façons d'en donner un."""
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.resolve_curated_author", lambda: None
    )
    code = main(["corpus", "discover"])
    assert code == 1
    erreur = capsys.readouterr().err
    assert "--author" in erreur and "CINOC_HF_AUTHOR" in erreur


def test_discover_uses_the_same_resolution_as_the_web(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Même fonction que la page Bibliothèque : une capacité, deux transports."""
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.resolve_curated_author", lambda: "ma-ri"
    )
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.discover_curated", lambda author: ()
    )
    assert main(["corpus", "discover"]) == 0
    assert "ma-ri" in capsys.readouterr().out


def test_the_corpus_verbs_are_declared() -> None:
    args = build_parser().parse_args(["corpus", "search", "presse", "--language", "fr"])
    assert (args.command, args.corpus_command) == ("corpus", "search")
    assert args.language == "fr"


@pytest.mark.parametrize(
    ("argv", "cible", "attendu"),
    [
        (
            ["iiif", "https://ex.test/manifest.json", "--limit", "2"],
            "import_iiif_corpus",
            {"positionnel": "https://ex.test/manifest.json", "limit": 2},
        ),
        (
            [
                "escriptorium",
                "https://es.test",
                "42",
                "--token",
                "t",
                "--layer",
                "auto",
            ],
            "import_escriptorium_corpus",
            {"positionnel": "https://es.test", "layer": "auto"},
        ),
        (
            ["hf", "owner/jeu", "--split", "test"],
            "import_hf_corpus",
            {"positionnel": "owner/jeu", "split": "test"},
        ),
        (
            ["curated", "owner/cure", "--revision", "abc123"],
            "import_curated_hf_corpus",
            {"positionnel": "owner/cure", "revision": "abc123"},
        ),
    ],
)
def test_each_source_reaches_its_own_importer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    argv: list[str],
    cible: str,
    attendu: dict[str, object],
) -> None:
    """Chaque source appelle **le sien**, avec ses options.

    Le défaut que ce test empêche est celui qu'un `match` non exhaustif
    produirait : retomber silencieusement sur un autre importeur, et rapporter
    un corpus qui n'est pas celui qu'on a demandé.
    """
    vus: dict[str, object] = {}

    def _sonde(*args: object, **kwargs: object) -> CorpusSpec:
        # Les importeurs n'ont pas tous le même nombre de positionnels
        # (eScriptorium en prend trois avant `dest`) : on garde le premier —
        # l'identifiant de la source — et le dernier, qui est la destination.
        vus["positionnel"] = args[0]
        vus.update(kwargs)
        return _faux_corpus(Path(str(args[-1])), name="x")

    monkeypatch.setattr(f"cinoc.interfaces._corpus_command.{cible}", _sonde)
    code = main(
        ["corpus", "import", *argv, "--dest", str(tmp_path / "c")]
    )

    assert code == 0
    for cle, valeur in attendu.items():
        assert vus[cle] == valeur, f"{cle} n'a pas traversé"


def test_search_says_when_nothing_matches(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Une liste vide se dit ; une sortie muette se lirait « ça a marché »."""
    from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue

    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.fetch_catalogue",
        lambda: HTRUnitedCatalogue.from_demo(),
    )
    assert main(["corpus", "search", "zzzzz-introuvable"]) == 0
    assert "Aucune entrée" in capsys.readouterr().out


def test_search_caps_the_listing_and_says_what_is_left(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Un catalogue tronqué en silence donnerait une fausse idée de sa taille."""
    from cinoc.adapters.corpus.htr_united import HTRUnitedCatalogue

    catalogue = HTRUnitedCatalogue.from_demo()
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.fetch_catalogue", lambda: catalogue
    )
    assert main(["corpus", "search", "", "--limit", "1"]) == 0
    sortie = capsys.readouterr().out
    if len(catalogue.search("")) > 1:
        assert "autre(s)" in sortie


def test_discover_lists_the_datasets_it_finds(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cinoc.adapters.corpus.huggingface import CuratedDatasetRef

    ref = CuratedDatasetRef(
        repo_id="ma-ri/dresden",
        title="Dresden curé",
        revision="0123456789abcdef",
        last_modified="2026-08-01",
    )
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.resolve_curated_author", lambda: "ma-ri"
    )
    monkeypatch.setattr(
        "cinoc.interfaces._corpus_command.discover_curated", lambda author: (ref,)
    )
    assert main(["corpus", "discover"]) == 0
    sortie = capsys.readouterr().out
    assert "ma-ri/dresden" in sortie
    # La révision épinglée est **affichée** : c'est elle qui rend un run rejouable.
    assert "@0123456789ab" in sortie

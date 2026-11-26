"""``--repeat`` et ``--resume-dir`` ensemble : une archive par répétition.

Les deux options s'excluaient — « rejouer un cache mesurerait le cache ». Mais
une campagne publiée (P5h) doit **et** répéter un moteur stochastique cinq fois
**et** archiver chaque sortie pour qu'un tiers la re-note : sans archive, les
répétitions ne se re-notent pas. Chaque répétition a donc son dossier neuf
(``<archive>/repetition-<k>``) : aucune ne relit une autre, et la même commande
en ``--offline`` re-note les cinq.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cinoc.interfaces.cli import main

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


def _config(tmp_path: Path) -> str:
    shutil.copytree(EXAMPLES, tmp_path / "examples")
    for gt in (tmp_path / "examples" / "corpus").glob("*.gt.txt"):
        stem = gt.name.removesuffix(".gt.txt")
        (gt.parent / f"{stem}.png").write_bytes(b"png:" + stem.encode())
    return str(tmp_path / "examples" / "config.yaml")


def test_each_repetition_is_archived_in_its_own_folder(tmp_path: Path) -> None:
    config = _config(tmp_path)
    archive = tmp_path / "archive"
    report = tmp_path / "r.html"
    base = ["run", config, "--resume-dir", str(archive), "-o", str(report)]

    assert main([*base, "--repeat", "2"]) == 0

    folders = sorted(p.name for p in archive.iterdir())
    assert folders == ["repetition-1", "repetition-2"]
    for folder in folders:
        assert list((archive / folder).glob("*/index.json"))
    first = json.loads(Path(f"{report}.variance.json").read_text(encoding="utf-8"))

    assert main([*base, "--repeat", "2", "--offline"]) == 0

    again = json.loads(Path(f"{report}.variance.json").read_text(encoding="utf-8"))
    assert again == first


def test_an_offline_repeat_needs_every_repetition(tmp_path: Path) -> None:
    config = _config(tmp_path)
    archive = tmp_path / "archive"
    base = ["run", config, "--resume-dir", str(archive), "-o", str(tmp_path / "r.html")]
    assert main([*base, "--repeat", "2"]) == 0
    shutil.rmtree(archive / "repetition-2")

    assert main([*base, "--repeat", "2", "--offline"]) == 1

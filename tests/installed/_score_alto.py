"""Noter un ALTO d'un autre outil : le corpus et la spec **du guide** (D-307).

Sans aucun import de ``cinoc`` : le parcours du paquet installé s'en sert, et la
suite de l'arbre de sources aussi (``tests/interfaces/test_guide_score_alto.py``).
La spec est **lue dans le guide**, jamais recopiée : un bloc qui change ou
disparaît fait échouer les deux.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRST_CORPUS = ROOT / "tests" / "fixtures" / "first_corpus"
_NS = "http://www.loc.gov/standards/alto/ns-v4#"


def guide_spec() -> str:
    """Le bloc YAML que le guide marque ``<!-- spec: score-alto -->``."""
    guide = (ROOT / "docs" / "guide.md").read_text(encoding="utf-8")
    found = re.search(r"<!-- spec: score-alto -->\n```yaml\n(.*?)```", guide, re.S)
    assert found, "le guide ne donne plus la spec « noter un ALTO »"
    return found.group(1)


def alto_of(text: str) -> str:
    """Un ALTO d'« un autre outil » dont les lignes sont ``text``."""
    lignes = "".join(
        f'<TextLine ID="L{i}"><String CONTENT="{ligne}"/></TextLine>'
        for i, ligne in enumerate(text.strip().splitlines(), start=1)
    )
    return (
        f'<alto xmlns="{_NS}"><Layout><Page ID="P1" WIDTH="760" HEIGHT="170">'
        f'<PrintSpace><TextBlock ID="B1">{lignes}</TextBlock></PrintSpace>'
        "</Page></Layout></alto>"
    )


def pages_zip(dest: Path, *, transcriptions: bool) -> Path:
    """Images + ALTO (+ transcriptions) à plat, comme on les dépose."""
    archive = dest / "pages.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        for gt in sorted(FIRST_CORPUS.glob("*.gt.txt")):
            page = gt.name.removesuffix(".gt.txt")
            zf.write(FIRST_CORPUS / f"{page}.png", f"{page}.png")
            zf.writestr(f"{page}.xml", alto_of(gt.read_text(encoding="utf-8")))
            if transcriptions:
                zf.write(gt, gt.name)
    return archive

"""Catalogue des rapports servis par la vitrine (couche 8).

Un rapport = un ``RunResult`` **sauvé** (JSON, via ``run --json``) déposé dans un
dossier. La vitrine les **liste** et les **rend en HTML à la demande** : le rendu
est déterministe (§12), donc recalculable sans état serveur, et le format unique
``RunResult`` reste la source de vérité (pas de HTML pré-figé).

Tout accès passe par ``validated_path`` (couche 6) : un identifiant ne peut pas
sortir du dossier (défense path-traversal, invariant §12).
"""

from __future__ import annotations

import filecmp
import hashlib
import shutil
from pathlib import Path

from cinoc.app.security import validated_path


def available_reports(reports_dir: Path) -> list[str]:
    """Identifiants (stems ``.json``) des rapports disponibles, **triés**.

    Dossier absent → ``[]`` (le Space peut démarrer avant qu'un rapport existe).
    """
    if not reports_dir.is_dir():
        return []
    return sorted(path.stem for path in reports_dir.glob("*.json"))


def resolve_report(reports_dir: Path, name: str) -> Path:
    """Chemin sûr de ``<name>.json``, **confiné** à ``reports_dir``.

    Lève ``PathSecurityError`` si ``name`` tente de sortir du dossier **ou**
    n'existe pas (``must_exist``) — le routeur traduit les deux en 404, sans
    distinguer (pas de fuite d'information).
    """
    return validated_path(f"{name}.json", reports_dir, must_exist=True)


#: Graines recopiées au dernier démarrage (``nom\tempreinte`` par ligne), dans
#: le dossier de données. Pas en ``.json`` : le catalogue le listerait.
SEEDS_FILE = ".graines"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_reports(src: Path, dst: Path) -> None:
    """Copie les rapports *bakés* ou déposés (``src``) dans le dossier de données.

    Permet à la vitrine de servir, depuis un **seul** dossier inscriptible, à la
    fois les rapports livrés dans l'image (graine) et ceux produits au runtime.
    Un rapport présent qui n'est pas une graine n'est jamais réécrit (un run
    produit prime sur la graine homonyme) ; ``src`` absent → no-op.

    **Le dossier de données dure** (D-307) : les graines du lancement précédent
    — notées dans :data:`SEEDS_FILE`, et encore intactes — sont retirées avant
    de recopier celles d'aujourd'hui. Sans quoi un rapport relancé (``cinoc run
    --json``) restait servi dans son ancienne version, et un rapport retiré du
    dépôt, ou d'un autre ``--reports-dir``, restait listé.
    """
    if src == dst:
        return
    notes = dst / SEEDS_FILE
    if notes.is_file():
        for ligne in notes.read_text(encoding="utf-8").splitlines():
            nom, _, empreinte = ligne.partition("\t")
            ancienne = dst / Path(nom).name
            if ancienne.is_file() and _digest(ancienne) == empreinte:
                ancienne.unlink()
        notes.unlink()
    if not src.is_dir():
        return
    dst.mkdir(parents=True, exist_ok=True)
    semees: list[str] = []
    for path in sorted(src.glob("*.json")):
        target = dst / path.name
        if not target.exists():
            shutil.copy2(path, target)
            semees.append(f"{path.name}\t{_digest(target)}")
    if semees:
        notes.write_text("\n".join(semees) + "\n", encoding="utf-8")


def report_image_root(
    served: Path, *, deposit_dir: Path, uploads_dir: Path
) -> Path:
    """Racine contre laquelle se relisent les images du rapport ``served``.

    Un ``RunResult`` écrit ses références d'image relatives à la racine du run
    qui l'a produit (D-282) : le dossier de la spec pour ``cinoc run``, le
    dossier des corpus déposés pour un run lancé depuis la page. Un rapport
    **déposé** (``cinoc serve --reports-dir``, rapports bakés d'un Space) est
    donc relu contre **son dossier de dépôt** : c'est là que ``cinoc run
    --json`` l'a écrit, à côté de sa spec. Il est reconnu à ce qu'il est encore
    la graine : présent dans ``deposit_dir`` et identique, octet pour octet, à
    la copie servie. Tout autre rapport — un run du serveur, ou un homonyme
    qu'un run a réécrit — se relit contre ``uploads_dir``.

    Quand dépôt et données sont un **même** dossier, rien ne distingue une
    graine d'un run du serveur : la règle d'avant (``uploads_dir``) vaut.
    """
    deposited = deposit_dir / served.name
    if (
        deposit_dir.resolve() != served.parent.resolve()
        and deposited.is_file()
        and filecmp.cmp(deposited, served, shallow=False)
    ):
        return deposit_dir
    return uploads_dir


__all__ = [
    "available_reports",
    "report_image_root",
    "resolve_report",
    "seed_reports",
]

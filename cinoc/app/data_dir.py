"""Résolution du dossier de **données inscriptible** (couche 6).

Distinct du dossier des rapports *bakés* (livrés dans l'image d'un Space, donc
appartenant à root et **non inscriptibles** par l'utilisateur non-root qui sert
l'app). L'historique longitudinal, les rapports de run, les corpus déposés et
les exports ALTO y vivent — **jamais** dans le dossier baké, sous peine
d'``OperationalError`` / d'échec d'écriture (cause des *Internal Server Error*
sur Hugging Face).

Ordre de résolution : argument explicite › ``CINOC_DATA_DIR`` › ``/data``
(montage de stockage persistant Hugging Face, s'il est inscriptible) › dossier
**par utilisateur** de la plate-forme (hors mode public) › dossier temporaire
neuf. Le dernier recours est **toujours inscriptible** : on ne démarre jamais
sur un emplacement qui fera planter la première écriture.

**Pourquoi un dossier par utilisateur (D-307).** Le défaut était un dossier
temporaire neuf à chaque lancement : un corpus déposé et un run lancé depuis la
page disparaissaient au redémarrage de ``cinoc serve``, sans qu'aucun message
ne l'ait dit. Le mode public garde l'éphémère : un serveur exposé ne garde pas
sur son disque ce que des visiteurs y ont déposé.
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

#: Surcharge explicite de l'emplacement de données.
DATA_DIR_ENV = "CINOC_DATA_DIR"

#: Montage du stockage persistant d'un Space HF (présent si l'option est activée).
_PERSISTENT_MOUNT = Path("/data")


@dataclass(frozen=True)
class DataDir:
    """Le dossier retenu, et s'il survit au processus (``ephemeral``)."""

    path: Path
    ephemeral: bool


def _is_writable_dir(path: Path) -> bool:
    return path.is_dir() and os.access(path, os.W_OK)


def user_data_dir() -> Path:
    """Dossier de données **par utilisateur**, à la convention de la plate-forme.

    ``%LOCALAPPDATA%\\cinoc`` sous Windows, ``~/Library/Application
    Support/cinoc`` sous macOS, ``$XDG_DATA_HOME/cinoc`` ailleurs (repli
    ``~/.local/share/cinoc`` ; un ``XDG_DATA_HOME`` relatif est ignoré, comme le
    veut la spécification XDG). Ne crée rien.
    """
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA")
        root = Path(local) if local else Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        xdg = os.environ.get("XDG_DATA_HOME", "")
        root = Path(xdg) if xdg and Path(xdg).is_absolute() else (
            Path.home() / ".local" / "share"
        )
    return root / "cinoc"


def _user_dir_if_writable() -> Path | None:
    """Le dossier par utilisateur, créé ; ``None`` s'il ne peut pas l'être."""
    chosen = user_data_dir()
    try:
        chosen.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.warning("[data_dir] dégradé : %s non créable (%s)", chosen, exc)
        return None
    if not _is_writable_dir(chosen):
        logger.warning("[data_dir] dégradé : %s non inscriptible", chosen)
        return None
    return chosen


def resolve_data_dir(
    data_dir: Path | str | None = None, *, public: bool = False
) -> DataDir:
    """Renvoie un dossier de données **inscriptible**, créé au besoin.

    Argument explicite > ``CINOC_DATA_DIR`` > ``/data`` (si inscriptible) >
    dossier par utilisateur (``public`` faux) > dossier temporaire. Un choix
    explicite est réputé durable : c'est l'opérateur qui l'a nommé.
    """
    if data_dir is not None:
        chosen, ephemeral = Path(data_dir), False
    elif env := os.environ.get(DATA_DIR_ENV):
        chosen, ephemeral = Path(env), False
    elif _is_writable_dir(_PERSISTENT_MOUNT):
        chosen, ephemeral = _PERSISTENT_MOUNT / "cinoc", False
    elif not public and (user := _user_dir_if_writable()) is not None:
        chosen, ephemeral = user, False
    else:
        chosen, ephemeral = Path(tempfile.mkdtemp(prefix="cinoc-data-")), True
    chosen.mkdir(parents=True, exist_ok=True)
    return DataDir(path=chosen, ephemeral=ephemeral)


__all__ = ["DATA_DIR_ENV", "DataDir", "resolve_data_dir", "user_data_dir"]

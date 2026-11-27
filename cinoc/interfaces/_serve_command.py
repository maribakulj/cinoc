"""Commande ``cinoc serve`` : la vitrine web, servie en local (couche 8).

Extraite de ``cli.py`` (budget de taille). Transport mince : elle charge les
clés locales, résout **une fois** le dossier de données et le **dit** — un
testeur a perdu corpus et rapport au redémarrage sans qu'aucun message ne lui
ait dit où ils vivaient (D-307) —, puis passe la factory à uvicorn.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cinoc.app.data_dir import DATA_DIR_ENV, DataDir, resolve_data_dir


def load_dotenv(path: Path = Path(".env")) -> list[str]:
    """Charge un fichier ``.env`` (``CLE=valeur`` par ligne) dans l'environnement.

    Sans dépendance. **Ne remplace jamais** une variable déjà définie : l'env réel
    prime (un secret HuggingFace l'emporte sur le ``.env`` local). ``#`` et lignes
    vides ignorés. Renvoie les **noms** chargés (jamais les valeurs) pour une trace
    lisible. C'est le moyen d'entrer ses clés en local (``MISTRAL_API_KEY=…``).
    """
    if not path.is_file():
        return []
    loaded: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")
            loaded.append(key)
    return loaded


def data_dir_line(data: DataDir) -> str:
    """Où vivent corpus déposés, rapports de run et historique — et s'ils
    survivent au serveur."""
    if data.ephemeral:
        return (
            f"Données : {data.path} — temporaire (mode public) : effacé avec le "
            f"processus ; {DATA_DIR_ENV}=<dossier> pour un dossier durable."
        )
    return (
        f"Données : {data.path} (corpus déposés, rapports, historique ; "
        f"{DATA_DIR_ENV}=<dossier> pour en changer)."
    )


def serve_command(host: str, port: int, reports_dir: str | None) -> int:
    # Clés locales depuis ``.env`` (avant tout : la disponibilité des moteurs est
    # capturée au démarrage). Sur HuggingFace, les secrets du Space priment.
    loaded = load_dotenv()
    if loaded:
        print(f"Clés chargées depuis .env : {', '.join(loaded)}")
    # uvicorn = extra [serve], importé paresseusement : la CLI reste utilisable
    # (demo/run/compare) sans la pile web installée.
    try:
        import uvicorn  # type: ignore[import-not-found]

        from cinoc.interfaces.web.app import REPORTS_DIR_ENV, resolve_public_mode
    except ImportError:
        print(
            "Erreur : serveur non installé (pip install 'cinoc[serve]').",
            file=sys.stderr,
        )
        return 1
    if host not in ("127.0.0.1", "localhost"):
        # 0.0.0.0 expose le service au réseau : sécurité = responsabilité du
        # déploiement (reverse-proxy, mode public). On le signale, sans bloquer.
        print(
            f"Attention : écoute sur {host} (exposé au réseau). "
            "En public, placez un reverse-proxy et activez le mode public.",
            file=sys.stderr,
        )
    if reports_dir is not None:
        os.environ[REPORTS_DIR_ENV] = reports_dir
    # Résolu ici, une fois, et transmis à la factory par la même variable que
    # l'opérateur poserait : le dossier annoncé est celui que le serveur prend
    # (un temporaire n'est pas recréé, différent, par la factory).
    data = resolve_data_dir(public=resolve_public_mode(None))
    os.environ[DATA_DIR_ENV] = str(data.path)
    print(data_dir_line(data))
    print(f"Cinoc sert sur http://{host}:{port} (Ctrl-C pour arrêter).")
    # On passe la FACTORY à uvicorn (factory=True), jamais un app de module :
    # zéro effet de bord à l'import (gate no_side_effect_imports).
    uvicorn.run(
        "cinoc.interfaces.web.app:create_app",
        host=host,
        port=port,
        factory=True,
    )
    return 0


__all__ = ["data_dir_line", "load_dotenv", "serve_command"]

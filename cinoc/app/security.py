"""Sécurité des entrées utilisateur (couche 6) — invariant produit §12.

``validated_path`` est le **garde-fou central** contre la traversée de
répertoires : tout chemin venant d'une entrée utilisateur (corpus, sortie) passe
par lui. La couche 8 (web) réutilisera ce **même** helper — la sécurité chemin
n'est pas un détail web.

``check_ollama_host`` est son pendant réseau pour l'hôte d'un serveur ollama
reçu par HTTP : une liste blanche **de l'opérateur**, et non une adresse au
choix du client.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from cinoc.domain.errors import CinocError


class PathSecurityError(CinocError):
    """Un chemin utilisateur sort de la zone autorisée (path traversal)."""


def safe_stem(value: str, *, suffix: str = "", fallback: str = "x") -> str:
    """Composant de chemin **sûr** dérivé d'une chaîne (anti path-traversal).

    Slug lisible (caractères sûrs sur tous les OS : ``A-Za-z0-9._-``) + empreinte
    SHA-256 courte de la valeur **brute** → jamais de collision même si deux
    valeurs se réduisent au même slug. ``suffix`` distingue des variantes (vignette
    vs fac-similé) ; ``fallback`` remplace un slug vide (valeur tout-symboles).

    Source unique du « nom de fichier sûr » (invariant produit §12) — réutilisée
    par ``alto_store`` et ``report_images``.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-") or fallback
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned}-{digest}{suffix}"


def validated_path(user_path: str, base: Path, *, must_exist: bool = False) -> Path:
    """Résout ``user_path`` (sous ``base``) et garantit qu'il y reste confiné.

    ``Path.resolve()`` écrase ``..``, les liens symboliques et le relatif ; on
    vérifie ensuite que le résultat est bien sous ``base``. Un chemin absolu
    n'est accepté que s'il tombe lui-même sous ``base``.
    """
    if not user_path or not user_path.strip():
        raise PathSecurityError("chemin vide.")
    if "\x00" in user_path:
        raise PathSecurityError("chemin contient un octet nul.")
    base_resolved = base.expanduser().resolve()
    candidate = Path(user_path)
    # ``target`` est toujours absolu (candidat absolu, sinon préfixé par ``base``
    # déjà résolu) → pas de ``~`` en tête : aucun ``expanduser`` à refaire ici.
    target = candidate if candidate.is_absolute() else base_resolved / candidate
    try:
        resolved = target.resolve()
    except (OSError, RuntimeError) as exc:
        raise PathSecurityError(
            f"chemin invalide : {user_path!r} ({exc})."
        ) from exc
    if not resolved.is_relative_to(base_resolved):
        raise PathSecurityError(
            f"chemin hors de la zone autorisée : {user_path!r}."
        )
    if must_exist and not resolved.exists():
        raise PathSecurityError(f"chemin inexistant : {user_path!r}.")
    return resolved


#: Hôtes ollama autorisés, séparés par des virgules (noms d'hôte ou IP, sans
#: schéma ni port). **Remplace** le défaut quand elle est posée : vide, elle
#: n'autorise plus rien.
OLLAMA_HOSTS_ENV = "CINOC_OLLAMA_HOSTS"

#: Défaut : la machine elle-même, et elle seule — c'est là qu'un serveur ollama
#: écoute quand personne n'a rien configuré.
_DEFAULT_OLLAMA_HOSTS = ("localhost", "127.0.0.1")


class HostNotAllowedError(CinocError):
    """Un hôte reçu d'un client n'est pas dans la liste blanche de l'opérateur."""


def _allowed_ollama_hosts(get_env: Callable[[str], str | None]) -> frozenset[str]:
    """Les hôtes ollama que l'opérateur autorise (``CINOC_OLLAMA_HOSTS``)."""
    raw = get_env(OLLAMA_HOSTS_ENV)
    if raw is None:
        return frozenset(_DEFAULT_OLLAMA_HOSTS)
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def check_ollama_host(
    host: str, *, get_env: Callable[[str], str | None] = os.environ.get
) -> None:
    """Lève si ``host`` ne désigne pas un serveur que l'opérateur autorise.

    Un ``host`` reçu dans un corps HTTP partait tel quel au correcteur, qui y
    postait ses requêtes : sur une instance privée, le serveur devenait un
    relais vers l'adresse du choix du client — service de métadonnées d'un
    nuage, machine du réseau interne (SSRF). La comparaison porte sur le **nom
    d'hôte exact** : ``localhost.evil.example`` n'est pas ``localhost``. Le port
    reste libre, comme l'est déjà celui du défaut.

    Les transports qui reçoivent une adresse d'un tiers l'appellent ; la ligne
    de commande non — celui qui la lance **est** l'opérateur.
    """
    allowed = _allowed_ollama_hosts(get_env)
    parts = urlsplit(host.strip())
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not hostname:
        raise HostNotAllowedError(
            f"hôte ollama illisible : {host!r} (attendu http(s)://hôte[:port])."
        )
    if parts.username is not None or parts.password is not None:
        raise HostNotAllowedError(
            f"hôte ollama refusé : {host!r} porte des identifiants."
        )
    if hostname not in allowed:
        raise HostNotAllowedError(
            f"hôte ollama refusé : {hostname!r} n'est pas dans la liste blanche "
            f"de l'opérateur ({OLLAMA_HOSTS_ENV} = "
            f"{', '.join(sorted(allowed)) or 'vide'})."
        )


__all__ = [
    "OLLAMA_HOSTS_ENV",
    "HostNotAllowedError",
    "PathSecurityError",
    "check_ollama_host",
    "safe_stem",
    "validated_path",
]

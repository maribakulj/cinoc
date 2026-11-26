"""Sécurité des entrées utilisateur (couche 6) — invariant produit §12.

``validated_path`` est le **garde-fou central** contre la traversée de
répertoires : tout chemin venant d'une entrée utilisateur (corpus, sortie) passe
par lui. La couche 8 (web) réutilisera ce **même** helper — la sécurité chemin
n'est pas un détail web.

``check_model_host`` est son pendant réseau pour l'hôte d'un **serveur de
modèles** reçu par HTTP — ``host`` d'ollama, ``base_url`` d'une instance
OpenAI-compatible (vLLM, SGLang) : une liste blanche **de l'opérateur**, et non
une adresse au choix du client. Une seule liste pour toutes les cibles.
"""

from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Callable, Mapping
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


#: Hôtes de serveurs de modèles autorisés (ollama, OpenAI-compatibles), séparés
#: par des virgules (noms d'hôte ou IP, sans schéma ni port). **Remplace** le
#: défaut quand elle est posée : vide, elle n'autorise plus rien.
MODEL_HOSTS_ENV = "CINOC_MODEL_HOSTS"

#: Défaut : la machine elle-même, et elle seule — c'est là qu'un serveur local
#: (ollama, vLLM) écoute quand personne n'a rien configuré.
_DEFAULT_MODEL_HOSTS = ("localhost", "127.0.0.1")


class HostNotAllowedError(CinocError):
    """Un hôte reçu d'un client n'est pas dans la liste blanche de l'opérateur."""


def _allowed_model_hosts(get_env: Callable[[str], str | None]) -> frozenset[str]:
    """Les hôtes que l'opérateur autorise (``CINOC_MODEL_HOSTS``)."""
    raw = get_env(MODEL_HOSTS_ENV)
    if raw is None:
        return frozenset(_DEFAULT_MODEL_HOSTS)
    return frozenset(h.strip().lower() for h in raw.split(",") if h.strip())


def check_model_host(
    host: str, *, get_env: Callable[[str], str | None] = os.environ.get
) -> None:
    """Lève si ``host`` ne désigne pas un serveur que l'opérateur autorise.

    Un ``host`` reçu dans un corps HTTP partait tel quel au correcteur, qui y
    postait ses requêtes : sur une instance privée, le serveur devenait un
    relais vers l'adresse du choix du client — service de métadonnées d'un
    nuage, machine du réseau interne (SSRF). Un ``base_url`` d'instance
    OpenAI-compatible est la même porte sous un autre nom (D-293). La
    comparaison porte sur le **nom d'hôte exact** : ``localhost.evil.example``
    n'est pas ``localhost``. Le port reste libre, comme l'est déjà celui du
    défaut.

    Ce n'est pas le filtre d'adresses publiques des imports de corpus
    (``adapters/corpus/_http``) : un serveur de modèles auto-hébergé est
    précisément une adresse privée (boucle locale, réseau du labo). Le contrôle
    est le nom que l'opérateur a écrit ; la résolution de ce nom est la sienne.

    Les transports qui reçoivent une adresse d'un tiers l'appellent ; la ligne
    de commande non — celui qui la lance **est** l'opérateur.
    """
    allowed = _allowed_model_hosts(get_env)
    parts = urlsplit(host.strip())
    hostname = (parts.hostname or "").lower()
    if parts.scheme not in {"http", "https"} or not hostname:
        raise HostNotAllowedError(
            "hôte de serveur de modèles illisible (attendu http(s)://hôte[:port])."
        )
    if parts.username is not None or parts.password is not None:
        raise HostNotAllowedError(
            "hôte de serveur de modèles refusé : l'URL porte des identifiants."
        )
    if hostname not in allowed:
        raise HostNotAllowedError(
            f"hôte de serveur de modèles refusé : {hostname!r} n'est pas dans la "
            f"liste blanche de l'opérateur ({MODEL_HOSTS_ENV} = "
            f"{', '.join(sorted(allowed)) or 'vide'})."
        )


#: Réglages d'``adapter_kwargs`` qui désignent une **cible réseau** ou sa clé.
ENDPOINT_KWARGS = ("api_key_env", "base_url", "host")


def check_endpoint_settings(
    settings: Mapping[str, object],
    *,
    public_mode: bool,
    get_env: Callable[[str], str | None] = os.environ.get,
) -> None:
    """Les gardes d'un transport HTTP sur les réglages de cible d'un module.

    - **mode public** (Space) : *fail-closed* — aucune cible réglable, même
      l'hôte par défaut de la liste ; aucun serveur de modèles n'y est joignable ;
    - ``api_key_env`` : refusé. Nommer une variable du serveur la ferait envoyer
      à l'hôte de la spec — une autre clé, un jeton —, et le message d'erreur
      d'une API (401) en rend un fragment au client. C'est un réglage
      d'opérateur, que la ligne de commande garde ;
    - ``host`` et ``base_url`` : confrontés à la liste blanche (``check_model_host``).
    """
    targets = [k for k in ENDPOINT_KWARGS if k in settings]
    if public_mode and targets:
        raise HostNotAllowedError(
            f"réglage refusé en mode public : {', '.join(targets)} (aucun "
            "serveur de modèles n'est joignable d'une instance publique)."
        )
    if "api_key_env" in settings:
        raise HostNotAllowedError(
            "réglage refusé par HTTP : api_key_env (il ferait envoyer une "
            "variable du serveur à l'hôte de la spec) — réglage d'opérateur, par "
            "la ligne de commande."
        )
    for key in ("host", "base_url"):
        value = settings.get(key)
        if isinstance(value, str):
            check_model_host(value, get_env=get_env)


__all__ = [
    "ENDPOINT_KWARGS",
    "MODEL_HOSTS_ENV",
    "HostNotAllowedError",
    "PathSecurityError",
    "check_endpoint_settings",
    "check_model_host",
    "safe_stem",
    "validated_path",
]

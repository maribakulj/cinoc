"""Transport HTTP **durci anti-SSRF** pour les importeurs de corpus (couche 5).

Un importeur va chercher des ressources à une URL **fournie par l'utilisateur** :
le risque est qu'on serve de proxy vers le réseau interne (SSRF) ou qu'on télécharge
sans borne (DoS mémoire/disque). Défenses, toutes testées :

- **schéma** ``http``/``https`` seuls (pas de ``file://``, ``gopher://``…) ;
- **pas de userinfo** dans l'URL ;
- **résolution DNS validée** : *toutes* les IP résolues doivent être **publiques**
  (rejet loopback / privé / link-local / réservé / multicast / non-spécifié) ;
  une IP **littérale** n'est pas résolue du tout, et une adresse qui **encapsule**
  une IPv4 (IPv4-mapped, NAT64 bien connu) est jugée sur cette IPv4 ;
- **redirections re-validées** à chaque saut (une 30x ne peut pas pointer vers
  l'interne) ; nombre de sauts borné ;
- **taille plafonnée** au fil de l'eau (on ne fait pas confiance à
  ``Content-Length``).

**DNS-rebinding fermé — épinglage d'IP.** ``assert_public_url`` résout l'hôte
**une seule fois**, valide **toutes** les IP, et **retourne** ces IP. La
connexion vise alors directement l'IP **épinglée** (transport ``httpx`` à
``network_backend`` custom, cf. :class:`_PinnedBackend`) : il n'y a **pas de
seconde résolution** que pourrait détourner un DNS hostile. Le nom d'hôte de
l'URL reste inchangé, donc le ``Host`` envoyé, le **SNI** et la vérification du
certificat TLS portent toujours sur le vrai hôte (aucun override fragile) —
seule la cible TCP est figée. L'épinglage est ré-appliqué **à chaque saut** de
redirection. Le **gate « mode public » (403)** côté interface reste la première
barrière (les imports distants y sont refusés) ; l'épinglage est la défense en
profondeur, désormais étanche.

Auth & redirections : les en-têtes (jeton) ne suivent **pas** un changement
d'hôte (cf. ``_stream_validated``). Une seule pile HTTP (``httpx`` + son moteur
``httpcore``) ; **aucun état global** (pas d'``install_opener``).
"""

from __future__ import annotations

import contextlib
import ipaddress
import json
import os
import socket
import typing
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpcore
import httpx

from cinoc.domain.errors import CinocError

#: Plafonds (généreux mais bornés — un Space gratuit n'est pas un entrepôt).
MANIFEST_MAX_BYTES = 16 * 1024 * 1024
IMAGE_MAX_BYTES = 50 * 1024 * 1024
DEFAULT_TIMEOUT = 30.0
_MAX_REDIRECTS = 5
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class CorpusHttpError(CinocError):
    """Échec de transport d'un importeur de corpus."""


class SsrfError(CorpusHttpError):
    """L'URL cible une ressource interdite (schéma, userinfo ou IP non publique)."""


class HttpFetchError(CorpusHttpError):
    """La requête a échoué (statut, redirection cassée, dépassement de taille)."""


#: Préfixe NAT64 « bien connu » (RFC 6052 §2.1) : les **32 derniers bits**
#: portent l'IPv4 traduite. Sur un réseau IPv6-seul (DNS64 — macOS et beaucoup
#: de réseaux mobiles), *toute* résolution d'un hôte IPv4 passe par là. Juger
#: l'enveloppe IPv6 au lieu de l'IPv4 embarquée revient à refuser Gallica, IIIF
#: et HuggingFace : ``64:ff9b::`` commence par un octet nul, donc tombe dans
#: ``::/8``, que ``ipaddress`` classe **réservé**.
_NAT64_WELL_KNOWN = ipaddress.IPv6Network("64:ff9b::/96")


def _embedded_ipv4(
    ip: ipaddress.IPv4Address | ipaddress.IPv6Address,
) -> ipaddress.IPv4Address | None:
    """L'IPv4 réellement visée par ``ip``, ou ``None`` si elle n'en encapsule pas.

    Deux encapsulations existent : ``::ffff:a.b.c.d`` (IPv4-mapped) et le NAT64
    bien connu. Un préfixe NAT64 **propre au site** (RFC 6052 §2.2) est
    indétectable et reste jugé comme l'IPv6 globale qu'il est.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        return typing.cast(ipaddress.IPv4Address, mapped)
    if isinstance(ip, ipaddress.IPv6Address) and ip in _NAT64_WELL_KNOWN:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def _is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """``ip`` vise-t-elle une ressource publique ?

    Une adresse qui **encapsule** une IPv4 est jugée sur cette IPv4 : le filtre
    ne se laisse donc pas contourner par l'enveloppe (``64:ff9b::7f00:1`` est
    du loopback, et refusé) ni ne refuse à tort une cible publique traduite.
    """
    embedded = _embedded_ipv4(ip)
    if embedded is not None:
        ip = embedded
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def assert_public_url(url: str) -> tuple[str, ...]:
    """Valide ``url`` et **retourne les IP publiques** vers lesquelles épingler.

    Résout l'hôte **une seule fois** et exige que **toutes** les IP retournées
    soient publiques : un nom qui résout (même partiellement) vers l'interne est
    rejeté (``SsrfError``). Les IP validées sont retournées pour que l'appelant
    **épingle** la connexion dessus (anti-DNS-rebinding) — pas de seconde
    résolution. Pour une IP littérale, retourne cette IP (aucun DNS réel).
    """
    parts = urlsplit(url)
    if parts.scheme not in _ALLOWED_SCHEMES:
        raise SsrfError(f"schéma non autorisé : {parts.scheme!r} (http/https seuls).")
    if parts.username or parts.password:
        raise SsrfError("userinfo interdit dans l'URL.")
    host = parts.hostname
    if not host:
        raise SsrfError("URL sans hôte.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None  # type: ignore[assignment]
    if literal is not None:
        # Promesse tenue : une IP littérale ne passe **pas** par le résolveur.
        # Y passer laissait un DNS64 substituer une adresse NAT64 à l'IP écrite
        # noir sur blanc dans l'URL — et la rejeter.
        if not _is_public(literal):
            raise SsrfError(f"IP non publique : {host}.")
        return (host,)
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise SsrfError(f"résolution DNS impossible pour {host!r} : {exc}.") from exc
    pins: list[str] = []
    for info in infos:
        addr = str(info[4][0])  # sockaddr[0] = adresse textuelle (IPv4/IPv6)
        if not _is_public(ipaddress.ip_address(addr)):
            raise SsrfError(
                f"hôte {host!r} résout vers une IP non publique ({addr})."
            )
        if addr not in pins:
            pins.append(addr)
    return tuple(pins)


class _PinnedBackend(httpcore.SyncBackend):
    """Épingle la cible TCP sur des IP **pré-validées** (anti-DNS-rebinding).

    ``httpcore`` appelle ``connect_tcp(host, port)`` avec le **nom d'hôte** de
    l'origine ; on substitue les IP déjà résolues+validées, sans repasser par le
    DNS. Le nom d'hôte de l'URL restant inchangé, le SNI et la vérification du
    certificat TLS (pilotés par ``httpcore`` depuis l'origin) portent toujours
    sur le **vrai hôte** — donc aucun override fragile. On essaie les IP dans
    l'ordre (comme ``socket.create_connection`` le ferait), préservant le
    repli multi-adresses.
    """

    def __init__(self, ips: tuple[str, ...]) -> None:
        super().__init__()
        self._ips = ips

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: typing.Any = None,
    ) -> httpcore.NetworkStream:
        last_exc: httpcore.ConnectError | None = None
        for ip in self._ips:
            try:
                return super().connect_tcp(
                    ip,
                    port,
                    timeout=timeout,
                    local_address=local_address,
                    socket_options=socket_options,
                )
            except httpcore.ConnectError as exc:
                last_exc = exc
        assert last_exc is not None  # _ips est non vide (cf. _make_client)
        raise last_exc


def _pinned_transport(ips: tuple[str, ...]) -> httpx.HTTPTransport:
    """Transport ``httpx`` dont le backend réseau épingle ``ips``.

    ``httpx`` n'expose pas ``network_backend`` ; on le pose sur le pool interne
    (seul point d'injection). Le ``isinstance`` fait échouer **bruyamment** si
    une future version de ``httpx`` change la forme du pool, plutôt que de
    contourner silencieusement l'épinglage.
    """
    transport = httpx.HTTPTransport()
    pool = transport._pool
    if not isinstance(pool, httpcore.ConnectionPool):  # pragma: no cover
        transport.close()
        raise CorpusHttpError("épinglage IP indisponible : transport httpx inattendu.")
    pool._network_backend = _PinnedBackend(ips)
    return transport


def _make_client(pins: tuple[str, ...] | None, timeout: float) -> httpx.Client:
    """Client mono-saut. ``pins`` vide/None → résolution httpx normale.

    Le cas ``None`` n'arrive qu'en test (``assert_public_url`` neutralisé en
    no-op pour viser le loopback) ; en production il est toujours non vide.
    """
    if not pins:
        return httpx.Client(timeout=timeout, follow_redirects=False)
    return httpx.Client(
        transport=_pinned_transport(pins), timeout=timeout, follow_redirects=False
    )


@contextlib.contextmanager
def _stream_validated(
    url: str, *, timeout: float, headers: dict[str, str] | None = None
) -> Iterator[httpx.Response]:
    """GET en streaming, **épinglé à l'IP validée** et re-validé à chaque saut.

    Chaque saut (origine + redirections, bornées) : résout+valide une fois via
    ``assert_public_url``, épingle la connexion sur l'IP retournée, puis envoie.
    Les en-têtes fournis (ex. ``Authorization: Token …``) ne sont **jamais**
    propagés vers un **hôte différent** de l'origine (fuite de credentials sur
    redirection). Un client ``httpx`` distinct est créé par saut (épinglage
    propre à l'IP du saut) ; tous sont fermés à la sortie du contexte.
    """
    origin_host = urlsplit(url).hostname
    current = url
    with contextlib.ExitStack() as stack:
        for _ in range(_MAX_REDIRECTS + 1):
            pins = assert_public_url(current)
            # Auth conservée seulement tant qu'on reste sur l'hôte d'origine.
            hop_headers = headers if urlsplit(current).hostname == origin_host else None
            client = stack.enter_context(_make_client(pins, timeout))
            request = client.build_request("GET", current, headers=hop_headers)
            response = client.send(request, stream=True)
            if response.is_redirect:
                location = response.headers.get("location", "")
                response.close()
                if not location:
                    raise HttpFetchError(
                        f"redirection sans 'Location' depuis {current!r}."
                    )
                current = str(request.url.join(location))
                continue
            try:
                yield response
            finally:
                response.close()
            return
        raise HttpFetchError(f"trop de redirections (> {_MAX_REDIRECTS}) pour {url!r}.")


def _read_capped(response: httpx.Response, max_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise HttpFetchError(f"réponse dépasse le plafond de {max_bytes} octets.")
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_json(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> object:
    """Récupère et parse un JSON ; anti-SSRF + plafond ``MANIFEST_MAX_BYTES``.

    ``headers`` permet l'authentification d'API (ex. ``Authorization: Token …``) ;
    il n'est jamais journalisé (les messages d'erreur ne portent que l'URL).
    """
    try:
        with _stream_validated(url, timeout=timeout, headers=headers) as response:
            response.raise_for_status()
            raw = _read_capped(response, MANIFEST_MAX_BYTES)
    except httpx.HTTPStatusError as exc:
        raise HttpFetchError(
            f"statut HTTP {exc.response.status_code} sur {url!r}."
        ) from exc
    except httpx.HTTPError as exc:
        raise HttpFetchError(f"échec de transport sur {url!r} : {exc}.") from exc
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HttpFetchError(f"réponse non-JSON depuis {url!r} : {exc}.") from exc


def download(
    url: str,
    dest: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> None:
    """Télécharge ``url`` vers ``dest`` en **flux disque** ; anti-SSRF + plafond.

    Écrit au fil de l'eau dans un fichier ``.part`` voisin (jamais tout le corps
    en RAM), plafonne à ``IMAGE_MAX_BYTES``, puis **renomme atomiquement**
    (``os.replace``) vers ``dest``. À la moindre erreur (statut, dépassement de
    plafond, I/O, annulation), le ``.part`` est supprimé : **aucun fichier
    partiel** n'est laissé derrière, et ``dest`` n'apparaît qu'une fois complet.

    ``headers`` (ex. ``Authorization``) n'est transmis qu'à l'hôte d'origine —
    ``_stream_validated`` le retire sur une redirection cross-hôte (cf. D-050).
    """
    part = dest.with_name(dest.name + ".part")
    try:
        with _stream_validated(url, timeout=timeout, headers=headers) as response:
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise HttpFetchError(
                    f"statut HTTP {exc.response.status_code} sur {url!r}."
                ) from exc
            total = 0
            with part.open("wb") as handle:
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > IMAGE_MAX_BYTES:
                        raise HttpFetchError(
                            f"réponse dépasse le plafond de {IMAGE_MAX_BYTES} octets."
                        )
                    handle.write(chunk)
        os.replace(part, dest)
    except BaseException:
        part.unlink(missing_ok=True)
        raise


def fetch_bytes(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> bytes:
    """Récupère un corps **binaire** en mémoire ; anti-SSRF + plafond manifeste.

    Pour les ressources qui doivent être parsées depuis des **octets** (ex. ALTO
    Gallica : lxml refuse un ``str`` portant une déclaration d'encodage XML).
    """
    try:
        with _stream_validated(url, timeout=timeout, headers=headers) as response:
            response.raise_for_status()
            return _read_capped(response, MANIFEST_MAX_BYTES)
    except httpx.HTTPStatusError as exc:
        raise HttpFetchError(
            f"statut HTTP {exc.response.status_code} sur {url!r}."
        ) from exc
    except httpx.HTTPError as exc:
        # Échec de transport (connexion/timeout/protocole) : on l'enveloppe en
        # HttpFetchError pour que les appelants n'aient qu'un type réseau à gérer
        # (jamais une exception httpx brute qui échapperait au repli).
        raise HttpFetchError(f"échec de transport sur {url!r} : {exc}.") from exc


def fetch_text(
    url: str,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    headers: dict[str, str] | None = None,
) -> str:
    """Récupère un corps **texte** (UTF-8, erreurs remplacées) ; anti-SSRF + plafond.

    Pour les endpoints qui ne servent pas du JSON (ex. catalogue HTR-United).
    """
    # Accept #15 : un corps distant peut contenir des octets non-UTF-8 isolés ;
    # `errors="replace"` insère U+FFFD plutôt que d'échouer sur une donnée mal
    # encodée (le contenu reste exploitable, pas une GT manuelle).
    return fetch_bytes(url, timeout=timeout, headers=headers).decode(
        "utf-8", errors="replace"
    )


__all__ = [
    "CorpusHttpError",
    "HttpFetchError",
    "IMAGE_MAX_BYTES",
    "MANIFEST_MAX_BYTES",
    "SsrfError",
    "assert_public_url",
    "download",
    "fetch_bytes",
    "fetch_json",
    "fetch_text",
]

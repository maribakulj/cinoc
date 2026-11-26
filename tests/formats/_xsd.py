"""Oracle XSD des sorties d'écrivain — chargé hors réseau (A9, D-271).

Les schémas officiels sont vendorisés **octet pour octet** dans
``tests/fixtures/xsd/`` (provenance et empreintes : le ``README.md`` du
dossier) : ALTO 4.4 de loc.gov et PAGE 2019-07-15 de PRImA. L'``xsd:import``
d'ALTO pointe vers loc.gov ; un résolveur lxml le redirige vers la copie
locale, et le parseur refuse le réseau : une
validation qui irait chercher un schéma en ligne serait un test qui dépend
d'un serveur tiers, et qui passerait au vert le jour où il ne répond plus.

L'empreinte est revérifiée au chargement. Un oracle qu'on peut retoucher
pour faire passer un test n'est plus un oracle.
"""

from __future__ import annotations

import hashlib
from functools import cache
from pathlib import Path

from lxml import etree

XSD_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "xsd"

#: Fichiers vendorisés et leur SHA-256 (doivent rester ceux de loc.gov).
_SHA256 = {
    "alto-4-4.xsd": "5564fd29d2dd090d8102b8a0aa081906afd677cd5ecc632312e56f21ea14702b",
    "xlink.xsd": "f1f5bb6003165cdd8f6c1fcc32f8fd1f965e1681010f3b9806d9460bcffa8a3c",
    "pagecontent-2019-07-15.xsd": (
        "5d7da5af5f5e06d3b9cd1e78b407ffca1862f78ad9823ed89c302fb6409932d5"
    ),
}

#: Imports distants des schémas → fichier local.
_LOCAL = {"http://www.loc.gov/standards/xlink/xlink.xsd": "xlink.xsd"}

ALTO_V4_NS = "http://www.loc.gov/standards/alto/ns-v4#"
PAGE_2019_NS = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


class _LocalResolver(etree.Resolver):
    def resolve(  # type: ignore[override]
        self, system_url: str, public_id: str, context: object
    ) -> object:
        local = _LOCAL.get(system_url)
        if local is None:
            return None  # le parseur sans réseau refusera
        return self.resolve_filename(str(_checked(local)), context)


def _checked(name: str) -> Path:
    path = XSD_DIR / name
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != _SHA256[name]:
        raise AssertionError(
            f"{name} ne correspond plus au fichier officiel (sha256 {digest})."
        )
    return path


def _load(name: str) -> etree.XMLSchema:
    parser = etree.XMLParser(no_network=True, resolve_entities=False)
    parser.resolvers.add(_LocalResolver())
    return etree.XMLSchema(etree.parse(str(_checked(name)), parser))


@cache
def alto_schema() -> etree.XMLSchema:
    """Schéma ALTO 4.4 officiel (couvre le namespace ``ns-v4`` qu'écrit Cinoc)."""
    return _load("alto-4-4.xsd")


@cache
def page_schema() -> etree.XMLSchema:
    """Schéma PAGE 2019-07-15 officiel (le seul namespace qu'écrit Cinoc)."""
    return _load("pagecontent-2019-07-15.xsd")


def _errors(data: bytes, namespace: str, schema: etree.XMLSchema) -> list[str]:
    root = etree.fromstring(data)
    if etree.QName(root).namespace != namespace:
        return [f"namespace {etree.QName(root).namespace!r} ≠ {namespace!r}"]
    if schema.validate(root):
        return []
    return [f"l.{e.line} {e.message}" for e in schema.error_log]


def alto_errors(data: bytes) -> list[str]:
    """Erreurs de validation ALTO 4.4 de ``data`` (liste vide = conforme)."""
    return _errors(data, ALTO_V4_NS, alto_schema())


def page_errors(data: bytes) -> list[str]:
    """Erreurs de validation PAGE 2019 de ``data`` (liste vide = conforme)."""
    return _errors(data, PAGE_2019_NS, page_schema())

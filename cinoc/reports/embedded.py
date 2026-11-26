"""Scripts **embarqués** du rapport autonome (couche 7) — chargement + empreintes CSP.

**Source unique** des scripts inlinés dans le rapport (autonomie : ils voyagent
dans le document) : ``compare.js`` (comparer 2 runs) et ``report.js`` (navigation
clavier + palette). Chaque script est **statique** → son ``sha256`` est épinglé
dans la CSP des réponses ``/reports/`` (``get_csp_policy``) ; jamais
``'unsafe-inline'``. **Ajouter un script du rapport = l'ajouter à
``EMBEDDED_SCRIPTS`` ICI** (les hashes CSP suivent automatiquement).
"""

from __future__ import annotations

import base64
import hashlib
from functools import cache
from importlib import resources

#: Scripts inlinés dans **tout** rapport, dans un ordre stable (déterminisme).
EMBEDDED_SCRIPTS: tuple[str, ...] = ("compare.js", "report.js")


@cache
def asset_text(name: str) -> str:
    """Texte d'un fichier du paquet (``_assets/<name>`` : script, CSS), lu
    **une fois**."""
    return (
        resources.files("cinoc.reports")
        .joinpath(f"_assets/{name}")
        .read_text(encoding="utf-8")
    )


@cache
def script_hash(name: str) -> str:
    """Empreinte CSP (``'sha256-…'``) d'un script — constante, calculée 1×."""
    digest = hashlib.sha256(asset_text(name).encode("utf-8")).digest()
    return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"


def script_csp_hashes() -> str:
    """Empreintes de **tous** les scripts embarqués (pour ``script-src`` /reports/)."""
    return " ".join(script_hash(name) for name in EMBEDDED_SCRIPTS)


def inline_script(name: str) -> str:
    """``<script>…</script>`` inliné (autonomie du rapport)."""
    return f"<script>{asset_text(name)}</script>"


__all__ = [
    "EMBEDDED_SCRIPTS",
    "asset_text",
    "inline_script",
    "script_csp_hashes",
    "script_hash",
]

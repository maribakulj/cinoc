"""Persistance des exports **ALTO XML** d'un run (couche 6).

Un run dont une étape exporte l'ALTO (réglage ``alto`` de Tesseract, étape ``alto``
d'une recette) produit un artefact ``ALTO_XML`` par document que
le ``RunResult`` (métriques scalaires) **ne porte pas** et que le workspace
temporaire du run **détruit** à la fin. Ce store le **persiste**, indexé par
``run_id``, pour qu'un endpoint web le restitue en archive ZIP — la forme
ré-importable dans un outil de relecture (eScriptorium, Transkribus).

Un seul chemin : le sink du ``JobRunner`` y dépose les ALTO produits ; le routeur
des rapports les rezippe à la demande. Pas de second format, pas de cache pré-écrit.
"""

from __future__ import annotations

import io
import threading
import zipfile
from pathlib import Path

from cinoc.adapters.layout.alto_source import alto_file_name
from cinoc.app.security import PathSecurityError, safe_stem, validated_path


class AltoStore:
    """Registre disque des exports ALTO (``base_dir/<run>/<entrée>.alto.xml``)."""

    def __init__(self, base_dir: Path) -> None:
        self._base = base_dir
        self._lock = threading.Lock()

    def save(
        self, run_id: str, document_id: str, pipeline_name: str, xml: bytes
    ) -> None:
        """Persiste un ALTO XML pour ``(run_id, pipeline_name, document_id)``.

        Nommé comme le fait la CLI (``alto_file_name``) : une archive web
        décompressée à côté des images se relit par ``cinoc correct --pipeline``
        ou ``alto_source``, comme un ``--alto-dir`` (D-307). Deux pipelines qui
        se réduiraient au même nom : le second est refusé (``FileExistsError``),
        jamais écrit par-dessus le premier.
        """
        with self._lock:
            folder = self._base / safe_stem(run_id)
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / alto_file_name(document_id, pipeline_name)
            if target.exists():
                raise FileExistsError(
                    f"ALTO {target.name!r} déjà écrit pour ce run : "
                    f"{pipeline_name!r} se réduit au nom d'un autre pipeline."
                )
            target.write_bytes(xml)

    def has(self, run_id: str) -> bool:
        """``True`` si au moins un ALTO est persisté pour ce run."""
        folder = self._folder(run_id)
        if folder is None or not folder.is_dir():
            return False
        return any(folder.glob("*.alto.xml"))

    def archive(self, run_id: str) -> bytes | None:
        """Archive ZIP **déterministe** (entrées triées) des ALTO du run, ou ``None``.

        ``None`` si aucun ALTO n'est persisté (run sans export) → le routeur répond
        ``404``. Les octets XML ne sont jamais altérés (ré-import fidèle)."""
        folder = self._folder(run_id)
        if folder is None or not folder.is_dir():
            return None
        files = sorted(folder.glob("*.alto.xml"))
        if not files:
            return None
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in files:
                archive.writestr(path.name, path.read_bytes())
        return buffer.getvalue()

    def _folder(self, run_id: str) -> Path | None:
        """Dossier du run, **chemin validé** (anti path-traversal sur le run_id URL)."""
        try:
            return validated_path(safe_stem(run_id), self._base)
        except PathSecurityError:
            return None


__all__ = ["AltoStore"]

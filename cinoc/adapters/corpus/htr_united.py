"""Catalogue **HTR-United** (découverte de corpus GT) — couche 5.

HTR-United publie un index communautaire de corpus de vérité-terrain HTR/OCR sous
forme d'un fichier YAML versionné sur GitHub. Cet adapter **découvre** (télécharge
l'index + recherche), il ne **matérialise pas** un corpus (les entrées pointent
vers des dépôts ALTO/PAGE — matérialisation = incrémentale, ultérieure).

Repli **hors-ligne** assumé : si l'index distant est injoignable ou illisible, on
sert un **socle de démonstration** intégré (petit, pas un dump) avec
``source="demo"`` / ``is_demo=True`` — l'appelant sait que ce n'est pas le
catalogue à jour (alimente la future UI de sélection de corpus).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlsplit

import yaml

from cinoc.adapters.corpus._http import DEFAULT_TIMEOUT, CorpusHttpError, fetch_text
from cinoc.formats import safe_load_yaml

logger = logging.getLogger(__name__)

#: Index communautaire (YAML brut sur GitHub).
CATALOGUE_URL = (
    "https://raw.githubusercontent.com/HTR-United/htr-united/master/htr-united.yml"
)


@dataclass(frozen=True)
class HTRUnitedEntry:
    """Une entrée du catalogue (métadonnées de découverte, pas le corpus)."""

    id: str
    title: str
    url: str
    description: str
    languages: tuple[str, ...]


#: Socle de démonstration minimal (corpus HTR-United réels) — repli hors-ligne.
_DEMO_ENTRIES: tuple[HTRUnitedEntry, ...] = (
    HTRUnitedEntry(
        id="cremma-medieval",
        title="CREMMA Medieval",
        url="https://github.com/HTR-United/cremma-medieval",
        description="Manuscrits médiévaux français et latins.",
        languages=("fr", "la"),
    ),
    HTRUnitedEntry(
        id="lectaurep-repertoires",
        title="LECTAUREP Répertoires",
        url="https://github.com/HTR-United/lectaurep-repertoires",
        description="Répertoires de notaires manuscrits (XIXe-XXe).",
        languages=("fr",),
    ),
    HTRUnitedEntry(
        id="caroline-minuscule",
        title="Caroline Minuscule",
        url="https://github.com/HTR-United/CemmaCarolineMinuscule",
        description="Minuscule caroline latine.",
        languages=("la",),
    ),
)


def _as_languages(raw: object) -> tuple[str, ...]:
    """Normalise un champ langue (str, liste de str, ou liste de dicts)."""
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, list):
        out: list[str] = []
        for item in raw:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                value = item.get("iso") or item.get("lang") or item.get("label")
                if value:
                    out.append(str(value))
        return tuple(out)
    return ()


def _last_path_segment(url: str) -> str:
    """Le dernier segment du **chemin** d'une URL : un fragment de suivi
    (``record/3333627#.YhN1G1vMLUQ``) ou une requête n'est pas un identifiant."""
    return urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]


def _entry_from_dict(item: dict[str, object]) -> HTRUnitedEntry | None:
    url = str(item.get("url", "") or "")
    title = str(item.get("title", "") or "")
    if not url and not title:
        return None
    entry_id = str(item.get("id") or "") or _last_path_segment(url) or title
    return HTRUnitedEntry(
        id=entry_id,
        title=title or entry_id,
        url=url,
        description=str(item.get("description", "") or ""),
        languages=_as_languages(item.get("language")),
    )


def parse_catalogue(raw_yaml: str) -> tuple[HTRUnitedEntry, ...]:
    """Parse l'index YAML HTR-United → entrées. Pur (tolérant au schéma).

    Par le chargeur **sans alias** (``formats.safe_load_yaml``) : l'index est
    une source tierce lue par la page d'accueil, et l'index réel n'a ni ancre
    ni alias (vérifié le 2026-11-26 : 26 483 événements YAML, aucun). Un index
    à alias lève ``yaml.YAMLError`` → repli démo, comme un index illisible.
    """
    data = safe_load_yaml(raw_yaml)
    if isinstance(data, dict):
        for key in ("data", "projects", "catalog", "catalogue"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
    if not isinstance(data, list):
        return ()
    entries = [
        _entry_from_dict(item) for item in data if isinstance(item, dict)
    ]
    return tuple(e for e in entries if e is not None)


@dataclass(frozen=True)
class HTRUnitedCatalogue:
    """Index HTR-United chargé, avec sa provenance (``remote`` | ``demo``)."""

    entries: tuple[HTRUnitedEntry, ...]
    source: str

    @property
    def is_demo(self) -> bool:
        return self.source == "demo"

    @classmethod
    def from_demo(cls) -> HTRUnitedCatalogue:
        return cls(entries=_DEMO_ENTRIES, source="demo")

    def search(
        self, query: str = "", language: str | None = None
    ) -> tuple[HTRUnitedEntry, ...]:
        results = self.entries
        if query:
            q = query.lower()
            results = tuple(
                e
                for e in results
                if q in e.title.lower()
                or q in e.description.lower()
                or q in e.id.lower()
                or any(q in lg.lower() for lg in e.languages)
            )
        if language:
            lang = language.lower()
            results = tuple(
                e for e in results if any(lang in lg.lower() for lg in e.languages)
            )
        return results


def fetch_catalogue(
    *, catalogue_url: str = CATALOGUE_URL, timeout: float = DEFAULT_TIMEOUT
) -> HTRUnitedCatalogue:
    """Télécharge l'index HTR-United ; **repli démo** si indisponible/illisible."""
    try:
        raw = fetch_text(catalogue_url, timeout=timeout)
        entries = parse_catalogue(raw)
    except (CorpusHttpError, yaml.YAMLError) as exc:
        logger.warning(
            "[htr_united] index distant indisponible (%s) — repli démo : %s",
            catalogue_url,
            exc,
        )
        return HTRUnitedCatalogue.from_demo()
    return HTRUnitedCatalogue(entries=entries, source="remote")


__all__ = [
    "CATALOGUE_URL",
    "HTRUnitedCatalogue",
    "HTRUnitedEntry",
    "fetch_catalogue",
    "parse_catalogue",
]

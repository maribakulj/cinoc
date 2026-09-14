"""Pont ``CanonicalLayout`` → ``DocumentManifest`` de ``saknussemm``.

Isolé de l'adapter pour une raison de contrat : c'est **la** traduction entre
deux modèles de mise en page, et elle a un coût mesurable. Vérifiée sur les deux
corpus du dépôt (1088 lignes, ``37-GT-BNL`` + ``BnF-bpt6k3265015q``) : rôle de
césure, texte de ligne, confiance et ``SUBS_CONTENT`` identiques à ce que le
parser de ``saknussemm`` obtient en lisant l'ALTO lui-même.

Cette parité **dépend** du fait que ``alto_to_layout`` transporte les ``SP``,
les ``HYP`` et les ``SUBS``. Avant qu'il le fasse, la même conversion perdait
36 % des rôles de césure et faussait 21 % des textes sur le corpus BnF.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from cinoc.domain.errors import AdapterStepError

if TYPE_CHECKING:  # pragma: no cover
    from cinoc.domain.layout import CanonicalLayout, Region


def _flatten_regions(regions: tuple[Region, ...]) -> list[Region]:
    """Régions imbriquées aplaties : un bloc ALTO composé porte ses lignes dans
    ses enfants, et ``saknussemm`` raisonne sur des blocs plats."""
    out: list[Region] = []
    for region in regions:
        if region.lines:
            out.append(region)
        out.extend(_flatten_regions(region.regions))
    return out


def layout_to_manifest(layout: CanonicalLayout, *, document_id: str) -> Any:
    """Traduit une mise en page neutre en manifeste ``saknussemm``.

    Lève si une ligne n'a pas d'identifiant : ``saknussemm`` fait de
    ``(page_id, line_id)`` **l'identité** d'une ligne, pas son rang. Une ligne
    anonyme ne peut donc pas traverser la bibliothèque, et le dire ici nomme la
    vraie cause.
    """
    from saknussemm.core.pairing import (  # type: ignore[import-not-found]  # noqa: PLC0415
        HYPHEN_CHARS,
        link_hyphen_pairs,
        trailing_hyphen_char,
    )
    from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415
        BlockManifest,
        Coords,
        DocumentManifest,
        HyphenRole,
        LineManifest,
        PageManifest,
    )

    pages = []
    for page_index, lpage in enumerate(layout.pages):
        page_id = f"P_{page_index + 1:04d}"
        blocks, lines = [], []
        order = 0
        for block_index, region in enumerate(_flatten_regions(lpage.regions)):
            block_id = region.id or f"B_{block_index + 1:04d}"
            line_ids = []
            for line_index, line in enumerate(region.lines):
                if not line.id:
                    raise AdapterStepError(
                        "layout_to_manifest : une ligne du bloc "
                        f"{block_id!r} n'a pas d'identifiant. saknussemm fait "
                        "de (page, ligne) une identité, pas un rang."
                    )
                confidences = [
                    w.confidence for w in line.words if w.confidence is not None
                ]
                first = line.words[0] if line.words else None
                last = line.words[-1] if line.words else None
                lm = LineManifest(
                    line_id=line.id,
                    page_id=page_id,
                    block_id=block_id,
                    line_order_global=order,
                    line_order_in_block=line_index,
                    coords=_coords(Coords, line),
                    ocr_text=line.text,
                    # ``None`` et non ``len(words)`` : en ALTO la géométrie par
                    # jeton se redistribue à n'importe quel compte de mots, donc
                    # le compte n'est pas une contrainte de projection.
                    word_count=None,
                    ocr_confidence=(
                        sum(confidences) / len(confidences) if confidences else None
                    ),
                )
                _set_hyphenation(
                    lm,
                    HyphenRole,
                    trailing_hyphen_char,
                    HYPHEN_CHARS,
                    first_subs=_subs(first),
                    last_subs=_subs(last),
                )
                lines.append(lm)
                line_ids.append(line.id)
                order += 1
            blocks.append(
                BlockManifest(
                    block_id=block_id,
                    page_id=page_id,
                    block_order=block_index,
                    coords=_coords(Coords, region),
                    line_ids=line_ids,
                )
            )
        # **Chaîner les voisins avant d'apparier les césures.**
        #
        # ``prev_text``/``next_text`` du payload envoyé au modèle sont résolus
        # depuis ces deux liens ; sans eux, **chaque ligne arrive seule**. Le
        # correcteur ne peut alors pas réparer ce qui n'est lisible qu'avec la
        # ligne d'à côté — mesuré sur le corpus BNL : `"2 de garanties` reste
        # `"2 de garanties` là où il fallait lire `tant de garanties`, la
        # preuve étant dans la ligne précédente (`tout au`).
        #
        # Le parser ALTO de ``saknussemm`` fait exactement cette boucle ; ce
        # pont, qui le remplace, l'avait omise. Les deux voies alimentent le
        # même moteur : elles doivent le nourrir pareil.
        for rang, ligne in enumerate(lines):
            if rang > 0:
                ligne.prev_line_id = lines[rang - 1].line_id
            if rang < len(lines) - 1:
                ligne.next_line_id = lines[rang + 1].line_id
        link_hyphen_pairs(lines)
        pages.append(
            PageManifest(
                page_id=page_id,
                source_file=f"{document_id}#{page_index}",
                page_index=page_index,
                page_width=lpage.width or 0,
                page_height=lpage.height or 0,
                blocks=blocks,
                lines=lines,
            )
        )
    return DocumentManifest(
        document_id=document_id,
        source_files=[p.source_file for p in pages],
        pages=pages,
    )


def _subs(word: Any) -> tuple[str | None, str | None]:
    """``(SUBS_TYPE, SUBS_CONTENT)`` d'un mot, ou ``(None, None)`` sans mot."""
    if word is None:
        return None, None
    return word.subs_type, word.subs_content


def _coords(coords_cls: Any, element: Any) -> Any:
    box = element.geometry.bbox if element.geometry else None
    return coords_cls(
        hpos=box.x if box else 0,
        vpos=box.y if box else 0,
        width=box.width if box else 0,
        height=box.height if box else 0,
    )


def _set_hyphenation(
    lm: Any,
    hyphen_role: Any,
    trailing: Any,
    hyphen_chars: Any,
    *,
    first_subs: tuple[str | None, str | None],
    last_subs: tuple[str | None, str | None],
) -> None:
    """Deux sources, comme le parser ALTO de ``saknussemm`` : le ``SUBS_TYPE``
    (explicite) et une marque de coupure en fin de ligne (heuristique)."""
    first_type, first_content = first_subs
    last_type, last_content = last_subs
    is_part2 = first_type == "HypPart2"
    is_part1 = last_type == "HypPart1" or (
        trailing(lm.ocr_text, hyphen_chars) is not None
    )
    if is_part1 and is_part2:
        lm.hyphen_role = hyphen_role.BOTH
        lm.hyphen_source_explicit = True
        lm.hyphen_subs_content = first_content
        lm.hyphen_forward_explicit = last_type == "HypPart1"
        lm.hyphen_forward_subs_content = last_content
    elif is_part2:
        lm.hyphen_role = hyphen_role.PART2
        lm.hyphen_source_explicit = True
        lm.hyphen_subs_content = first_content
    elif is_part1:
        lm.hyphen_role = hyphen_role.PART1
        lm.hyphen_source_explicit = last_type == "HypPart1"
        lm.hyphen_subs_content = last_content


def manifest_page_ids(manifest: Any) -> list[str]:
    """Les ``page_id`` fabriqués ci-dessus, dans l'ordre des pages du layout."""
    return [page.page_id for page in manifest.pages]


__all__ = ["layout_to_manifest", "manifest_page_ids"]

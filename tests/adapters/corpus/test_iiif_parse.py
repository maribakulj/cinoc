"""Parseur IIIF v2/v3 (pur, sans réseau) : URL d'image directe ou via service."""

from __future__ import annotations

import pytest

from cinoc.adapters.corpus.iiif import parse_manifest

V2 = {
    "@context": "http://iiif.io/api/presentation/2/context.json",
    "sequences": [
        {
            "canvases": [
                {
                    "label": "f. 1",
                    "images": [{"resource": {"@id": "https://ex.org/img/1.jpg"}}],
                },
                {
                    "label": "f. 2",
                    "images": [{"resource": {"service": {"@id": "https://ex.org/iiif/2"}}}],
                },
                {"label": "f. 3 sans image", "images": []},
            ]
        }
    ],
}

V3 = {
    "@context": "http://iiif.io/api/presentation/3/context.json",
    "type": "Manifest",
    "items": [
        {
            "label": {"en": ["Page 1"]},
            "items": [
                {"items": [{"body": {"id": "https://ex.org/p1.jpg", "type": "Image"}}]}
            ],
        },
        {
            "label": {"fr": ["Page 2"]},
            "items": [
                {"items": [{"body": {"type": "Image", "service": [{"id": "https://ex.org/iiif/p2"}]}}]}
            ],
        },
    ],
}


def test_v2_direct_and_service_urls() -> None:
    images = parse_manifest(V2)
    assert len(images) == 2  # le canvas sans image est ignoré
    assert images[0].image_url == "https://ex.org/img/1.jpg"
    assert images[0].label == "f. 1"
    # via service IIIF Image API sans version déclarée, identifiant ``@id`` (forme
    # 2.x) → syntaxe 2.x : ``full`` est valide de 2.0 à 2.1, ``max`` dès 2.1 seulement
    assert images[1].image_url == "https://ex.org/iiif/2/full/full/0/default.jpg"


def test_v3_direct_and_service_and_language_map() -> None:
    images = parse_manifest(V3)
    assert len(images) == 2
    assert images[0].image_url == "https://ex.org/p1.jpg"
    assert images[0].label == "Page 1"  # map de langue v3 aplatie
    # identifiant ``id`` (forme 3.0) → syntaxe 3.0
    assert images[1].image_url == "https://ex.org/iiif/p2/full/max/0/default.jpg"
    assert images[1].label == "Page 2"


def test_label_fallback_when_missing() -> None:
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "type": "Manifest",
        "items": [
            {
                "items": [
                    {"items": [{"body": {"id": "http://e.org/x", "type": "Image"}}]}
                ]
            }
        ],
    }
    images = parse_manifest(manifest)
    assert images[0].label == "canvas_1"


def test_v3_label_nested_list_is_stringified() -> None:
    # Une map de langue dont la valeur est une liste non-str ne doit pas casser
    # le type str de IIIFImage.label (régression d'audit).
    manifest = {
        "@context": "http://iiif.io/api/presentation/3/context.json",
        "type": "Manifest",
        "items": [
            {
                "label": {"none": [42]},
                "items": [
                    {"items": [{"body": {"id": "http://e.org/x", "type": "Image"}}]}
                ],
            }
        ],
    }
    (image,) = parse_manifest(manifest)
    assert image.label == "42" and isinstance(image.label, str)


def test_empty_manifest_yields_no_images() -> None:
    assert parse_manifest({"@context": "…/presentation/3/…", "type": "Manifest"}) == ()
    assert parse_manifest({}) == ()


def _v2_with(resource: dict[str, object]) -> dict[str, object]:
    return {
        "@context": "http://iiif.io/api/presentation/2/context.json",
        "sequences": [
            {"canvases": [{"label": "p", "images": [{"resource": resource}]}]}
        ],
    }


# Formes de service relevées sur des manifestes réels (audit de substitution) :
# la requête « image entière » dépend de la version de l'Image API déclarée.
_GALLICA_SVC = "https://gallica.bnf.fr/iiif/ark:/12148/bpt6k5619759j/f1"
_NGA_SVC = (
    "https://media.nga.gov/iiif/public/objects/1/0/6/3/8/2/106382-primary-0-nativeres.ptif"
)


@pytest.mark.parametrize(
    ("resource", "expected"),
    [
        # Gallica : Image API 1.1 (@context image/1, profil Stanford) → ``native``.
        (
            {
                "@id": f"{_GALLICA_SVC}/full/full/0/native.jpg",
                "service": {
                    "@context": "http://iiif.io/api/image/1/context.json",
                    "@id": _GALLICA_SVC,
                    "profile": "http://library.stanford.edu/iiif/image-api/1.1/compliance.html#level2",
                },
            },
            f"{_GALLICA_SVC}/full/full/0/native.jpg",
        ),
        # NGA : Image API 2 → ``full/full`` (identique à l'URL directe).
        (
            {
                "@id": f"{_NGA_SVC}/full/full/0/default.jpg",
                "service": {
                    "@context": "http://iiif.io/api/image/2/context.json",
                    "@id": _NGA_SVC,
                    "profile": "http://iiif.io/api/image/2/level2.json",
                },
            },
            f"{_NGA_SVC}/full/full/0/default.jpg",
        ),
        # Image API 3 typée → ``full/max`` ; profil nu ``level1`` = forme 3.0.
        (
            {"id": "https://ex.org/a/full/600,/0/default.jpg",
             "service": [{"id": "https://ex.org/a", "type": "ImageService3"}]},
            "https://ex.org/a/full/max/0/default.jpg",
        ),
        (
            {"service": [{"@id": "https://ex.org/b/", "profile": "level1"}]},
            "https://ex.org/b/full/max/0/default.jpg",
        ),
        # Bodleian : ``@id`` = base du service → l'image est construite par lui.
        (
            {
                "@id": "https://ex.org/svc",
                "service": {
                    "@context": "http://iiif.io/api/image/2/context.json",
                    "@id": "https://ex.org/svc",
                },
            },
            "https://ex.org/svc/full/full/0/default.jpg",
        ),
        # Sans service : l'URL directe, sauf un ``info.json``.
        ({"@id": "https://ex.org/plain.png"}, "https://ex.org/plain.png"),
    ],
)
def test_full_image_url_follows_image_api_version(
    resource: dict[str, object], expected: str
) -> None:
    (image,) = parse_manifest(_v2_with(resource))
    assert image.image_url == expected


def test_direct_info_json_without_service_is_skipped() -> None:
    assert parse_manifest(_v2_with({"@id": "https://ex.org/svc/info.json"})) == ()

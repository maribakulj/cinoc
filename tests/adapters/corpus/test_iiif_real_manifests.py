"""Manifestes IIIF **réels** rejoués hors ligne : la page importée est la vraie image.

Deux défauts trouvés par l'audit de substitution (``docs/ANALYSE_SUBSTITUTION.md``,
défauts 4 et 5), chacun sur un manifeste réel en cassette
(``tests/fixtures/cassettes/iiif_bodleian.json``, ``iiif_wellcome.json`` — source,
droits et réduction documentés dans chaque cassette) :

- **Bodleian (Presentation 2)** : ``resource.@id`` *est* l'URL de base du service
  d'images ; elle répond 303 vers ``info.json``. Prise pour l'image, elle donnait
  un corpus de JSON enregistrés sous ``page_*.jpg``.
- **Wellcome (Presentation 2 et 3)** : ``resource.@id`` / ``body.id`` est une
  **vignette** (≈ 742×1024) quand le service offre la pleine résolution
  (2569×3543) : l'OCR tournait sur ~12× moins de pixels, sans le dire.

Les corps d'image des cassettes sont des JPEG blancs aux dimensions de la vraie
réponse (``real_size``) : on prouve *quelle* réponse a été écrite, sans
redistribuer les images.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from cinoc.adapters.corpus import _http
from cinoc.adapters.corpus._http import CorpusHttpError, NotAnImageError
from cinoc.app.corpus_import import import_iiif_corpus
from tests.adapters.corpus._cassette import replaying

_CASSETTES = Path(__file__).resolve().parents[2] / "fixtures" / "cassettes"

_BODLEIAN = (
    "https://iiif.bodleian.ox.ac.uk/iiif/manifest/"
    "e32a277e-91e2-4a6d-8ba6-cc4bad230410.json"
)
_WELLCOME_V2 = "https://iiif.wellcomecollection.org/presentation/v2/b18035723"
_WELLCOME_V3 = "https://iiif.wellcomecollection.org/presentation/b18035723"


def _responses(cassette: str) -> dict[str, dict[str, object]]:
    data = json.loads((_CASSETTES / f"{cassette}.json").read_text(encoding="utf-8"))
    return {i["request"]["url"]: i["response"] for i in data["interactions"]}


def _body(response: dict[str, object]) -> bytes:
    return base64.b64decode(str(response["body_b64"]))


def _assert_full_resolution(
    cassette: str, spec_images: list[Path], expected: list[tuple[str, list[int]]]
) -> None:
    """Chaque fichier écrit est, octet pour octet, la réponse pleine résolution."""
    responses = _responses(cassette)
    assert len(spec_images) == len(expected)
    for path, (url, size) in zip(spec_images, expected, strict=True):
        response = responses[url]
        assert response["real_size"] == size
        written = path.read_bytes()
        assert written.startswith(b"\xff\xd8\xff"), f"{path.name} n'est pas un JPEG"
        assert written == _body(response), (
            f"{path.name} n'est pas la réponse pleine résolution {size} de {url}"
        )


def test_bodleian_v2_imports_images_not_info_json(tmp_path: Path) -> None:
    with replaying("iiif_bodleian"):
        spec = import_iiif_corpus(_BODLEIAN, tmp_path, name="bodleian")
    base = "https://iiif.bodleian.ox.ac.uk/iiif/image"
    _assert_full_resolution(
        "iiif_bodleian",
        [Path(d.image_uri) for d in spec.documents],
        [
            (
                f"{base}/e58b8c60-005c-4c41-a22f-07d49cb25ede/full/full/0/default.jpg",
                [2644, 4000],
            ),
            (
                f"{base}/02ddc913-ecab-471e-8ca3-6bd402bff215/full/full/0/default.jpg",
                [2620, 4000],
            ),
        ],
    )


_WELLCOME_FULL = [
    (
        "https://iiif.wellcomecollection.org/image/b18035723_0001.JP2"
        "/full/full/0/default.jpg",
        [2569, 3543],
    ),
    (
        "https://iiif.wellcomecollection.org/image/b18035723_0003.JP2"
        "/full/full/0/default.jpg",
        [2411, 3372],
    ),
]


@pytest.mark.parametrize("manifest", [_WELLCOME_V3, _WELLCOME_V2])
def test_wellcome_uses_full_resolution_service_not_thumbnail(
    manifest: str, tmp_path: Path
) -> None:
    with replaying("iiif_wellcome"):
        spec = import_iiif_corpus(manifest, tmp_path, name="wellcome")
    _assert_full_resolution(
        "iiif_wellcome", [Path(d.image_uri) for d in spec.documents], _WELLCOME_FULL
    )


def test_download_refuses_service_base_answering_info_json(tmp_path: Path) -> None:
    # La réponse réelle du service Bodleian (303 → info.json) n'est pas une image :
    # refus typé, et rien n'est écrit — ni la destination, ni un ``.part``.
    service = (
        "https://iiif.bodleian.ox.ac.uk/iiif/image/e58b8c60-005c-4c41-a22f-07d49cb25ede"
    )
    dest = tmp_path / "page_0001.jpg"
    with replaying("iiif_bodleian"), pytest.raises(NotAnImageError, match="json"):
        _http.download(service, dest)
    assert list(tmp_path.iterdir()) == []
    # Échec d'unité isolé côté orchestrateur, 422 côté web : même famille d'erreur.
    assert issubclass(NotAnImageError, CorpusHttpError)

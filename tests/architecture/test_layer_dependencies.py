"""Règle d'import des couches : chacune n'importe que des couches plus internes
qu'elle, et sa liste blanche de bibliothèques externes.

Une table (``LAYERS``), un test paramétré : une ligne par couche dit ce qu'elle
peut importer, et pourquoi (P5g 8, D-303 — neuf copies du même corps avant).
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

ROOT = Path(__file__).resolve().parents[2] / "cinoc"
ALLOWED_EXT = {"pydantic", "pydantic_core", "typing_extensions", "annotated_types"}
#: La couche formats peut aussi parler XML (lxml) et lire des profils (yaml).
FORMATS_ALLOWED_EXT = ALLOWED_EXT | {"lxml", "yaml"}
STDLIB = set(sys.stdlib_module_names)


def _imported_modules(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                yield "cinoc.domain"
            elif node.module:
                yield node.module


#: La couche adapters traduit des libs externes (moteurs OCR/LLM) vers le
#: ``Module`` Protocol ; elle peut donc parler domain + pipeline + formats.
#: Libs de moteur autorisées (ajoutées à la tranche qui les introduit) :
#: ``PIL`` : découpage des blocs (``layout/crop``) du pipeline hybride seg→OCR.
#: ``yaml`` : catalogue HTR-United (``htr-united.yml``).
#: ``httpcore`` : moteur de transport de ``httpx`` (toujours co-installé), requis
#: pour l'épinglage d'IP anti-DNS-rebinding (``corpus/_http._PinnedBackend``).
#: ``datasets`` : import de corpus HuggingFace en streaming (extra ``[huggingface]``,
#: import paresseux dans ``corpus/huggingface``). ``huggingface_hub`` : snapshot
#: partiel d'un dataset curé publié (même extra, même import paresseux).
#: ``paddlex`` : segmenteur de mise en page PP-DocLayout (extra ``[segment]``,
#: import paresseux dans ``layout/pp_doclayout``).
#: ``saknussemm`` : post-correction **dans** la mise en page (extra
#: ``[saknussemm]``, imports paresseux dans ``layout/saknussemm_correct`` et son
#: pont). Le banc corrigeait du texte plat ; cette brique corrige un ``LAYOUT``
#: en gardant l'identite de ligne, donc l'appariement avant/apres est connu.
ADAPTERS_ALLOWED_EXT = ALLOWED_EXT | {
    "openai", "anthropic", "mistralai", "httpx", "httpcore",
    # Le client HTTP de mistralai 3.x (sa dépendance déclarée), que l'adaptateur
    # construit pour y poser la coupure en vol (S29a, `llm/mistral.mistral_sdk`).
    "httpx2",
    "datasets", "huggingface_hub", "PIL", "yaml", "paddlex", "kraken",
    # Moteurs OCR/HTR locaux in-tree (extras `[pero]`/`[calamari]`, D-078).
    "pero_ocr", "calamari_ocr", "cv2", "numpy",
    # Extracteur d'entités nommées (extra `[ner]`, import paresseux dans
    # `ner/spacy_extractor`).
    "spacy",
    # Post-correction structurée (extra `[saknussemm]`, imports paresseux).
    "saknussemm",
    # Segmenteur de mise en page installable **par pip** (extra `[yolo]`, import
    # paresseux dans `layout/doclayout_yolo`). Les deux autres segmenteurs
    # exigent PaddleX ou une adresse : sans celui-ci, la famille hybride n'est
    # exécutable sur aucune machine nue.
    "doclayout_yolo",
    # Scoreur de qualité D'AlemBERT pour le routage sélectif de la correction
    # (extra `[qe]`, imports paresseux dans `quality/dalembert`).
    "torch", "transformers",
}

#: evaluation parle domain + formats + scipy (Wilcoxon/Friedman) + rapidfuzz
#: (alignement caractère de diacritic_err) + numpy (FCA hongrois, percentiles
#: lines). ``PIL`` retiré : la qualité d'image (seul consommateur) a été supprimée.
EVAL_ALLOWED_EXT = ALLOWED_EXT | {"scipy", "rapidfuzz", "numpy"}

#: interfaces (couche 8) câble le transport web : FastAPI + son socle ASGI
#: (starlette) + le serveur uvicorn. Ajoutés à la tranche T4 (`serve`).
#: ``jinja2`` (déjà dans l'extra ``serve``, moteur des gabarits de starlette) :
#: importé pour rendre sous ``StrictUndefined`` (D-301).
INTERFACES_ALLOWED_EXT = ALLOWED_EXT | {"fastapi", "jinja2", "starlette", "uvicorn"}


class Layer(NamedTuple):
    """Une couche : les paquets ``cinoc`` qu'elle peut importer (elle comprise)
    et les bibliothèques externes de sa liste blanche."""

    packages: tuple[str, ...]
    external: frozenset[str] | set[str]


_INNER = ("domain", "formats", "evaluation", "pipeline", "adapters")

LAYERS: dict[str, Layer] = {
    # Types purs : stdlib + pydantic.
    "domain": Layer(("domain",), ALLOWED_EXT),
    # Parle XML (lxml) et lit des profils (yaml). Jamais une lib de métrique
    # (jiwer/rapidfuzz) ni un moteur OCR.
    "formats": Layer(("domain", "formats"), ALLOWED_EXT | {"lxml", "yaml"}),
    "evaluation": Layer(("domain", "formats", "evaluation"), EVAL_ALLOWED_EXT),
    # Aucune lib de moteur ni de métrique : l'exécution est agnostique.
    "pipeline": Layer(("domain", "pipeline"), ALLOWED_EXT),
    "adapters": Layer(
        ("domain", "pipeline", "formats", "adapters"), ADAPTERS_ALLOWED_EXT
    ),
    # Paquet de **données** (prompts curés) : loader pur (stdlib + domain). Un
    # prompt ne calcule rien, ne fait pas d'I/O métier.
    "prompts": Layer(("domain",), ALLOWED_EXT),
    # app câble les couches internes ; il orchestre, ne calcule pas. Pas de lib
    # métier directe (métriques/moteurs) — il délègue. ``yaml`` : specs.
    "app": Layer((*_INNER, "app", "prompts"), ALLOWED_EXT | {"yaml"}),
    # reports lit le RunResult : domain + evaluation seulement (jamais app/
    # pipeline/adapters). Pas de data-layer, pas de moteur. ``yaml`` : glossaire.
    "reports": Layer(("domain", "evaluation", "reports"), ALLOWED_EXT | {"yaml"}),
    # Feuille : peut câbler toutes les couches internes.
    "interfaces": Layer(
        (*_INNER, "app", "reports", "interfaces"), INTERFACES_ALLOWED_EXT
    ),
}


def test_every_python_package_has_its_rule() -> None:
    """Un paquet de ``cinoc/`` qui porte du code a sa ligne dans ``LAYERS`` :
    une couche nouvelle n'échappe pas au contrôle en silence."""
    with_code = {
        p.parent.relative_to(ROOT).parts[0]
        for p in ROOT.rglob("*.py")
        if p.parent != ROOT and "__pycache__" not in p.parts
    }
    assert with_code <= set(LAYERS), sorted(with_code - set(LAYERS))


@pytest.mark.parametrize("layer", sorted(LAYERS))
def test_layer_imports_are_allowed(layer: str) -> None:
    rule = LAYERS[layer]
    allowed = tuple(f"cinoc.{pkg}" for pkg in rule.packages)
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / layer).rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or any(mod.startswith(pkg) for pkg in allowed):
                continue
            if mod == "__future__" or top in rule.external or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans {layer} : {offenders}"


#: Sous-dossiers d'``adapters`` auxquels une bibliothèque tierce est **interdite**,
#: et la raison. La clé est le dossier, la valeur le paquet qui n'a rien à y faire.
#:
#: ``saknussemm`` hors de son adapter : trois clients ont vécu dans
#: ``adapters/llm/`` sous des noms génériques (``ollama_structured``,
#: ``mistral_structured``, ``mistral_multimodal``) alors qu'ils n'existaient que
#: pour lui — ils implémentent **son** protocole de fournisseur, pas le ``Module``
#: de cinoc. Un lecteur qui ouvrait ``adapters/llm/mistral_structured.py`` croyait
#: y trouver le client Mistral du banc. Ils vivent désormais en
#: ``adapters/correction/``, dont le nom dit à quoi ils servent.
_FORBIDDEN_IN: dict[str, str] = {"llm": "saknussemm"}


def test_no_third_party_bleeds_into_a_neighbouring_adapter_folder() -> None:
    """Une bibliothèque tierce reste dans le dossier qui la sert.

    **Le défaut que ce test ferme n'est pas une violation de couche** — tout se
    passait en couche 5, où l'import d'une lib externe est légitime. C'est un
    défaut de *placement* : du code à la forme d'une bibliothèque, rangé sous un
    nom qui promet autre chose. Aucun garde-fou ne le voyait, et une seule
    session y a ajouté trois fichiers sans que personne le remarque.

    La règle est mécanique, donc elle ne dépend pas de la vigilance : si un
    client de ``saknussemm`` doit exister, il va dans ``adapters/correction/``.
    """
    coupables: dict[str, list[str]] = {}
    for dossier, interdit in _FORBIDDEN_IN.items():
        racine = ROOT / "adapters" / dossier
        if not racine.is_dir():
            continue
        for chemin in sorted(racine.rglob("*.py")):
            if "__pycache__" in chemin.parts:
                continue
            arbre = ast.parse(chemin.read_text(encoding="utf-8"))
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    noms = [a.name for a in noeud.names]
                elif isinstance(noeud, ast.ImportFrom):
                    noms = [noeud.module or ""]
                else:
                    continue
                if any(n.split(".")[0] == interdit for n in noms):
                    rel = chemin.relative_to(ROOT).as_posix()
                    coupables.setdefault(rel, []).append(f"L{noeud.lineno}")
    assert not coupables, (
        f"bibliothèque tierce hors de son dossier : {coupables}. Un client écrit "
        "pour une bibliothèque va dans le dossier qui la sert "
        "(`adapters/correction/` pour saknussemm), pas sous un nom générique."
    )

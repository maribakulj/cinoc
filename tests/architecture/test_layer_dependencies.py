"""La couche domain n'importe que stdlib + pydantic + pydantic_core."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "cinoc"
DOMAIN = ROOT / "domain"
FORMATS = ROOT / "formats"
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


def test_domain_imports_are_pure():
    offenders: dict[str, list[str]] = {}
    for path in DOMAIN.glob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or mod.startswith("cinoc.domain"):
                continue
            if mod == "__future__" or top in ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[path.name] = bad
    assert not offenders, f"imports interdits dans domain : {offenders}"


def test_formats_imports_are_allowed():
    """formats n'importe que stdlib + pydantic + lxml/yaml + domain/formats.
    Jamais une lib de métrique (jiwer/rapidfuzz) ni un moteur OCR."""
    offenders: dict[str, list[str]] = {}
    for path in FORMATS.rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if (
                mod == "cinoc"
                or mod.startswith("cinoc.domain")
                or mod.startswith("cinoc.formats")
            ):
                continue
            if mod == "__future__" or top in FORMATS_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans formats : {offenders}"


def test_pipeline_imports_are_allowed():
    """pipeline (couche 4) n'importe que stdlib + pydantic + domain (+ pipeline).
    Aucune lib de moteur ni de métrique : l'exécution est agnostique."""
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "pipeline").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if (
                mod == "cinoc"
                or mod.startswith("cinoc.domain")
                or mod.startswith("cinoc.pipeline")
            ):
                continue
            if mod == "__future__" or top in ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans pipeline : {offenders}"


#: La couche adapters traduit des libs externes (moteurs OCR/LLM) vers le
#: ``Module`` Protocol ; elle peut donc parler domain + pipeline + formats, et
#: ses extras moteur seront ajoutés ici au fil des tranches.
ADAPTERS_ALLOWED_PKG = (
    "cinoc.domain",
    "cinoc.pipeline",
    "cinoc.formats",
    "cinoc.adapters",
)
#: Libs de moteur autorisées en adapters (ajoutées à la tranche qui les introduit).
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
    "pytesseract", "openai", "anthropic", "mistralai", "httpx", "httpcore",
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


def test_adapters_imports_are_allowed():
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "adapters").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or any(
                mod.startswith(pkg) for pkg in ADAPTERS_ALLOWED_PKG
            ):
                continue
            if mod == "__future__" or top in ADAPTERS_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans adapters : {offenders}"


#: evaluation parle domain + formats + scipy (Wilcoxon/Friedman) + rapidfuzz
#: (alignement caractère de diacritic_err) + numpy (FCA hongrois, percentiles
#: lines) ; jiwer/shapely s'ajouteront à la tranche qui les introduit. ``PIL``
#: retiré : la qualité d'image (seul consommateur) a été supprimée.
EVAL_ALLOWED_EXT = ALLOWED_EXT | {"scipy", "rapidfuzz", "numpy"}


def test_evaluation_imports_are_allowed():
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "evaluation").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if (
                mod == "cinoc"
                or mod.startswith("cinoc.domain")
                or mod.startswith("cinoc.formats")
                or mod.startswith("cinoc.evaluation")
            ):
                continue
            if mod == "__future__" or top in EVAL_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans evaluation : {offenders}"


#: app câble toutes les couches internes (domain..adapters) ; il orchestre, ne
#: calcule pas. Pas de lib métier directe (métriques/moteurs) — il délègue.
APP_ALLOWED_PKG = (
    "cinoc.domain",
    "cinoc.formats",
    "cinoc.evaluation",
    "cinoc.pipeline",
    "cinoc.adapters",
    "cinoc.app",
    # Paquet de **données** (prompts curés), loader pur (stdlib + domain) — leaf.
    "cinoc.prompts",
)
#: app charge des specs YAML (loader) → ``yaml`` autorisé.
APP_ALLOWED_EXT = ALLOWED_EXT | {"yaml"}


def test_prompts_imports_are_pure():
    """``prompts`` est un paquet de **données** : loader pur (stdlib + domain).
    Jamais une couche externe (un prompt ne calcule rien, ne fait pas d'I/O métier)."""
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "prompts").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or mod.startswith("cinoc.domain"):
                continue
            if mod == "__future__" or top in ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans prompts : {offenders}"


def test_app_imports_are_allowed():
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "app").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or any(
                mod.startswith(pkg) for pkg in APP_ALLOWED_PKG
            ):
                continue
            if mod == "__future__" or top in APP_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans app : {offenders}"


#: reports lit aussi une donnée YAML (glossaire pédagogique FR/EN).
REPORTS_ALLOWED_EXT = ALLOWED_EXT | {"yaml"}


def test_reports_imports_are_allowed():
    """reports lit le RunResult : domain + evaluation seulement (jamais app/
    pipeline/adapters). Pas de data-layer, pas de moteur."""
    allowed = ("cinoc.domain", "cinoc.evaluation", "cinoc.reports")
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "reports").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or any(mod.startswith(pkg) for pkg in allowed):
                continue
            if mod == "__future__" or top in REPORTS_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans reports : {offenders}"


#: interfaces (couche 8) câble le transport web : FastAPI + son socle ASGI
#: (starlette) + le serveur uvicorn. Ajoutés à la tranche T4 (`serve`).
INTERFACES_ALLOWED_EXT = ALLOWED_EXT | {"fastapi", "starlette", "uvicorn"}


def test_interfaces_imports_are_allowed():
    """interfaces = feuille : peut câbler toutes les couches internes."""
    allowed = (
        "cinoc.domain",
        "cinoc.formats",
        "cinoc.evaluation",
        "cinoc.pipeline",
        "cinoc.adapters",
        "cinoc.app",
        "cinoc.reports",
        "cinoc.interfaces",
    )
    offenders: dict[str, list[str]] = {}
    for path in (ROOT / "interfaces").rglob("*.py"):
        bad: list[str] = []
        for mod in _imported_modules(path):
            top = mod.split(".")[0]
            if mod == "cinoc" or any(mod.startswith(pkg) for pkg in allowed):
                continue
            if mod == "__future__" or top in INTERFACES_ALLOWED_EXT or top in STDLIB:
                continue
            bad.append(mod)
        if bad:
            offenders[str(path.relative_to(ROOT))] = bad
    assert not offenders, f"imports interdits dans interfaces : {offenders}"

"""Détection de disponibilité des moteurs : sondes injectées → déterministe."""

from __future__ import annotations

from cinoc.app.engines import PUBLIC_ENGINE_KINDS, engine_statuses


def _statuses(**kw: object) -> dict[str, tuple[bool, str]]:
    out = engine_statuses(**kw)  # type: ignore[arg-type]
    return {s.kind: (s.available, s.detail) for s in out}


def test_precomputed_always_available() -> None:
    st = _statuses(
        has_binary=lambda _n: None,
        has_module=lambda _n: False,
        get_env=lambda _n: None,
    )
    assert st["precomputed"][0] is True


def test_tesseract_needs_binary_and_module() -> None:
    common = {"get_env": lambda _n: None}
    # ni binaire ni module
    st = _statuses(has_binary=lambda _n: None, has_module=lambda _n: False, **common)
    assert st["tesseract"][0] is False and "binaire" in st["tesseract"][1]
    # binaire présent mais pytesseract absent
    st = _statuses(
        has_binary=lambda _n: "/usr/bin/tesseract",
        has_module=lambda _n: False,
        **common,
    )
    assert st["tesseract"][0] is False and "pytesseract" in st["tesseract"][1]
    # les deux présents
    st = _statuses(
        has_binary=lambda _n: "/usr/bin/tesseract",
        has_module=lambda _n: True,
        **common,
    )
    assert st["tesseract"][0] is True


def test_openai_needs_module_and_key() -> None:
    base = {"has_binary": lambda _n: None}
    # SDK absent
    st = _statuses(has_module=lambda _n: False, get_env=lambda _n: "sk", **base)
    assert st["openai"][0] is False and "SDK" in st["openai"][1]
    # SDK présent, clé absente
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: None, **base)
    assert st["openai"][0] is False and "OPENAI_API_KEY" in st["openai"][1]
    # SDK + clé
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: "sk", **base)
    assert st["openai"][0] is True


def test_google_vision_needs_httpx_and_key() -> None:
    base = {"has_binary": lambda _n: None}
    # httpx absent → extra [google] manquant
    st = _statuses(has_module=lambda _n: False, get_env=lambda _n: "k", **base)
    assert st["google_vision"][0] is False and "[google]" in st["google_vision"][1]
    # httpx présent, clé absente
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: None, **base)
    assert (
        st["google_vision"][0] is False
        and "GOOGLE_VISION_API_KEY" in st["google_vision"][1]
    )
    # httpx + clé
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: "k", **base)
    assert st["google_vision"][0] is True


def test_pero_and_calamari_need_their_lib() -> None:
    # Moteurs locaux (pas de clé) : dispo dès que la lib est présente, comme Kraken.
    common = {"has_binary": lambda _n: None, "get_env": lambda _n: None}
    absent = _statuses(has_module=lambda _n: False, **common)
    assert absent["pero"][0] is False and "[pero]" in absent["pero"][1]
    assert absent["calamari"][0] is False and "[calamari]" in absent["calamari"][1]
    present = _statuses(has_module=lambda _n: True, **common)
    assert present["pero"][0] is True
    assert present["calamari"][0] is True


def test_azure_di_needs_httpx_endpoint_and_key() -> None:
    base = {"has_binary": lambda _n: None}
    # httpx absent
    st = _statuses(has_module=lambda _n: False, get_env=lambda _n: "v", **base)
    assert st["azure_di"][0] is False and "[azure]" in st["azure_di"][1]
    # httpx présent, endpoint absent
    st = _statuses(
        has_module=lambda _n: True,
        get_env=lambda n: None if n == "AZURE_DOC_INTEL_ENDPOINT" else "v",
        **base,
    )
    assert (
        st["azure_di"][0] is False
        and "AZURE_DOC_INTEL_ENDPOINT" in st["azure_di"][1]
    )
    # endpoint présent, clé absente
    st = _statuses(
        has_module=lambda _n: True,
        get_env=lambda n: "https://x" if n == "AZURE_DOC_INTEL_ENDPOINT" else None,
        **base,
    )
    assert (
        st["azure_di"][0] is False and "AZURE_DOC_INTEL_KEY" in st["azure_di"][1]
    )
    # endpoint + clé
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: "v", **base)
    assert st["azure_di"][0] is True


def test_mistral_needs_sdk_and_key() -> None:
    base = {"has_binary": lambda _n: None}
    st = _statuses(has_module=lambda _n: False, get_env=lambda _n: "k", **base)
    assert st["mistral"][0] is False and "SDK" in st["mistral"][1]
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: None, **base)
    assert st["mistral"][0] is False and "MISTRAL_API_KEY" in st["mistral"][1]
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: "k", **base)
    assert st["mistral"][0] is True


def test_anthropic_needs_sdk_and_key() -> None:
    base = {"has_binary": lambda _n: None}
    st = _statuses(has_module=lambda _n: False, get_env=lambda _n: "k", **base)
    assert st["anthropic"][0] is False and "SDK" in st["anthropic"][1]
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: None, **base)
    assert st["anthropic"][0] is False and "ANTHROPIC_API_KEY" in st["anthropic"][1]
    st = _statuses(has_module=lambda _n: True, get_env=lambda _n: "k", **base)
    assert st["anthropic"][0] is True


def test_cloud_available_with_sdk_and_key() -> None:
    # Modèle Picarones : un moteur cloud est dispo dès que SDK + clé sont là,
    # SANS masquage par un quelconque « mode public ». La sécurité d'un Space
    # exposé tient à sa visibilité (privé) + présence/absence de la clé.
    st = _statuses(
        has_binary=lambda _n: None,
        has_module=lambda _n: True,
        get_env=lambda _n: "key",
    )
    assert st["mistral"][0] is True
    assert st["openai"][0] is True
    assert st["anthropic"][0] is True


def test_public_engine_kinds_is_free_first_party_socle() -> None:
    # Le socle gratuit exécutable publiquement = precomputed (démo) + tesseract.
    # Fail-closed : aucun moteur cloud (clé) n'y figure → il est gated en 403.
    assert PUBLIC_ENGINE_KINDS == frozenset({"precomputed", "tesseract"})
    cloud = {
        "openai", "anthropic", "mistral", "mistral_ocr", "google_vision", "azure_di"
    }
    assert PUBLIC_ENGINE_KINDS.isdisjoint(cloud)
    # Tout kind du socle public est un moteur réellement connu (pas un typo).
    known = {s.kind for s in engine_statuses()}
    assert PUBLIC_ENGINE_KINDS <= known


def test_ollama_needs_httpx() -> None:
    common = {"has_binary": lambda _n: None, "get_env": lambda _n: None}
    assert _statuses(has_module=lambda _n: False, **common)["ollama"][0] is False
    assert _statuses(has_module=lambda _n: True, **common)["ollama"][0] is True


def test_default_probes_run_without_error() -> None:
    # sondes réelles (env de CI) : ne lève pas, precomputed reste dispo.
    statuses = engine_statuses()
    kinds = {s.kind for s in statuses}
    assert kinds == {
        "precomputed", "tesseract", "kraken", "pero", "calamari", "mistral_ocr",
        "google_vision", "azure_di", "openai", "anthropic", "mistral", "ollama",
    }
    assert next(s for s in statuses if s.kind == "precomputed").available


# --- Segmenteurs (catégorie distincte des moteurs OCR, T2) ---------------------

def test_segmenter_available_when_sdk_present() -> None:
    from cinoc.app.engines import segmenter_statuses

    statuses = {
        s.kind: s
        for s in segmenter_statuses(has_module=lambda n: n in {"paddlex", "httpx"})
    }
    assert statuses["pp_doclayout"].available is True
    assert statuses["remote_segmenter"].available is True


def test_segmenter_unavailable_signals_extra() -> None:
    from cinoc.app.engines import segmenter_statuses

    statuses = {s.kind: s for s in segmenter_statuses(has_module=lambda _n: False)}
    paddle = statuses["pp_doclayout"]
    assert paddle.available is False
    assert "[segment]" in paddle.detail


def test_remote_segmenter_needs_httpx() -> None:
    from cinoc.app.engines import segmenter_statuses

    statuses = {
        s.kind: s for s in segmenter_statuses(has_module=lambda n: n == "httpx")
    }
    remote = statuses["remote_segmenter"]
    assert remote.available is True
    statuses_off = {
        s.kind: s for s in segmenter_statuses(has_module=lambda _n: False)
    }
    assert statuses_off["remote_segmenter"].available is False


def test_segmenter_not_in_ocr_engine_list() -> None:
    # le segmenteur ne doit PAS apparaître parmi les moteurs de transcription
    # (sinon il polluerait le <select> du lanceur OCR).
    kinds = {s.kind for s in engine_statuses()}
    assert "pp_doclayout" not in kinds
    assert "remote_segmenter" not in kinds


def test_ner_status_available_with_spacy() -> None:
    from cinoc.app.engines import ner_status

    status = ner_status(has_module=lambda n: n == "spacy")
    assert status.kind == "ner"
    assert status.available is True


def test_ner_status_unavailable_signals_extra() -> None:
    from cinoc.app.engines import ner_status

    status = ner_status(has_module=lambda _n: False)
    assert status.available is False
    assert "[ner]" in status.detail


def test_ner_not_in_ocr_engine_list() -> None:
    # la NER est un post-traitement, pas un moteur de transcription.
    assert "ner" not in {s.kind for s in engine_statuses()}


def test_correction_status_names_the_capability_not_the_provider() -> None:
    """**L'identifiant dit ce qui est offert, pas qui l'offre.**

    Il portait ``saknussemm``, c'est-à-dire le nom d'une bibliothèque, dans une
    surface que la CLI et le web exposent. Or c'est la *fonction* qui est
    stable : le fournisseur, lui, peut changer. Le détail continue de nommer la
    lib — c'est une information d'installation, et elle reste utile.
    """
    from cinoc.app.engines import correction_status

    status = correction_status(has_module=lambda n: n == "saknussemm")
    assert status.kind == "structured_correction"
    assert status.label == "Post-correction structurée"
    assert "saknussemm" in status.detail, (
        "le détail doit dire quoi installer ; c'est l'identifiant qui n'a pas "
        "à porter le nom d'un fournisseur."
    )
    assert status.available is True


def test_correction_status_says_the_package_is_not_on_pypi() -> None:
    """Anti-silence : ``pip install cinoc[saknussemm]`` va chercher un dépôt git.

    Ne pas le dire ferait chercher longtemps pourquoi un extra « manquant »
    reste manquant après installation.
    """
    from cinoc.app.engines import correction_status

    status = correction_status(has_module=lambda n: False)
    assert status.available is False
    assert "saknussemm" in status.detail
    assert "pas publié" in status.detail or "dépôt" in status.detail

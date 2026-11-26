"""Les modèles d'un fournisseur, **demandés en direct** (couche 6) — web et CLI.

Une liste figée est un cache qu'on a oublié d'invalider (D-268) : celle qui
vivait ici proposait au composeur des modèles retirés par leur fournisseur.
Une seule fonction, :func:`available_models`, interroge l'API (ou le serveur
Ollama) et sert les trois transports : ``/api/models/{provider}`` (composeur),
``cinoc list models`` et ``cinoc run --check``. La vision, l'OCR et le cycle de
vie ne sont dits que si le fournisseur les **déclare** — « inconnu » sinon.

**Aucun modèle par défaut.** Une spec qui ne nomme pas son modèle est refusée
par un message qui liste ceux que la clé permet (:func:`missing_model_message`)
— ou qui dit pourquoi la liste n'a pas pu être lue (pas de clé, SDK absent,
serveur injoignable). Les **tarifs**, eux, restent une donnée (``pricing.json``) :
aucune de ces API ne publie de prix.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pydantic import BaseModel, ConfigDict

from cinoc.adapters.llm._listing import ModelInfo, ModelListingError
from cinoc.domain.errors import CinocError
from cinoc.domain.run_spec import RunSpec

#: Combien de noms un message d'erreur cite avant de résumer.
_CITED = 30


#: Signature commune : réglages de l'instance, nom à résoudre éventuel.
_Lister = Callable[[Mapping[str, object], str | None], tuple[ModelInfo, ...]]


def _openai(
    settings: Mapping[str, object], wanted: str | None
) -> tuple[ModelInfo, ...]:
    del wanted
    from cinoc.adapters.llm.openai import list_models  # noqa: PLC0415

    return list_models(
        base_url=settings.get("base_url"), api_key_env=settings.get("api_key_env")
    )


def _anthropic(
    settings: Mapping[str, object], wanted: str | None
) -> tuple[ModelInfo, ...]:
    del settings
    from cinoc.adapters.llm.anthropic import list_models  # noqa: PLC0415

    return list_models(wanted=wanted)


def _mistral(
    settings: Mapping[str, object], wanted: str | None
) -> tuple[ModelInfo, ...]:
    del settings, wanted
    from cinoc.adapters.llm.mistral import list_models  # noqa: PLC0415

    return list_models()


def _ollama(
    settings: Mapping[str, object], wanted: str | None
) -> tuple[ModelInfo, ...]:
    del wanted
    from cinoc.adapters.llm.ollama import list_models  # noqa: PLC0415

    host = settings.get("host")
    return list_models(host) if isinstance(host, str) and host else list_models()


#: Fournisseur (``kind`` de brique) → lecture en direct de ses modèles.
#: ``mistral_ocr`` partage le compte et la liste de ``mistral``.
_LISTERS: dict[str, _Lister] = {
    "anthropic": _anthropic,
    "mistral": _mistral,
    "mistral_ocr": _mistral,
    "ollama": _ollama,
    "openai": _openai,
}


class ModelChoiceError(CinocError):
    """Une spec ne nomme pas son modèle, ou en nomme un que le fournisseur
    n'offre pas."""


class ModelListing(BaseModel):
    """Les modèles d'un fournisseur, ou la raison pour laquelle on n'a pas pu
    les lire (``unavailable``) — jamais une liste vide qui se lirait
    « aucun modèle »."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str
    models: tuple[ModelInfo, ...] = ()
    unavailable: str | None = None

    def offers(self, model: str) -> bool:
        """``model`` est-il servi — sous son nom, un alias, ou (Ollama) son
        nom sans tag (``:latest``) ?"""
        from cinoc.adapters.llm.ollama import same_model  # noqa: PLC0415

        for listed in self.models:
            if model == listed.name or model in listed.aliases:
                return True
            if self.provider == "ollama" and same_model(model, listed.name):
                return True
        return False


def model_providers() -> tuple[str, ...]:
    """Les briques qui exigent un modèle nommé et savent lister les leurs."""
    return tuple(sorted(_LISTERS))


def available_models(
    provider: str,
    settings: Mapping[str, object] | None = None,
    *,
    wanted: str | None = None,
) -> ModelListing:
    """Les modèles que ``provider`` offre **maintenant**, demandés en direct.

    ``settings`` : les réglages de l'instance (``base_url``/``api_key_env``
    d'``openai``, ``host`` d'``ollama``) — un serveur auto-hébergé liste ses
    propres modèles. ``wanted`` : un nom à résoudre s'il n'est pas listé
    (alias d'Anthropic). Fournisseur inconnu, clé ou SDK absent, serveur
    injoignable → ``unavailable`` dit pourquoi.
    """
    lister = _LISTERS.get(provider)
    if lister is None:
        return ModelListing(
            provider=provider,
            unavailable=f"fournisseur sans liste de modèles : {provider!r} "
            f"(connus : {', '.join(model_providers())})",
        )
    try:
        models = lister(settings or {}, wanted)
    except CinocError as exc:  # ModelListingError, ou réglage illisible
        return ModelListing(provider=provider, unavailable=str(exc))
    return ModelListing(provider=provider, models=models)


def describe_listing(listing: ModelListing) -> str:
    """Une phrase : les modèles disponibles, ou pourquoi on ne les connaît pas."""
    if listing.unavailable is not None:
        return (
            f"Liste des modèles {listing.provider} indisponible : "
            f"{listing.unavailable}."
        )
    if not listing.models:
        return f"Aucun modèle disponible chez {listing.provider}."
    names = [m.name for m in listing.models]
    cited = ", ".join(names[:_CITED])
    more = f" (… et {len(names) - _CITED} autres)" if len(names) > _CITED else ""
    return f"Modèles disponibles chez {listing.provider} : {cited}{more}."


def missing_model_message(adapter_name: str, settings: Mapping[str, object]) -> str:
    """Le refus d'une instance sans modèle : ce qu'il faut écrire, et parmi quoi."""
    provider = adapter_name.split(":", 1)[0]
    return (
        f"{adapter_name} : aucun modèle nommé (adapter_kwargs.{adapter_name}.model)"
        " — aucun modèle par défaut. "
        + describe_listing(available_models(provider, settings))
    )


def _named_model(settings: Mapping[str, object]) -> str | None:
    model = settings.get("model")
    return model if isinstance(model, str) and model.strip() else None


def check_spec_models(spec: RunSpec, *, live: bool) -> tuple[str, ...]:
    """Chaque instance d'un fournisseur nomme son modèle ; ``live`` : et ce
    modèle est offert **maintenant** (D13 du pilote, ``cinoc run --check``).

    Sans modèle → ``ModelChoiceError`` qui liste les disponibles. Modèle absent
    d'une liste lue → ``ModelChoiceError``. Liste **illisible** (fournisseur
    injoignable, pas de clé sur la machine qui relit) → une **note**, pas un
    refus : ``--check`` ne sait pas, il le dit ; refuser serait affirmer
    l'absence d'un modèle qu'on n'a pas pu voir. Rend les notes.

    Les **données de langue** de Tesseract sont ses modèles : elles sont
    vérifiées ici aussi, ``live`` ou non — la sonde est locale
    (:func:`check_spec_languages`). Le même contrôle sert donc ``--check``,
    ``cinoc run`` et le dépôt web.
    """
    notes: list[str] = []
    seen: set[str] = set()
    for pipeline in spec.pipelines:
        for step in pipeline.steps:
            name = step.adapter_name
            provider = name.split(":", 1)[0]
            if provider not in _LISTERS or name in seen:
                continue
            seen.add(name)
            settings = spec.adapter_kwargs.get(name, {})
            model = _named_model(settings)
            if model is None:
                raise ModelChoiceError(missing_model_message(name, settings))
            if not live:
                continue
            listing = available_models(provider, settings, wanted=model)
            if listing.unavailable is not None:
                notes.append(
                    f"{name} : modèle {model!r} non vérifié — {listing.unavailable}."
                )
            elif not listing.offers(model):
                raise ModelChoiceError(
                    f"{name} : modèle {model!r} absent chez {provider}. "
                    + describe_listing(listing)
                )
    return (*notes, *check_spec_languages(spec))


#: Briques qui lisent des données de langue Tesseract (réglage ``lang``).
_TESSERACT_KINDS = frozenset({"tesseract", "tesseract_layout"})


def check_spec_languages(spec: RunSpec) -> tuple[str, ...]:
    """Chaque langue Tesseract demandée est **installée** (D13 du pilote) :
    ``lang: grc+frm`` était déclaré « Spec valide » puis échouait page à page.

    ``tesseract --list-langs`` est lu **une fois** pour la spec. Une langue
    absente → ``ModelChoiceError`` qui la nomme avec les disponibles. Binaire
    introuvable → une **note** (comme une liste de modèles illisible) : la
    disponibilité du moteur est jugée ailleurs, et ``--check`` ne refuse pas
    ce qu'il n'a pas pu voir. Rend les notes.
    """
    from cinoc.adapters.ocr._tesseract_cli import (  # noqa: PLC0415
        installed_languages,
        missing_languages,
    )
    from cinoc.app.modules.registry import socle_params  # noqa: PLC0415

    wanted: dict[str, str] = {}
    for pipeline in spec.pipelines:
        for step in pipeline.steps:
            kind = step.adapter_name.split(":", 1)[0]
            if kind not in _TESSERACT_KINDS or step.adapter_name in wanted:
                continue
            lang = spec.adapter_kwargs.get(step.adapter_name, {}).get("lang")
            if not isinstance(lang, str):
                defaults = {p.name: p.default for p in socle_params(kind) or ()}
                lang = str(defaults.get("lang"))
            wanted[step.adapter_name] = lang
    if not wanted:
        return ()
    tessdata = installed_languages()
    if tessdata is None:
        return tuple(
            f"{name} : langue(s) {lang!r} non vérifiée(s) — binaire tesseract "
            "introuvable."
            for name, lang in sorted(wanted.items())
        )
    for name, lang in sorted(wanted.items()):
        missing = missing_languages(lang, tessdata)
        if missing:
            offered = ", ".join(tessdata.languages) or "aucune"
            raise ModelChoiceError(
                f"{name} : langue(s) Tesseract non installée(s) : "
                f"{', '.join(repr(m) for m in missing)} (lang: {lang!r}). "
                f"Installées : {offered}."
            )
    return ()


__all__ = [
    "ModelChoiceError",
    "ModelInfo",
    "ModelListing",
    "ModelListingError",
    "available_models",
    "check_spec_languages",
    "check_spec_models",
    "describe_listing",
    "missing_model_message",
    "model_providers",
]

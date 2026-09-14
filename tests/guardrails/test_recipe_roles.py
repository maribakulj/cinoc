"""Garde-fou : le catalogue des recettes ne peut pas ignorer une brique du registre.

**Le défaut que ce fichier ferme.** Deux segmenteurs ont été enregistrés —
``tesseract_layout`` et ``doclayout_yolo``, les deux seuls exécutables sur une
machine nue — sans jamais arriver dans le rôle ``segmenter``. Le catalogue ne
proposait donc que ``pp_doclayout`` (qui exige PaddleX) et ``remote_segmenter``
(qui exige une adresse) : **aucune des briques offertes ne tournait**.

C'est la même maladie que les listes de fournisseurs recopiées, sur un autre
support. Le garde-fou existant ne regardait que les noms de fournisseurs LLM ;
celui-ci regarde les rôles.

**Pourquoi un garde-fou et pas une dérivation.** L'ordre des briques d'un rôle
porte une information : *la première est le défaut*. Dériver du registre
détruirait ce choix. La liste reste donc écrite à la main — et confrontée.
"""

from __future__ import annotations

from typing import Any

from cinoc.app.modules.registry import ModuleRegistry, register_default_modules
from cinoc.app.recipes import roles

#: Sac de paramètres généreux : on veut **construire** chaque brique pour lire sa
#: signature, pas la configurer. Une brique qui refuse malgré tout est ignorée —
#: elle exige une valeur qu'aucun défaut ne peut inventer (un sidecar, une
#: source pré-calculée), et elle n'a donc pas sa place dans un catalogue.
_SAC: dict[str, Any] = {
    "label": "x",
    "model": "m",
    "endpoint": "https://exemple.test",
    "source_label": "s",
    "producer": "rules",
    "ocr_sidecar": "",
    "strategy": "columns",
}


def _briques_construisibles() -> dict[str, tuple[frozenset[str], frozenset[str]]]:
    """``kind → (entrées, sorties)`` pour tout ce que le registre sait bâtir."""
    registre = ModuleRegistry()
    register_default_modules(registre)
    out: dict[str, tuple[frozenset[str], frozenset[str]]] = {}
    for kind in sorted(registre.kinds()):
        # Trois formes de nom, parce que la convention ``<kind>:<label>`` a des
        # variantes : ``precomputed`` se nomme d'après ``source_label`` et non
        # ``label``, et le registre vérifie que le module construit porte bien
        # le nom demandé — ce contrôle a d'ailleurs attrapé une vraie erreur de
        # spec (``alto_source:brut`` pour un module sans label).
        for nom in (kind, f"{kind}:x", f"{kind}:s"):
            try:
                module = registre.build(nom, _SAC)
            except Exception:  # noqa: BLE001 — on teste la constructibilité
                continue
            out[kind] = (
                frozenset(t.value for t in module.input_types),
                frozenset(t.value for t in module.output_types),
            )
            break
    return out


def test_every_brick_named_by_a_role_exists() -> None:
    """Une brique nommée mais absente du registre est un menu qui ment."""
    connues = set(_briques_construisibles())
    manquantes = {
        nom: sorted(set(role.briques) - connues)
        for nom, role in roles().items()
        if set(role.briques) - connues
    }
    assert not manquantes, (
        f"rôles nommant des briques inexistantes : {manquantes}."
    )


def test_every_segmenter_of_the_registry_is_offered() -> None:
    """**Le pendant, et c'est lui qui a manqué.**

    Enregistrer un segmenteur sans l'ajouter au rôle le rend invisible aux
    recettes : il existe, il fonctionne, et personne ne peut le choisir.

    ``alto_source`` et ``precomputed_layout`` ont la même signature mais leur
    propre rôle — l'un fait entrer un ALTO existant, l'autre rejoue une mise en
    page figée. Ce ne sont pas des détecteurs, et les proposer comme tels
    tromperait.
    """
    propres = {"alto_source", "precomputed_layout"}
    detecteurs = {
        kind
        for kind, (entrees, sorties) in _briques_construisibles().items()
        if entrees == {"image"} and sorties == {"layout"} and kind not in propres
    }
    offerts = set(roles()["segmenter"].briques)
    oublies = sorted(detecteurs - offerts)
    assert not oublies, (
        f"segmenteurs enregistrés mais absents du rôle 'segmenter' : {oublies}. "
        "Une brique que le catalogue ignore est une brique que personne ne peut "
        "choisir."
    )


def test_a_role_brick_honours_the_role_signature() -> None:
    """Une brique proposée doit **savoir** produire ce que le rôle promet.

    Sinon la recette compose un pipeline que l'exécuteur refusera — et l'erreur
    tombe au run, pas au moment du choix.

    **Un rôle ``fanout`` est l'exception, et elle est de fond** : la sortie qu'il
    déclare est celle de l'*étape*, que l'exécuteur assemble en parcourant les
    régions. La *brique*, elle, ne voit qu'un bloc à la fois — elle rend donc
    soit son texte (``raw_text``, une ligne par bloc), soit son propre
    sous-layout (``layout``, plusieurs lignes, greffées par le fan-out).
    Confondre les deux niveaux ferait rejeter des reconnaisseurs parfaitement
    valides.
    """
    briques = _briques_construisibles()
    par_region = {"raw_text", "layout"}
    fautives: dict[str, list[str]] = {}
    for nom, role in roles().items():
        attendu = par_region if role.fanout else {t.value for t in role.sorties}
        for brique in role.briques:
            signature = briques.get(brique)
            if signature is None:
                continue
            if not attendu & signature[1]:
                fautives.setdefault(nom, []).append(
                    f"{brique} produit {sorted(signature[1])}, le rôle veut "
                    f"{sorted(attendu)}"
                )
    assert not fautives, f"briques incompatibles avec leur rôle : {fautives}."

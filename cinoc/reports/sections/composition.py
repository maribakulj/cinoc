"""Section composition : **ce qu'il y a exactement dans chaque chaîne** (couche 7).

Le rapport disait quelle chaîne gagne, jamais **de quoi elle est faite**. Un nom
comme ``T_saknussemm_vision_bert`` porte une intention, pas un contenu : il ne
dit ni quel segmenteur, ni quel modèle, ni quels réglages. Comparer deux chiffres
sans pouvoir lire les deux montages, c'est comparer deux boîtes noires — et un
banc existe précisément pour ouvrir les boîtes.

Tout vient du ``RunManifest`` : ``pipeline_specs`` (le DAG déclaré) et
``adapter_kwargs`` (les paramètres de construction). Rien n'est reconstitué ni
deviné ; un champ absent n'est pas affiché.

Trois choses sont rendues visibles parce qu'elles changent le résultat et ne se
lisent nulle part ailleurs :

* **la forme du DAG** — une étape qui prend son entrée d'une autre que la
  précédente, ou qui en réunit deux, n'est pas une chaîne linéaire, et le nom ne
  le dit pas ;
* **le fan-out** — une étape marquée ``par région`` s'exécute *une fois par
  bloc* ; c'est la différence entre lire une page et lire trente morceaux ;
* **les paramètres réels** — ``psm``, ``model``, ``role``, ``qe_skip``… Deux
  chaînes au nom voisin peuvent ne différer que par un nombre, et c'est alors ce
  nombre, seul, que le banc mesure.
"""

from __future__ import annotations

from typing import Any

from cinoc.evaluation.result import RunResult
from cinoc.reports.engine_badges import engine_cell, engine_order
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext

#: Paramètres masqués : ils n'apprennent rien sur ce que fait la brique.
#: ``label`` ne sert qu'à nommer les fichiers du workspace.
_BRUIT = frozenset({"label", "source_label"})


def _params(kwargs: dict[str, Any]) -> str:
    """``model=… psm=6`` — les réglages qui distinguent deux briques jumelles."""
    utiles = {k: v for k, v in sorted(kwargs.items()) if k not in _BRUIT}
    if not utiles:
        return ""
    return " · ".join(f"{escape(k)}={escape(str(v))}" for k, v in utiles.items())


def _flux(step: dict[str, Any], rang: int, precedent: str | None) -> str:
    """D'où l'étape tire son entrée, **quand ce n'est pas l'évidence**.

    Une étape qui suit simplement la précédente n'a rien à signaler ; une qui
    remonte plus haut, ou qui réunit deux sources, change la forme du graphe et
    doit se voir.
    """
    fusion = step.get("merge_from") or []
    if fusion:
        return "⊕ " + " + ".join(escape(str(s)) for s in fusion)
    depuis = step.get("inputs_from") or {}
    sources = {str(v) for v in depuis.values()}
    if not sources or (rang and sources == {precedent}):
        return ""
    return "← " + ", ".join(escape(s) for s in sorted(sources))


def _etape(
    step: dict[str, Any],
    rang: int,
    precedent: str | None,
    kwargs: dict[str, Any],
    lang: str,
) -> str:
    adapter = str(step.get("adapter_name", ""))
    reglages = _params(kwargs.get(adapter) or {})
    marques: list[str] = []
    if step.get("fanout"):
        marques.append(localized(lang, "par région", "per region"))
    if step.get("crop"):
        marques.append(localized(lang, "découpe", "crops"))
    flux = _flux(step, rang, precedent)
    entrees = " · ".join(escape(str(t)) for t in step.get("input_types") or [])
    sorties = " · ".join(escape(str(t)) for t in step.get("output_types") or [])
    suffixe = (
        f' <span class="muted">{escape(" · ".join(marques))}</span>'
        if marques
        else ""
    )
    return (
        "<tr>"
        f'<td class="lbl">{rang + 1}</td>'
        f'<td class="lbl"><code>{escape(adapter)}</code>{suffixe}</td>'
        f'<td class="lbl">{entrees} → {sorties}</td>'
        f'<td class="lbl">{flux}</td>'
        f'<td class="lbl">{reglages}</td>'
        "</tr>"
    )


class CompositionSection:
    """Rend, pour chaque pipeline, la suite d'étapes réellement exécutée."""

    @property
    def name(self) -> str:
        return "composition"

    @property
    def requires(self) -> tuple[str, ...]:
        return ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        specs = getattr(result.manifest, "pipeline_specs", None) or []
        if not specs:
            return None
        lang = ctx.lang
        kwargs = dict(getattr(result.manifest, "adapter_kwargs", None) or {})
        # L'ordre vient de ``result.pipelines`` — **le même partout** : c'est ce
        # qui fait que le badge « A » désigne la même chaîne d'une section à
        # l'autre. Le recalculer autrement ici ferait mentir les lettres.
        ordre = engine_order(p.pipeline for p in result.pipelines)
        titres = (
            localized(lang, "étape", "step"),
            localized(lang, "brique", "module"),
            localized(lang, "consomme → produit", "consumes → produces"),
            localized(lang, "entrée", "input"),
            localized(lang, "réglages", "settings"),
        )
        entete = "".join(f"<th>{escape(t)}</th>" for t in titres)

        blocs: list[str] = []
        for spec in sorted(
            (dict(s) for s in specs),
            key=lambda s: ordre.get(str(s.get("name", "")), 10_000),
        ):
            nom = str(spec.get("name", ""))
            steps = [dict(s) for s in spec.get("steps") or []]
            lignes: list[str] = []
            precedent: str | None = None
            for rang, step in enumerate(steps):
                lignes.append(_etape(step, rang, precedent, kwargs, lang))
                precedent = str(step.get("id", ""))
            depart = " · ".join(
                escape(str(t)) for t in spec.get("initial_inputs") or []
            )
            libelle = localized(lang, "entrée du run", "run input")
            blocs.append(
                f"<h3>{engine_cell(nom, ordre.get(nom, 0))}</h3>\n"
                + (
                    f'<p class="muted">{libelle} : {depart}</p>\n'
                    if depart
                    else ""
                )
                + f'<table class="tbl"><thead><tr>{entete}</tr></thead>'
                + f"<tbody>{''.join(lignes)}</tbody></table>"
            )

        titre = localized(lang, "Composition des chaînes", "Pipeline composition")
        chapeau = localized(
            lang,
            "Ce que chaque chaîne exécute réellement, étape par étape — tiré du "
            "manifeste, pas reconstitué. La colonne <em>entrée</em> n'est "
            "renseignée que lorsqu'une étape ne suit pas simplement la "
            "précédente : <code>←</code> désigne l'étape dont elle tire son "
            "entrée, <code>⊕</code> une fusion de plusieurs.",
            "What each pipeline actually runs, step by step — read from the "
            "manifest, not reconstructed. The <em>input</em> column is filled "
            "only when a step does not simply follow the previous one: "
            "<code>←</code> names the step it draws from, <code>⊕</code> a "
            "merge of several.",
        )
        return Html(
            f"<h2>{escape(titre)}</h2>\n<p>{chapeau}</p>\n" + "\n".join(blocs)
        )


__all__ = ["CompositionSection"]

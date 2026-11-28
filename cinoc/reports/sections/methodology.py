"""Section méthodologie & reproductibilité (couche 7).

Appendice **toujours visible** (hors onglets, comme le glossaire) : explicite le
corpus, les moteurs, les métriques, les **vues d'évaluation** (profil de
normalisation, caractères exclus, dimensions ignorées, avertissements),
l'environnement (binaires, dépendances, versions de modules) et les conventions
de calcul — tout dérivé du ``RunManifest`` et du ``RunResult`` (aucune valeur
fabriquée ; un champ absent n'est pas affiché).
"""

from __future__ import annotations

from cinoc.domain.artifacts import ArtifactType
from cinoc.domain.evaluation import EvaluationView
from cinoc.evaluation.result import RunResult
from cinoc.reports.html import escape, localized
from cinoc.reports.section import Html, SectionContext
from cinoc.reports.sections._profile_text import profile_definition

#: Une vue ne normalise que du texte : sur une vue structure ou entités, le
#: profil n'a rien à préparer, la ligne « Normalisation » mentirait.
_TEXT_TYPES = frozenset({ArtifactType.RAW_TEXT, ArtifactType.CORRECTED_TEXT})


def _kv(label: str, value: str) -> str:
    return f'<tr><td class="lbl">{escape(label)}</td><td class="lbl">{value}</td></tr>'


def _locks(title: str, mapping: dict[str, str]) -> str:
    """``<details>`` natif d'un lock ``{nom: version}`` ; vide → ``""``."""
    if not mapping:
        return ""
    rows = "".join(
        f'<tr><td class="lbl">{escape(k)}</td><td class="disp">{escape(v)}</td></tr>'
        for k, v in sorted(mapping.items())
    )
    return (
        f'<details><summary class="muted">{escape(title)}</summary>\n'
        f'<table class="data compact"><tbody>{rows}</tbody></table></details>'
    )


def _view_block(view: EvaluationView, lang: str) -> str:
    """Métadonnées méthodologiques d'une vue (champs présents seulement)."""
    rows = ""
    if view.description:
        rows += _kv(
            localized(lang, "Description", "Description"), escape(view.description)
        )
    if view.target_step is not None:
        # Une vue qui ne note pas la sortie finale doit le dire : sans cette
        # ligne, deux vues d'un même pipeline sembleraient noter la même chose.
        rows += _kv(
            localized(lang, "Étape notée", "Scored step"), escape(view.target_step)
        )
    # Le nom **et** la définition du profil, dérivée de ses leviers (D-285) :
    # c'est la convention sous laquelle le chiffre de la vue a été calculé.
    # ``char_exclude`` y est dit aussi (« puis caractères exclus »).
    if view.candidate_types & _TEXT_TYPES:
        rows += _kv(
            localized(lang, "Normalisation", "Normalisation"),
            profile_definition(view, lang),
        )
    if view.metric_names:
        rows += _kv(
            localized(lang, "Métriques", "Metrics"),
            escape(", ".join(view.metric_names)),
        )
    if view.ignored_dimensions:
        rows += _kv(
            localized(lang, "Dimensions ignorées", "Ignored dimensions"),
            escape(", ".join(view.ignored_dimensions)),
        )
    for w in view.warnings:
        rows += _kv(localized(lang, "Avertissement", "Warning"), escape(w))
    return (
        f"<h3>{escape(view.name)}</h3>\n"
        f'<table class="data compact"><tbody>{rows}</tbody></table>\n'
    )


class MethodologySection:
    """Méthodologie & reproductibilité — appendice toujours visible."""

    name = "methodology"
    requires: tuple[str, ...] = ()

    def render(self, result: RunResult, ctx: SectionContext) -> Html | None:
        m = result.manifest
        lang = ctx.lang
        eval_docs = len({d.document_id for d in result.documents})
        engines = sorted({p.pipeline for p in result.pipelines})
        metrics = sorted({s.metric for p in result.pipelines for s in p.aggregate})
        # Documents : taille du corpus ; nombre réellement évalué si différent.
        docs_val = str(m.n_documents)
        if eval_docs and eval_docs != m.n_documents:
            docs_val += localized(
                lang, f" (évalués : {eval_docs})", f" (evaluated: {eval_docs})"
            )
        run_rows = (
            _kv(localized(lang, "Corpus", "Corpus"), escape(m.corpus_name))
            + _kv(localized(lang, "Documents", "Documents"), escape(docs_val))
            + _kv(
                localized(lang, "Moteurs", "Engines"),
                escape(", ".join(engines)) or "—",
            )
            + _kv(
                localized(lang, "Métriques", "Metrics"),
                escape(", ".join(metrics)) or "—",
            )
            + _kv(
                localized(lang, "Date", "Date"),
                escape(m.completed_at.date().isoformat()),
            )
            + _kv(
                localized(lang, "Version du code", "Code version"),
                escape(m.code_version),
            )
        )
        views = "".join(_view_block(v, lang) for v in m.view_specs)
        views_html = (
            f"<h2>{localized(lang, 'Vues d’évaluation', 'Evaluation views')}</h2>\n"
            f"{views}"
            if views
            else ""
        )
        env = (
            _locks(
                localized(lang, "Binaires système", "System binaries"),
                m.system_binaries_lock,
            )
            + _locks(
                localized(lang, "Versions de modules", "Module versions"),
                m.module_versions,
            )
            + _locks(
                localized(lang, "Modèles servis", "Served models"),
                {name: ", ".join(models) for name, models in m.served_models.items()},
            )
            + _locks(
                localized(lang, "Dépendances", "Dependencies"),
                m.dependencies_lock,
            )
            + _locks(
                localized(lang, "Base Unicode", "Unicode database"),
                (
                    {"unicodedata": m.unicode_version}
                    if m.unicode_version is not None
                    else {}
                ),
            )
        )
        env_html = (
            f"<h2>{localized(lang, 'Environnement', 'Environment')}</h2>\n{env}"
            if env
            else ""
        )
        # La phrase sur les unités en échec suit la politique **du run**
        # (D-288) : « omis de ses agrégats » est faux sous ``empty_page``.
        policy = result.manifest.failure_policy
        code = f"<code>failure_policy: {policy}</code>"
        if policy == "empty_page":
            failed_fr = (
                "Un document qu’un moteur n’a pas produit (unité en échec) est "
                "noté comme une <b>page vide</b> — les comptes de sa référence "
                "face à une sortie sans texte : un CER de 1, une exactitude "
                "de 0, un taux d’insertion de 0 ; une sortie partielle ou "
                f"tronquée est notée telle que produite ({code})."
            )
            failed_en = (
                "A document an engine did not produce (failed unit) is scored "
                "as an <b>empty page</b> — the counts of its reference against "
                "an output with no text: a CER of 1, an accuracy of 0, an "
                "insertion rate of 0; a partial or truncated output is scored "
                f"as produced ({code})."
            )
        else:
            failed_fr = (
                "Un document qu’un moteur n’a pas produit (unité en échec) est "
                "<b>exclu</b> de ses agrégats, sans score factice ; une sortie "
                "<b>partielle</b> ou <b>tronquée</b> n’y est pas notée non plus "
                "(sa statistique est gardée à part) ; l’agrégat porte alors "
                "« n notés / n attendus » et sa couverture par motif, la "
                "qualité opérationnelle du résultat notant les sorties telles "
                f"que produites ({code})."
            )
            failed_en = (
                "A document an engine did not produce (failed unit) is "
                "<b>left out</b> of its aggregates, with no fake score; a "
                "<b>partial</b> or <b>truncated</b> output is not scored either "
                "(its statistic is kept apart); the aggregate then shows “n "
                "scored / n expected” and its coverage by reason, the result’s "
                f"operational quality scoring outputs as produced ({code})."
            )
        conventions = localized(
            lang,
            "<b>Conventions.</b> Les métriques d’erreur (CER, WER, MER) sont des "
            "distances d’édition rapportées à la référence (plus bas = mieux), "
            "calculées sur les deux textes préparés par le profil de la vue "
            "(ci-dessus) ; leurs définitions sont au glossaire, où chaque "
            "métrique porte son unité et sa catégorie — <b>établie</b> (conforme "
            "à une référence nommée), <b>adaptée</b> (variante justifiée), "
            "<b>exploratoire</b> (sans référence nommée) : seules les établies "
            "sont classées et entrent dans la famille de Holm des tests. Les "
            "durées sont le wall-clock de l’exécuteur, une fois par unité ; une "
            "unité reprise d’une archive garde celle de sa première exécution, "
            "marquée ↺ et séparée des durées mesurées par ce run. "
            "Les agrégats "
            "par moteur sont <b>micro</b> : la métrique calculée sur les "
            "<b>comptes cumulés</b> des documents notés — pour un taux d’erreur, "
            "Σ erreurs / Σ longueurs de référence (un long document pèse à "
            "proportion de sa taille, une page à référence vide y apporte ses "
            "insertions) ; pour un F1, celui de (Σ vrais positifs, Σ faux "
            "positifs, Σ manqués) ; pour une exactitude, max(0, 1 − Σ erreurs / "
            "Σ longueurs), la borne s’appliquant au corpus et le taux non tronqué "
            "étant écrit à côté quand elle est atteinte. Les comptes S, D, I d’un "
            "alignement sont ceux qui maximisent les substitutions parmi les "
            "alignements de coût minimal (« ab » → « ba » : deux substitutions, "
            "pas une suppression et une insertion) ; leur somme — donc CER et "
            "WER — est celle de jiwer, mais <b>MER, cMER, taux d’insertion et "
            "de suppression peuvent s’écarter de jiwer</b> sur ces ex æquo, "
            "que jiwer départage selon l’ordre de son calcul. "
            "L’IC 95 % (mode détaillé) d’un taux "
            "d’erreur est un bootstrap de ce même ratio, documents "
            "rééchantillonnés ; celui d’un MER, dont le dénominateur dépend de la "
            "sortie, n’est pas estimable. Une moyenne des taux par document "
            "(macro) est nommée comme telle (« moyen », µ). Une valeur absente "
            "est rendue « — », jamais interprétée comme zéro ; une valeur "
            "indéfinie (dénominateur nul) est rendue « indéfini ». "
            f"{failed_fr} Une "
            "vue qui ne nomme pas de profil reçoit <code>flat_text</code> ; la "
            "comparaison brute se demande explicitement "
            "(<code>normalization_profile: null</code>).",
            "<b>Conventions.</b> Error metrics (CER, WER, MER) are edit distances "
            "relative to the reference (lower is better), computed on both texts "
            "as prepared by the view’s profile (above); their definitions are in "
            "the glossary, where each metric carries its unit and its category — "
            "<b>established</b> (conforming to a named reference), <b>adapted</b> "
            "(a justified variant), <b>exploratory</b> (no named reference): only "
            "established metrics are ranked and enter the Holm family of tests. "
            "Durations are the executor’s wall-clock, once per unit; a unit "
            "resumed from an archive keeps the one of its first execution, "
            "marked ↺ and kept apart from the durations this run measured. "
            "Per-engine aggregates "
            "are <b>micro</b>: the metric computed on the <b>summed counts</b> "
            "of the scored documents — for an error rate, Σ errors / Σ reference "
            "lengths (a long document weighs in proportion to its size, a page "
            "with an empty reference brings its insertions); for an F1, the F1 "
            "of (Σ true positives, Σ false positives, Σ missed); for an "
            "accuracy, max(0, 1 − Σ errors / Σ lengths), the bound applying to "
            "the corpus and the untruncated rate being written beside it when "
            "it is reached. The S, D, I counts of an alignment are those that "
            "maximise substitutions among minimum-cost alignments (“ab” → "
            "“ba”: two substitutions, not a deletion and an insertion); their "
            "sum — hence CER and WER — is jiwer’s, but <b>MER, cMER, insertion "
            "and deletion rates can differ from jiwer</b> on such ties, which "
            "jiwer breaks by its traversal order. The 95% CI "
            "(detailed mode) of an error rate is a bootstrap of that same "
            "ratio, resampling documents; that of a MER, whose denominator "
            "depends on the output, is not estimable. A mean of per-document "
            "rates (macro) is named as such (“mean”, µ). A missing value "
            "renders as “—”, never as zero; an undefined value (zero "
            "denominator) renders as “undefined”. "
            f"{failed_en} A view naming no profile "
            "gets <code>flat_text</code>; raw comparison is requested explicitly "
            "(<code>normalization_profile: null</code>).",
        )
        title = localized(
            lang, "Méthodologie & reproductibilité", "Methodology & reproducibility"
        )
        intro = localized(
            lang,
            "Ce que mesure le benchmark, sur quel corpus, avec quels moteurs et "
            "quelles conventions — pour interpréter et reproduire les résultats.",
            "What the benchmark measures, on which corpus, with which engines and "
            "conventions — to interpret and reproduce the results.",
        )
        return Html(
            f"<h1>{title}</h1>\n<p class=\"muted\">{intro}</p>\n"
            f'<table class="data compact"><tbody>{run_rows}</tbody></table>\n'
            f"{views_html}{env_html}"
            f'<p class="muted">{conventions}</p>\n'
        )


__all__ = ["MethodologySection"]

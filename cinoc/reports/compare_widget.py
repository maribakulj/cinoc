"""Widget « comparer un run » (couche 7) — **client-side, autonome, déterministe**.

Trois morceaux insérés en fin de ``<body>`` du rapport :

1. un **bouton** + un ``<input type=file>`` caché ;
2. les **données CER du run courant** dans un bloc ``type="application/json"``
   **inerte** (non exécuté → hors ``script-src``), échappé contre toute rupture
   de ``</script>`` ;
3. le **script statique** ``_assets/compare.js`` inliné (autonomie : il voyage
   dans le document).

Le script étant **constant**, son empreinte ``sha256`` (``compare_script_hash``)
est ajoutée à la CSP des seules réponses ``/reports/`` (l'inline reste interdit
partout ailleurs — la CSP reste un contrat). Le visiteur charge un second
``RunResult`` JSON depuis son disque : tout se passe **dans le navigateur**, zéro
réseau (cf. invariant d'autonomie du rapport).
"""

from __future__ import annotations

import json

from cinoc.evaluation.result import RunResult
from cinoc.reports.embedded import inline_script, script_hash
from cinoc.reports.section import Html


def compare_script_hash() -> str:
    """Empreinte CSP du script de comparaison (délègue à ``embedded``)."""
    return script_hash("compare.js")


def _cer_by_key(result: RunResult) -> dict[str, float]:
    """CER agrégé par ``"<pipeline> · <view>"`` (clé de jointure entre deux runs)."""
    out: dict[str, float] = {}
    for pipeline in result.pipelines:
        for score in result.principal_aggregate(pipeline):
            if score.metric == "cer" and score.value is not None:
                out[f"{pipeline.pipeline} · {pipeline.view}"] = score.value
    return out


def _safe_json(data: object) -> str:
    """JSON ASCII avec ``<``/``>``/``&`` échappés (anti-rupture de ``</script>``)."""
    return (
        json.dumps(data, ensure_ascii=True, sort_keys=True)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def compare_widget(result: RunResult) -> Html:
    """Bouton + données du run courant + script — à insérer en fin de ``<body>``."""
    payload = _safe_json({"cer": _cer_by_key(result)})
    return Html(
        '<div class="compare-bar">'
        '<button id="cinoc-compare-btn" class="compare-btn" type="button">'
        "⇄ Comparer un run</button>"
        '<input id="cinoc-compare-file" type="file" '
        'accept=".json,application/json" hidden>'
        "</div>"
        f'<script id="cinoc-compare-data" type="application/json">{payload}</script>'
        f"{inline_script('compare.js')}"
    )


__all__ = ["compare_script_hash", "compare_widget"]

"""Tranche 1b — les quatre issues d'une ligne de correction structurée (§ 2.1 f).

Révision n° 7 du ``CONTRATS.md``. Une ligne de ``saknussemm`` finit en quatre
classes ; les trois premières sont des **décisions du correcteur** (l'unité
reste complète, sa sortie est notée normalement), la quatrième est un
**incident d'exécution** :

- **corrigée** (``corrected`` avec texte modifié) ; ``review_required`` en est
  une sous-classe, comptée à part ;
- **abstention volontaire** (``corrected`` avec ``final_text == source_text``) ;
- **refus technique** (code de ``FALLBACK_REASON_CODES`` hors
  ``all_attempts_exhausted`` et ``chunk_error_absorbed``) ;
- **repli** (``all_attempts_exhausted``, ``chunk_error_absorbed``) : seule
  classe qui rend l'étape **partielle**. Une unité 100 % en repli n'est jamais
  ``ok``.

Les rapports sont produits par la **vraie** bibliothèque : l'étape testée est
l'adaptateur ``SaknussemmCorrector`` du produit, branché par l'API publique de
découverte, avec un client de complétion **scripté par identifiant de ligne**
(un client structuré en mémoire : aucun réseau). La classe de chaque ligne se
lit à son statut et à son code de raison, jamais à son texte : le même texte
final (la source) sort des trois premières classes et du repli.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from cinoc.adapters.extension import (
    Artifact,
    ArtifactType,
    CanonicalLayout,
    RunContext,
    RunControl,
    StepOutput,
    layout_step_output,
)
from cinoc.domain.layout import LayoutPage, Line, Region
from cinoc.evaluation.result import RunResult
from tests.adversarial._contrat import (
    axes,
    composante,
    composante_partielle,
    comptes_lignes,
    couverture,
    somme_comptes,
    statistique,
    statistique_partielle,
    support_micro,
)

from ._kit import (
    T,
    aggregate,
    corpus,
    execute,
    pipeline,
    registry_with,
    spec,
    step,
    text_view,
)

pytestmark = [pytest.mark.tranche("1b"), pytest.mark.valide]

PARTIAL = "partial"  # UnitOutcome (§ 2.1 e, f)
SOURCE = "le ſoleil luit"  # ſ long : une erreur de l'OCR
REFERENCE = "le soleil luit"
TOO_DIFFERENT = "zzzz yyyy xxxx wwww vvvv"

#: Texte de chaque ligne, par document (une liste = une page).
LAYOUTS: dict[str, list[list[tuple[str, str]]]] = {
    # corrigée, review_required, abstention, refus, refus, abstention.
    "mix": [
        [
            ("m1", SOURCE),
            ("m2", "en 1789 il vint"),
            ("m3", "rien a dire ici"),
            ("m4", "il fait beau auiourd hui"),
            ("m6", "les chats dorment bien"),
            ("m7", "les chats dorment bien aussi"),
        ]
    ],
    "abst": [[("a1", SOURCE)]],
    "refus": [[("r1", SOURCE)]],
    "repli": [[("f1", SOURCE)]],
    # page 1 : le client panne (repli) ; page 2 : deux corrections.
    "part": [
        [("p1", SOURCE), ("p2", "rien a dire ici"), ("p3", "la ſeine coule")],
        [("q1", SOURCE), ("q2", "la ſeine coule")],
    ],
}


#: Ce que le client répond, par identifiant de ligne : un texte proposé, ou
#: ``fail`` (le client lève : repli ``chunk_error_absorbed``), ou ``transient``
#: (panne de transport : repli ``all_attempts_exhausted`` après les essais).
#: Une ligne absente du script reçoit sa source inchangée.
def _script(failure: str = "fail") -> dict[str, str]:
    return {
        "m1": REFERENCE,
        "m2": "en 1798 il vint",  # chiffres modifiés : correction à revoir
        "m4": TOO_DIFFERENT,  # trop éloignée de la source
        "m6": "les chats dorment bien aussi les chats dorment bien aussi",
        "r1": TOO_DIFFERENT,
        "f1": failure,
        "p1": failure,
        "q1": REFERENCE,
        "q2": "la seine coule",
    }


class _ScriptedClient:
    """``StructuredCompletionClient`` en mémoire, scripté par ``line_id``."""

    def __init__(self, script: Mapping[str, str]) -> None:
        self._script = script
        self.responses: list[Any] = []

    async def complete_structured(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_payload: dict[str, Any],
        json_schema: dict[str, Any],
        temperature: float = 0.0,
    ) -> tuple[dict[str, Any], None]:
        from saknussemm.core.protocols import (  # noqa: PLC0415
            ProviderTransientError,
        )
        from saknussemm.errors import ProviderError  # noqa: PLC0415

        lines = user_payload["lines"]
        for line in lines:
            order = self._script.get(line["line_id"])
            if order == "fail":
                raise ProviderError("panne simulée")
            if order == "transient":
                raise ProviderTransientError("503 simulé")
        answered = [
            {
                "line_id": line["line_id"],
                "corrected_text": self._script.get(line["line_id"], line["ocr_text"]),
            }
            for line in lines
        ]
        self.responses.append({"model": model, "lines": answered})
        return {"lines": answered}, None

    def usage(self) -> None:
        return None


class _Pages:
    """Segmenteur de test : rend la mise en page prévue pour le document."""

    name = "ce_pages"
    version = "1.0"
    input_types = frozenset({ArtifactType.IMAGE})
    output_types = frozenset({ArtifactType.LAYOUT})

    def execute(
        self,
        inputs: Mapping[ArtifactType, Artifact],
        params: object,
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        pages = tuple(
            LayoutPage(
                regions=(
                    Region(
                        id=f"{page[0][0]}_r",
                        lines=tuple(Line(id=i, text=t) for i, t in page),
                    ),
                )
            )
            for page in LAYOUTS[context.document_id]
        )
        return layout_step_output(CanonicalLayout(pages=pages), context, self.name)


def _corrector(client: _ScriptedClient) -> object:
    """L'adaptateur **réel** ``SaknussemmCorrector`` ; seul le fournisseur est
    remplacé par le client scripté (le producteur de la bibliothèque, ses
    gardes, sa revue et son rapport restent ceux de ``saknussemm``)."""
    from saknussemm.producers.llm_edit import LLMEditProducer  # noqa: PLC0415

    from cinoc.adapters.layout.saknussemm_correct import (  # noqa: PLC0415
        SaknussemmCorrector,
    )

    class _Corrector(SaknussemmCorrector):
        PARAMS = ()  # instance déjà construite : aucun réglage de spec

        @property
        def name(self) -> str:
            return "ce_sak"

        def _build_producer(self, control: RunControl) -> tuple[Any, Any]:
            return LLMEditProducer(client, api_key="", model="m"), client

    return _Corrector(label="ce", producer="ollama", model="m")


def _run(
    tmp_path: Path,
    documents: tuple[str, ...],
    *,
    failure: str = "fail",
    references: Mapping[str, str] | None = None,
) -> RunResult:
    """Un pipeline ``p`` (segmenteur de test → correcteur réel) sur ``documents``."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    pairs = dict.fromkeys(documents, REFERENCE) | dict(references or {})
    chain = pipeline(
        "p",
        step("seg", "ce_pages", out_type=T.LAYOUT),
        step("corr", "ce_sak", in_type=T.LAYOUT, out_type=T.CORRECTED_TEXT),
    )
    return execute(
        spec(
            corpus(tmp_path, pairs),
            [chain],
            [text_view(candidates=(T.CORRECTED_TEXT,))],
        ),
        registry_with(_Pages(), _corrector(_ScriptedClient(_script(failure)))),
    )


def _units(result: RunResult) -> dict[str, Any]:
    return {u.document_id: u for u in result.usage}


MIX = {
    "corrected": 1,
    "review_required": 1,
    "abstained": 2,
    "refused": {"too_different_from_source": 1, "absorbs_next_line": 1},
    "fallback": {},
}
ABST = {
    "corrected": 0,
    "review_required": 0,
    "abstained": 1,
    "refused": {},
    "fallback": {},
}
REFUS = {
    "corrected": 0,
    "review_required": 0,
    "abstained": 0,
    "refused": {"too_different_from_source": 1},
    "fallback": {},
}
REPLI = {
    "corrected": 0,
    "review_required": 0,
    "abstained": 0,
    "refused": {},
    "fallback": {"chunk_error_absorbed": 1},
}
PART = {
    "corrected": 2,
    "review_required": 0,
    "abstained": 0,
    "refused": {},
    "fallback": {"chunk_error_absorbed": 3},
}


def _same(comptes: dict[str, Any], attendu: dict[str, Any], doc: str) -> None:
    """Compare des comptes de lignes, exactement. Arbitrage du 28/11 (§ 2.1 f,
    révision n° 7) : ``corrected`` et ``review_required`` sont des classes
    **disjointes** — le total des corrections est leur somme."""
    assert comptes == attendu, (doc, comptes)


# --------------------------------------------------------------------------
# Les quatre classes sont comptées par unité et par pipeline.
# --------------------------------------------------------------------------


def test_f_quatre_classes__comptees_par_unite_et_par_pipeline(tmp_path: Path) -> None:
    """§ 2.1 f : lignes corrigées, ``review_required``, abstentions, refus par
    code, replis par code, **par unité** (``DocumentUsage``) et **par pipeline**
    (somme des unités). ``mix`` : 1 corrigée, 1 à revoir (chiffres changés),
    2 abstentions, 2 refus (``too_different_from_source``, ``absorbs_next_line``)
    ; ``abst`` : 1 abstention ; ``refus`` : 1 refus ; ``repli`` : 1 repli ;
    ``part`` : page 1 en repli (ses 3 lignes, dont ``p2`` qui n'a pourtant rien
    à corriger : le repli est celui du lot, pas de la ligne), page 2 corrigée
    (2 lignes). Total du pipeline : 3 corrigées, 1 à revoir, 3 abstentions,
    3 refus, 4 replis."""
    result = _run(tmp_path, tuple(LAYOUTS))
    units = _units(result)
    attendu = {
        "mix": MIX,
        "abst": ABST,
        "refus": REFUS,
        "repli": REPLI,
        "part": PART,
    }
    par_unite = {doc: comptes_lignes(units[doc]) for doc in LAYOUTS}
    for doc, comptes in par_unite.items():
        _same(comptes, attendu[doc], doc)
    (entry,) = result.pipelines
    _same(
        comptes_lignes(entry),
        {
            "corrected": sum(a["corrected"] for a in attendu.values()),
            "review_required": 1,
            "abstained": 3,
            "refused": {"too_different_from_source": 2, "absorbs_next_line": 1},
            "fallback": {"chunk_error_absorbed": 4},
        },
        "pipeline",
    )
    # Le total du pipeline est la somme des unités, compte par compte.
    total = somme_comptes(list(par_unite.values()))
    publie = comptes_lignes(entry)
    assert (publie["review_required"], publie["abstained"]) == (
        total["review_required"],
        total["abstained"],
    )
    assert (
        publie["refused"] == total["refused"]
        and publie["fallback"] == total["fallback"]
    )


def test_f_seul_le_repli_rend_lunite_partielle(tmp_path: Path) -> None:
    """§ 2.1 f : corrigée, abstention et refus technique laissent l'unité
    **complète** (``ok``, observation notée) ; le repli, seul, la rend
    ``partial``. ``part`` (page 1 en repli) est partielle même si la page 2 est
    corrigée ; ``repli`` (toutes ses lignes en repli) ne passe jamais pour
    ``ok``."""
    result = _run(tmp_path, tuple(LAYOUTS))
    outcomes = {doc: str(unit.outcome) for doc, unit in _units(result).items()}
    assert outcomes == {
        "mix": "ok",
        "abst": "ok",
        "refus": "ok",
        "repli": PARTIAL,
        "part": PARTIAL,
    }, outcomes


@pytest.mark.parametrize(
    ("failure", "code"),
    [
        pytest.param("fail", "chunk_error_absorbed", id="chunk_error_absorbed"),
        pytest.param(
            "transient", "all_attempts_exhausted", id="all_attempts_exhausted"
        ),
    ],
)
def test_f_unite_entierement_en_repli__jamais_ok_et_observation_partielle(
    tmp_path: Path, failure: str, code: str
) -> None:
    """§ 2.1 f : une unité dont **toutes** les lignes sont en repli est
    ``partial``, sans aucune correction, quel que soit le code de repli (les
    deux codes de l'incident d'exécution). Son observation porte
    ``partial_output`` et n'est pas notée par défaut ; sa statistique, calculée
    sur le texte produit (la source, une substitution sur 14 caractères), est
    gardée dans ``stat_partielle``. La qualité conditionnelle est indéfinie (0
    observation complète, couverture 1/1 partielle). ``all_attempts_exhausted``
    passe par les essais de la bibliothèque (une douzaine de secondes de
    délais d'attente)."""
    result = _run(tmp_path, ("repli",), failure=failure)
    (unit,) = result.usage
    assert str(unit.outcome) == PARTIAL, unit
    comptes = comptes_lignes(unit)
    assert comptes["fallback"] == {code: 1}
    assert (comptes["review_required"], comptes["abstained"], comptes["refused"]) == (
        0,
        0,
        {},
    )
    assert comptes["corrected"] == 0
    (doc,) = result.documents
    (score,) = doc.scores
    assert axes(score)[2] == "partial_output"
    assert score.value is None and statistique(score) is None
    assert composante_partielle(score, "substitutions") == 1
    assert composante_partielle(score, "reference_length") == 14
    agg = aggregate(result, "p")
    assert agg.value is None
    assert (support_micro(agg), agg.expected) == (0, 1)
    assert couverture(agg) == {"partial_output": 1}


# --------------------------------------------------------------------------
# Le CER ne dépend pas de la classe.
# --------------------------------------------------------------------------


def test_f_le_cer_ne_depend_pas_de_la_classe(tmp_path: Path) -> None:
    """§ 2.1 f : « le CER compare le texte produit à la vérité terrain, quelle
    que soit la classe ». ``abst`` (abstention), ``refus`` (refus technique) et
    ``repli`` sortent le **même texte** (la source ``le ſoleil luit``) : même
    statistique (1 substitution sur 14 caractères). La classe ne change que
    l'axe 3 : les deux décisions du correcteur sont notées (CER 1/14), le repli
    est partiel (même statistique, gardée dans ``stat_partielle``). La classe se
    lit au statut et au code de raison, non au texte — ici identique."""
    result = _run(tmp_path, ("abst", "refus", "repli"))
    scores = {doc.document_id: doc.scores[0] for doc in result.documents}
    for doc in ("abst", "refus"):
        assert axes(scores[doc]) == ("applicable", "available", "valid"), doc
        assert [
            composante(scores[doc], nom)
            for nom in ("substitutions", "deletions", "insertions", "reference_length")
        ] == [1, 0, 0, 14]
        assert scores[doc].value == pytest.approx(1 / 14)
    repli = scores["repli"]
    assert axes(repli)[2] == "partial_output" and repli.value is None
    assert [
        composante_partielle(repli, nom)
        for nom in ("substitutions", "deletions", "insertions", "reference_length")
    ] == [1, 0, 0, 14]


def test_f_unite_partielle_mixte__statistique_partielle_sur_le_texte_produit(
    tmp_path: Path,
) -> None:
    """§ 2.1 f : ``part`` — page 1 en repli (source gardée : 2 ``ſ`` à corriger),
    page 2 corrigée. Le texte produit compte 2 substitutions sur 75 caractères de
    référence (5 lignes de 14, 15, 14, 14 et 14 caractères + 4 sauts) : c'est la
    ``stat_partielle`` de l'unité, et l'observation n'est pas notée par défaut."""
    result = _run(
        tmp_path,
        ("part",),
        references={
            "part": "\n".join(
                [
                    "le soleil luit",
                    "rien a dire ici",
                    "la seine coule",
                    "le soleil luit",
                    "la seine coule",
                ]
            )
        },
    )
    (doc,) = result.documents
    (score,) = doc.scores
    assert axes(score)[2] == "partial_output" and score.value is None
    assert statistique_partielle(score) is not None
    assert [
        composante_partielle(score, nom)
        for nom in ("substitutions", "deletions", "insertions", "reference_length")
    ] == [2, 0, 0, 75]


# --------------------------------------------------------------------------
# Persistance.
# --------------------------------------------------------------------------


def test_f_persistance__aller_retour_json_conserve_les_comptes_de_classes(
    tmp_path: Path,
) -> None:
    """§ 2.1 f : le ``RunResult`` relu depuis son JSON porte les mêmes comptes de
    classes, par unité et par pipeline, la même issue ``partial`` et la même
    ``stat_partielle``."""
    result = _run(tmp_path, ("mix", "repli"))
    reloaded = RunResult.model_validate_json(result.model_dump_json())
    assert reloaded == result
    units = _units(reloaded)
    _same(comptes_lignes(units["mix"]), MIX, "mix")
    _same(comptes_lignes(units["repli"]), REPLI, "repli")
    assert str(units["repli"].outcome) == PARTIAL
    _same(
        comptes_lignes(reloaded.pipelines[0]),
        {
            "corrected": 1,
            "review_required": 1,
            "abstained": 2,
            "refused": {"too_different_from_source": 1, "absorbs_next_line": 1},
            "fallback": {"chunk_error_absorbed": 1},
        },
        "pipeline",
    )
    repli = next(d for d in reloaded.documents if d.document_id == "repli")
    assert composante_partielle(repli.scores[0], "reference_length") == 14

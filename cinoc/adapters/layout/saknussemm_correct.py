"""``SaknussemmCorrector`` — ``LAYOUT → LAYOUT + CORRECTED_TEXT`` (couche 5).

La post-correction du banc était **texte plat → texte plat** : on aplatissait
avant de corriger, donc l'identité de ligne, la géométrie et la césure étaient
détruites *avant* que le modèle voie quoi que ce soit. Cette étape corrige
**dans** la mise en page : chaque ligne garde son identifiant d'un bout à
l'autre, et l'appariement avant/après est **connu** au lieu d'être deviné.

Deux sorties, et c'est délibéré :

* ``LAYOUT`` — la mise en page corrigée, que ``alto_assembler`` sait rendre en
  ALTO et que les métriques de structure savent noter ;
* ``CORRECTED_TEXT`` — le même contenu aplati, **pour que le bilan de correction
  existant fonctionne sans être modifié**. Il cherche un ``RAW_TEXT`` et un
  ``CORRECTED_TEXT`` dans les sorties du pipeline ; les lui donner coûte une
  projection et évite d'inventer un type d'artefact pour ça ;
* ``DECISIONS`` — ce qui a été changé, ce qui a été **refusé**, et pourquoi.
  Un texte corrigé ne dit pas si une ligne est intacte parce qu'une garde l'a
  protégée ou parce que rien n'a été proposé : deux situations que rien ne
  distingue une fois le texte écrit.

Ce que la bibliothèque décide, l'étape le rapporte sans le retoucher : une ligne
refusée par une garde ressort **avec son texte d'origine**. C'est le principe de
`saknussemm` — l'application décide, le modèle informe — et le contredire ici
reviendrait à réintroduire en aval ce que les gardes ont écarté.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.adapters.layout.to_text import _page_text
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.errors import AdapterStepError
from cinoc.domain.layout import CanonicalLayout, Line, Region
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"

#: Le seul producteur qui consomme l'image de la page.
VISION_PRODUCER = "mistral_vision"

#: **La** table des producteurs qui interrogent un modèle : nom → le client que
#: ``saknussemm`` recevra. Tout le reste en dérive (noms acceptés, exigence de
#: ``model``), pour qu'ajouter un fournisseur soit une ligne et non trois.
#:
#: Elle n'est **pas** dérivable de ``app.engines.providers_for_mode`` et c'est
#: délibéré : ``saknussemm`` ne consomme pas un adapter de pipeline mais un
#: ``StructuredCompletionClient``, que chaque fournisseur doit implémenter à la
#: main. Un fournisseur présent dans cinoc mais absent ici n'est pas un oubli —
#: c'est un client qui n'existe pas encore, et le proposer ferait échouer le run
#: au premier appel. ``mistral_vision`` n'a d'ailleurs aucun pendant là-bas :
#: c'est une *capacité* (regarder le scan), pas un fournisseur de plus.
MODEL_PRODUCERS: dict[str, str] = {
    "ollama": "serveur local, sans clé",
    "mistral": "API Mistral, correction sur le texte",
    VISION_PRODUCER: "API Mistral, découpe chaque ligne dans le scan",
}

#: Producteurs câblés. ``rules`` est déterministe et hors ligne : il n'interroge
#: aucun modèle, donc il ne figure pas dans la table ci-dessus.
PRODUCERS = ("rules", *sorted(MODEL_PRODUCERS))

#: Scoreurs de qualité branchables. Le routage est **opt-in** : sans scoreur,
#: chaque ligne part au producteur, exactement comme avant.
#:
#: ``heuristic`` est celui que ``saknussemm`` livre ; son propre docstring dit
#: qu'il voudrait D'AlemBERT plutôt qu'une règle de pouce, et la calibration de
#: ce dépôt lui donne raison — AUC ligne 0,500 (le hasard) contre 0,766.
QE_SCORERS = ("heuristic", "dalembert")


def _require_saknussemm() -> Any:
    try:
        import saknussemm  # type: ignore[import-not-found]  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - dépend de l'installation
        raise AdapterStepError(
            "saknussemm_correct : la bibliothèque 'saknussemm' n'est pas "
            "installée — `pip install cinoc[saknussemm]`."
        ) from exc
    return saknussemm


class SaknussemmCorrector:
    """Corrige un ``CanonicalLayout`` ligne à ligne, identités préservées."""

    def __init__(
        self,
        *,
        label: str,
        producer: str = "rules",
        model: str = "",
        host: str = "http://localhost:11434",
        xml_scale: float = 1.0,
        qe: str = "",
        qe_skip: float | None = None,
        qe_escalate: float | None = None,
    ) -> None:
        if producer not in PRODUCERS:
            raise AdapterStepError(
                f"SaknussemmCorrector : producteur {producer!r} inconnu "
                f"(attendu : {', '.join(PRODUCERS)})."
            )
        if producer in MODEL_PRODUCERS and not model:
            raise AdapterStepError(
                f"SaknussemmCorrector : le producteur {producer!r} exige un `model`."
            )
        if xml_scale <= 0:
            raise AdapterStepError(
                f"SaknussemmCorrector : `xml_scale` doit être > 0 (reçu {xml_scale})."
            )
        if qe and qe not in QE_SCORERS:
            raise AdapterStepError(
                f"SaknussemmCorrector : scoreur QE {qe!r} inconnu "
                f"(attendu : {', '.join(QE_SCORERS)})."
            )
        if not qe and (qe_skip is not None or qe_escalate is not None):
            # Des seuils sans scoreur ne routent rien, et l'utilisateur croirait
            # avoir activé une économie qui n'existe pas.
            raise AdapterStepError(
                "SaknussemmCorrector : des seuils de routage sans `qe` ne "
                "s'appliquent à rien — nomme un scoreur."
            )
        self._label = label
        self._producer = producer
        self._model = model
        self._host = host
        self._xml_scale = xml_scale
        self._qe = qe
        self._qe_skip = qe_skip
        self._qe_escalate = qe_escalate

    @property
    def _wants_image(self) -> bool:
        return self._producer == VISION_PRODUCER

    @property
    def name(self) -> str:
        return f"saknussemm:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        """``LAYOUT`` seul, **+ ``IMAGE``** pour le producteur vision.

        Déclaré d'après le producteur et non en dur : une étape qui exigerait
        l'image sans l'utiliser refuserait des pipelines parfaitement valides,
        et une étape qui l'utiliserait sans la déclarer la recevrait vide.
        """
        if self._wants_image:
            return frozenset({ArtifactType.LAYOUT, ArtifactType.IMAGE})
        return frozenset({ArtifactType.LAYOUT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset(
            {
                ArtifactType.LAYOUT,
                ArtifactType.CORRECTED_TEXT,
                ArtifactType.DECISIONS,
            }
        )

    # -- producteur ---------------------------------------------------------

    def _api_key(self) -> str:
        """``MISTRAL_API_KEY``, exigée **avant** le premier appel.

        Échouer ici plutôt qu'à la première ligne évite de découvrir la clé
        manquante après avoir traduit tout un manifeste.
        """
        import os  # noqa: PLC0415

        key = os.environ.get("MISTRAL_API_KEY", "")
        if not key:
            raise AdapterStepError(
                f"{self.name} : le producteur {self._producer!r} exige "
                "MISTRAL_API_KEY."
            )
        return key

    def _build_qe(self) -> tuple[Any, Any]:
        """``(scoreur, politique)`` — ``(None, None)`` si le routage est éteint.

        Le scoreur **informe**, il ne décide pas : c'est la politique qui,
        au-dessus de sa note, fait sauter une ligne propre ou escalader la plus
        risquée. Séparer les deux est la doctrine de ``saknussemm``, et la
        respecter ici évite qu'un seuil se retrouve enfoui dans un modèle.
        """
        if not self._qe:
            return None, None
        from saknussemm.core.quality import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            HeuristicQEScorer,
            RoutingPolicy,
        )

        if self._qe == "dalembert":
            from cinoc.adapters.quality.dalembert import (  # noqa: PLC0415
                DalembertQEScorer,
            )

            scoreur: Any = DalembertQEScorer()
        else:
            scoreur = HeuristicQEScorer()
        return scoreur, RoutingPolicy(
            skip_at_or_below=self._qe_skip,
            escalate_at_or_above=self._qe_escalate,
        )

    def _build_producer(self) -> Any:
        if self._producer == "rules":
            from saknussemm.producers.rules import (  # type: ignore[import-not-found]  # noqa: PLC0415
                RulesProducer,
                default_french_ocr_rules,
            )

            return RulesProducer(default_french_ocr_rules())

        if self._producer == VISION_PRODUCER:
            return self._build_vision_producer()

        from saknussemm.producers.llm_edit import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            LLMEditProducer,
        )

        if self._producer == "mistral":
            from cinoc.adapters.correction.mistral_structured import (  # noqa: PLC0415
                MistralStructuredClient,
            )

            return LLMEditProducer(
                MistralStructuredClient(),
                api_key=self._api_key(),
                model=self._model,
            )

        from cinoc.adapters.correction.ollama_structured import (  # noqa: PLC0415
            OllamaStructuredClient,
        )

        return LLMEditProducer(
            OllamaStructuredClient(host=self._host), api_key="", model=self._model
        )

    def _build_vision_producer(self) -> Any:
        """``VisionEditProducer`` + le plafond d'images **déclaré** au moteur.

        Sans ``max_images``, le routeur composerait un lot de plus de huit
        découpes et l'API le refuserait après les avoir encodées pour rien ; le
        déclarer fait scinder le lot en amont de la requête.
        """
        # La clé d'abord : c'est le manque le plus fréquent et le moins cher à
        # constater. Importer avant elle ferait répondre « module introuvable »
        # à qui a simplement oublié d'exporter sa clé.
        cle = self._api_key()

        from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            ModelCapabilities,
        )
        from saknussemm.producers.vision import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            VisionEditProducer,
        )

        from cinoc.adapters.correction.mistral_multimodal import (  # noqa: PLC0415
            MAX_IMAGES_PER_CALL,
            MistralMultimodalClient,
        )

        return VisionEditProducer(
            MistralMultimodalClient(),
            api_key=cle,
            model=self._model,
            capabilities=ModelCapabilities(
                text=True,
                vision=True,
                structured_output=True,
                max_images=MAX_IMAGES_PER_CALL,
            ),
        )

    def _page_images(
        self, inputs: dict[ArtifactType, Artifact], page_ids: list[str]
    ) -> dict[str, Any]:
        """``page_id → ImageAsset`` pour le producteur vision.

        ``xml_scale`` porte le seul décalage que la v1 de ``saknussemm`` traite :
        une géométrie exprimée dans un autre espace que les pixels du scan. Un
        ALTO en ``mm10`` numérisé à 300 DPI demande ``dpi/254 ≈ 1,1811`` — le
        cas du corpus BNL de ce dépôt. Le laisser à 1,0 (le défaut) veut dire
        « l'OCR a tourné à la résolution native », et c'est le cas courant.

        Il est **explicite** et non deviné : les pages ALTO de la BNL ne
        déclarent ni ``WIDTH`` ni ``HEIGHT``, donc aucune comparaison avec la
        taille réelle de l'image ne pourrait le retrouver. Une échelle devinée
        qui se trompe découpe à côté et le modèle corrige la mauvaise ligne —
        en silence.
        """
        from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            ImageTransform,
        )
        from saknussemm.producers.vision import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            build_image_asset,
        )

        image = inputs.get(ArtifactType.IMAGE)
        if image is None or image.uri is None:
            raise AdapterStepError(
                f"{self.name} : le producteur {self._producer!r} regarde le scan "
                "et n'a reçu aucune IMAGE."
            )
        transform = ImageTransform(scale_x=self._xml_scale, scale_y=self._xml_scale)
        return {
            page_id: build_image_asset(page_id, image.uri, transform=transform)
            for page_id in page_ids
        }

    # -- exécution ----------------------------------------------------------

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        artifact = inputs.get(ArtifactType.LAYOUT)
        if artifact is None or artifact.uri is None:
            raise AdapterStepError(f"{self.name} : artefact LAYOUT sans URI.")
        try:
            layout = CanonicalLayout.model_validate_json(
                Path(artifact.uri).read_bytes()
            )
        except (OSError, ValueError) as exc:
            raise AdapterStepError(
                f"{self.name} : {artifact.uri!r} n'est pas un CanonicalLayout "
                f"lisible — {exc}"
            ) from exc
        _require_saknussemm()

        from saknussemm.core.pipeline import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
            CorrectionPipeline,
        )

        from cinoc.adapters.layout._saknussemm_bridge import (  # noqa: PLC0415
            layout_to_manifest,
            manifest_page_ids,
        )

        manifest = layout_to_manifest(layout, document_id=context.document_id)
        control.raise_if_cancelled()

        class _Observer:
            def on_event(self, event_type: str, payload: dict[str, Any]) -> None:
                pass

        # Le profil de gardes suit le producteur, pas une préférence : un VLM lit
        # l'image, pas l'OCR, donc une lecture **correcte** d'une ligne bien
        # abîmée s'écarte du texte source plus que la garde texte ne tolère.
        # Garder la garde texte ici rejetterait précisément les corrections que
        # la vision existe pour produire.
        guard_config = None
        if self._wants_image:
            from saknussemm.core.schemas import (  # type: ignore[import-not-found]  # noqa: PLC0415, E501
                GuardConfig,
            )

            guard_config = GuardConfig.vision()
        scoreur, politique = self._build_qe()
        pipeline = CorrectionPipeline(
            producer=self._build_producer(),
            observer=_Observer(),
            guard_config=guard_config,
            qe_scorer=scoreur,
            routing_policy=politique,
        )
        page_images = (
            self._page_images(inputs, manifest_page_ids(manifest))
            if self._wants_image
            else None
        )
        # ``source_files`` vide : on ne réécrit aucun XML. L'artefact de sortie
        # est la mise en page, et ``alto_assembler`` sait en faire un ALTO — le
        # moteur n'a donc rien à rendre lui-même.
        result = pipeline.run_sync(
            document_manifest=manifest, source_files={}, page_images=page_images
        )

        decided = {
            (outcome.page_id, outcome.line_id): outcome.decision.final_text
            for outcome in result.report.lines
        }
        corrected = _apply(layout, decided, manifest_page_ids(manifest))
        return self._emit(corrected, _decisions(result, context.document_id), context)

    def _emit(
        self, layout: CanonicalLayout, decisions: bytes, context: RunContext
    ) -> StepOutput:
        payload = layout.model_dump_json().encode("utf-8")
        text = _flatten(layout).encode("utf-8")
        layout_path = self._out(context, "layout.json")
        text_path = self._out(context, "corrected.txt")
        decisions_path = self._out(context, "decisions.json")
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_bytes(payload)
        text_path.write_bytes(text)
        decisions_path.write_bytes(decisions)
        return StepOutput(
            artifacts={
                ArtifactType.LAYOUT: Artifact(
                    id=f"{context.document_id}:{self.name}:layout",
                    document_id=context.document_id,
                    type=ArtifactType.LAYOUT,
                    uri=str(layout_path),
                    content_hash=compute_content_hash(payload),
                ),
                ArtifactType.CORRECTED_TEXT: Artifact(
                    id=f"{context.document_id}:{self.name}:text",
                    document_id=context.document_id,
                    type=ArtifactType.CORRECTED_TEXT,
                    uri=str(text_path),
                    content_hash=compute_content_hash(text),
                ),
                ArtifactType.DECISIONS: Artifact(
                    id=f"{context.document_id}:{self.name}:decisions",
                    document_id=context.document_id,
                    type=ArtifactType.DECISIONS,
                    uri=str(decisions_path),
                    content_hash=compute_content_hash(decisions),
                ),
            }
        )

    def _out(self, context: RunContext, suffix: str) -> Path:
        if context.workspace_uri:
            return workspace_artifact_path(
                context.workspace_uri, context.document_id, self._label, suffix
            )
        return Path(f"{context.document_id.replace('/', '_')}.{self._label}.{suffix}")


def _decisions(result: object, document_id: str) -> bytes:
    """Sérialise ce que la bibliothèque a décidé, ligne par ligne.

    Le **statut** distingue trois situations qu'un texte corrigé confond :
    la ligne a changé, une garde a refusé un changement proposé, ou rien n'a
    été proposé. Sans cette distinction, un correcteur prudent et un correcteur
    inerte rendent le même artefact.
    """
    lignes = []
    for outcome in result.report.lines:  # type: ignore[attr-defined]
        decision = outcome.decision
        propose = outcome.proposal.output_text if outcome.proposal else None
        raison = decision.reason
        lignes.append(
            {
                "document_id": document_id,
                "page_id": outcome.page_id,
                "line_id": outcome.line_id,
                "status": decision.status,
                "source_text": outcome.source_text,
                "final_text": decision.final_text,
                "proposed_text": propose,
                "hyphen_role": outcome.hyphen_role,
                "reason_code": raison.code if raison else None,
                "reason_detail": raison.detail if raison else None,
            }
        )
    return json.dumps(
        {"document_id": document_id, "lines": lignes}, ensure_ascii=False
    ).encode("utf-8")


def _apply(
    layout: CanonicalLayout,
    decided: dict[tuple[str, str], str],
    page_ids: list[str],
) -> CanonicalLayout:
    """Repose les textes décidés sur la mise en page, identités à l'appui.

    Les mots sont **abandonnés sur une ligne modifiée** : leur géométrie décrit
    des caractères qui ne sont plus là. Les garder ferait dire à l'artefact une
    position que rien ne soutient — le contraire de ce que la structure sert à
    porter.
    """

    def region(reg: Region, page_id: str) -> Region:
        lines = []
        for line in reg.lines:
            texte = decided.get((page_id, line.id or ""))
            if texte is None or texte == line.text:
                lines.append(line)
                continue
            lines.append(
                Line(
                    id=line.id,
                    text=texte,
                    geometry=line.geometry,
                    baseline=line.baseline,
                    words=(),
                    confidence=line.confidence,
                )
            )
        return reg.model_copy(
            update={
                "lines": tuple(lines),
                "regions": tuple(region(r, page_id) for r in reg.regions),
            }
        )

    pages = tuple(
        page.model_copy(
            update={"regions": tuple(region(r, page_ids[i]) for r in page.regions)}
        )
        for i, page in enumerate(layout.pages)
    )
    return layout.model_copy(update={"pages": pages})


def _flatten(layout: CanonicalLayout) -> str:
    """Aplatit **avec la fonction de ``to_text``**, pas avec une copie.

    Le bilan de correction compare le ``RAW_TEXT`` produit par ``to_text`` au
    ``CORRECTED_TEXT`` produit ici : deux conventions d'aplatissement
    différentes fausseraient la comparaison sans rien casser de visible. Une
    première version réécrivait la boucle et ajoutait 41 lignes vides sur le
    corpus BnF — les régions sans texte — ce qui aurait décalé tout
    l'appariement de lignes.
    """
    return "\n".join(_page_text(page) for page in layout.pages)


__all__ = [
    "MODEL_PRODUCERS",
    "QE_SCORERS",
    "PRODUCERS",
    "VISION_PRODUCER",
    "SaknussemmCorrector",
]

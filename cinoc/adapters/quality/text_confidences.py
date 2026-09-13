"""``LanguageConfidenceScorer`` — une confiance par mot, là où le moteur n'en donne pas.

Le banc mesure la **calibration** des confidences : ECE, MCE, courbe de
fiabilité, table par bin. Tout cet appareil ne s'allume que si le pipeline émet
un artefact ``CONFIDENCES``, et **deux moteurs seulement** en émettent —
Tesseract et Kraken. Pour l'OCR Mistral, pour un VLM en transcription directe,
pour un ALTO livré sans ``CC``, et pour tout texte **corrigé**, la section
restait vide : non pas parce qu'il n'y avait rien à dire, mais parce que
personne ne fournissait la donnée.

Cette étape la fournit, pour n'importe quel texte, à partir d'un modèle de
langue d'époque (:mod:`~cinoc.adapters.quality.dalembert`).

**Ce n'est pas la même grandeur qu'une confiance moteur, et il faut le dire.**
Tesseract répond « à quel point suis-je sûr de *ces pixels* » ; un modèle de
langue répond « à quel point ce mot est-il plausible dans cette langue ». Un mot
parfaitement lu mais rare aura une bonne confiance Tesseract et une mauvaise
note ici. Les confondre serait une erreur.

Mais la calibration, elle, ne mesure qu'**une seule chose** : est-ce que cet
indice prédit l'erreur ? Les deux grandeurs y sont donc comparables sur le seul
critère qui compte, et le banc peut répondre à une question qu'on ne pouvait pas
poser — qui prédit le mieux une erreur d'OCR, la confiance du moteur ou le
jugement d'un modèle de langue ?

**L'inversion est le point délicat.** Le scoreur rend un *besoin de correction*
(haut = suspect) ; une confiance est son contraire (haut = sûr). ``1 − note``
fait la bascule, et se tromper de sens produirait une courbe de fiabilité
parfaitement retournée — qui *ressemble* à un résultat, ce qui la rend
dangereuse plutôt que fausse.
"""

from __future__ import annotations

import json
from pathlib import Path

from cinoc.adapters._workspace import workspace_artifact_path
from cinoc.domain.artifacts import Artifact, ArtifactType, compute_content_hash
from cinoc.domain.confidence import ConfidenceToken
from cinoc.domain.errors import AdapterStepError
from cinoc.pipeline.protocols import ParamValue
from cinoc.pipeline.run_control import RunControl
from cinoc.pipeline.types import RunContext, StepOutput

_VERSION = "1.0"

#: Longueur maximale d'un ``ConfidenceToken`` (contrat du type domaine). Un
#: « mot » plus long est un artefact d'OCR, pas un mot : on le tronque plutôt
#: que de faire échouer la page pour lui.
_MAX_TOKEN = 256


def confidence_from(need: float) -> float:
    """Besoin de correction → **confiance**. L'inversion, isolée et nommée.

    Une ligne qui vaut ``0,9`` de besoin vaut ``0,1`` de confiance. La borner
    dans ``[0, 1]`` n'est pas de la superstition : ``ConfidenceToken`` refuse
    tout ce qui en sort, et une note calibrée peut frôler les bornes.
    """
    return min(1.0, max(0.0, 1.0 - need))


class LanguageConfidenceScorer:
    """``RAW_TEXT | CORRECTED_TEXT → CONFIDENCES`` par un modèle de langue."""

    def __init__(self, *, label: str, model: str = "") -> None:
        if not label or not all(c.isalnum() or c in "_-" for c in label):
            raise AdapterStepError(
                f"LanguageConfidenceScorer : label invalide {label!r} "
                "(alphanumérique + _ - uniquement)."
            )
        self._label = label
        self._model = model

    @property
    def name(self) -> str:
        return f"text_confidences:{self._label}"

    @property
    def version(self) -> str:
        return _VERSION

    @property
    def input_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.RAW_TEXT})

    @property
    def output_types(self) -> frozenset[ArtifactType]:
        return frozenset({ArtifactType.CONFIDENCES})

    def _scorer(self) -> object:
        from cinoc.adapters.quality.dalembert import (  # noqa: PLC0415
            DEFAULT_MODEL,
            DalembertQEScorer,
        )

        return DalembertQEScorer(model=self._model or DEFAULT_MODEL)

    @staticmethod
    def _platt(surprise: float) -> float:
        from cinoc.adapters.quality.dalembert import platt  # noqa: PLC0415

        return platt(surprise)

    def execute(
        self,
        inputs: dict[ArtifactType, Artifact],
        params: dict[str, ParamValue],  # noqa: ARG002 — contrat Module
        context: RunContext,
        control: RunControl,
    ) -> StepOutput:
        control.raise_if_cancelled()
        source = inputs.get(ArtifactType.RAW_TEXT)
        if source is None or source.uri is None:
            raise AdapterStepError(f"{self.name} : artefact texte sans URI.")
        if context.workspace_uri is None:
            raise AdapterStepError(f"{self.name} : workspace requis.")
        try:
            texte = Path(source.uri).read_text(encoding="utf-8")
        except OSError as exc:
            raise AdapterStepError(
                f"{self.name} : texte illisible — {exc}"
            ) from exc
        tokens = self.score(texte, control)
        payload = json.dumps(
            [token.model_dump() for token in tokens], ensure_ascii=False
        ).encode("utf-8")
        chemin = workspace_artifact_path(
            context.workspace_uri, context.document_id, self._label,
            "confidences.json",
        )
        chemin.write_bytes(payload)
        return StepOutput(
            artifacts={
                ArtifactType.CONFIDENCES: Artifact(
                    id=f"{context.document_id}:{self._label}:confidences",
                    document_id=context.document_id,
                    type=ArtifactType.CONFIDENCES,
                    uri=str(chemin),
                    content_hash=compute_content_hash(payload),
                )
            }
        )

    def score(self, texte: str, control: RunControl) -> list[ConfidenceToken]:
        """Un ``ConfidenceToken`` par mot, ligne par ligne.

        **Ligne par ligne, et pas page entière** : le modèle a une fenêtre, et
        surtout la surprise d'un mot doit se mesurer dans *son* contexte. Coller
        la page en une chaîne ferait juger le début d'un paragraphe par la fin du
        précédent.
        """
        scorer = self._scorer()
        tokens: list[ConfidenceToken] = []
        for ligne in texte.splitlines():
            control.raise_if_cancelled()
            if not ligne.strip():
                continue
            for mot, surprise in scorer.word_surprisals(ligne):  # type: ignore[attr-defined]
                propre = mot.strip()[:_MAX_TOKEN]
                if propre:
                    tokens.append(
                        ConfidenceToken(
                            text=propre,
                            confidence=confidence_from(self._platt(surprise)),
                        )
                    )
        return tokens


__all__ = ["LanguageConfidenceScorer", "confidence_from"]

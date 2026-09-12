"""``DalembertQEScorer`` — le besoin de correction d'une ligne, par D'AlemBERT.

``saknussemm`` livre un scoreur de référence, ``heuristic-qe``, et son propre
docstring dit pourquoi il ne suffit pas : « le scoreur veut D'AlemBERT, pas une
règle de pouce ». Sur le corpus de calibration de ce dépôt, il ne sépare
**rien** — AUC 0,500 au mot comme à la ligne, c'est-à-dire le hasard. D'AlemBERT
(``pjox/dalembert``, MLM entraîné sur du français d'Ancien Régime) atteint
**0,766 d'AUC à la ligne**. C'est ce que ce module branche.

**Le piège que ce scoreur devait éviter, et comment il l'évite.** Un modèle
contemporain juge improbable une orthographe d'époque, donc signale comme
« à corriger » une transcription parfaitement fidèle. La vérification
préalable a isolé la cause : la pénalité portait sur les **glyphes**
(``ſ``, ligatures) et non sur la **langue**. Le scoreur note donc une **copie
dé-glyphée** — ``ſ`` → ``s``, ``ﬁ`` → ``fi`` — pendant que le document, lui,
n'est pas touché. La perplexité mesure alors l'invraisemblance *linguistique*
seule, et ``auoir``, ``estoit``, la morphologie d'époque restent intactes
(règle 3 de ``saknussemm`` : l'orthographe historique se préserve).

**Comment la note est fabriquée**, à l'identique de la calibration :

1. pseudo-vraisemblance par masquage — chaque sous-mot est masqué tour à tour et
   on mesure la surprise du modèle sur le vrai jeton ;
2. un mot vaut le **maximum** de ses sous-mots (une erreur d'OCR n'abîme souvent
   qu'un morceau du mot ; en faire la moyenne la noierait) ;
3. la ligne vaut le **maximum** de ses mots — c'est le réducteur ``max`` du
   rapport de calibration ;
4. la surprise est ramenée dans ``[0, 1]`` par la sigmoïde de Platt **mesurée**,
   pas choisie : ``midpoint`` 10,9436 et ``scale`` 6,7179.

Les masques d'une même ligne partent en **un seul lot** : sans ça une page
demanderait un passage avant par sous-mot, et le coût serait dissuasif là où il
n'est qu'un détail d'implémentation.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from cinoc.domain.errors import AdapterStepError

#: Modèle de référence : MLM français d'Ancien Régime.
DEFAULT_MODEL = "pjox/dalembert"

#: Table **typographique**, pas linguistique. Aucun ``u``/``v``, aucune
#: morphologie : neutraliser la langue d'époque reviendrait à traiter une
#: transcription fidèle comme une faute.
GLYPHS = {
    "ſ": "s",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "æ": "ae",
    "œ": "oe",
    "Æ": "Ae",
    "Œ": "Oe",
}

#: Sigmoïde de Platt **mesurée** sur le corpus de calibration (réducteur
#: ``max``) : ``qe-report-max.json``, AUC ligne 0,766 contre 0,500 pour
#: l'heuristique. Les changer sans re-mesurer rendrait la note incomparable
#: d'un run à l'autre — c'est de la donnée calibrée, pas un réglage.
PLATT_MIDPOINT = 10.9436
PLATT_SCALE = 6.7179

#: Plafond de sous-mots notés par ligne. Une ligne de journal en fait une
#: vingtaine ; au-delà c'est une ligne aberrante (bloc entier collé), et le coût
#: croît linéairement. On note le début plutôt que de refuser ou de ramer.
MAX_SUBWORDS = 128


def deglyph(text: str) -> str:
    """La copie notée : typographie neutralisée, langue intacte."""
    for ancien, neuf in GLYPHS.items():
        text = text.replace(ancien, neuf)
    return text


def platt(surprisal: float) -> float:
    """Surprise (nats) → probabilité de besoin de correction, dans ``[0, 1]``."""
    return 1.0 / (1.0 + math.exp(-(surprisal - PLATT_MIDPOINT) / PLATT_SCALE))


@lru_cache(maxsize=2)
def _load(model_name: str) -> tuple[Any, Any]:
    """Tokeniseur + modèle, chargés **une fois**. Grands, et immuables."""
    try:
        import torch  # noqa: PLC0415
        from transformers import (  # type: ignore[import-not-found]  # noqa: PLC0415
            AutoModelForMaskedLM,
            AutoTokenizer,
        )
    except ImportError as exc:
        raise AdapterStepError(
            "dalembert : torch/transformers absents — "
            "`pip install 'cinoc[qe]'`."
        ) from exc
    # ``transformers`` ne livre pas de stubs : mypy voit des appels non typés.
    tokenizer = AutoTokenizer.from_pretrained(model_name)  # type: ignore[no-untyped-call]
    model = AutoModelForMaskedLM.from_pretrained(model_name)  # type: ignore[no-untyped-call]
    model.eval()
    torch.set_grad_enabled(False)
    return tokenizer, model


class DalembertQEScorer:
    """``needs_correction(text) -> [0, 1]``, par pseudo-perplexité masquée."""

    def __init__(self, *, model: str = DEFAULT_MODEL) -> None:
        self._model_name = model

    @property
    def name(self) -> str:
        return f"dalembert-qe:{self._model_name}"

    def needs_correction(self, text: str) -> float:
        """Note d'une ligne. Une ligne sans mot vaut ``0`` — pas ``None``.

        Le contrat de ``saknussemm`` est un flottant ; rendre 0 pour une ligne
        de ponctuation dit « rien à corriger », ce qui est vrai, et laisse le
        routeur la sauter au lieu de payer un appel pour un tiret.
        """
        mots = self.word_surprisals(text)
        if not mots:
            return 0.0
        return platt(max(surprise for _, surprise in mots))

    def word_surprisals(self, text: str) -> list[tuple[str, float]]:
        """``(mot, surprise)`` pour chaque mot alphanumérique de la ligne.

        Exposé, et pas seulement la note : c'est ce qui permet de dire **quel**
        mot a déclenché la note. Une note seule ne s'audite pas.
        """
        import torch  # noqa: PLC0415

        propre = deglyph(text)
        if not propre.strip():
            return []
        tokenizer, model = _load(self._model_name)
        encodage = tokenizer(
            propre, return_tensors="pt", return_offsets_mapping=True
        )
        ids = encodage["input_ids"][0]
        offsets = encodage["offset_mapping"][0].tolist()
        word_ids = encodage.word_ids(0)

        groupes: dict[int, list[int]] = {}
        for position, word_id in enumerate(word_ids):
            if word_id is not None and position < MAX_SUBWORDS:
                groupes.setdefault(word_id, []).append(position)
        positions = [p for poss in groupes.values() for p in poss]
        if not positions:
            return []

        # Un lot : autant de copies de la ligne que de sous-mots, chacune avec
        # **un** masque. Séquentiellement ce serait un passage avant par
        # sous-mot, soit des milliers pour une page.
        lot = ids.unsqueeze(0).repeat(len(positions), 1)
        for rang, position in enumerate(positions):
            lot[rang, position] = tokenizer.mask_token_id
        logits = model(input_ids=lot).logits

        surprises: dict[int, float] = {}
        for rang, position in enumerate(positions):
            ligne = logits[rang, position]
            ligne = ligne - ligne.max()
            vrai = int(ids[position])
            surprises[position] = math.log(
                float(torch.exp(ligne).sum())
            ) - float(ligne[vrai])

        return _par_mot(propre, offsets, surprises)


def _mots_du_texte(texte: str) -> list[tuple[int, int, str]]:
    """Les mots **séparés par des blancs**, avec leurs bornes de caractères."""
    spans: list[tuple[int, int, str]] = []
    debut: int | None = None
    for index, char in enumerate(texte):
        if char.isspace():
            if debut is not None:
                spans.append((debut, index, texte[debut:index]))
                debut = None
        elif debut is None:
            debut = index
    if debut is not None:
        spans.append((debut, len(texte), texte[debut:]))
    return spans


def _par_mot(
    texte: str,
    offsets: list[list[int]],
    surprises: dict[int, float],
) -> list[tuple[str, float]]:
    """Regroupe les surprises par mot **du texte**, pas par mot du tokeniseur.

    Le tokeniseur coupe ``c0urt`` en morceaux et donne au chiffre son propre
    identifiant de mot : s'y fier ferait désigner ``'0'`` comme le mot fautif,
    ce qui est vrai du sous-mot et inutile à qui relit une ligne.

    La **note de ligne ne change pas** — elle est le maximum sur tous les
    sous-mots, quel que soit le découpage qui les regroupe. Seule change la
    réponse à « quel mot ? », et c'est elle qui rend une note auditable.
    """
    out: list[tuple[str, float]] = []
    for debut, fin, mot in _mots_du_texte(texte):
        if not any(c.isalnum() for c in mot):
            continue
        dedans = [
            surprise
            for position, surprise in surprises.items()
            if offsets[position][0] < fin and offsets[position][1] > debut
        ]
        if dedans:
            # ``max`` et non la moyenne : une erreur d'OCR n'abîme souvent qu'un
            # morceau du mot, et la moyenne la noierait.
            out.append((mot, max(dedans)))
    return out


__all__ = [
    "DEFAULT_MODEL",
    "GLYPHS",
    "MAX_SUBWORDS",
    "PLATT_MIDPOINT",
    "PLATT_SCALE",
    "DalembertQEScorer",
    "deglyph",
    "platt",
]

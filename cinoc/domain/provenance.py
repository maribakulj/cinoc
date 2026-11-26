"""Provenance d'un artefact.

Empreinte minimale attachée à chaque ``Artifact`` produit par une étape
de pipeline. Permet la reproductibilité : même entrée + même
``parameters_hash`` (l'empreinte de l'étape : brique, réglages effectifs,
version du module, binaires) = mêmes artefacts, au déterminisme près des
moteurs.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProvenanceRecord(BaseModel):
    """Empreinte de production d'un artefact.

    Immuable : pour modifier une provenance, on crée un nouvel artefact.

    Attributs
    ---------
    timestamp:
        Date/heure UTC de production (défaut : maintenant).
    code_version:
        Version du code qui a produit l'artefact. Str opaque — une trace, pas
        une identité : une correction de métrique la change sans changer
        aucune sortie.
    parameters_hash:
        Empreinte SHA-256 hex de l'**étape** qui a produit l'artefact
        (``cinoc.pipeline.fingerprint.step_fingerprint``) : la brique et ses
        ``params``, les réglages effectifs du module (modèle, prompt, défauts,
        endpoint lu dans l'environnement), sa version et ses binaires. La clé
        du cache de reprise en dérive. ``None`` pour les artefacts initiaux
        (image fournie, GT lue).
    served_models:
        Modèle(s) que le fournisseur dit avoir servi(s) pour produire
        l'artefact (``response.model``) ; vide si la réponse ne le dit pas.
        Une observation, pas une identité : hors de la comparaison.
    """

    model_config = ConfigDict(frozen=True)

    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC),
    )
    code_version: str
    parameters_hash: str | None = None
    served_models: tuple[str, ...] = ()

    def is_compatible_with(self, other: ProvenanceRecord) -> bool:
        """Deux artefacts produits par le même contexte de calcul.

        Le timestamp et les modèles servis (des observations) n'entrent pas
        dans la comparaison — seule la combinaison ``(code_version,
        parameters_hash)`` la détermine.
        """
        return (
            self.code_version == other.code_version
            and self.parameters_hash == other.parameters_hash
        )


__all__ = ["ProvenanceRecord"]

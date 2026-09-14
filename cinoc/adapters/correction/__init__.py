"""Fournisseurs de la **post-correction structurée** (couche 5).

Ces clients n'ont pas la forme des adapters de ``adapters/llm/`` et ne servent
pas au même usage. Un adapter LLM est une **brique de pipeline** : il implémente
le ``Module`` Protocol de cinoc et produit un artefact. Ceux-ci implémentent le
``StructuredCompletionClient`` (ou son pendant multimodal) d'une bibliothèque
**tierce**, qui les appelle depuis son propre moteur.

Ils vivaient dans ``adapters/llm/``, sous des noms génériques, alors qu'ils
n'existent que pour cette bibliothèque-là : un lecteur qui ouvrait
``adapters/llm/mistral_structured.py`` croyait y trouver le client Mistral de
cinoc. Le dossier dit désormais à quoi ils servent, et
``tests/architecture/test_layer_dependencies.py`` interdit qu'un import de la
bibliothèque tierce reparaisse dans ``adapters/llm/``.
"""

from __future__ import annotations

__all__: list[str] = []

---
title: Cinoc — banc d'essai OCR/HTR/VLM
emoji: 📜
colorFrom: indigo
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: apache-2.0
---

# Cinoc — banc d'essai OCR/HTR/VLM

Banc d'essai **déterministe** de pipelines de transcription (OCR / HTR / VLM).
Ce Space **exécute un vrai OCR Tesseract gratuitement** — **sans clé ni
installation** : déposez un corpus, lancez Tesseract, obtenez un rapport CER/WER/MER
réel. Il sert aussi des rapports `RunResult` pré-calculés, rendus en HTML autonome.

- `/` — liste des rapports disponibles
- `/library` — préparer un corpus (upload ZIP)
- `/benchmark` — lancer un run **Tesseract** (gratuit, local) sur un corpus
- `/reports/<nom>` — un rapport rendu en HTML
- `/health` — sonde de vivacité

**Par défaut, l'instance exécute ses moteurs avec la clé de son opérateur** —
aucun blocage. Sans clé posée, seul le **socle gratuit** tourne (Tesseract, aucun
secret, aucun appel facturé) ; dès qu'une clé est présente (`MISTRAL_API_KEY`,
`OPENAI_API_KEY`…), les moteurs **cloud** (OCR→LLM, VLM) s'exécutent normalement.

## Utiliser un moteur cloud (Mistral, OpenAI…)

1. **Secret** : `MISTRAL_API_KEY` = votre clé (Settings → Variables and secrets).
   Le SDK `mistralai` est déjà dans `requirements.txt`. Redéployez.
2. C'est tout : le menu déroulant « Modèle » du Banc d'essai se remplit directement
   depuis l'API Mistral (`models.list`) et les prompts sont éditables par concurrent.

> 🔴 **Sécurité** : sur un Space **public**, la clé que vous posez est dépensable par
> n'importe quel visiteur. Rendez le Space **Private** (Settings → Visibility →
> Private) si vous y posez une clé facturée, **ou** activez le verrou ci-dessous.

## Verrou « mode public » — opt-in, pour protéger une clé sur un Space public

Si vous tenez à exposer un Space **public** *tout en* gardant une clé posée sans
qu'un visiteur puisse la dépenser, activez le verrou **fail-closed** : variable
`CINOC_PUBLIC_MODE` = `true` (Settings → Variables and secrets). Alors seul le
**socle gratuit** (Tesseract) s'exécute ; les moteurs **cloud**, les **imports
distants** (IIIF/Gallica/…) et les **plugins tiers** sont **refusés** (`403`), et
une archive ZIP déposée est plafonnée à 25 Mo (200 Mo sans le verrou, comme en
local). Le verrou est **désactivé par défaut** : ne le posez que si ce scénario
est le vôtre.

> Ce fichier est l'en-tête de configuration du Space Hugging Face (`sdk: docker`).
> Au déploiement, il devient le `README.md` racine du dépôt du Space ; le
> `Dockerfile` et `requirements.txt` vivent dans `deploy/`.

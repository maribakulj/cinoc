# Vitrine Cinoc (lecture seule) pour un Hugging Face Space (SDK: docker).
# Sert les rapports RunResult d'un dossier baké — AUCUNE clé API requise.
# Construit depuis la racine du dépôt :  docker build -f deploy/Dockerfile .
FROM python:3.11-slim

# HF Space : utilisateur non-root + port 7860 (convention Spaces).
RUN useradd --create-home --uid 1000 cinoc
WORKDIR /home/cinoc/app

# 1) Dépendances d'abord (cache de couche). Seul l'extra [serve] est requis :
#    la vitrine ne lance aucun moteur → ni binaire tesseract, ni SDK LLM.
COPY deploy/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2) Le code + le paquet (installé sans deps : tout est déjà figé ci-dessus).
COPY pyproject.toml README.md ./
COPY cinoc ./cinoc
RUN pip install --no-cache-dir --no-deps .

# 3) Les rapports à exposer (déposés dans deploy/reports/ avant le build).
#    Dossier toujours présent (même vide) → la vitrine démarre proprement.
COPY deploy/reports ./reports
ENV CINOC_REPORTS_DIR=/home/cinoc/app/reports

USER cinoc
EXPOSE 7860
# 0.0.0.0 est attendu en conteneur (le réseau est géré par la plateforme).
CMD ["cinoc", "serve", "--host", "0.0.0.0", "--port", "7860"]

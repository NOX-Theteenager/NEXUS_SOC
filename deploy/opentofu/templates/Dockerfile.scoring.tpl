# =============================================================================
# NEXUS SOC — Dockerfile scoring-service (généré par OpenTofu)
# Python 3.11 slim : FastAPI + modèles IA + Kafka + PostgreSQL
# =============================================================================

FROM python:3.11-slim

LABEL org.opencontainers.image.title="NEXUS SOC Scoring Service"
LABEL org.opencontainers.image.version="${nexus_version}"
LABEL org.opencontainers.image.description="Service de scoring IA et API REST NEXUS SOC"

WORKDIR /app

# Dépendances système minimales
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Dépendances Python (couche cachée séparément pour les rebuilds rapides)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Sources du service
COPY app.py              ./scoring_service_app.py
COPY auth_middleware.py  .
COPY pseudonymizer.py    .
COPY admin_api.py        .
COPY provisioning_api.py .

# Point d'entrée
EXPOSE 8000
CMD ["uvicorn", "scoring_service_app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]

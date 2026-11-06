# ====================================================================
# Stage 1: Builder - Installation des dépendances
# ====================================================================
FROM python:3.12-slim AS builder

# Définir le répertoire de travail
WORKDIR /build

# Installer les dépendances système nécessaires pour compiler certains packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Copier le fichier requirements.txt
COPY backend/requirements.txt .

# Créer un virtual environment et installer les dépendances
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Installer les dépendances Python avec timeout élevé
RUN pip install --default-timeout=1000 --no-cache-dir --upgrade pip && \
    pip install --default-timeout=1000 --no-cache-dir -r requirements.txt

# ====================================================================
# Stage 2: Runtime - Image finale légère
# ====================================================================
FROM python:3.12-slim

# Metadata labels
LABEL maintainer="Bassem Ben Hamed"
LABEL description="API Backend pour la détection de fraude avec MLflow"
LABEL version="1.0.0"

# Installer uniquement les bibliothèques système nécessaires au runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libstdc++6 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Créer un utilisateur non-root pour la sécurité
RUN groupadd -r appuser && useradd -r -g appuser -u 1001 appuser

# Définir le répertoire de travail
WORKDIR /app

# Copier le virtual environment depuis le builder
COPY --from=builder /opt/venv /opt/venv

# Copier le code source de l'application
COPY --chown=appuser:appuser backend/src/ /app/backend/src/

# ✅ Seulement preprocessing — nécessaire pour les prédictions
COPY --chown=appuser:appuser artifacts/preprocessing/scaler.pkl /app/artifacts/preprocessing/
COPY --chown=appuser:appuser artifacts/preprocessing/label_encoders.pkl /app/artifacts/preprocessing/
COPY --chown=appuser:appuser artifacts/preprocessing/feature_names.pkl /app/artifacts/preprocessing/
COPY --chown=appuser:appuser artifacts/preprocessing/smote_config.pkl /app/artifacts/preprocessing/
# ✅ Seulement le meilleur modèle — pas tous les modèles
COPY --chown=appuser:appuser artifacts/mlflow/Best_Fraud_LightGBM/1.0.0/ /app/model_registry/

# Configurer les variables d'environnement
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/backend/src:/app" \
    PYTHONUNBUFFERED=1 \
    MODEL_REGISTRY_DIR=/app/model_registry \
    PROCESSORS_DIR=/app/artifacts/preprocessing

# Exposer le port de l'API
EXPOSE 8000

# Healthcheck pour vérifier que l'API est opérationnelle
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Passer à l'utilisateur non-root
USER appuser

# Commande pour lancer l'application
CMD ["uvicorn", "backend.src.api:app", "--host", "0.0.0.0", "--port", "8000"]
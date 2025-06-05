FROM python:3.11-slim

# Métadonnées
LABEL maintainer="SLASHR <contact@slashr.fr>"
LABEL version="2.0.0"
LABEL description="Keyword-URL Matcher v2 Premium"

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV DEBIAN_FRONTEND=noninteractive

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Créer un utilisateur non-root
RUN useradd --create-home --shell /bin/bash app

# Définir le répertoire de travail
WORKDIR /app

# Copier les fichiers de dépendances
COPY requirements.txt .

# Installer les dépendances Python
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Copier le code de l'application
COPY . .

# Créer les dossiers nécessaires avec les bonnes permissions
RUN mkdir -p uploads results models static templates data && \
    chown -R app:app /app && \
    chmod -R 755 /app

# Changer vers l'utilisateur non-root
USER app

# Exposer le port
EXPOSE 8000

# Vérification de santé
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Commande par défaut avec Gunicorn pour la production
CMD ["gunicorn", "app.main:app", "-w", "1", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000", "--timeout", "300", "--preload"] 
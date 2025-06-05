#!/bin/bash

# Script de déploiement pour Keyword-URL Matcher
# À exécuter dans le dossier /seo-tools/ sur le VPS

set -e

echo "🚀 Déploiement de Keyword-URL Matcher"

# Variables
PROJECT_NAME="keyword-matcher"
CONTAINER_PREFIX="keyword-matcher"

# Vérifier que nous sommes dans le bon dossier
if [[ ! -f "docker-compose.prod.yml" ]]; then
    echo "❌ Erreur: docker-compose.prod.yml non trouvé"
    echo "Assurez-vous d'être dans le dossier du projet"
    exit 1
fi

# Créer les dossiers de données s'ils n'existent pas
echo "📁 Création des dossiers de données..."
mkdir -p data/{uploads,results,models,static}
chmod -R 755 data/

# Copier le fichier d'environnement
if [[ -f "env.production" ]]; then
    cp env.production .env
    echo "✅ Fichier .env configuré"
else
    echo "⚠️  Fichier env.production non trouvé, utilisation des variables par défaut"
fi

# Arrêter les anciens conteneurs s'ils existent
echo "🛑 Arrêt des anciens conteneurs..."
docker-compose -f docker-compose.prod.yml down --remove-orphans || true

# Supprimer les anciennes images (optionnel)
read -p "Supprimer les anciennes images Docker ? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🗑️  Suppression des anciennes images..."
    docker system prune -f
    docker image prune -f
fi

# Construire les nouvelles images
echo "🔨 Construction des images Docker..."
docker-compose -f docker-compose.prod.yml build --no-cache

# Démarrer les services
echo "🚀 Démarrage des services..."
docker-compose -f docker-compose.prod.yml up -d

# Vérifier que les services sont démarrés
echo "⏳ Vérification du démarrage des services..."
sleep 10

# Vérifier le statut des conteneurs
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    echo "✅ Services démarrés avec succès !"
    
    # Afficher les informations de connexion
    echo ""
    echo "🌐 L'application est accessible à :"
    echo "   - URL: http://$(hostname -I | awk '{print $1}'):8080/seo-tools/keyword-matcher/"
    echo "   - ou avec votre domaine: https://exemple.com/seo-tools/keyword-matcher/"
    echo ""
    echo "📊 Monitoring :"
    echo "   - Logs: docker-compose -f docker-compose.prod.yml logs -f"
    echo "   - Status: docker-compose -f docker-compose.prod.yml ps"
    echo ""
    
    # Afficher les logs récents
    echo "📋 Logs récents :"
    docker-compose -f docker-compose.prod.yml logs --tail=20
    
else
    echo "❌ Erreur lors du démarrage des services"
    echo "📋 Logs d'erreur :"
    docker-compose -f docker-compose.prod.yml logs
    exit 1
fi

echo "🎉 Déploiement terminé !" 
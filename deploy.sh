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

# Vérifier que Redis est accessible
echo "🔍 Vérification de la connectivité Redis..."
if docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 ping | grep -q "PONG"; then
    echo "✅ Redis existant accessible"
else
    echo "❌ Erreur: Redis existant non accessible sur 172.17.0.1:6379"
    echo "Vérifiez que Redis est bien démarré avec docker ps"
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
sleep 15

# Vérifier le statut des conteneurs
if docker-compose -f docker-compose.prod.yml ps | grep -q "Up"; then
    echo "✅ Services démarrés avec succès !"
    
    # Tester la connectivité Redis depuis le conteneur
    echo "🔍 Test de connectivité Redis depuis le conteneur..."
    if docker exec keyword-matcher-app python -c "import redis; r=redis.from_url('redis://172.17.0.1:6379/2'); print('Redis OK:', r.ping())" 2>/dev/null; then
        echo "✅ Connexion Redis OK depuis le conteneur"
    else
        echo "⚠️  Problème de connexion Redis depuis le conteneur"
    fi
    
    # Afficher les informations de connexion
    echo ""
    echo "🌐 L'application est accessible à :"
    echo "   - URL: http://$(hostname -I | awk '{print $1}'):8081/seo-tools/keyword-matcher/"
    echo "   - ou avec votre domaine: https://exemple.com/seo-tools/keyword-matcher/"
    echo ""
    echo "📊 Monitoring :"
    echo "   - Logs: docker-compose -f docker-compose.prod.yml logs -f"
    echo "   - Status: docker-compose -f docker-compose.prod.yml ps"
    echo "   - Redis partagé: docker exec keyword-matcher-app redis-cli -h 172.17.0.1 -p 6379 -n 2 info"
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
echo ""
echo "💡 Informations importantes :"
echo "   - L'outil utilise le Redis existant (DB 2 pour éviter les conflits)"
echo "   - Port modifié en 8081 pour éviter les conflits avec les autres services"
echo "   - Pas de nouveau conteneur Redis créé = économie de RAM" 
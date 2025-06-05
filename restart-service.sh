#!/bin/bash

# Script de redémarrage propre pour keyword-matcher
# À exécuter depuis /seo-tools/

set -e

echo "🔄 Redémarrage propre de keyword-matcher"

# Vérifier qu'on est dans le bon dossier
if [[ ! -f "docker-compose.yml" ]]; then
    echo "❌ Erreur: Vous devez être dans /seo-tools/"
    exit 1
fi

# Arrêter complètement le service
echo "🛑 Arrêt complet du service..."
docker-compose stop keyword-matcher
docker-compose rm -f keyword-matcher

# Nettoyer les processus orphelins
echo "🧹 Nettoyage des processus orphelins..."
docker system prune -f

# Vérifier Redis
echo "🔍 Vérification Redis..."
if docker exec redis-judge redis-cli ping | grep -q "PONG"; then
    echo "✅ Redis accessible"
else
    echo "❌ Problème Redis"
    exit 1
fi

# Nettoyer la DB keyword-matcher si nécessaire
read -p "Nettoyer la base Redis keyword-matcher (DB 2) ? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🧹 Nettoyage base Redis..."
    docker exec redis-judge redis-cli -n 2 flushdb
fi

# Reconstruire l'image
echo "🔨 Reconstruction de l'image..."
docker-compose build --no-cache keyword-matcher

# Redémarrer avec un seul worker
echo "🚀 Redémarrage du service..."
docker-compose up -d keyword-matcher

# Attendre le démarrage
echo "⏳ Attente du démarrage (20s)..."
sleep 20

# Vérifier le statut
if docker ps | grep -q "keyword-matcher.*Up"; then
    echo "✅ Service redémarré avec succès !"
    
    # Tester l'endpoint
    echo "🔍 Test de l'endpoint..."
    if curl -s http://localhost:8011/health | grep -q "healthy"; then
        echo "✅ Endpoint opérationnel"
    else
        echo "⚠️  Problème avec l'endpoint"
    fi
    
    # Afficher les logs récents
    echo "📋 Logs récents (10 dernières lignes) :"
    docker-compose logs --tail=10 keyword-matcher
    
else
    echo "❌ Échec du redémarrage"
    echo "📋 Logs d'erreur :"
    docker-compose logs keyword-matcher
    exit 1
fi

echo ""
echo "🎉 Redémarrage terminé !"
echo "📊 Commandes utiles :"
echo "   - Logs: docker-compose logs -f keyword-matcher"
echo "   - Test: curl http://localhost:8011/health"
echo "   - Interface: https://agence-slashr.fr/keyword-matcher/" 
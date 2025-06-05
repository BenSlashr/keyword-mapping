#!/bin/bash

# Script de déploiement pour intégrer Keyword-URL Matcher
# À exécuter depuis /seo-tools/keyword-matcher/

set -e

echo "🚀 Intégration de Keyword-URL Matcher dans l'architecture SEO-Tools"

# Vérifier qu'on est dans le bon dossier
if [[ ! -f "app/main.py" ]]; then
    echo "❌ Erreur: Assurez-vous d'être dans le dossier keyword-matcher"
    exit 1
fi

# Aller dans le dossier parent (seo-tools)
cd ..

# Vérifier qu'on est dans seo-tools
if [[ ! -f "docker-compose.yml" ]]; then
    echo "❌ Erreur: docker-compose.yml principal non trouvé"
    echo "Assurez-vous d'être dans /seo-tools/"
    exit 1
fi

# Vérifier que redis-judge tourne
echo "🔍 Vérification de redis-judge..."
if docker ps | grep -q "redis-judge"; then
    echo "✅ redis-judge est en cours d'exécution"
else
    echo "❌ redis-judge n'est pas démarré. Lancement..."
    docker-compose up -d redis-judge
    sleep 5
fi

# Créer les dossiers de données pour keyword-matcher
echo "📁 Création des dossiers de données..."
mkdir -p keyword-matcher/data/{uploads,results,models}
chmod -R 755 keyword-matcher/data/

# Copier le fichier d'environnement
if [[ -f "keyword-matcher/env.production" ]]; then
    cp keyword-matcher/env.production keyword-matcher/.env
    echo "✅ Fichier .env configuré"
else
    echo "⚠️  Fichier env.production non trouvé"
fi

# Vérifier si le service keyword-matcher existe déjà dans docker-compose.yml
if grep -q "keyword-matcher:" docker-compose.yml; then
    echo "✅ Service keyword-matcher déjà présent dans docker-compose.yml"
else
    echo "⚠️  Le service keyword-matcher n'est pas dans docker-compose.yml"
    echo "📋 Ajoutez cette configuration dans votre docker-compose.yml :"
    echo ""
    cat keyword-matcher/docker-service.yml
    echo ""
    read -p "Continuer quand même ? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Arrêter keyword-matcher s'il existe
echo "🛑 Arrêt de l'ancien conteneur keyword-matcher..."
docker-compose stop keyword-matcher 2>/dev/null || true
docker-compose rm -f keyword-matcher 2>/dev/null || true

# Construire et démarrer keyword-matcher
echo "🔨 Construction et démarrage de keyword-matcher..."
docker-compose build keyword-matcher
docker-compose up -d keyword-matcher

# Attendre le démarrage
echo "⏳ Attente du démarrage (15s)..."
sleep 15

# Vérifier que le service est démarré
if docker ps | grep -q "keyword-matcher"; then
    echo "✅ keyword-matcher démarré avec succès !"
    
    # Test de santé
    echo "🔍 Test de santé..."
    if curl -s http://localhost:8011/health | grep -q "healthy"; then
        echo "✅ Service opérationnel"
    else
        echo "⚠️  Service démarré mais test de santé échoué"
    fi
    
    # Test Redis
    echo "🔍 Test connexion Redis..."
    if docker exec keyword-matcher python -c "
import redis
r = redis.from_url('redis://redis-judge:6379/2')
print('Redis ping:', r.ping())
" 2>/dev/null | grep -q "True"; then
        echo "✅ Connexion Redis OK"
    else
        echo "⚠️  Problème de connexion Redis"
    fi
    
    # Informations de connexion
    echo ""
    echo "🌐 L'application est accessible à :"
    echo "   - URL locale: http://localhost:8011/keyword-matcher/"
    echo "   - URL publique: https://agence-slashr.fr/keyword-matcher/"
    echo ""
    echo "📊 Monitoring :"
    echo "   - Logs: docker-compose logs -f keyword-matcher"
    echo "   - Status: docker-compose ps"
    echo "   - Redis: docker exec keyword-matcher redis-cli -h redis-judge -p 6379 -n 2 info"
    echo ""
    echo "📋 Configuration Nginx à ajouter :"
    echo "   Voir le fichier: keyword-matcher/nginx-config-example.conf"
    
else
    echo "❌ Erreur lors du démarrage"
    echo "📋 Logs d'erreur :"
    docker-compose logs keyword-matcher
    exit 1
fi

echo "🎉 Intégration terminée !"
echo ""
echo "💡 Prochaines étapes :"
echo "   1. Ajouter la configuration Nginx (voir nginx-config-example.conf)"
echo "   2. Recharger Nginx: sudo systemctl reload nginx"
echo "   3. Tester l'accès: https://agence-slashr.fr/keyword-matcher/" 
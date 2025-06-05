#!/bin/bash

# Script de test de connectivité Redis
echo "🔍 Test de connectivité Redis pour Keyword-URL Matcher"

# Test 1: Redis accessible depuis l'hôte
echo "1️⃣ Test Redis depuis l'hôte..."
if docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 ping | grep -q "PONG"; then
    echo "   ✅ Redis accessible depuis l'hôte"
else
    echo "   ❌ Redis non accessible depuis l'hôte"
    exit 1
fi

# Test 2: Vérifier les bases de données Redis utilisées
echo "2️⃣ Vérification des bases de données Redis..."
echo "   📋 Bases de données en cours d'utilisation :"
for db in {0..5}; do
    keys=$(docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 -n $db dbsize 2>/dev/null || echo "0")
    if [ "$keys" != "0" ]; then
        echo "      - DB $db: $keys clés"
    fi
done

# Test 3: Test de la DB 2 (celle qu'on va utiliser)
echo "3️⃣ Test de la base de données 2..."
test_key="keyword-matcher-test-$(date +%s)"
if docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 -n 2 set "$test_key" "test-value" > /dev/null; then
    if docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 -n 2 get "$test_key" | grep -q "test-value"; then
        echo "   ✅ Lecture/écriture OK sur DB 2"
        docker run --rm redis:7-alpine redis-cli -h 172.17.0.1 -p 6379 -n 2 del "$test_key" > /dev/null
    else
        echo "   ❌ Problème de lecture sur DB 2"
        exit 1
    fi
else
    echo "   ❌ Problème d'écriture sur DB 2"
    exit 1
fi

# Test 4: Si le conteneur keyword-matcher existe, tester depuis l'intérieur
if docker ps | grep -q "keyword-matcher-app"; then
    echo "4️⃣ Test depuis le conteneur keyword-matcher..."
    if docker exec keyword-matcher-app python -c "
import redis
import sys
try:
    r = redis.from_url('redis://172.17.0.1:6379/2')
    r.ping()
    r.set('test-from-container', 'ok')
    value = r.get('test-from-container')
    r.delete('test-from-container')
    if value == b'ok':
        print('✅ Connexion Redis OK depuis le conteneur')
        sys.exit(0)
    else:
        print('❌ Problème de données Redis depuis le conteneur')
        sys.exit(1)
except Exception as e:
    print(f'❌ Erreur Redis depuis le conteneur: {e}')
    sys.exit(1)
" 2>/dev/null; then
        echo "   ✅ Test conteneur réussi"
    else
        echo "   ⚠️  Problème de connexion depuis le conteneur"
    fi
else
    echo "4️⃣ Conteneur keyword-matcher non trouvé (normal si pas encore déployé)"
fi

echo ""
echo "🎉 Tests de connectivité Redis terminés"
echo "💡 Configuration recommandée : REDIS_URL=redis://172.17.0.1:6379/2" 
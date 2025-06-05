# Guide de Déploiement - Keyword-URL Matcher

## Architecture de déploiement

L'outil sera accessible à `agence-slashr.fr/keyword-matcher/` et s'intègre dans votre architecture SEO-Tools existante :

```
/seo-tools/
├── docker-compose.yml            # Orchestration principale (EXISTANT)
├── redis-judge (conteneur)       # Redis partagé (EXISTANT)
├── bigbrother/                   # Port 8007 (EXISTANT)
├── analyseur-entites/            # Port 8008 (EXISTANT)
├── robots/                       # Port 8009 (EXISTANT)
├── judge/                        # Port 8010 (EXISTANT)
└── keyword-matcher/              # Port 8011 (NOUVEAU)
    ├── Dockerfile
    ├── env.production
    ├── docker-service.yml
    ├── app/
    ├── templates/
    └── data/
```

## Économies de ressources

✅ **Redis partagé** : Utilise `redis-judge` existant (DB 2)
✅ **Architecture unifiée** : Un seul docker-compose.yml
✅ **Pas de nouveau worker** : Système de jobs asyncio intégré

**Économie estimée** : ~150-200 MB de RAM

## Étapes de déploiement

### 1. Préparation

```bash
# Sur votre VPS, aller dans seo-tools
cd /var/www/seo-tools

# Cloner le projet keyword-matcher
git clone <votre-repo> keyword-matcher
# ou
scp -r ./keyword-matcher user@vps:/var/www/seo-tools/
```

### 2. Configuration du docker-compose principal

Ajoutez cette section dans votre `/var/www/seo-tools/docker-compose.yml` :

```yaml
  keyword-matcher:
    build: ./keyword-matcher
    container_name: keyword-matcher
    ports:
      - "8011:8000"
    env_file:
      - ./keyword-matcher/.env
    environment:
      - PORT=8000
      - HOST=0.0.0.0
      - BASE_PATH=/keyword-matcher
      - REDIS_URL=redis://redis-judge:6379/2
      - DEBUG=False
      - MAX_KEYWORDS=1000000
      - MAX_PAGES=50000
    volumes:
      - ./keyword-matcher/data/uploads:/app/uploads
      - ./keyword-matcher/data/results:/app/results
      - ./keyword-matcher/data/models:/app/models
    depends_on:
      - redis-judge
    restart: unless-stopped
```

### 3. Configuration d'environnement

```bash
cd keyword-matcher

# Configurer l'environnement
cp env.production .env

# Éditer si nécessaire
nano .env
```

### 4. Déploiement automatique

```bash
# Dans /seo-tools/keyword-matcher/
chmod +x deploy-integration.sh
./deploy-integration.sh
```

Le script va :
1. ✅ Vérifier que redis-judge tourne
2. 📁 Créer les dossiers de données
3. 🔨 Construire et démarrer le service
4. 🔍 Tester la connectivité Redis
5. 📋 Afficher les instructions Nginx

### 5. Configuration Nginx

Ajoutez cette section dans votre configuration Nginx principale :

```nginx
# Dans votre configuration Nginx existante
location /keyword-matcher/ {
    proxy_pass http://127.0.0.1:8011/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Prefix /keyword-matcher;
    
    # Pour les WebSockets
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Timeouts
    proxy_connect_timeout 60s;
    proxy_send_timeout 60s;
    proxy_read_timeout 300s;
}

location = /keyword-matcher {
    return 301 /keyword-matcher/;
}
```

Puis recharger Nginx :
```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 6. Vérification

```bash
# Status des conteneurs
docker-compose ps

# Test local
curl http://localhost:8011/health

# Test public (après config Nginx)
curl https://agence-slashr.fr/keyword-matcher/health

# Logs
docker-compose logs -f keyword-matcher
```

## Gestion Redis partagé

### Répartition des bases de données
- **DB 0** : Judge SEO
- **DB 1** : Autres projets
- **DB 2** : Keyword-URL Matcher (nouveau)

### Monitoring Redis
```bash
# État général
docker exec redis-judge redis-cli info

# Utilisation par base
for db in {0..2}; do 
    echo "DB $db: $(docker exec redis-judge redis-cli -n $db dbsize) clés"
done

# Jobs keyword-matcher en cours
docker exec redis-judge redis-cli -n 2 keys "*job*"
```

## Commandes de gestion

### Service keyword-matcher
```bash
# Démarrer/Arrêter
docker-compose up -d keyword-matcher
docker-compose stop keyword-matcher

# Logs en temps réel
docker-compose logs -f keyword-matcher

# Redémarrer après modification
docker-compose build keyword-matcher
docker-compose up -d keyword-matcher
```

### Maintenance
```bash
# Mise à jour du code
cd /var/www/seo-tools/keyword-matcher
git pull origin main
cd ..
docker-compose build keyword-matcher
docker-compose up -d keyword-matcher

# Nettoyer la DB Redis si nécessaire
docker exec redis-judge redis-cli -n 2 flushdb

# Sauvegarde des données
tar -czf backup_keyword_matcher_$(date +%Y%m%d).tar.gz keyword-matcher/data/
```

## Ports utilisés

| Service | Port | URL |
|---------|------|-----|
| bigbrother | 8007 | /bigbrother/ |
| analyseur-entites | 8008 | /analyseur-entites/ |
| robots | 8009 | /robots/ |
| judge-app | 8010 | /judge/ |
| **keyword-matcher** | **8011** | **/keyword-matcher/** |

## Troubleshooting

### Service ne démarre pas
```bash
# Vérifier les logs
docker-compose logs keyword-matcher

# Vérifier Redis
docker ps | grep redis-judge
docker exec redis-judge redis-cli ping

# Reconstruire l'image
docker-compose build --no-cache keyword-matcher
```

### Problèmes Redis
```bash
# Tester la connexion
docker exec keyword-matcher python -c "
import redis
r = redis.from_url('redis://redis-judge:6379/2')
print('Redis OK:', r.ping())
"

# Vérifier les logs Redis
docker logs redis-judge
```

### Conflits de ports
Si le port 8011 est occupé, modifiez dans `docker-compose.yml` :
```yaml
ports:
  - "8012:8000"  # Ou un autre port libre
```

Et mettez à jour la configuration Nginx correspondante.

## Avantages de cette intégration

✅ **Cohérence** : Même pattern que vos autres outils
✅ **Simplicité** : Un seul docker-compose pour tout
✅ **Performance** : Redis optimisé et partagé
✅ **Maintenance** : Gestion centralisée des services
✅ **Économie** : Pas de duplication d'infrastructure

## URLs finales

- **Interface** : https://agence-slashr.fr/keyword-matcher/
- **API** : https://agence-slashr.fr/keyword-matcher/docs
- **Health** : https://agence-slashr.fr/keyword-matcher/health 
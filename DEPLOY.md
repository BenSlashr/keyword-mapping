# Guide de Déploiement - Keyword-URL Matcher

## Architecture de déploiement

L'outil sera accessible à `exemple.com/seo-tools/keyword-matcher/` avec la configuration suivante :

```
VPS
├── /seo-tools/                    # Dossier principal 
│   ├── docker-compose.yml         # Orchestration des services
│   └── keyword-matcher/           # Votre outil
│       ├── docker-compose.prod.yml
│       ├── Dockerfile.prod
│       ├── nginx/
│       ├── app/
│       └── templates/
```

## Prérequis

- Docker et Docker Compose installés sur le VPS
- Nom de domaine configuré vers le VPS
- Reverse proxy global (Nginx/Traefik) configuré si nécessaire

## Étapes de déploiement

### 1. Préparation sur le VPS

```bash
# Se connecter au VPS
ssh user@votre-vps.com

# Créer la structure de dossiers
mkdir -p /var/www/seo-tools
cd /var/www/seo-tools

# Cloner ou copier le projet
git clone <votre-repo> keyword-matcher
# ou
scp -r ./keyword-matcher user@vps:/var/www/seo-tools/
```

### 2. Configuration

```bash
cd keyword-matcher

# Copier et modifier le fichier d'environnement
cp env.production .env

# Éditer avec vos paramètres
nano .env
```

Modifiez les variables importantes :
```env
DOMAIN=votre-domaine.com
ROOT_PATH=/seo-tools/keyword-matcher
GOOGLE_REDIRECT_URI=https://votre-domaine.com/seo-tools/keyword-matcher/auth/callback
```

### 3. Déploiement automatique

```bash
# Rendre le script exécutable
chmod +x deploy.sh

# Lancer le déploiement
./deploy.sh
```

### 4. Configuration du reverse proxy principal

Si vous avez un Nginx principal sur le VPS, ajoutez cette configuration :

```nginx
# /etc/nginx/sites-available/seo-tools
server {
    listen 80;
    server_name votre-domaine.com;

    # Redirection HTTPS (recommandé)
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name votre-domaine.com;

    # Configuration SSL
    ssl_certificate /path/to/your/cert.pem;
    ssl_certificate_key /path/to/your/key.pem;

    # Proxy vers le conteneur keyword-matcher
    location /seo-tools/keyword-matcher/ {
        proxy_pass http://127.0.0.1:8080/seo-tools/keyword-matcher/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Pour les WebSockets
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # Autres configurations pour d'autres outils...
}
```

### 5. Vérification

```bash
# Vérifier les conteneurs
docker-compose -f docker-compose.prod.yml ps

# Vérifier les logs
docker-compose -f docker-compose.prod.yml logs -f keyword-matcher

# Test de santé
curl http://localhost:8080/seo-tools/keyword-matcher/health
```

## Commandes utiles

### Gestion des services
```bash
# Démarrer
docker-compose -f docker-compose.prod.yml up -d

# Arrêter
docker-compose -f docker-compose.prod.yml down

# Redémarrer un service
docker-compose -f docker-compose.prod.yml restart keyword-matcher

# Voir les logs
docker-compose -f docker-compose.prod.yml logs -f
```

### Maintenance
```bash
# Mise à jour du code
git pull origin main
docker-compose -f docker-compose.prod.yml build --no-cache
docker-compose -f docker-compose.prod.yml up -d

# Nettoyage
docker system prune -f
docker image prune -f

# Sauvegarde des données
tar -czf backup_$(date +%Y%m%d).tar.gz data/
```

### Monitoring
```bash
# Utilisation des ressources
docker stats

# Espace disque
du -sh data/

# Logs d'erreur spécifiques
docker-compose -f docker-compose.prod.yml logs keyword-matcher | grep ERROR
```

## Troubleshooting

### L'application n'est pas accessible
1. Vérifier que les conteneurs tournent : `docker-compose -f docker-compose.prod.yml ps`
2. Vérifier les logs : `docker-compose -f docker-compose.prod.yml logs`
3. Tester en local : `curl http://localhost:8080/seo-tools/keyword-matcher/health`

### WebSocket ne fonctionne pas
1. Vérifier la configuration nginx pour les upgrades WebSocket
2. S'assurer que le port 8080 est accessible
3. Vérifier les headers de forwarding

### Problèmes de performance
1. Augmenter les ressources Docker si nécessaire
2. Vérifier l'utilisation disque : `df -h`
3. Monitorer la RAM : `free -h`

### Erreurs de permissions
```bash
# Corriger les permissions des dossiers de données
sudo chown -R 1000:1000 data/
chmod -R 755 data/
```

## Sécurité

- Utilisez HTTPS en production
- Configurez un firewall pour limiter l'accès aux ports
- Mettez à jour régulièrement les images Docker
- Sauvegardez régulièrement les données importantes

## Support

En cas de problème :
1. Consultez les logs avec `docker-compose -f docker-compose.prod.yml logs`
2. Vérifiez la configuration dans `env.production`
3. Testez les endpoints avec curl
4. Vérifiez la connectivité Redis 
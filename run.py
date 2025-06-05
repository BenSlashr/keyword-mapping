#!/usr/bin/env python3
"""
Script de démarrage pour Keyword-URL Matcher v2 Premium
"""

import os
import sys
import uvicorn
from app.config import Config

def main():
    """Point d'entrée principal"""
    
    # Vérifier que Redis est accessible
    try:
        import redis
        redis_client = redis.from_url(Config.REDIS_URL)
        redis_client.ping()
        print("✅ Connexion Redis OK")
    except Exception as e:
        print(f"❌ Erreur connexion Redis: {e}")
        print("Assurez-vous que Redis est démarré : redis-server")
        sys.exit(1)
    
    # Créer les dossiers nécessaires
    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(Config.RESULTS_DIR, exist_ok=True)
    os.makedirs(Config.MODELS_DIR, exist_ok=True)
    os.makedirs("templates", exist_ok=True)
    os.makedirs("static", exist_ok=True)
    
    print("🚀 Démarrage Keyword-URL Matcher v2 Premium")
    print(f"📊 Interface web: http://localhost:8000")
    print(f"📋 API docs: http://localhost:8000/docs")
    print(f"📈 Métriques: http://localhost:{Config.PROMETHEUS_PORT}/metrics")
    
    # Démarrer l'application
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=Config.DEBUG,
        log_level="info",
        access_log=True
    )

if __name__ == "__main__":
    main() 
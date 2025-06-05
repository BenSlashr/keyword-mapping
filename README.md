# Keyword-URL Matcher v2 Premium

> Outil d'assignation automatique de mots-clés vers des pages web avec scoring hybride avancé

## 🚀 Fonctionnalités

- **Assignation automatique** de mots-clés vers pages avec algorithme de scoring hybride
- **Embeddings passage-level** avec FAISS pour recherche sémantique ultra-rapide
- **Scoring hybride** combinant embeddings, BM25, similarité de titre et numérique
- **Seuil adaptatif** basé sur Q3 - 1.5*IQR pour optimisation automatique
- **Détection de cannibalisation** via intégration Google Search Console
- **Interface web moderne** avec Alpine.js et Tailwind CSS
- **Exports multiples** : Excel formaté, CSV, JSON, rapport HTML
- **Monitoring temps réel** avec métriques Prometheus
- **Crawling en direct** et support sitemap XML
- **API RESTful** complète avec WebSockets

## 📋 Prérequis

- Python 3.9+
- Redis Server
- 8GB RAM minimum (16GB recommandé)
- GPU optionnel (accélération FAISS)

## 🛠️ Installation

### 1. Cloner le repository
```bash
git clone https://github.com/votre-org/keyword-url-matcher-v2.git
cd keyword-url-matcher-v2
```

### 2. Créer un environnement virtuel
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou
venv\Scripts\activate  # Windows
```

### 3. Installer les dépendances
```bash
pip install -r requirements.txt
```

### 4. Configuration
```bash
cp env.example .env
# Éditer .env avec vos paramètres
```

Variables d'environnement importantes :
```env
REDIS_URL=redis://localhost:6379/0
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
MAX_KEYWORDS=1000000
MAX_PAGES=50000
```

### 5. Démarrer Redis
```bash
redis-server
```

### 6. Démarrer l'application
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

L'application sera accessible sur `http://localhost:8000`

## 📊 Utilisation

### Interface Web

1. **Upload des mots-clés** : Fichier CSV avec colonnes `keyword, volume`
2. **Source des pages** : 
   - CSV avec colonnes `url, content`
   - URL de sitemap XML
   - Crawl en direct depuis une URL seed
3. **Configuration avancée** :
   - Seuil minimal de score
   - Pondération du volume
   - Nombre de suggestions alternatives
   - Activation Search Console
4. **Monitoring en temps réel** via WebSocket
5. **Export des résultats** en multiple formats

### API REST

#### Créer un job de matching
```bash
curl -X POST "http://localhost:8000/jobs/match" \
  -F "keywords_file=@keywords.csv" \
  -F "pages_file=@pages.csv" \
  -F "source_type=csv" \
  -F "min_score_threshold=0.50"
```

#### Suivre la progression
```bash
curl "http://localhost:8000/jobs/{job_id}"
```

#### Récupérer les résultats
```bash
# JSON
curl "http://localhost:8000/jobs/{job_id}/result"

# Excel
curl "http://localhost:8000/jobs/{job_id}/result?format=xlsx" -o results.xlsx

# CSV
curl "http://localhost:8000/jobs/{job_id}/result?format=csv" -o results.csv
```

## 🧠 Algorithme de Scoring

### Composants du score hybride

```python
score = 0.55 * embedding_sim + 0.25 * bm25_score + 0.10 * title_sim + 0.10 * numeric_sim
```

1. **Embedding Similarity (55%)** : Similarité cosinus entre embeddings
2. **BM25 Score (25%)** : Score BM25 traditionnel
3. **Title Similarity (10%)** : Similarité avec le titre de page
4. **Numeric Similarity (10%)** : Correspondance des valeurs numériques

### Seuil adaptatif
```python
score_threshold = max(Q3(scores) - 1.5 * IQR(scores), 0.50)
```

## 📈 Performance

### Benchmarks

| Taille | Temps (8 vCPU) | RAM | 
|--------|----------------|-----|
| 50k KW × 5k pages | ≤ 6 min | < 8 GB |
| 1M KW × 50k pages | ≤ 40 min | 32 GB |

### Optimisations

- **FAISS HNSW** : Index haute performance avec ef=200, M=32
- **Chunking intelligent** : 512 tokens avec overlap 128
- **Cache embeddings** : SHA-256 based, évite les recalculs
- **Processing parallèle** : Traitement par batches optimisé

## 🔍 Monitoring

### Métriques Prometheus

- `keyword_matcher_keywords_processed_total` : Mots-clés traités
- `keyword_matcher_processing_duration_seconds` : Temps de traitement
- `keyword_matcher_faiss_queries_total` : Requêtes FAISS
- `keyword_matcher_memory_usage_bytes` : Utilisation mémoire
- `keyword_matcher_active_jobs` : Jobs actifs

### Endpoints de santé

```bash
# Status général
curl http://localhost:8000/health

# Métriques détaillées
curl http://localhost:8000/metrics
```

## 🔧 Configuration avancée

### Weights du scoring
```python
WEIGHTS = {
    "embedding": 0.55,  # Poids des embeddings
    "bm25": 0.25,       # Poids BM25
    "title": 0.10,      # Poids titre
    "numeric": 0.10     # Poids numérique
}
```

### Paramètres FAISS
```python
FAISS_EF_SEARCH = 200      # Précision recherche
FAISS_M_CONNECTIONS = 32   # Connections HNSW
```

### Chunking
```python
CHUNK_SIZE = 512          # Taille des chunks
CHUNK_OVERLAP = 128       # Overlap entre chunks
```

## 🔐 Intégration Google Search Console

### Configuration OAuth

1. Créer un projet dans Google Cloud Console
2. Activer l'API Search Console
3. Créer des identifiants OAuth 2.0
4. Configurer les variables d'environnement

### Détection de cannibalisation

L'outil compare automatiquement :
- URLs assignées par l'algorithme
- URLs top CTR dans Search Console (90 derniers jours)
- Calcul de perte de confiance estimée

## 📊 Formats d'export

### Excel (.xlsx)
- **Summary** : Statistiques générales
- **Assignments** : Assignations détaillées
- **Orphans** : Mots-clés orphelins
- **Cannibalization** : Alertes de cannibalisation

### CSV
- Format unifié avec colonnes `type` pour filtrage
- Encoding UTF-8 avec BOM

### JSON
- Structure complète des résultats
- Métadonnées d'export incluses

### HTML
- Rapport interactif avec graphiques
- Top assignations et distributions

## 🐳 Déploiement Docker

```bash
# Build
docker build -t keyword-matcher-v2 .

# Run
docker run -d \
  --name keyword-matcher \
  -p 8000:8000 \
  -e REDIS_URL=redis://redis:6379/0 \
  keyword-matcher-v2
```

### Docker Compose
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - redis
  
  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
```

## 🧪 Tests

```bash
# Tests unitaires
pytest tests/

# Tests d'intégration
pytest tests/integration/

# Tests de performance
pytest tests/performance/ -v
```

### Golden Set
- 200 mots-clés labellisés manuellement
- Precision@1 ≥ 0.85 requis en CI
- Régression automatique détectée

## 📝 API Documentation

Documentation interactive disponible sur :
- Swagger UI : `http://localhost:8000/docs`
- ReDoc : `http://localhost:8000/redoc`

### Endpoints principaux

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/jobs/match` | Créer un job de matching |
| GET | `/jobs/{id}` | Status du job |
| GET | `/jobs/{id}/result` | Résultats du job |
| DELETE | `/jobs/{id}` | Annuler un job |
| GET | `/health` | Santé de l'application |
| GET | `/metrics` | Métriques Prometheus |

## 🤝 Contribution

1. Fork le repository
2. Créer une branche feature : `git checkout -b feature/amazing-feature`
3. Commit : `git commit -m 'Add amazing feature'`
4. Push : `git push origin feature/amazing-feature`
5. Ouvrir une Pull Request

## 📄 Licence

Ce projet est sous licence MIT. Voir `LICENSE` pour plus de détails.

## 🏢 Support

Développé par **SLASHK** - Agence SEO à Lille

- 📧 Email : contact@slashk.fr
- 🌐 Website : https://slashk.fr
- 📱 LinkedIn : @slashk-seo

## 🔄 Changelog

### v2.0.0 (2024)
- ✨ Algorithme de scoring hybride
- ✨ Interface web moderne
- ✨ Intégration Search Console
- ✨ Monitoring Prometheus
- ✨ Exports multiples
- ✨ API WebSocket temps réel

### v1.0.0 (2023)
- 🎉 Version initiale CLI
- 📊 Scoring basique TF-IDF 
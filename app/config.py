"""Configuration et paramètres de l'application"""

import os
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuration principale de l'application"""
    
    # Redis
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Google Search Console
    GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
    GOOGLE_REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
    
    # Application
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"
    ROOT_PATH = os.getenv("ROOT_PATH", "")
    DOMAIN = os.getenv("DOMAIN", "localhost")
    MAX_KEYWORDS = int(os.getenv("MAX_KEYWORDS", 1000000))
    MAX_PAGES = int(os.getenv("MAX_PAGES", 50000))
    MAX_UPLOAD_SIZE = os.getenv("MAX_UPLOAD_SIZE", "500MB")
    
    # Performance FAISS
    FAISS_EF_SEARCH = int(os.getenv("FAISS_EF_SEARCH", 200))
    FAISS_M_CONNECTIONS = int(os.getenv("FAISS_M_CONNECTIONS", 32))
    
    # Chunking
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 128))
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", 384))
    
    # Pondération du score hybride
    WEIGHTS = {
        "embedding": float(os.getenv("EMBEDDING_WEIGHT", 0.55)),
        "bm25": float(os.getenv("BM25_WEIGHT", 0.25)),
        "title": float(os.getenv("TITLE_WEIGHT", 0.1)),
        "numeric": float(os.getenv("NUMERIC_WEIGHT", 0.1))
    }
    
    # Seuils
    MIN_SCORE_THRESHOLD = float(os.getenv("MIN_SCORE_THRESHOLD", 0.20))
    MIN_CONFIDENCE_DISPLAY = float(os.getenv("MIN_CONFIDENCE_DISPLAY", 0.30))
    
    # Monitoring
    ENABLE_PROMETHEUS = os.getenv("ENABLE_PROMETHEUS", "True").lower() == "true"
    PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", 9090))
    
    # Modèle d'embeddings
    EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    
    # Dossiers de travail
    UPLOAD_DIR = "uploads"
    RESULTS_DIR = "results"
    MODELS_DIR = "models"
    
    @classmethod
    def get_all(cls) -> Dict[str, Any]:
        """Retourne toutes les configurations sous forme de dictionnaire"""
        return {
            key: getattr(cls, key) 
            for key in dir(cls) 
            if not key.startswith('_') and key.isupper()
        } 
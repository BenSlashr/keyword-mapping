"""Module de gestion des embeddings et similarité"""

import numpy as np
import faiss
from typing import List, Dict, Tuple, Optional
from sentence_transformers import SentenceTransformer
import logging
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pickle
import os
from tqdm import tqdm

from ..config import Config
from ..models import Page

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Gestionnaire des embeddings et de l'index FAISS"""
    
    def __init__(self):
        self.model = None
        self.index = None
        self.chunk_metadata = []  # Liste des métadonnées pour chaque chunk
        self.url_to_chunks = {}   # Mapping URL -> liste des indices de chunks
        self.chunk_cache = {}     # Cache des embeddings par hash de contenu
        
    def initialize_model(self):
        """Initialise le modèle de sentence transformers"""
        logger.info(f"Chargement du modèle d'embeddings: {Config.EMBEDDING_MODEL}")
        self.model = SentenceTransformer(Config.EMBEDDING_MODEL)
        logger.info("Modèle d'embeddings chargé avec succès")
        
    def create_faiss_index(self, dimension: int = Config.EMBEDDING_DIMENSION):
        """Crée un index FAISS avec similarité cosinus"""
        logger.info(f"Création de l'index FAISS cosinus (dimension={dimension})")
        
        # Index avec similarité cosinus pour une meilleure précision sémantique
        self.index = faiss.IndexFlatIP(dimension)  # Inner Product = cosinus pour vecteurs normalisés
        
        logger.info("Index FAISS créé avec succès")
        
    def chunk_text(self, text: str, chunk_size: int = Config.CHUNK_SIZE, 
                   overlap: int = Config.CHUNK_OVERLAP) -> List[str]:
        """Découpe un texte en chunks avec overlap"""
        if not text or len(text.strip()) == 0:
            return []
            
        words = text.split()
        if len(words) <= chunk_size:
            return [text]
            
        chunks = []
        for i in range(0, len(words), chunk_size - overlap):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            chunks.append(chunk_text)
            
            # Arrêter si on a dépassé la fin du texte
            if i + chunk_size >= len(words):
                break
                
        return chunks
    
    def get_content_hash(self, content: str) -> str:
        """Génère un hash SHA-256 du contenu pour le cache"""
        return hashlib.sha256(content.encode('utf-8')).hexdigest()
    
    def extract_weighted_content(self, page: Page) -> str:
        """Extrait et pondère le contenu d'une page selon les poids configurés"""
        content_parts = []
        
        # Title avec poids x3
        if page.title:
            content_parts.extend([page.title] * 3)
            
        # H1 avec poids x2  
        if page.h1:
            content_parts.extend([page.h1] * 2)
            
        # Meta description avec poids x2
        if page.meta_description:
            content_parts.extend([page.meta_description] * 2)
            
        # H2 et H3 avec poids x1.5
        if page.h2:
            for h2 in page.h2:
                content_parts.extend([h2] * 1)
        if page.h3:
            for h3 in page.h3:
                content_parts.extend([h3] * 1)
                
        # Body content avec poids x1
        if page.content:
            content_parts.append(page.content)
            
        return ' '.join(content_parts)
    
    def process_pages(self, pages: List[Page], show_progress: bool = True) -> Dict[str, List[int]]:
        """Traite une liste de pages et crée les embeddings"""
        if not self.model:
            self.initialize_model()
            
        if not self.index:
            self.create_faiss_index()
            
        logger.info(f"Traitement de {len(pages)} pages")
        
        all_chunks = []
        new_embeddings = []
        
        iterator = tqdm(pages, desc="Traitement des pages") if show_progress else pages
        
        for page in iterator:
            # Extraction du contenu pondéré
            weighted_content = self.extract_weighted_content(page)
            
            # Hash du contenu pour cache
            content_hash = self.get_content_hash(weighted_content)
            
            # Chunking
            chunks = self.chunk_text(weighted_content)
            page_chunk_indices = []
            
            for chunk_idx, chunk_text in enumerate(chunks):
                chunk_hash = self.get_content_hash(chunk_text)
                
                # Vérifier le cache
                if chunk_hash in self.chunk_cache:
                    embedding = self.chunk_cache[chunk_hash]
                else:
                    # Calculer l'embedding
                    embedding = self.model.encode([chunk_text])[0]
                    self.chunk_cache[chunk_hash] = embedding
                    
                # Ajouter aux données
                chunk_metadata = {
                    'url': page.url,
                    'chunk_index': chunk_idx,
                    'chunk_text': chunk_text,
                    'chunk_hash': chunk_hash,
                    'title': page.title,
                    'page_position': len(all_chunks)
                }
                
                self.chunk_metadata.append(chunk_metadata)
                all_chunks.append(chunk_text)
                new_embeddings.append(embedding)
                page_chunk_indices.append(len(self.chunk_metadata) - 1)
                
            self.url_to_chunks[page.url] = page_chunk_indices
            
        # Ajouter les embeddings à l'index FAISS
        if new_embeddings:
            embeddings_array = np.array(new_embeddings).astype('float32')
            # Normaliser les embeddings pour la similarité cosinus
            faiss.normalize_L2(embeddings_array)
            self.index.add(embeddings_array)
            
        logger.info(f"Index FAISS mis à jour: {self.index.ntotal} embeddings total")
        
        return self.url_to_chunks
    
    def search_similar_chunks(self, query: str, k: int = 10) -> List[Tuple[int, float]]:
        """Recherche les chunks les plus similaires à une requête"""
        if not self.model or not self.index:
            raise ValueError("Modèle ou index non initialisé")
            
        if self.index.ntotal == 0:
            return []
            
        # Encoder la requête
        query_embedding = self.model.encode([query]).astype('float32')
        # Normaliser la requête pour la similarité cosinus
        faiss.normalize_L2(query_embedding)
        
        # Rechercher dans l'index
        scores, indices = self.index.search(query_embedding, k)
        
        # Avec IndexFlatIP et vecteurs normalisés, les scores sont directement les similarités cosinus
        similarities = []
        for score, idx in zip(scores[0], indices[0]):
            if idx != -1:  # -1 indique aucun résultat trouvé
                # Les scores sont déjà des similarités cosinus (entre -1 et 1)
                similarity = max(0.0, float(score))  # Garder seulement les scores positifs
                similarities.append((int(idx), similarity))
                
        return similarities
    
    def get_chunk_metadata(self, chunk_index: int) -> Optional[Dict]:
        """Récupère les métadonnées d'un chunk"""
        if 0 <= chunk_index < len(self.chunk_metadata):
            return self.chunk_metadata[chunk_index]
        return None
    
    def save_index(self, filepath: str):
        """Sauvegarde l'index FAISS et les métadonnées"""
        if self.index:
            # Sauvegarder l'index FAISS
            faiss.write_index(self.index, f"{filepath}.faiss")
            
            # Sauvegarder les métadonnées
            metadata = {
                'chunk_metadata': self.chunk_metadata,
                'url_to_chunks': self.url_to_chunks,
                'chunk_cache': self.chunk_cache
            }
            
            with open(f"{filepath}.metadata.pkl", 'wb') as f:
                pickle.dump(metadata, f)
                
            logger.info(f"Index sauvegardé: {filepath}")
    
    def load_index(self, filepath: str):
        """Charge un index FAISS et ses métadonnées"""
        try:
            # Charger l'index FAISS
            self.index = faiss.read_index(f"{filepath}.faiss")
            
            # Charger les métadonnées
            with open(f"{filepath}.metadata.pkl", 'rb') as f:
                metadata = pickle.load(f)
                
            self.chunk_metadata = metadata['chunk_metadata']
            self.url_to_chunks = metadata['url_to_chunks']
            self.chunk_cache = metadata.get('chunk_cache', {})
            
            logger.info(f"Index chargé: {filepath} ({self.index.ntotal} embeddings)")
            
        except Exception as e:
            logger.error(f"Erreur lors du chargement de l'index: {e}")
            raise
    
    def get_stats(self) -> Dict[str, int]:
        """Retourne les statistiques de l'index"""
        return {
            'total_embeddings': self.index.ntotal if self.index else 0,
            'total_chunks': len(self.chunk_metadata),
            'total_pages': len(self.url_to_chunks),
            'cache_size': len(self.chunk_cache)
        } 
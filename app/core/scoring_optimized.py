"""Module de scoring hybride OPTIMISÉ pour des performances maximales"""

import re
import math
import numpy as np
from typing import List, Dict, Tuple, Optional
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity
import logging

from ..config import Config
from ..models import Keyword, Assignment

logger = logging.getLogger(__name__)


class OptimizedHybridScorer:
    """Version ultra-optimisée du scoring hybride"""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self.bm25_model = None
        self.title_embeddings_cache = {}  # Cache des embeddings de titre
        self.corpus_texts = None
        self._precompute_data()
        
    def _precompute_data(self):
        """Précalcule toutes les données nécessaires UNE SEULE FOIS"""
        logger.info("🚀 Précalcul des données pour optimisation...")
        
        # 1. Préparer le corpus une seule fois
        self.corpus_texts = [meta['chunk_text'] for meta in self.embedding_manager.chunk_metadata]
        
        # 2. Créer le modèle BM25 une seule fois
        if self.corpus_texts:
            processed_corpus = [self.preprocess_text(text) for text in self.corpus_texts]
            tokenized_corpus = [text.split() for text in processed_corpus]
            self.bm25_model = BM25Okapi(tokenized_corpus)
            logger.info(f"✅ Modèle BM25 créé pour {len(self.corpus_texts)} chunks")
        
        # 3. Précalculer tous les embeddings de titre
        if self.embedding_manager.model:
            unique_titles = set()
            for meta in self.embedding_manager.chunk_metadata:
                title = meta.get('title')
                if title and title not in unique_titles:
                    unique_titles.add(title)
            
            if unique_titles:
                titles_list = list(unique_titles)
                title_embeddings = self.embedding_manager.model.encode(titles_list)
                
                for title, embedding in zip(titles_list, title_embeddings):
                    self.title_embeddings_cache[title] = embedding
                
                logger.info(f"✅ {len(unique_titles)} embeddings de titre précalculés")
    
    def preprocess_text(self, text: str) -> str:
        """Version simplifiée et rapide du préprocessing"""
        if not text:
            return ""
        return re.sub(r'[^\w\s]', ' ', text.lower()).strip()
    
    def get_bm25_scores_batch(self, keyword_tokens: List[str]) -> np.ndarray:
        """Calcule les scores BM25 pour tous les chunks en une fois"""
        if not self.bm25_model:
            return np.zeros(len(self.corpus_texts))
        
        return np.array(self.bm25_model.get_scores(keyword_tokens))
    
    def assign_keywords_to_pages_optimized(self, keywords: List[Keyword], 
                                         top_suggestions: int = 3) -> Tuple[List[Assignment], List[Keyword]]:
        """Version ultra-optimisée de l'assignation"""
        
        if not self.embedding_manager.index or self.embedding_manager.index.ntotal == 0:
            logger.error("Index FAISS vide ou non initialisé")
            return [], keywords
        
        assignments = []
        orphan_keywords = []
        
        logger.info(f"🚀 Assignation optimisée de {len(keywords)} mots-clés")
        
        # Traitement par batch pour réduire les appels répétés
        for keyword in keywords:
            try:
                # 1. Recherche FAISS optimisée (moins de chunks)
                similar_chunks = self.embedding_manager.search_similar_chunks(
                    keyword.keyword, k=min(10, self.embedding_manager.index.ntotal)  # Réduit de 50 à 10
                )
                
                if not similar_chunks:
                    orphan_keywords.append(keyword)
                    continue
                
                # 2. Calcul BM25 optimisé
                keyword_tokens = self.preprocess_text(keyword.keyword).split()
                bm25_scores = self.get_bm25_scores_batch(keyword_tokens)
                
                # 3. Calcul des scores finaux sans logging excessif
                chunk_scores = []
                for chunk_idx, embedding_sim in similar_chunks:
                    chunk_metadata = self.embedding_manager.get_chunk_metadata(chunk_idx)
                    if not chunk_metadata:
                        continue
                    
                    # Score hybride simplifié
                    scores = {
                        'embedding': float(embedding_sim),
                        'bm25': min(float(bm25_scores[chunk_idx]) / 10.0, 1.0) if chunk_idx < len(bm25_scores) else 0.0,
                        'title': 0.0,  # Calcul différé
                        'numeric': 0.0  # Désactivé pour l'optimisation
                    }
                    
                    # Embedding de titre depuis le cache
                    title = chunk_metadata.get('title')
                    if title and title in self.title_embeddings_cache:
                        keyword_embedding = self.embedding_manager.model.encode([keyword.keyword])
                        title_embedding = self.title_embeddings_cache[title]
                        title_sim = cosine_similarity(keyword_embedding, title_embedding.reshape(1, -1))[0][0]
                        scores['title'] = max(0.0, float(title_sim))
                    
                    # Score final
                    final_score = (
                        Config.WEIGHTS['embedding'] * scores['embedding'] +
                        Config.WEIGHTS['bm25'] * scores['bm25'] +
                        Config.WEIGHTS['title'] * scores['title']
                        # Pas de score numérique pour l'optimisation
                    )
                    
                    chunk_scores.append({
                        'score': final_score,
                        'chunk_idx': chunk_idx,
                        'metadata': chunk_metadata
                    })
                
                if not chunk_scores:
                    orphan_keywords.append(keyword)
                    continue
                
                # Tri et assignation
                chunk_scores.sort(key=lambda x: x['score'], reverse=True)
                best_score = chunk_scores[0]['score']
                
                # Seuil fixe simplifié au lieu du calcul adaptatif
                if best_score >= 0.15:  # Seuil fixe pour l'optimisation
                    best_chunk = chunk_scores[0]
                    alternatives = [
                        cs['metadata']['url'] for cs in chunk_scores[1:top_suggestions+1]
                        if cs['metadata']['url'] != best_chunk['metadata']['url']
                    ]
                    
                    assignment = Assignment(
                        keyword=keyword.keyword,
                        url=best_chunk['metadata']['url'],
                        score=best_score,
                        chunk_position=best_chunk['metadata']['chunk_index'],
                        alternative_urls=alternatives[:top_suggestions],
                        is_manual=False
                    )
                    
                    assignments.append(assignment)
                else:
                    orphan_keywords.append(keyword)
                    
            except Exception as e:
                logger.error(f"Erreur assignation {keyword.keyword}: {e}")
                orphan_keywords.append(keyword)
        
        logger.info(f"✅ Assignation terminée: {len(assignments)} assignés, {len(orphan_keywords)} orphelins")
        return assignments, orphan_keywords 
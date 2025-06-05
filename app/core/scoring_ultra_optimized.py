"""Module de scoring hybride ULTRA-OPTIMISÉ pour performances extrêmes"""

import re
import numpy as np
from typing import List, Dict, Tuple
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity
import logging

from ..config import Config
from ..models import Keyword, Assignment

logger = logging.getLogger(__name__)


class UltraOptimizedHybridScorer:
    """Version ultra-optimisée avec batch processing"""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self.bm25_model = None
        self.title_embeddings_cache = {}
        self.keyword_embeddings_cache = {}  # Cache des embeddings de mots-clés
        self.corpus_texts = None
        self._precompute_data()
        
    def _precompute_data(self):
        """Précalcule toutes les données nécessaires"""
        logger.info("🚀 Précalcul ultra-optimisé...")
        
        self.corpus_texts = [meta['chunk_text'] for meta in self.embedding_manager.chunk_metadata]
        
        if self.corpus_texts:
            # BM25 avec preprocessing minimal
            tokenized_corpus = [text.lower().split() for text in self.corpus_texts]
            self.bm25_model = BM25Okapi(tokenized_corpus)
            logger.info(f"✅ BM25 créé pour {len(self.corpus_texts)} chunks")
        
        # Cache des embeddings de titre avec batch encoding
        if self.embedding_manager.model:
            unique_titles = set()
            for meta in self.embedding_manager.chunk_metadata:
                title = meta.get('title')
                if title:
                    unique_titles.add(title)
            
            if unique_titles:
                titles_list = list(unique_titles)
                # Encoder tous les titres en une fois (batch)
                title_embeddings = self.embedding_manager.model.encode(titles_list, batch_size=32)
                
                for title, embedding in zip(titles_list, title_embeddings):
                    self.title_embeddings_cache[title] = embedding
                
                logger.info(f"✅ {len(unique_titles)} titres encodés en batch")
    
    def precompute_keyword_embeddings(self, keywords: List[Keyword]):
        """Précalcule tous les embeddings de mots-clés en batch"""
        keyword_texts = [kw.keyword for kw in keywords]
        
        # Encoder tous les mots-clés en une fois
        keyword_embeddings = self.embedding_manager.model.encode(keyword_texts, batch_size=64)
        
        for keyword, embedding in zip(keyword_texts, keyword_embeddings):
            self.keyword_embeddings_cache[keyword] = embedding
        
        logger.info(f"✅ {len(keywords)} mots-clés encodés en batch")
    
    def assign_keywords_to_pages_ultra_optimized(self, keywords: List[Keyword], 
                                               top_suggestions: int = 3) -> Tuple[List[Assignment], List[Keyword]]:
        """Version ultra-optimisée avec batch processing"""
        
        if not self.embedding_manager.index or self.embedding_manager.index.ntotal == 0:
            logger.error("Index FAISS vide")
            return [], keywords
        
        # 1. Précalculer tous les embeddings de mots-clés
        self.precompute_keyword_embeddings(keywords)
        
        assignments = []
        orphan_keywords = []
        
        logger.info(f"🚀 Processing ultra-optimisé de {len(keywords)} mots-clés")
        
        # 2. Traitement streamliné
        for keyword in keywords:
            try:
                # Recherche FAISS ultra-réduite
                similar_chunks = self.embedding_manager.search_similar_chunks(
                    keyword.keyword, k=min(5, self.embedding_manager.index.ntotal)  # Réduit à 5
                )
                
                if not similar_chunks:
                    orphan_keywords.append(keyword)
                    continue
                
                # Score simplifié sans BM25 pour gagner en vitesse
                best_score = 0.0
                best_metadata = None
                
                for chunk_idx, embedding_sim in similar_chunks:
                    chunk_metadata = self.embedding_manager.get_chunk_metadata(chunk_idx)
                    if not chunk_metadata:
                        continue
                    
                    # Score ultra-simplifié : embedding + title seulement
                    score = float(embedding_sim) * 0.7  # Poids embedding
                    
                    # Score titre depuis cache
                    title = chunk_metadata.get('title')
                    if title and title in self.title_embeddings_cache and keyword.keyword in self.keyword_embeddings_cache:
                        keyword_emb = self.keyword_embeddings_cache[keyword.keyword]
                        title_emb = self.title_embeddings_cache[title]
                        title_sim = float(np.dot(keyword_emb, title_emb) / (np.linalg.norm(keyword_emb) * np.linalg.norm(title_emb)))
                        score += max(0.0, title_sim) * 0.3  # Poids titre
                    
                    if score > best_score:
                        best_score = score
                        best_metadata = chunk_metadata
                
                # Seuil ultra-bas pour maximiser les assignations
                if best_score >= 0.10 and best_metadata:
                    assignment = Assignment(
                        keyword=keyword.keyword,
                        url=best_metadata['url'],
                        score=best_score,
                        chunk_position=best_metadata['chunk_index'],
                        alternative_urls=[],  # Pas d'alternatives pour optimiser
                        is_manual=False
                    )
                    assignments.append(assignment)
                else:
                    orphan_keywords.append(keyword)
                    
            except Exception as e:
                logger.error(f"Erreur {keyword.keyword}: {e}")
                orphan_keywords.append(keyword)
        
        logger.info(f"✅ Ultra-optimisé terminé: {len(assignments)} assignés")
        return assignments, orphan_keywords 
"""Module de scoring FINAL OPTIMISÉ - Version production ultra-rapide"""

import numpy as np
from typing import List, Tuple
import logging

from ..models import Keyword, Assignment

logger = logging.getLogger(__name__)


class FinalOptimizedScorer:
    """Version finale optimisée pour production - objectif < 60s"""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self.keyword_embeddings = None
        self.all_chunk_embeddings = None
        self._prepare_vectorized_data()
        
    def _prepare_vectorized_data(self):
        """Prépare toutes les données en format vectorisé pour NumPy"""
        logger.info("🚀 Préparation vectorisée finale...")
        
        # Récupérer tous les embeddings de chunks depuis FAISS
        if self.embedding_manager.index and self.embedding_manager.index.ntotal > 0:
            # Extraire directement tous les vecteurs de l'index FAISS
            self.all_chunk_embeddings = self.embedding_manager.index.reconstruct_n(0, self.embedding_manager.index.ntotal)
            logger.info(f"✅ {len(self.all_chunk_embeddings)} embeddings extraits de FAISS")
    
    def assign_keywords_vectorized(self, keywords: List[Keyword], top_suggestions: int = 3) -> Tuple[List[Assignment], List[Keyword]]:
        """Assignation vectorisée ultra-rapide avec NumPy pur"""
        
        if self.all_chunk_embeddings is None or len(self.all_chunk_embeddings) == 0:
            logger.error("Pas d'embeddings disponibles")
            return [], keywords
        
        # 1. Encoder tous les mots-clés en batch
        keyword_texts = [kw.keyword for kw in keywords]
        self.keyword_embeddings = self.embedding_manager.model.encode(keyword_texts, batch_size=128)
        
        logger.info(f"🚀 Calcul vectorisé pour {len(keywords)} mots-clés")
        
        # 2. Calcul de similarité vectorisé pour TOUS les mots-clés d'un coup
        # Shape: (n_keywords, n_chunks)
        similarity_matrix = np.dot(self.keyword_embeddings, self.all_chunk_embeddings.T)
        
        # 3. Pour chaque mot-clé, trouver les meilleurs chunks
        assignments = []
        orphan_keywords = []
        
        threshold = 0.05  # Seuil ultra-bas pour maximiser les assignations
        
        for i, keyword in enumerate(keywords):
            # Récupérer les scores de similarité pour ce mot-clé
            keyword_scores = similarity_matrix[i]
            
            # Trouver les indices des meilleurs chunks (triés par score décroissant)
            top_indices = np.argsort(keyword_scores)[::-1][:top_suggestions + 1]  # +1 pour la meilleure + alternatives
            top_scores = keyword_scores[top_indices]
            
            # Vérifier si le meilleur score dépasse le seuil
            best_score = top_scores[0]
            if best_score >= threshold:
                # Récupérer les métadonnées du meilleur chunk
                best_chunk_metadata = self.embedding_manager.get_chunk_metadata(int(top_indices[0]))
                if best_chunk_metadata:
                    # Construire la liste des URLs alternatives
                    alternative_urls = []
                    best_url = best_chunk_metadata['url']
                    
                    for j in range(1, min(len(top_indices), top_suggestions + 1)):
                        alt_metadata = self.embedding_manager.get_chunk_metadata(int(top_indices[j]))
                        if alt_metadata and alt_metadata['url'] != best_url:
                            alternative_urls.append(alt_metadata['url'])
                            if len(alternative_urls) >= top_suggestions:
                                break
                    
                    assignment = Assignment(
                        keyword=keyword.keyword,
                        url=best_url,
                        score=float(best_score),
                        chunk_position=best_chunk_metadata['chunk_index'],
                        alternative_urls=alternative_urls,
                        is_manual=False
                    )
                    assignments.append(assignment)
                else:
                    orphan_keywords.append(keyword)
            else:
                orphan_keywords.append(keyword)
        
        logger.info(f"✅ Vectorisé terminé: {len(assignments)} assignés, {len(orphan_keywords)} orphelins")
        return assignments, orphan_keywords 
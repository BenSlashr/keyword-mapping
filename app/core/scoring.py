"""Module de scoring hybride pour l'assignation keyword-URL"""

import re
import math
import numpy as np
from typing import List, Dict, Tuple, Optional
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import logging

from ..config import Config
from ..models import Keyword, Assignment

logger = logging.getLogger(__name__)


class HybridScorer:
    """Calculateur de score hybride pour l'assignation mots-clés vers pages"""
    
    def __init__(self, embedding_manager):
        self.embedding_manager = embedding_manager
        self.bm25_models = {}  # Cache des modèles BM25 par ensemble de documents
        self.tfidf_vectorizer = TfidfVectorizer(
            lowercase=True,
            stop_words=None,  # Nous gérerons les stop words nous-mêmes
            ngram_range=(1, 2)
        )
        
    def preprocess_text(self, text: str) -> str:
        """Préprocesse le texte (lowercase, suppression des stop words)"""
        if not text:
            return ""
            
        # Lowercase
        text = text.lower()
        
        # Suppression des caractères spéciaux mais conservation des espaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Suppression des espaces multiples
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    def extract_numbers(self, text: str) -> List[float]:
        """Extrait les nombres d'un texte"""
        numbers = re.findall(r'\d+(?:\.\d+)?', text)
        return [float(num) for num in numbers]
    
    def numeric_similarity(self, keyword: str, content: str) -> float:
        """Calcule la similarité numérique entre keyword et contenu"""
        kw_numbers = self.extract_numbers(keyword)
        content_numbers = self.extract_numbers(content)
        
        if not kw_numbers or not content_numbers:
            return 0.0
            
        # Calculer la distance minimale entre les nombres
        min_distance = float('inf')
        for kw_num in kw_numbers:
            for content_num in content_numbers:
                distance = abs(kw_num - content_num) / max(kw_num, content_num, 1.0)
                min_distance = min(min_distance, distance)
                
        # Convertir la distance en similarité
        return 1.0 - min(min_distance, 1.0)
    
    def get_bm25_score(self, keyword: str, chunk_text: str, corpus_texts: List[str]) -> float:
        """Calcule le score BM25 pour un keyword sur un chunk"""
        # Créer un identifiant unique pour ce corpus
        corpus_id = hash(tuple(corpus_texts[:10]))  # Utiliser les 10 premiers pour l'ID
        
        # Vérifier si le modèle BM25 est en cache
        if corpus_id not in self.bm25_models:
            logger.info(f"Création du modèle BM25 pour corpus de {len(corpus_texts)} documents")
            
            # Préprocesser tous les textes
            processed_corpus = [self.preprocess_text(text) for text in corpus_texts]
            tokenized_corpus = [text.split() for text in processed_corpus]
            
            # Créer le modèle BM25
            self.bm25_models[corpus_id] = BM25Okapi(tokenized_corpus)
            
        bm25_model = self.bm25_models[corpus_id]
        
        # Calculer le score BM25
        processed_keyword = self.preprocess_text(keyword)
        keyword_tokens = processed_keyword.split()
        
        # Trouver l'index du chunk dans le corpus
        processed_chunk = self.preprocess_text(chunk_text)
        try:
            chunk_index = [self.preprocess_text(text) for text in corpus_texts].index(processed_chunk)
            scores = bm25_model.get_scores(keyword_tokens)
            return float(scores[chunk_index]) if chunk_index < len(scores) else 0.0
        except ValueError:
            # Si le chunk n'est pas trouvé, calculer directement
            chunk_tokens = processed_chunk.split()
            return bm25_model.get_score(keyword_tokens, chunk_tokens)
    
    def calculate_hybrid_score(self, keyword: Keyword, chunk_metadata: Dict, 
                             corpus_texts: List[str], title_embedding: Optional[np.ndarray] = None) -> float:
        """Calcule le score hybride pour une paire keyword-chunk"""
        
        scores = {}
        
        # 1. Similarité par embeddings (déjà calculée par FAISS)
        # Cette valeur sera fournie par la recherche FAISS
        embed_sim = chunk_metadata.get('embedding_similarity', 0.0)
        scores['embedding'] = embed_sim
        
        # 2. Score BM25
        chunk_text = chunk_metadata.get('chunk_text', '')
        try:
            bm25_score = self.get_bm25_score(keyword.keyword, chunk_text, corpus_texts)
            # Normaliser le score BM25 (généralement entre 0-10)
            bm25_score = min(bm25_score / 10.0, 1.0)
            scores['bm25'] = bm25_score
        except Exception as e:
            logger.warning(f"Erreur calcul BM25: {e}")
            scores['bm25'] = 0.0
        
        # 3. Similarité avec le titre
        if title_embedding is not None and self.embedding_manager.model:
            try:
                keyword_embedding = self.embedding_manager.model.encode([keyword.keyword])
                title_sim = cosine_similarity(keyword_embedding, title_embedding.reshape(1, -1))[0][0]
                scores['title'] = max(0.0, float(title_sim))
            except Exception as e:
                logger.warning(f"Erreur calcul similarité titre: {e}")
                scores['title'] = 0.0
        else:
            scores['title'] = 0.0
        
        # 4. Similarité numérique
        try:
            num_sim = self.numeric_similarity(keyword.keyword, chunk_text)
            scores['numeric'] = num_sim
        except Exception as e:
            logger.warning(f"Erreur calcul similarité numérique: {e}")
            scores['numeric'] = 0.0
        
        # Calcul du score final pondéré
        final_score = (
            Config.WEIGHTS['embedding'] * scores['embedding'] +
            Config.WEIGHTS['bm25'] * scores['bm25'] +
            Config.WEIGHTS['title'] * scores['title'] +
            Config.WEIGHTS['numeric'] * scores['numeric']
        )
        
        # Log détaillé pour debug
        logger.debug(f"Scores pour '{keyword.keyword}' -> '{chunk_metadata.get('url', '')[:50]}...': "
                    f"embed={scores['embedding']:.3f}, bm25={scores['bm25']:.3f}, "
                    f"title={scores['title']:.3f}, numeric={scores['numeric']:.3f}, "
                    f"final={final_score:.3f}")
        
        return final_score
    
    def calculate_adaptive_threshold(self, scores: List[float]) -> float:
        """Calcule le seuil adaptatif basé sur Q3 - 1.5*IQR"""
        if not scores or len(scores) < 4:
            return Config.MIN_SCORE_THRESHOLD
            
        scores = sorted(scores)
        n = len(scores)
        
        # Calcul des quartiles
        q1_index = n // 4
        q3_index = 3 * n // 4
        
        q1 = scores[q1_index]
        q3 = scores[q3_index]
        iqr = q3 - q1
        
        # Seuil adaptatif : Q3 - 1.5*IQR
        adaptive_threshold = q3 - 1.5 * iqr
        
        # S'assurer que le seuil n'est pas trop bas
        final_threshold = max(adaptive_threshold, Config.MIN_SCORE_THRESHOLD)
        
        logger.info(f"Seuil adaptatif calculé: {final_threshold:.3f} "
                   f"(Q1={q1:.3f}, Q3={q3:.3f}, IQR={iqr:.3f})")
        
        return final_threshold
    
    def assign_keywords_to_pages(self, keywords: List[Keyword], 
                               top_suggestions: int = 3) -> Tuple[List[Assignment], List[Keyword]]:
        """Assigne les mots-clés aux pages en utilisant le scoring hybride"""
        
        if not self.embedding_manager.index or self.embedding_manager.index.ntotal == 0:
            logger.error("Index FAISS vide ou non initialisé")
            return [], keywords
            
        assignments = []
        orphan_keywords = []
        
        # Préparer le corpus pour BM25
        corpus_texts = [meta['chunk_text'] for meta in self.embedding_manager.chunk_metadata]
        
        logger.info(f"Assignation de {len(keywords)} mots-clés")
        
        for keyword in keywords:
            try:
                # Recherche des chunks similaires avec FAISS
                similar_chunks = self.embedding_manager.search_similar_chunks(
                    keyword.keyword, k=min(50, self.embedding_manager.index.ntotal)
                )
                
                if not similar_chunks:
                    logger.warning(f"Aucun chunk trouvé pour: {keyword.keyword}")
                    orphan_keywords.append(keyword)
                    continue
                
                # Calculer les scores hybrides pour chaque chunk
                chunk_scores = []
                for chunk_idx, embedding_sim in similar_chunks:
                    chunk_metadata = self.embedding_manager.get_chunk_metadata(chunk_idx)
                    if not chunk_metadata:
                        continue
                        
                    # Ajouter la similarité d'embedding aux métadonnées
                    chunk_metadata['embedding_similarity'] = embedding_sim
                    
                    # Calculer le titre embedding si disponible
                    title_embedding = None
                    if chunk_metadata.get('title') and self.embedding_manager.model:
                        title_embedding = self.embedding_manager.model.encode([chunk_metadata['title']])[0]
                    
                    # Calculer le score hybride
                    hybrid_score = self.calculate_hybrid_score(
                        keyword, chunk_metadata, corpus_texts, title_embedding
                    )
                    
                    chunk_scores.append({
                        'score': hybrid_score,
                        'chunk_idx': chunk_idx,
                        'metadata': chunk_metadata
                    })
                
                # Trier par score décroissant
                chunk_scores.sort(key=lambda x: x['score'], reverse=True)
                
                if not chunk_scores:
                    orphan_keywords.append(keyword)
                    continue
                
                # Calculer le seuil adaptatif
                all_scores = [cs['score'] for cs in chunk_scores]
                adaptive_threshold = self.calculate_adaptive_threshold(all_scores)
                
                # Vérifier si le meilleur score dépasse le seuil
                best_score = chunk_scores[0]['score']
                if best_score >= adaptive_threshold:
                    # Créer l'assignation
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
                    logger.debug(f"Assigné: {keyword.keyword} -> {assignment.url} (score: {best_score:.3f})")
                    
                else:
                    logger.debug(f"Score trop bas pour {keyword.keyword}: {best_score:.3f} < {adaptive_threshold:.3f}")
                    orphan_keywords.append(keyword)
                    
            except Exception as e:
                logger.error(f"Erreur lors de l'assignation de {keyword.keyword}: {e}")
                orphan_keywords.append(keyword)
        
        logger.info(f"Assignations créées: {len(assignments)}, Orphelins: {len(orphan_keywords)}")
        
        return assignments, orphan_keywords 
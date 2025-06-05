"""Gestionnaire de jobs pour le traitement asynchrone"""

import asyncio
import logging
import json
import pandas as pd
import time
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Any
from celery import Celery
import redis
import psutil

from ..config import Config
from ..models import (
    JobProgress, JobResult, JobStatus, SourceType, 
    Keyword, Assignment, CannibalAlert
)
from ..core.embeddings import EmbeddingManager
from ..core.scoring import HybridScorer
from ..core.scoring_optimized import OptimizedHybridScorer
from ..core.scoring_ultra_optimized import UltraOptimizedHybridScorer
from ..core.scoring_final_optimized import FinalOptimizedScorer
from ..core.parsers import PageLoader
from .search_console import SearchConsoleService

logger = logging.getLogger(__name__)

# Configuration Celery
celery_app = Celery(
    'keyword_matcher',
    broker=Config.REDIS_URL,
    backend=Config.REDIS_URL
)

celery_app.conf.update(
    task_serializer='json',
    result_serializer='json',
    accept_content=['json'],
    result_expires=3600,
    timezone='UTC',
    enable_utc=True,
)


class JobManager:
    """Gestionnaire principal des jobs de matching"""
    
    def __init__(self):
        self.redis_client = redis.from_url(Config.REDIS_URL)
        self.active_jobs = {}
        
    async def create_job(self, job_id: str, params: Dict[str, Any]) -> bool:
        """Crée un nouveau job dans Redis"""
        try:
            job_data = {
                'job_id': job_id,
                'status': JobStatus.PENDING,
                'progress': 0.0,
                'eta_seconds': None,
                'memory_mb': 0.0,
                'current_step': 'Initialisation',
                'error_message': None,
                'created_at': datetime.utcnow().isoformat(),
                'params': params
            }
            
            # Stocker dans Redis
            self.redis_client.setex(
                f"job:{job_id}",
                3600,  # Expire après 1 heure
                json.dumps(job_data)
            )
            
            logger.info(f"Job créé: {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Erreur création job {job_id}: {e}")
            return False
    
    async def get_job_progress(self, job_id: str) -> Optional[JobProgress]:
        """Récupère la progression d'un job"""
        try:
            job_data_str = self.redis_client.get(f"job:{job_id}")
            if not job_data_str:
                return None
            
            job_data = json.loads(job_data_str)
            
            return JobProgress(
                job_id=job_data['job_id'],
                status=JobStatus(job_data['status']),
                progress=job_data['progress'],
                eta_seconds=job_data.get('eta_seconds'),
                memory_mb=job_data['memory_mb'],
                current_step=job_data['current_step'],
                error_message=job_data.get('error_message')
            )
            
        except Exception as e:
            logger.error(f"Erreur récupération progression job {job_id}: {e}")
            return None
    
    async def update_job_progress(self, job_id: str, **updates) -> bool:
        """Met à jour la progression d'un job"""
        try:
            job_data_str = self.redis_client.get(f"job:{job_id}")
            if not job_data_str:
                return False
            
            job_data = json.loads(job_data_str)
            job_data.update(updates)
            
            # Mettre à jour la mémoire utilisée
            process = psutil.Process()
            job_data['memory_mb'] = process.memory_info().rss / 1024 / 1024
            
            self.redis_client.setex(
                f"job:{job_id}",
                3600,
                json.dumps(job_data)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur mise à jour job {job_id}: {e}")
            return False
    
    async def get_job_result(self, job_id: str) -> Optional[JobResult]:
        """Récupère le résultat d'un job terminé"""
        try:
            result_data_str = self.redis_client.get(f"result:{job_id}")
            if not result_data_str:
                return None
            
            result_data = json.loads(result_data_str)
            
            # Reconstituer les objets
            assignments = [Assignment(**a) for a in result_data['assignments']]
            orphans = [Keyword(**k) for k in result_data['orphans']]
            cannibals = [CannibalAlert(**c) for c in result_data['cannibals']]
            
            return JobResult(
                job_id=result_data['job_id'],
                assignments=assignments,
                orphans=orphans,
                cannibals=cannibals,
                stats=result_data['stats'],
                created_at=result_data['created_at'],
                completed_at=result_data.get('completed_at')
            )
            
        except Exception as e:
            logger.error(f"Erreur récupération résultat job {job_id}: {e}")
            return None
    
    async def save_job_result(self, job_id: str, result: JobResult) -> bool:
        """Sauvegarde le résultat d'un job"""
        try:
            result_data = {
                'job_id': result.job_id,
                'assignments': [a.dict() for a in result.assignments],
                'orphans': [k.dict() for k in result.orphans],
                'cannibals': [c.dict() for c in result.cannibals],
                'stats': result.stats,
                'created_at': result.created_at,
                'completed_at': result.completed_at
            }
            
            self.redis_client.setex(
                f"result:{job_id}",
                86400,  # Expire après 24 heures
                json.dumps(result_data)
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde résultat job {job_id}: {e}")
            return False
    
    async def cancel_job(self, job_id: str) -> bool:
        """Annule un job en cours"""
        try:
            # Marquer le job comme annulé
            await self.update_job_progress(
                job_id,
                status=JobStatus.FAILED.value,
                error_message="Job annulé par l'utilisateur"
            )
            
            # Supprimer de la liste des jobs actifs si présent
            if job_id in self.active_jobs:
                del self.active_jobs[job_id]
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur annulation job {job_id}: {e}")
            return False
    
    async def list_jobs(self, status: Optional[JobStatus] = None, limit: int = 50) -> List[Dict]:
        """Liste les jobs avec filtrage optionnel"""
        try:
            jobs = []
            keys = self.redis_client.keys("job:*")
            
            for key in keys[:limit]:
                job_data_str = self.redis_client.get(key)
                if job_data_str:
                    job_data = json.loads(job_data_str)
                    
                    # Filtrer par statut si spécifié
                    if status is None or job_data['status'] == status.value:
                        jobs.append({
                            'job_id': job_data['job_id'],
                            'status': job_data['status'],
                            'progress': job_data['progress'],
                            'created_at': job_data['created_at'],
                            'current_step': job_data['current_step']
                        })
            
            # Trier par date de création (plus récent en premier)
            jobs.sort(key=lambda x: x['created_at'], reverse=True)
            
            return jobs
            
        except Exception as e:
            logger.error(f"Erreur listage jobs: {e}")
            return []
    
    async def run_matching_job(self, job_id: str, params: Dict[str, Any]):
        """Exécute un job de matching en arrière-plan"""
        start_time = time.time()
        
        try:
            await self.update_job_progress(
                job_id,
                status=JobStatus.PROCESSING.value,
                current_step="Démarrage du traitement",
                progress=0.0
            )
            
            # 1. Charger les mots-clés (5%)
            await self.update_job_progress(
                job_id,
                current_step="Chargement des mots-clés",
                progress=5.0
            )
            
            keywords = await self._load_keywords(params['keywords_path'])
            logger.info(f"Job {job_id}: {len(keywords)} mots-clés chargés")
            
            # 2. Charger les pages selon la source (15%)
            await self.update_job_progress(
                job_id,
                current_step="Chargement des pages",
                progress=15.0
            )
            
            pages = await self._load_pages(params)
            logger.info(f"Job {job_id}: {len(pages)} pages chargées")
            
            # 3. Créer les embeddings (25-75% - étape la plus longue)
            await self.update_job_progress(
                job_id,
                current_step="Préparation des embeddings",
                progress=25.0
            )
            
            embedding_manager = EmbeddingManager()
            
            await self.update_job_progress(
                job_id,
                current_step="Génération des embeddings en cours...",
                progress=45.0
            )
            
            url_to_chunks = embedding_manager.process_pages(pages, show_progress=False)
            
            await self.update_job_progress(
                job_id,
                current_step="Embeddings créés",
                progress=75.0
            )
            
            # 4. Assignation avec scoring hybride OPTIMISÉ (85%)
            await self.update_job_progress(
                job_id,
                current_step="Assignation des mots-clés",
                progress=85.0
            )
            
            # Utiliser le scorer FINAL pour des performances maximales
            scorer = FinalOptimizedScorer(embedding_manager)
            top_suggestions = params.get('top_suggestions', 3)
            assignments, orphans = scorer.assign_keywords_vectorized(keywords, top_suggestions)
            
            # 5. Pas de vérification de cannibalisation (fonctionnalité supprimée)
            cannibals = []
            
            # 6. Calcul des statistiques (95%)
            await self.update_job_progress(
                job_id,
                current_step="Calcul des statistiques",
                progress=95.0
            )
            
            stats = {
                'total_keywords': len(keywords),
                'assigned_keywords': len(assignments),
                'orphan_keywords': len(orphans),
                'total_pages': len(pages),
                'processing_time_seconds': time.time() - start_time,
                'average_score': sum(a.score for a in assignments) / len(assignments) if assignments else 0,
                'cannibalization_alerts': len(cannibals)
            }
            
            # 7. Créer et sauvegarder le résultat
            result = JobResult(
                job_id=job_id,
                assignments=assignments,
                orphans=orphans,
                cannibals=cannibals,
                stats=stats,
                created_at=datetime.utcnow().isoformat(),
                completed_at=datetime.utcnow().isoformat()
            )
            
            await self.save_job_result(job_id, result)
            
            # 8. Marquer comme terminé
            await self.update_job_progress(
                job_id,
                status=JobStatus.COMPLETED.value,
                current_step="Traitement terminé",
                progress=100.0
            )
            
            logger.info(f"Job {job_id} terminé avec succès en {time.time() - start_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Erreur job {job_id}: {e}")
            logger.error(traceback.format_exc())
            
            await self.update_job_progress(
                job_id,
                status=JobStatus.FAILED.value,
                error_message=str(e),
                current_step="Erreur de traitement"
            )
    
    async def _load_keywords(self, keywords_path: str) -> List[Keyword]:
        """Charge les mots-clés depuis un fichier CSV"""
        try:
            # Supprimer le BOM si présent
            with open(keywords_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            with open(keywords_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Essayer différents séparateurs
            df = None
            used_sep = None
            
            for sep in [',', ';', '\t', '|']:
                try:
                    test_df = pd.read_csv(keywords_path, sep=sep, nrows=1)
                    if len(test_df.columns) > 1:
                        df = pd.read_csv(keywords_path, sep=sep, quoting=1, skipinitialspace=True)
                        used_sep = sep
                        break
                except:
                    continue
            
            if df is None:
                # Fallback avec séparateur par défaut
                try:
                    df = pd.read_csv(keywords_path, quoting=1, skipinitialspace=True)
                    used_sep = ','
                except:
                    df = pd.read_csv(keywords_path)
                    used_sep = ','
            
            logger.info(f"CSV mots-clés chargé avec séparateur '{used_sep}', colonnes: {list(df.columns)}")
            
            # Recherche flexible de la colonne keyword
            keyword_col = None
            volume_col = None
            
            # Noms possibles pour la colonne keyword
            keyword_possibilities = ['keyword', 'Keyword', 'mot-clé', 'mot_clé', 'query', 'terme']
            for col_name in keyword_possibilities:
                if col_name in df.columns:
                    keyword_col = col_name
                    break
            
            if keyword_col is None:
                available_cols = list(df.columns)
                raise ValueError(f"Colonne keyword non trouvée. Colonnes disponibles: {available_cols}. "
                               f"Noms acceptés: {keyword_possibilities}")
            
            # Recherche flexible de la colonne volume
            volume_possibilities = ['volume', 'Volume', 'Search Volume', 'search_volume', 'vol']
            for col_name in volume_possibilities:
                if col_name in df.columns:
                    volume_col = col_name
                    break
            
            logger.info(f"Colonnes détectées - keyword: '{keyword_col}', volume: '{volume_col or 'non trouvée'}'")
            
            keywords = []
            for _, row in df.iterrows():
                keyword = Keyword(
                    keyword=row[keyword_col],
                    volume=row.get(volume_col, None) if volume_col else None
                )
                keywords.append(keyword)
            
            logger.info(f"Chargé {len(keywords)} mots-clés depuis {keywords_path}")
            return keywords
            
        except Exception as e:
            logger.error(f"Erreur chargement keywords {keywords_path}: {e}")
            raise
    
    async def _load_pages(self, params: Dict[str, Any]) -> List:
        """Charge les pages selon le type de source"""
        try:
            source_type = SourceType(params['source_type'])
            
            if source_type == SourceType.CSV:
                return await PageLoader.load_from_csv(params['pages_path'])
            elif source_type == SourceType.SITEMAP:
                return await PageLoader.load_from_sitemap(params['sitemap_url'])
            elif source_type == SourceType.LIVE_CRAWL:
                return await PageLoader.load_from_live_crawl(
                    params['seed_url'],
                    depth=params.get('crawl_depth', 2),
                    max_pages=Config.MAX_PAGES
                )
            else:
                raise ValueError(f"Type de source non supporté: {source_type}")
                
        except Exception as e:
            logger.error(f"Erreur chargement pages: {e}")
            raise 
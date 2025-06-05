"""Service de monitoring et métriques avec Prometheus"""

import asyncio
import logging
import time
import psutil
from typing import Dict, Any, List
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import redis

from ..config import Config
from ..models import MetricsResponse

logger = logging.getLogger(__name__)


class MetricsCollector:
    """Collecteur de métriques pour monitoring Prometheus"""
    
    def __init__(self):
        # Métriques Prometheus
        self.keywords_processed = Counter(
            'keyword_matcher_keywords_processed_total',
            'Nombre total de mots-clés traités'
        )
        
        self.processing_time = Histogram(
            'keyword_matcher_processing_duration_seconds',
            'Temps de traitement des jobs',
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600]
        )
        
        self.faiss_queries = Counter(
            'keyword_matcher_faiss_queries_total',
            'Nombre total de requêtes FAISS'
        )
        
        self.memory_usage = Gauge(
            'keyword_matcher_memory_usage_bytes',
            'Utilisation mémoire en bytes'
        )
        
        self.active_jobs_gauge = Gauge(
            'keyword_matcher_active_jobs',
            'Nombre de jobs actifs'
        )
        
        self.embeddings_total = Gauge(
            'keyword_matcher_embeddings_total',
            'Nombre total d\'embeddings dans l\'index'
        )
        
        self.assignment_scores = Histogram(
            'keyword_matcher_assignment_scores',
            'Distribution des scores d\'assignation',
            buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        )
        
        # Redis client pour récupérer des métriques
        self.redis_client = redis.from_url(Config.REDIS_URL)
        
        # État interne
        self.start_time = time.time()
        self.metrics_server_started = False
        self.update_task = None
        
    async def start(self):
        """Démarre le collecteur de métriques"""
        try:
            # Démarrer le serveur Prometheus seulement si activé et pas déjà démarré
            if Config.ENABLE_PROMETHEUS and not self.metrics_server_started:
                try:
                    start_http_server(Config.PROMETHEUS_PORT)
                    self.metrics_server_started = True
                    logger.info(f"Serveur métriques Prometheus démarré sur le port {Config.PROMETHEUS_PORT}")
                except OSError as e:
                    if e.errno == 98:  # Address already in use
                        logger.warning(f"Port {Config.PROMETHEUS_PORT} déjà utilisé, métriques Prometheus désactivées")
                        self.metrics_server_started = False
                    else:
                        raise
            elif not Config.ENABLE_PROMETHEUS:
                logger.info("Métriques Prometheus désactivées par configuration")
                self.metrics_server_started = False
            
            # Démarrer la tâche de mise à jour périodique
            if not self.update_task or self.update_task.done():
                self.update_task = asyncio.create_task(self._update_metrics_loop())
                logger.info("Collecteur de métriques démarré")
            
        except Exception as e:
            logger.error(f"Erreur démarrage collecteur métriques: {e}")
            # Ne pas lever l'exception pour ne pas empêcher le démarrage de l'app
            self.metrics_server_started = False
    
    async def stop(self):
        """Arrête le collecteur de métriques"""
        if self.update_task:
            self.update_task.cancel()
            try:
                await self.update_task
            except asyncio.CancelledError:
                pass
        
        logger.info("Collecteur de métriques arrêté")
    
    async def _update_metrics_loop(self):
        """Boucle de mise à jour des métriques"""
        while True:
            try:
                await self._update_system_metrics()
                await self._update_job_metrics()
                await asyncio.sleep(30)  # Mise à jour toutes les 30 secondes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Erreur mise à jour métriques: {e}")
                await asyncio.sleep(60)  # Attendre plus longtemps en cas d'erreur
    
    async def _update_system_metrics(self):
        """Met à jour les métriques système"""
        try:
            # Utilisation mémoire
            process = psutil.Process()
            memory_info = process.memory_info()
            self.memory_usage.set(memory_info.rss)
            
        except Exception as e:
            logger.error(f"Erreur mise à jour métriques système: {e}")
    
    async def _update_job_metrics(self):
        """Met à jour les métriques des jobs"""
        try:
            # Compter les jobs actifs
            active_jobs = 0
            job_keys = self.redis_client.keys("job:*")
            
            for key in job_keys:
                job_data = self.redis_client.get(key)
                if job_data:
                    import json
                    job_info = json.loads(job_data)
                    if job_info.get('status') == 'processing':
                        active_jobs += 1
            
            self.active_jobs_gauge.set(active_jobs)
            
        except Exception as e:
            logger.error(f"Erreur mise à jour métriques jobs: {e}")
    
    def record_keywords_processed(self, count: int):
        """Enregistre le nombre de mots-clés traités"""
        self.keywords_processed.inc(count)
    
    def record_processing_time(self, duration: float):
        """Enregistre la durée de traitement d'un job"""
        self.processing_time.observe(duration)
    
    def record_faiss_query(self):
        """Enregistre une requête FAISS"""
        self.faiss_queries.inc()
    
    def record_assignment_score(self, score: float):
        """Enregistre un score d'assignation"""
        self.assignment_scores.observe(score)
    
    def set_embeddings_total(self, count: int):
        """Met à jour le nombre total d'embeddings"""
        self.embeddings_total.set(count)
    
    async def get_current_metrics(self) -> MetricsResponse:
        """Récupère les métriques actuelles"""
        try:
            # Calculer les taux par seconde
            uptime = time.time() - self.start_time
            
            keywords_per_sec = self.keywords_processed._value._value / max(uptime, 1)
            faiss_qps = self.faiss_queries._value._value / max(uptime, 1)
            
            # Mémoire actuelle
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            # Jobs actifs
            active_jobs = int(self.active_jobs_gauge._value._value)
            
            # Total embeddings
            total_embeddings = int(self.embeddings_total._value._value)
            
            return MetricsResponse(
                keywords_processed_per_sec=keywords_per_sec,
                faiss_queries_per_sec=faiss_qps,
                memory_usage_mb=memory_mb,
                active_jobs=active_jobs,
                total_embeddings=total_embeddings
            )
            
        except Exception as e:
            logger.error(f"Erreur récupération métriques: {e}")
            return MetricsResponse(
                keywords_processed_per_sec=0.0,
                faiss_queries_per_sec=0.0,
                memory_usage_mb=0.0,
                active_jobs=0,
                total_embeddings=0
            )
    
    def get_health_status(self) -> Dict[str, Any]:
        """Retourne l'état de santé du service"""
        try:
            # Vérifier la connectivité Redis
            redis_ok = self.redis_client.ping()
            
            # Vérifier l'utilisation mémoire
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            memory_ok = memory_mb < 8192  # Limite à 8GB
            
            # Vérifier l'uptime
            uptime = time.time() - self.start_time
            
            # Statut global
            healthy = redis_ok and memory_ok
            
            return {
                'healthy': healthy,
                'uptime_seconds': uptime,
                'redis_connected': redis_ok,
                'memory_usage_mb': memory_mb,
                'memory_ok': memory_ok,
                'active_jobs': int(self.active_jobs_gauge._value._value),
                'total_keywords_processed': int(self.keywords_processed._value._value),
                'total_faiss_queries': int(self.faiss_queries._value._value),
                'prometheus_server_running': self.metrics_server_started
            }
            
        except Exception as e:
            logger.error(f"Erreur vérification santé: {e}")
            return {
                'healthy': False,
                'error': str(e),
                'uptime_seconds': time.time() - self.start_time
            }


class PerformanceMonitor:
    """Moniteur de performance pour les opérations critiques"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.operation_timers = {}
    
    def start_operation(self, operation_name: str) -> str:
        """Démarre le chronométrage d'une opération"""
        timer_id = f"{operation_name}_{int(time.time() * 1000)}"
        self.operation_timers[timer_id] = {
            'name': operation_name,
            'start_time': time.time()
        }
        return timer_id
    
    def end_operation(self, timer_id: str) -> float:
        """Termine le chronométrage et enregistre la métrique"""
        if timer_id not in self.operation_timers:
            logger.warning(f"Timer {timer_id} non trouvé")
            return 0.0
        
        timer_info = self.operation_timers[timer_id]
        duration = time.time() - timer_info['start_time']
        
        # Enregistrer selon le type d'opération
        if timer_info['name'] == 'job_processing':
            self.metrics_collector.record_processing_time(duration)
        
        del self.operation_timers[timer_id]
        
        logger.debug(f"Opération {timer_info['name']} terminée en {duration:.2f}s")
        return duration
    
    def get_active_operations(self) -> Dict[str, Dict[str, Any]]:
        """Retourne les opérations en cours"""
        active_ops = {}
        current_time = time.time()
        
        for timer_id, timer_info in self.operation_timers.items():
            active_ops[timer_id] = {
                'name': timer_info['name'],
                'duration': current_time - timer_info['start_time'],
                'start_time': timer_info['start_time']
            }
        
        return active_ops


class AlertManager:
    """Gestionnaire d'alertes pour les seuils critiques"""
    
    def __init__(self, metrics_collector: MetricsCollector):
        self.metrics_collector = metrics_collector
        self.alert_thresholds = {
            'memory_mb': 7168,  # 7GB
            'job_duration_minutes': 60,  # 1 heure
            'error_rate_percent': 10,  # 10%
            'queue_size': 100  # 100 jobs en attente
        }
        self.active_alerts = set()
    
    async def check_alerts(self) -> List[Dict[str, Any]]:
        """Vérifie les seuils et retourne les alertes actives"""
        alerts = []
        
        try:
            # Vérification mémoire
            process = psutil.Process()
            memory_mb = process.memory_info().rss / 1024 / 1024
            
            if memory_mb > self.alert_thresholds['memory_mb']:
                alert = {
                    'type': 'memory_high',
                    'severity': 'warning',
                    'message': f"Utilisation mémoire élevée: {memory_mb:.1f}MB",
                    'threshold': self.alert_thresholds['memory_mb'],
                    'current_value': memory_mb
                }
                alerts.append(alert)
                
                if 'memory_high' not in self.active_alerts:
                    self.active_alerts.add('memory_high')
                    logger.warning(alert['message'])
            else:
                self.active_alerts.discard('memory_high')
            
            # Vérification jobs bloqués
            # TODO: Implémenter la vérification des jobs longs
            
            return alerts
            
        except Exception as e:
            logger.error(f"Erreur vérification alertes: {e}")
            return []
    
    def get_alert_history(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Récupère l'historique des alertes"""
        # TODO: Implémenter la persistance des alertes
        return [] 
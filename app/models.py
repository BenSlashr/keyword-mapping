"""Modèles de données pour l'API"""

from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum


class JobStatus(str, Enum):
    """Statuts possibles d'un job"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SourceType(str, Enum):
    """Types de sources pour les pages"""
    CSV = "csv"
    SITEMAP = "sitemap"
    LIVE_CRAWL = "live_crawl"


class Keyword(BaseModel):
    """Modèle pour un mot-clé"""
    keyword: str = Field(..., description="Terme de recherche")
    volume: Optional[int] = Field(None, description="Volume de recherche mensuel")
    
    @validator('keyword')
    def validate_keyword(cls, v):
        if not v or not v.strip():
            raise ValueError('Le mot-clé ne peut pas être vide')
        return v.strip().lower()


class Page(BaseModel):
    """Modèle pour une page web"""
    url: str = Field(..., description="URL de la page")
    title: Optional[str] = Field(None, description="Titre de la page")
    meta_description: Optional[str] = Field(None, description="Meta description")
    content: Optional[str] = Field(None, description="Contenu textuel de la page")
    h1: Optional[str] = Field(None, description="Balise H1")
    h2: Optional[List[str]] = Field(default_factory=list, description="Balises H2")
    h3: Optional[List[str]] = Field(default_factory=list, description="Balises H3")


class Assignment(BaseModel):
    """Modèle pour une assignation mot-clé -> page"""
    keyword: str = Field(..., description="Mot-clé assigné")
    url: str = Field(..., description="URL assignée")
    score: float = Field(..., description="Score de confiance")
    chunk_position: Optional[int] = Field(None, description="Position du chunk dans la page")
    alternative_urls: List[str] = Field(default_factory=list, description="URLs alternatives")
    is_manual: bool = Field(False, description="Assignation manuelle")


class CannibalAlert(BaseModel):
    """Modèle pour alertes de cannibalisation"""
    keyword: str = Field(..., description="Mot-clé concerné")
    assigned_url: str = Field(..., description="URL assignée par l'algorithme")
    gsc_top_url: str = Field(..., description="URL top CTR dans Search Console")
    gsc_clicks: int = Field(..., description="Nombre de clics GSC")
    confidence_loss: float = Field(..., description="Perte de confiance estimée")


class JobParams(BaseModel):
    """Paramètres pour un job de matching"""
    source_type: SourceType = Field(..., description="Type de source des pages")
    min_score_threshold: float = Field(0.50, description="Seuil minimal de score")
    volume_weight: float = Field(1.0, description="Pondération du volume de recherche")
    enable_search_console: bool = Field(False, description="Activer Search Console")
    top_suggestions: int = Field(3, description="Nombre de suggestions alternatives")
    crawl_depth: Optional[int] = Field(2, description="Profondeur de crawl (live crawl)")
    seed_url: Optional[str] = Field(None, description="URL de départ (live crawl)")


class JobCreateRequest(BaseModel):
    """Requête de création de job"""
    params: JobParams = Field(..., description="Paramètres du job")


class JobProgress(BaseModel):
    """Progression d'un job"""
    job_id: str = Field(..., description="ID du job")
    status: JobStatus = Field(..., description="Statut du job")
    progress: float = Field(0.0, description="Progression en %")
    eta_seconds: Optional[int] = Field(None, description="Temps restant estimé")
    memory_mb: float = Field(0.0, description="Mémoire utilisée en MB")
    current_step: str = Field("", description="Étape en cours")
    error_message: Optional[str] = Field(None, description="Message d'erreur si échec")


class JobResult(BaseModel):
    """Résultat d'un job"""
    job_id: str = Field(..., description="ID du job")
    assignments: List[Assignment] = Field(..., description="Assignations réalisées")
    orphans: List[Keyword] = Field(..., description="Mots-clés orphelins")
    cannibals: List[CannibalAlert] = Field(..., description="Alertes de cannibalisation")
    stats: Dict[str, Any] = Field(..., description="Statistiques générales")
    created_at: str = Field(..., description="Date de création")
    completed_at: Optional[str] = Field(None, description="Date de completion")


class SearchConsoleAuth(BaseModel):
    """Modèle pour l'authentification Search Console"""
    property_url: str = Field(..., description="URL de la propriété Search Console")
    
    @validator('property_url')
    def validate_property_url(cls, v):
        if not v.startswith(('http://', 'https://', 'sc-domain:')):
            raise ValueError('URL de propriété invalide')
        return v


class MetricsResponse(BaseModel):
    """Réponse pour les métriques Prometheus"""
    keywords_processed_per_sec: float
    faiss_queries_per_sec: float
    memory_usage_mb: float
    active_jobs: int
    total_embeddings: int 
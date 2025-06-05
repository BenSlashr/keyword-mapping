"""Application FastAPI principale pour Keyword-URL Matcher v2"""

import os
import logging
import asyncio
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, BackgroundTasks, Form, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import uuid
from datetime import datetime

from .config import Config
from .models import (
    JobCreateRequest, JobProgress, JobResult, JobStatus, SourceType,
    Keyword, MetricsResponse, SearchConsoleAuth
)
from .core.embeddings import EmbeddingManager
from .core.scoring import HybridScorer
from .core.parsers import PageLoader
from .services.job_manager import JobManager
from .services.search_console import SearchConsoleService
from .services.export_service import ExportService
from .services.monitoring import MetricsCollector

# Configuration du logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Variables globales
job_manager: Optional[JobManager] = None
metrics_collector: Optional[MetricsCollector] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gestionnaire de cycle de vie de l'application"""
    global job_manager, metrics_collector
    
    # Démarrage
    logger.info("Démarrage de l'application Keyword-URL Matcher v2")
    
    # Créer les dossiers nécessaires
    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    os.makedirs(Config.RESULTS_DIR, exist_ok=True)
    os.makedirs(Config.MODELS_DIR, exist_ok=True)
    
    # Initialiser les services
    job_manager = JobManager()
    metrics_collector = MetricsCollector()
    
    # Démarrer le collecteur de métriques
    await metrics_collector.start()
    
    yield
    
    # Arrêt
    logger.info("Arrêt de l'application")
    if metrics_collector:
        await metrics_collector.stop()


# Création de l'application FastAPI
app = FastAPI(
    title="Keyword-URL Matcher v2 Premium",
    description="Outil d'assignation automatique de mots-clés vers des pages web",
    version="2.0.0",
    lifespan=lifespan,
    root_path=Config.ROOT_PATH
)

# Middleware CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates et fichiers statiques
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# Dépendances
def get_job_manager() -> JobManager:
    """Dépendance pour récupérer le gestionnaire de jobs"""
    if job_manager is None:
        raise HTTPException(status_code=500, detail="Service non initialisé")
    return job_manager


def get_metrics_collector() -> MetricsCollector:
    """Dépendance pour récupérer le collecteur de métriques"""
    if metrics_collector is None:
        raise HTTPException(status_code=500, detail="Service non initialisé")
    return metrics_collector


# Routes principales

@app.get("/", response_class=HTMLResponse)
async def root():
    """Page d'accueil de l'application"""
    return templates.TemplateResponse("index.html", {"request": {}})


@app.post("/jobs/match")
async def create_matching_job(
    background_tasks: BackgroundTasks,
    keywords_file: UploadFile = File(...),
    pages_file: Optional[UploadFile] = File(None),
    sitemap_url: Optional[str] = Form(None),
    seed_url: Optional[str] = Form(None),
    source_type: SourceType = Form(...),
    min_score_threshold: float = Form(0.50),
    volume_weight: float = Form(1.0),
    enable_search_console: bool = Form(False),
    top_suggestions: int = Form(3),
    crawl_depth: Optional[int] = Form(2),
    job_manager: JobManager = Depends(get_job_manager)
) -> dict:
    """Crée un nouveau job de matching keyword-URL"""
    
    try:
        # Générer un ID unique pour le job
        job_id = str(uuid.uuid4())
        
        # Validation des paramètres selon le type de source
        if source_type == SourceType.CSV and not pages_file:
            raise HTTPException(status_code=400, detail="Fichier pages requis pour source CSV")
        elif source_type == SourceType.SITEMAP and not sitemap_url:
            raise HTTPException(status_code=400, detail="URL sitemap requise pour source sitemap")
        elif source_type == SourceType.LIVE_CRAWL and not seed_url:
            raise HTTPException(status_code=400, detail="URL de départ requise pour live crawl")
        
        # Vérifier le format du fichier keywords
        if not keywords_file.filename.endswith('.csv'):
            raise HTTPException(status_code=400, detail="Le fichier keywords doit être au format CSV")
        
        # Sauvegarder les fichiers uploadés
        keywords_path = os.path.join(Config.UPLOAD_DIR, f"{job_id}_keywords.csv")
        with open(keywords_path, "wb") as f:
            content = await keywords_file.read()
            f.write(content)
        
        pages_path = None
        if pages_file and source_type == SourceType.CSV:
            pages_path = os.path.join(Config.UPLOAD_DIR, f"{job_id}_pages.csv")
            with open(pages_path, "wb") as f:
                content = await pages_file.read()
                f.write(content)
        
        # Créer les paramètres du job
        job_params = {
            'source_type': source_type,
            'min_score_threshold': min_score_threshold,
            'volume_weight': volume_weight,
            'enable_search_console': enable_search_console,
            'top_suggestions': top_suggestions,
            'crawl_depth': crawl_depth,
            'seed_url': seed_url,
            'sitemap_url': sitemap_url,
            'keywords_path': keywords_path,
            'pages_path': pages_path
        }
        
        # Lancer le job en arrière-plan
        background_tasks.add_task(job_manager.run_matching_job, job_id, job_params)
        
        # Enregistrer le job
        await job_manager.create_job(job_id, job_params)
        
        logger.info(f"Job de matching créé: {job_id}")
        
        return {"job_id": job_id, "status": "created"}
        
    except Exception as e:
        logger.error(f"Erreur création job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}")
async def get_job_status(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
) -> JobProgress:
    """Récupère le statut d'un job"""
    
    try:
        progress = await job_manager.get_job_progress(job_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Job non trouvé")
        
        return progress
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération statut job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/jobs/{job_id}/result")
async def get_job_result(
    job_id: str,
    format: str = "json",
    job_manager: JobManager = Depends(get_job_manager)
):
    """Récupère le résultat d'un job"""
    
    try:
        # Vérifier que le job est terminé
        progress = await job_manager.get_job_progress(job_id)
        if not progress:
            raise HTTPException(status_code=404, detail="Job non trouvé")
        
        if progress.status != JobStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="Job non terminé")
        
        # Récupérer le résultat
        result = await job_manager.get_job_result(job_id)
        if not result:
            raise HTTPException(status_code=404, detail="Résultat non trouvé")
        
        # Retourner selon le format demandé
        if format.lower() == "json":
            return result
        elif format.lower() == "xlsx":
            # Générer le fichier Excel
            export_service = ExportService()
            xlsx_path = await export_service.export_to_xlsx(result, job_id)
            return FileResponse(
                xlsx_path,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=f"keyword_matching_{job_id}.xlsx"
            )
        elif format.lower() == "csv":
            # Générer le fichier CSV
            export_service = ExportService()
            csv_path = await export_service.export_to_csv(result, job_id)
            return FileResponse(
                csv_path,
                media_type="text/csv",
                filename=f"keyword_matching_{job_id}.csv"
            )
        else:
            raise HTTPException(status_code=400, detail="Format non supporté")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur récupération résultat job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/jobs/{job_id}")
async def cancel_job(
    job_id: str,
    job_manager: JobManager = Depends(get_job_manager)
) -> dict:
    """Annule un job en cours"""
    
    try:
        success = await job_manager.cancel_job(job_id)
        if not success:
            raise HTTPException(status_code=404, detail="Job non trouvé ou déjà terminé")
        
        return {"status": "cancelled"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur annulation job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/search-console/oauth")
async def start_search_console_oauth() -> dict:
    """Démarre le processus OAuth pour Search Console"""
    
    try:
        gsc_service = SearchConsoleService()
        auth_url = await gsc_service.get_authorization_url()
        
        return {"auth_url": auth_url}
        
    except Exception as e:
        logger.error(f"Erreur OAuth Search Console: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/auth/callback")
async def oauth_callback(code: str, state: Optional[str] = None) -> dict:
    """Callback OAuth pour Search Console"""
    
    try:
        gsc_service = SearchConsoleService()
        success = await gsc_service.handle_oauth_callback(code, state)
        
        if success:
            return {"status": "success", "message": "Authentification réussie"}
        else:
            raise HTTPException(status_code=400, detail="Échec de l'authentification")
            
    except Exception as e:
        logger.error(f"Erreur callback OAuth: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search-console/properties")
async def get_search_console_properties() -> dict:
    """Récupère la liste des propriétés Search Console"""
    
    try:
        gsc_service = SearchConsoleService()
        properties = await gsc_service.get_properties()
        
        return {"properties": properties}
        
    except Exception as e:
        logger.error(f"Erreur récupération propriétés Search Console: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    metrics_collector: MetricsCollector = Depends(get_metrics_collector)
) -> MetricsResponse:
    """Récupère les métriques de performance"""
    
    try:
        metrics = await metrics_collector.get_current_metrics()
        return metrics
        
    except Exception as e:
        logger.error(f"Erreur récupération métriques: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/health")
async def health_check() -> dict:
    """Vérification de l'état de santé de l'application"""
    
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "2.0.0"
    }


@app.get("/jobs")
async def list_jobs(
    status: Optional[JobStatus] = None,
    limit: int = 50,
    job_manager: JobManager = Depends(get_job_manager)
) -> dict:
    """Liste les jobs avec filtrage optionnel"""
    
    try:
        jobs = await job_manager.list_jobs(status=status, limit=limit)
        return {"jobs": jobs}
        
    except Exception as e:
        logger.error(f"Erreur listage jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Routes WebSocket pour le suivi en temps réel
@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str):
    """WebSocket pour suivre la progression d'un job en temps réel"""
    
    await websocket.accept()
    
    try:
        # Récupérer l'instance du job manager
        manager = get_job_manager()
        
        while True:
            # Récupérer la progression du job
            progress = await manager.get_job_progress(job_id)
            
            if progress:
                await websocket.send_json(progress.dict())
                
                # Si le job est terminé, fermer la connexion
                if progress.status in [JobStatus.COMPLETED, JobStatus.FAILED]:
                    break
            else:
                await websocket.send_json({"error": "Job non trouvé"})
                break
            
            # Attendre avant la prochaine mise à jour
            await asyncio.sleep(2)
            
    except Exception as e:
        logger.error(f"Erreur WebSocket job {job_id}: {e}")
    finally:
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=Config.DEBUG,
        log_level="info"
    ) 
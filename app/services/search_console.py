"""Service Google Search Console pour l'authentification et l'analyse de cannibalisation"""

import logging
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import json

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

from ..config import Config
from ..models import Assignment, CannibalAlert

logger = logging.getLogger(__name__)


class SearchConsoleService:
    """Service pour interagir avec Google Search Console API"""
    
    def __init__(self):
        self.credentials = None
        self.service = None
        self.flow = None
        
    def _get_oauth_flow(self) -> Flow:
        """Crée un flow OAuth pour Google Search Console"""
        if not Config.GOOGLE_CLIENT_ID or not Config.GOOGLE_CLIENT_SECRET:
            raise ValueError("Identifiants Google OAuth non configurés")
        
        client_config = {
            "web": {
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [Config.GOOGLE_REDIRECT_URI]
            }
        }
        
        scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        
        flow = Flow.from_client_config(
            client_config,
            scopes=scopes,
            redirect_uri=Config.GOOGLE_REDIRECT_URI
        )
        
        return flow
    
    async def get_authorization_url(self) -> str:
        """Génère l'URL d'autorisation OAuth"""
        try:
            self.flow = self._get_oauth_flow()
            auth_url, _ = self.flow.authorization_url(
                access_type='offline',
                include_granted_scopes='true',
                prompt='consent'  # Force l'affichage de l'écran de consentement
            )
            
            logger.info("URL d'autorisation générée")
            return auth_url
            
        except Exception as e:
            logger.error(f"Erreur génération URL OAuth: {e}")
            raise
    
    async def handle_oauth_callback(self, code: str, state: Optional[str] = None) -> bool:
        """Traite le callback OAuth et récupère les tokens"""
        try:
            if not self.flow:
                self.flow = self._get_oauth_flow()
            
            # Échanger le code contre des tokens
            self.flow.fetch_token(code=code)
            self.credentials = self.flow.credentials
            
            # Créer le service API
            self.service = build('webmasters', 'v3', credentials=self.credentials)
            
            # Tester la connexion
            sites = self.service.sites().list().execute()
            logger.info(f"Authentification réussie, {len(sites.get('siteEntry', []))} propriétés trouvées")
            
            return True
            
        except Exception as e:
            logger.error(f"Erreur callback OAuth: {e}")
            return False
    
    async def get_properties(self) -> List[Dict[str, str]]:
        """Récupère la liste des propriétés Search Console"""
        try:
            if not self.service:
                raise ValueError("Service non authentifié")
            
            response = self.service.sites().list().execute()
            sites = response.get('siteEntry', [])
            
            properties = []
            for site in sites:
                properties.append({
                    'url': site['siteUrl'],
                    'permission_level': site['permissionLevel']
                })
            
            return properties
            
        except Exception as e:
            logger.error(f"Erreur récupération propriétés: {e}")
            return []
    
    async def get_search_analytics_data(self, site_url: str, 
                                      start_date: Optional[datetime] = None,
                                      end_date: Optional[datetime] = None) -> List[Dict]:
        """Récupère les données Search Analytics"""
        try:
            if not self.service:
                raise ValueError("Service non authentifié")
            
            # Dates par défaut : 90 derniers jours
            if not end_date:
                end_date = datetime.now()
            if not start_date:
                start_date = end_date - timedelta(days=90)
            
            request_body = {
                'startDate': start_date.strftime('%Y-%m-%d'),
                'endDate': end_date.strftime('%Y-%m-%d'),
                'dimensions': ['query', 'page'],
                'rowLimit': 25000  # Maximum autorisé
            }
            
            response = self.service.searchanalytics().query(
                siteUrl=site_url,
                body=request_body
            ).execute()
            
            rows = response.get('rows', [])
            logger.info(f"Récupéré {len(rows)} lignes de données Search Console")
            
            # Transformer les données
            data = []
            for row in rows:
                keys = row.get('keys', [])
                if len(keys) >= 2:
                    data.append({
                        'query': keys[0],
                        'page': keys[1],
                        'clicks': row.get('clicks', 0),
                        'impressions': row.get('impressions', 0),
                        'ctr': row.get('ctr', 0),
                        'position': row.get('position', 0)
                    })
            
            return data
            
        except Exception as e:
            logger.error(f"Erreur récupération données Search Console: {e}")
            return []
    
    async def detect_cannibalization(self, assignments: List[Assignment], 
                                   site_url: Optional[str] = None) -> List[CannibalAlert]:
        """Détecte la cannibalisation en comparant les assignations avec Search Console"""
        try:
            if not self.service:
                logger.warning("Service Search Console non authentifié")
                return []
            
            # Si aucune URL de site fournie, prendre la première propriété
            if not site_url:
                properties = await self.get_properties()
                if not properties:
                    logger.warning("Aucune propriété Search Console trouvée")
                    return []
                site_url = properties[0]['url']
            
            # Récupérer les données Search Console
            gsc_data = await self.get_search_analytics_data(site_url)
            
            if not gsc_data:
                logger.warning("Aucune donnée Search Console récupérée")
                return []
            
            # Créer un mapping query -> page avec le plus de clics
            query_to_top_page = {}
            for row in gsc_data:
                query = row['query'].lower()
                page = row['page']
                clicks = row['clicks']
                
                if query not in query_to_top_page or clicks > query_to_top_page[query]['clicks']:
                    query_to_top_page[query] = {
                        'page': page,
                        'clicks': clicks,
                        'impressions': row['impressions'],
                        'ctr': row['ctr'],
                        'position': row['position']
                    }
            
            # Détecter les cannibalisations
            cannibals = []
            for assignment in assignments:
                keyword_lower = assignment.keyword.lower()
                
                if keyword_lower in query_to_top_page:
                    gsc_top_page = query_to_top_page[keyword_lower]['page']
                    gsc_clicks = query_to_top_page[keyword_lower]['clicks']
                    
                    # Normaliser les URLs pour la comparaison
                    assigned_url_normalized = self._normalize_url(assignment.url)
                    gsc_url_normalized = self._normalize_url(gsc_top_page)
                    
                    # Si l'URL assignée est différente de l'URL top dans GSC
                    if assigned_url_normalized != gsc_url_normalized:
                        
                        # Calculer la perte de confiance estimée
                        confidence_loss = self._calculate_confidence_loss(
                            assignment.score,
                            gsc_clicks,
                            query_to_top_page[keyword_lower]['position']
                        )
                        
                        cannibal = CannibalAlert(
                            keyword=assignment.keyword,
                            assigned_url=assignment.url,
                            gsc_top_url=gsc_top_page,
                            gsc_clicks=gsc_clicks,
                            confidence_loss=confidence_loss
                        )
                        
                        cannibals.append(cannibal)
                        
                        logger.debug(f"Cannibalisation détectée pour '{assignment.keyword}': "
                                   f"assigné={assignment.url}, GSC={gsc_top_page}")
            
            logger.info(f"Détection terminée: {len(cannibals)} cannibalisations trouvées")
            return cannibals
            
        except Exception as e:
            logger.error(f"Erreur détection cannibalisation: {e}")
            return []
    
    def _normalize_url(self, url: str) -> str:
        """Normalise une URL pour comparaison"""
        # Supprimer le protocole et les paramètres
        url = url.lower()
        url = url.replace('https://', '').replace('http://', '')
        url = url.split('?')[0]  # Supprimer les paramètres
        url = url.rstrip('/')    # Supprimer le slash final
        
        return url
    
    def _calculate_confidence_loss(self, assignment_score: float, 
                                 gsc_clicks: int, gsc_position: float) -> float:
        """Calcule la perte de confiance estimée due à la cannibalisation"""
        # Facteurs de pondération
        click_weight = min(gsc_clicks / 100, 1.0)  # Normaliser à [0,1]
        position_penalty = max(0, (gsc_position - 1) / 10)  # Pénalité de position
        score_factor = 1.0 - assignment_score  # Plus le score est bas, plus la perte est élevée
        
        # Calcul de la perte (entre 0 et 1)
        confidence_loss = (click_weight * 0.4 + 
                          position_penalty * 0.3 + 
                          score_factor * 0.3)
        
        return min(confidence_loss, 1.0)
    
    async def refresh_credentials(self) -> bool:
        """Rafraîchit les credentials OAuth si nécessaire"""
        try:
            if self.credentials and self.credentials.expired and self.credentials.refresh_token:
                self.credentials.refresh(Request())
                logger.info("Credentials rafraîchis")
                return True
            return False
        except Exception as e:
            logger.error(f"Erreur rafraîchissement credentials: {e}")
            return False 
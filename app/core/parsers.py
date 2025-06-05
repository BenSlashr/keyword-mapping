"""Module de parsing et extraction de contenu des pages web"""

import aiohttp
import asyncio
import pandas as pd
import logging
import xml.etree.ElementTree as ET
from typing import List, Dict, Optional, AsyncGenerator
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from readability import Document
import re
from unidecode import unidecode

from ..models import Page, SourceType
from ..config import Config

logger = logging.getLogger(__name__)


class ContentExtractor:
    """Extracteur de contenu optimisé pour le SEO"""
    
    def __init__(self):
        self.session = None
        
    async def __aenter__(self):
        """Context manager pour la session HTTP"""
        connector = aiohttp.TCPConnector(limit=20, limit_per_host=5)
        timeout = aiohttp.ClientTimeout(total=30, connect=10)
        
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (compatible; KeywordURLMatcher/2.0; SEO Tool)'
            }
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Fermeture de la session HTTP"""
        if self.session:
            await self.session.close()
    
    def clean_text(self, text: str) -> str:
        """Nettoie et normalise le texte"""
        if not text:
            return ""
            
        # Suppression des caractères de contrôle et normalisation Unicode
        text = unidecode(text)
        
        # Suppression des espaces multiples et normalisation
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        return text
    
    def extract_content_from_html(self, html: str, url: str) -> Page:
        """Extrait le contenu structuré d'une page HTML"""
        try:
            # Utiliser readability pour extraire le contenu principal
            doc = Document(html)
            main_content = doc.content()
            
            # Parser avec BeautifulSoup pour extraction structurée
            soup = BeautifulSoup(html, 'lxml')
            main_soup = BeautifulSoup(main_content, 'lxml')
            
            # Extraction du titre
            title = None
            title_tag = soup.find('title')
            if title_tag:
                title = self.clean_text(title_tag.get_text())
            
            # Extraction de la meta description
            meta_desc = None
            meta_tag = soup.find('meta', attrs={'name': 'description'})
            if meta_tag:
                meta_desc = self.clean_text(meta_tag.get('content', ''))
            
            # Extraction des H1
            h1 = None
            h1_tag = soup.find('h1')
            if h1_tag:
                h1 = self.clean_text(h1_tag.get_text())
            
            # Extraction des H2
            h2_tags = soup.find_all('h2')
            h2_list = [self.clean_text(tag.get_text()) for tag in h2_tags if tag.get_text().strip()]
            
            # Extraction des H3
            h3_tags = soup.find_all('h3')
            h3_list = [self.clean_text(tag.get_text()) for tag in h3_tags if tag.get_text().strip()]
            
            # Extraction du contenu principal
            content = self.clean_text(main_soup.get_text())
            
            return Page(
                url=url,
                title=title,
                meta_description=meta_desc,
                content=content,
                h1=h1,
                h2=h2_list,
                h3=h3_list
            )
            
        except Exception as e:
            logger.error(f"Erreur extraction contenu pour {url}: {e}")
            return Page(url=url, content="")
    
    async def fetch_page(self, url: str, semaphore: asyncio.Semaphore) -> Optional[Page]:
        """Récupère et parse une page web"""
        async with semaphore:
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return self.extract_content_from_html(html, url)
                    else:
                        logger.warning(f"Status {response.status} pour {url}")
                        return None
                        
            except Exception as e:
                logger.error(f"Erreur récupération {url}: {e}")
                return None
    
    async def fetch_pages_batch(self, urls: List[str], max_concurrent: int = 10) -> List[Page]:
        """Récupère un batch de pages en parallèle"""
        semaphore = asyncio.Semaphore(max_concurrent)
        tasks = [self.fetch_page(url, semaphore) for url in urls]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        pages = []
        for result in results:
            if isinstance(result, Page):
                pages.append(result)
            elif isinstance(result, Exception):
                logger.error(f"Exception dans batch: {result}")
                
        return pages


class SitemapParser:
    """Parser de sitemaps XML"""
    
    def __init__(self):
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def parse_sitemap_xml(self, xml_content: str, base_url: str) -> List[str]:
        """Parse un sitemap XML et extrait les URLs"""
        try:
            root = ET.fromstring(xml_content)
            urls = []
            
            # Namespace pour les sitemaps
            namespaces = {
                'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'
            }
            
            # Chercher les URLs dans le sitemap
            for url_elem in root.findall('.//sm:url', namespaces):
                loc_elem = url_elem.find('sm:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    url = loc_elem.text.strip()
                    # Résoudre les URLs relatives
                    full_url = urljoin(base_url, url)
                    urls.append(full_url)
            
            # Si c'est un index de sitemaps, traiter récursivement
            for sitemap_elem in root.findall('.//sm:sitemap', namespaces):
                loc_elem = sitemap_elem.find('sm:loc', namespaces)
                if loc_elem is not None and loc_elem.text:
                    sitemap_url = loc_elem.text.strip()
                    full_sitemap_url = urljoin(base_url, sitemap_url)
                    # TODO: Implémenter la récursion pour les sous-sitemaps
                    logger.info(f"Sous-sitemap trouvé: {full_sitemap_url}")
            
            return urls
            
        except ET.ParseError as e:
            logger.error(f"Erreur parsing XML sitemap: {e}")
            return []
        except Exception as e:
            logger.error(f"Erreur générale parsing sitemap: {e}")
            return []
    
    async def fetch_sitemap_urls(self, sitemap_url: str) -> List[str]:
        """Récupère et parse un sitemap"""
        try:
            async with self.session.get(sitemap_url) as response:
                if response.status == 200:
                    content = await response.text()
                    return self.parse_sitemap_xml(content, sitemap_url)
                else:
                    logger.error(f"Erreur {response.status} récupération sitemap: {sitemap_url}")
                    return []
                    
        except Exception as e:
            logger.error(f"Erreur récupération sitemap {sitemap_url}: {e}")
            return []


class LiveCrawler:
    """Crawler en temps réel pour découvrir les pages"""
    
    def __init__(self, max_depth: int = 2, max_pages: int = 1000):
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.visited_urls = set()
        self.session = None
    
    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=10, limit_per_host=3)
        self.session = aiohttp.ClientSession(connector=connector)
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def normalize_url(self, url: str) -> str:
        """Normalise une URL"""
        parsed = urlparse(url)
        # Supprimer les fragments et certains paramètres
        normalized = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path.rstrip('/'),
            parsed.params,
            '',  # query supprimée pour éviter les doublons
            ''   # fragment supprimé
        ))
        return normalized
    
    def extract_links(self, html: str, base_url: str) -> List[str]:
        """Extrait les liens d'une page HTML"""
        try:
            soup = BeautifulSoup(html, 'lxml')
            links = []
            
            for link in soup.find_all('a', href=True):
                href = link['href']
                
                # Ignorer les liens de navigation, scripts, etc.
                if href.startswith(('#', 'javascript:', 'mailto:', 'tel:')):
                    continue
                
                # Résoudre l'URL relative
                full_url = urljoin(base_url, href)
                parsed = urlparse(full_url)
                
                # Filtrer les domaines externes
                base_domain = urlparse(base_url).netloc
                if parsed.netloc and parsed.netloc != base_domain:
                    continue
                
                # Filtrer les extensions non-web
                if parsed.path.lower().endswith(('.pdf', '.doc', '.xls', '.zip', '.jpg', '.png', '.gif')):
                    continue
                
                normalized_url = self.normalize_url(full_url)
                if normalized_url not in self.visited_urls:
                    links.append(normalized_url)
            
            return links
            
        except Exception as e:
            logger.error(f"Erreur extraction liens: {e}")
            return []
    
    async def crawl_page(self, url: str, depth: int = 0) -> List[str]:
        """Crawl une page et retourne les URLs découvertes"""
        if depth > self.max_depth or len(self.visited_urls) >= self.max_pages:
            return []
        
        if url in self.visited_urls:
            return []
        
        self.visited_urls.add(url)
        discovered_urls = [url]
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Extraire les liens si on n'a pas atteint la profondeur max
                    if depth < self.max_depth:
                        links = self.extract_links(html, url)
                        
                        # Crawler récursivement les liens trouvés
                        for link in links[:10]:  # Limiter à 10 liens par page
                            if len(self.visited_urls) >= self.max_pages:
                                break
                            sub_urls = await self.crawl_page(link, depth + 1)
                            discovered_urls.extend(sub_urls)
                            
        except Exception as e:
            logger.error(f"Erreur crawl {url}: {e}")
        
        return discovered_urls


class PageLoader:
    """Gestionnaire principal pour charger les pages selon différentes sources"""
    
    @staticmethod
    async def _scrape_pages_content(urls: List[str]) -> List[Page]:
        """Scrape le contenu des pages depuis leurs URLs"""
        try:
            async with ContentExtractor() as extractor:
                pages = await extractor.fetch_pages_batch(urls, max_concurrent=5)
                logger.info(f"Scrapé le contenu de {len(pages)} pages sur {len(urls)} URLs")
                return pages
        except Exception as e:
            logger.error(f"Erreur scraping pages: {e}")
            return []
    
    @staticmethod
    async def load_from_csv(file_path: str) -> List[Page]:
        """Charge les pages depuis un fichier CSV"""
        try:
            # Essayer différents séparateurs et encodages
            df = None
            used_sep = None
            
            # Supprimer le BOM si présent
            with open(file_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()
            
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            # Essayer différents séparateurs et gérer les contenus multi-lignes
            for sep in [',', ';', '\t', '|']:
                try:
                    test_df = pd.read_csv(file_path, sep=sep, nrows=1)
                    if len(test_df.columns) > 1:
                        # Charger avec gestion des sauts de ligne dans les cellules
                        df = pd.read_csv(file_path, sep=sep, quoting=1, skipinitialspace=True)
                        used_sep = sep
                        break
                except:
                    continue
            
            if df is None:
                # Fallback avec séparateur par défaut et gestion des quotes
                try:
                    df = pd.read_csv(file_path, quoting=1, skipinitialspace=True)
                    used_sep = ','
                except:
                    # Dernier recours - lecture basique
                    df = pd.read_csv(file_path)
                    used_sep = ','
            
            logger.info(f"CSV chargé avec séparateur '{used_sep}', colonnes: {list(df.columns)}")
            
            # Recherche flexible de la colonne URL
            url_col = None
            url_possibilities = ['url', 'URL', 'Url', 'lien', 'link', 'page_url', 'address']
            for col_name in url_possibilities:
                if col_name in df.columns:
                    url_col = col_name
                    break
            
            if url_col is None:
                available_cols = list(df.columns)
                raise ValueError(f"Colonne URL non trouvée. Colonnes disponibles: {available_cols}. "
                               f"Noms acceptés: {url_possibilities}")
            
            # Recherche flexible des autres colonnes
            title_col = None
            content_col = None
            meta_desc_col = None
            h1_col = None
            h2_col = None
            h3_col = None
            
            # Mappings pour les colonnes optionnelles
            column_mappings = {
                'title': ['title', 'Title', 'titre', 'Titre', 'name', 'page_title'],
                'content': ['content', 'Content', 'contenu', 'Contenu', 'text', 'body', 'description', 'texte', 'Texte'],
                'meta_description': ['meta_description', 'Meta Description', 'meta_desc', 'description'],
                'h1': ['h1', 'H1', 'heading1', 'title_h1'],
                'h2': ['h2', 'H2', 'heading2', 'title_h2'],
                'h3': ['h3', 'H3', 'heading3', 'title_h3']
            }
            
            for var_name, possibilities in column_mappings.items():
                for col_name in possibilities:
                    if col_name in df.columns:
                        locals()[f"{var_name}_col"] = col_name
                        break
            
            logger.info(f"Colonnes détectées - URL: '{url_col}', title: '{title_col}', "
                       f"content: '{content_col}', meta_desc: '{meta_desc_col}'")
            
            # Déterminer s'il faut scraper ou utiliser le contenu du CSV
            has_content_column = content_col is not None
            should_scrape = True
            
            if has_content_column:
                # Vérifier si la colonne contenu a des données réelles
                sample_content = []
                for _, row in df.head(10).iterrows():
                    content_val = row.get(content_col)
                    if pd.notna(content_val) and str(content_val).strip() not in ['', 'nan']:
                        content_str = str(content_val).strip()
                        if len(content_str) > 20:  # Au moins 20 caractères pour être considéré comme du contenu
                            sample_content.append(content_str)
                
                if len(sample_content) >= 3:  # Si au moins 3 pages ont du contenu
                    should_scrape = False
                    logger.info(f"✅ Contenu détecté dans le CSV - Pas de scraping nécessaire")
                else:
                    logger.info(f"⚠️  Colonne contenu détectée mais vide - Scraping activé")
            else:
                logger.info(f"❌ Pas de colonne contenu - Scraping activé")
            
            pages = []
            pages_to_scrape = []  # URLs sans contenu à scraper
            
            for _, row in df.iterrows():
                # Nettoyage des données
                url = str(row[url_col]).strip()
                if not url or url == 'nan' or not url.startswith(('http://', 'https://')):
                    continue
                
                # Extraire le contenu du CSV
                title = str(row[title_col]).strip() if title_col and pd.notna(row.get(title_col)) and str(row[title_col]).strip() not in ['nan', ''] else None
                
                # Nettoyage spécial pour le contenu
                if content_col and pd.notna(row.get(content_col)) and str(row[content_col]).strip() not in ['nan', '']:
                    raw_content = str(row[content_col]).strip()
                    
                    # Supprimer les préfixes b' et suffixes ' si présents
                    if raw_content.startswith("b'") and raw_content.endswith("'"):
                        raw_content = raw_content[2:-1]
                    
                    # Nettoyer les caractères d'échappement
                    raw_content = raw_content.replace('\\n', ' ').replace('\\t', ' ').replace('\\"', '"')
                    raw_content = raw_content.replace('\\\\', ' ')
                    
                    # Supprimer les espaces multiples
                    import re
                    raw_content = re.sub(r'\s+', ' ', raw_content).strip()
                    
                    # Décoder les séquences d'échappement restantes
                    try:
                        # Essayer de décoder les bytes si c'est une chaîne d'échappement
                        if '\\x' in raw_content:
                            raw_content = raw_content.encode().decode('unicode_escape')
                    except:
                        pass  # Si le décodage échoue, garder le contenu tel quel
                    
                    content = raw_content
                else:
                    content = ''
                meta_desc = str(row[meta_desc_col]).strip() if meta_desc_col and pd.notna(row.get(meta_desc_col)) and str(row[meta_desc_col]).strip() not in ['nan', ''] else None
                h1 = str(row[h1_col]).strip() if h1_col and pd.notna(row.get(h1_col)) and str(row[h1_col]).strip() not in ['nan', ''] else None
                h2 = str(row[h2_col]).split('|') if h2_col and pd.notna(row.get(h2_col)) and str(row[h2_col]).strip() not in ['nan', ''] else []
                h3 = str(row[h3_col]).split('|') if h3_col and pd.notna(row.get(h3_col)) and str(row[h3_col]).strip() not in ['nan', ''] else []
                
                page = Page(
                    url=url,
                    title=title,
                    meta_description=meta_desc,
                    content=content,
                    h1=h1,
                    h2=h2,
                    h3=h3
                )
                
                # Décider si cette page doit être scrapée
                if should_scrape or (not content and not title and not meta_desc):
                    pages_to_scrape.append(url)
                
                pages.append(page)
            
            # Scraper le contenu manquant si nécessaire
            if pages_to_scrape and should_scrape:
                logger.info(f"🔄 Scraping du contenu pour {len(pages_to_scrape)} pages...")
                scraped_pages = await PageLoader._scrape_pages_content(pages_to_scrape)
                
                # Mettre à jour les pages avec le contenu scrapé
                scraped_dict = {p.url: p for p in scraped_pages}
                for i, page in enumerate(pages):
                    if page.url in scraped_dict:
                        scraped = scraped_dict[page.url]
                        # Mettre à jour seulement si les champs sont vides
                        pages[i] = Page(
                            url=page.url,
                            title=page.title or scraped.title,
                            meta_description=page.meta_description or scraped.meta_description,
                            content=page.content or scraped.content,
                            h1=page.h1 or scraped.h1,
                            h2=page.h2 or scraped.h2,
                            h3=page.h3 or scraped.h3
                        )
            elif pages_to_scrape and not should_scrape:
                logger.info(f"⚡ Contenu CSV utilisé directement - Scraping évité pour {len(pages)} pages")
            
            logger.info(f"Chargé {len(pages)} pages valides depuis CSV")
            return pages
            
        except Exception as e:
            logger.error(f"Erreur chargement CSV {file_path}: {e}")
            raise
    
    @staticmethod
    async def load_from_sitemap(sitemap_url: str) -> List[Page]:
        """Charge les pages depuis un sitemap"""
        async with SitemapParser() as parser:
            urls = await parser.fetch_sitemap_urls(sitemap_url)
            
        if not urls:
            logger.warning(f"Aucune URL trouvée dans le sitemap: {sitemap_url}")
            return []
        
        logger.info(f"Trouvé {len(urls)} URLs dans le sitemap")
        
        # Récupérer le contenu des pages par batch
        async with ContentExtractor() as extractor:
            pages = []
            batch_size = 50
            
            for i in range(0, len(urls), batch_size):
                batch_urls = urls[i:i+batch_size]
                batch_pages = await extractor.fetch_pages_batch(batch_urls)
                pages.extend(batch_pages)
                
                logger.info(f"Traité {len(pages)}/{len(urls)} pages")
        
        return pages
    
    @staticmethod
    async def load_from_live_crawl(seed_url: str, depth: int = 2, max_pages: int = 1000) -> List[Page]:
        """Charge les pages via crawl en temps réel"""
        async with LiveCrawler(max_depth=depth, max_pages=max_pages) as crawler:
            urls = await crawler.crawl_page(seed_url)
        
        if not urls:
            logger.warning(f"Aucune URL découverte depuis: {seed_url}")
            return []
        
        logger.info(f"Découvert {len(urls)} URLs via crawl")
        
        # Récupérer le contenu des pages
        async with ContentExtractor() as extractor:
            pages = []
            batch_size = 20
            
            for i in range(0, len(urls), batch_size):
                batch_urls = urls[i:i+batch_size]
                batch_pages = await extractor.fetch_pages_batch(batch_urls)
                pages.extend(batch_pages)
                
                logger.info(f"Traité {len(pages)}/{len(urls)} pages")
        
        return pages 
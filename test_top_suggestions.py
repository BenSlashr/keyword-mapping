#!/usr/bin/env python3
"""
Test pour vérifier que le paramètre top_suggestions fonctionne
"""

import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.services.job_manager import JobManager
from app.models import SourceType

async def test_top_suggestions():
    """Test du paramètre top_suggestions"""
    print("🔍 TEST TOP SUGGESTIONS")
    print("=" * 50)
    
    # Utiliser le dernier job
    job_id = "d2b44967-0057-45a2-b971-0094cb842f85"
    keywords_file = f"uploads/{job_id}_keywords.csv"
    pages_file = f"uploads/{job_id}_pages.csv"
    
    if not os.path.exists(keywords_file) or not os.path.exists(pages_file):
        print(f"❌ Fichiers manquants")
        return
    
    # Test avec different valeurs de top_suggestions
    for top_suggestions in [1, 3, 5]:
        print(f"\n🧪 Test avec top_suggestions = {top_suggestions}")
        
        params = {
            'keywords_path': keywords_file,
            'source_type': SourceType.CSV.value,
            'pages_path': pages_file,
            'top_suggestions': top_suggestions,
            'min_score_threshold': 0.05
        }
        
        test_job_id = f"test_suggestions_{top_suggestions}"
        job_manager = JobManager()
        
        try:
            await job_manager.run_matching_job(test_job_id, params)
            
            # Récupérer le résultat
            result = await job_manager.get_job_result(test_job_id)
            
            if result and result.assignments:
                print(f"   ✅ {len(result.assignments)} assignations créées")
                
                # Vérifier quelques assignations pour le nombre d'alternatives
                print(f"   📊 Vérification des alternatives:")
                for i, assignment in enumerate(result.assignments[:3]):
                    nb_alternatives = len(assignment.alternative_urls)
                    print(f"   {i+1}. '{assignment.keyword}' -> {nb_alternatives} alternatives (max: {top_suggestions})")
                    
                    if nb_alternatives > top_suggestions:
                        print(f"   ⚠️  PROBLÈME: {nb_alternatives} > {top_suggestions}")
                    
                    # Afficher les URLs alternatives
                    if assignment.alternative_urls:
                        print(f"      Alternatives: {assignment.alternative_urls[:2]}...")
                
            else:
                print(f"   ❌ Aucun résultat")
                
        except Exception as e:
            print(f"   ❌ Erreur: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_top_suggestions()) 
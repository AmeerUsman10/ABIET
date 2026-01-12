"""
ABIET Learning Engine
Continuous learning from user interactions
"""

from typing import Dict, Any, List
import json
import os
from datetime import datetime

class LearningEngine:
    def __init__(self, storage_path: str = "learning_data.json"):
        self.storage_path = storage_path
        self.learning_data = self._load_learning_data()
        
    def _load_learning_data(self) -> Dict[str, Any]:
        """Load learning data from storage"""
        default_data = {"patterns": [], "corrections": [], "interactions": [], "usage_stats": {}}
        if os.path.exists(self.storage_path):
            with open(self.storage_path, 'r') as f:
                loaded = json.load(f)
            # Merge with defaults to ensure all keys exist
            for key, value in default_data.items():
                if key not in loaded:
                    loaded[key] = value
            return loaded
        return default_data
    
    def save_learning_data(self):
        """Save learning data to storage"""
        with open(self.storage_path, 'w') as f:
            json.dump(self.learning_data, f, indent=2)
    
    def record_query_pattern(self, natural_query: str, generated_sql: str, success: bool):
        """Record a query pattern for learning"""
        pattern = {
            "natural_query": natural_query,
            "generated_sql": generated_sql,
            "success": success,
            "timestamp": datetime.now().isoformat(),
            "usage_count": 1
        }
        
        self.learning_data["patterns"].append(pattern)
        self.save_learning_data()
    
    def record_correction(self, original_query: str, corrected_query: str):
        """Record a user correction for learning"""
        correction = {
            "original": original_query,
            "corrected": corrected_query,
            "timestamp": datetime.now().isoformat()
        }
        
        self.learning_data["corrections"].append(correction)
        self.save_learning_data()
    
    def record_interaction(self, natural_query: str, generated_sql: str = None, success: bool = True, feedback: str = None, error: str = None):
        """Record an interaction with OpenAI responses"""
        interaction = {
            "natural_query": natural_query,
            "generated_sql": generated_sql,
            "success": success,
            "feedback": feedback,
            "error": error,
            "timestamp": datetime.now().isoformat()
        }
        
        self.learning_data["interactions"].append(interaction)
        self.save_learning_data()
    
    def add_feedback_to_interaction(self, interaction_index: int, feedback: str):
        """Add user feedback to an existing interaction"""
        if 0 <= interaction_index < len(self.learning_data["interactions"]):
            self.learning_data["interactions"][interaction_index]["feedback"] = feedback
            self.save_learning_data()
    
    def get_interactions(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get recorded interactions, optionally limited"""
        interactions = self.learning_data["interactions"]
        if limit:
            interactions = interactions[-limit:]
        return interactions
    
    def find_similar_patterns(self, query: str, threshold: float = 0.8) -> List[Dict[str, Any]]:
        """Find similar query patterns"""
        # Implement similarity search (placeholder)
        return []
    
    def get_query_suggestions(self, partial_query: str) -> List[str]:
        """Get query suggestions based on partial input"""
        # Implement suggestion engine
        return []

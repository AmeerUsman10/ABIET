"""
ABIET Feedback Processor
Analyzes feedback data from learning engine to identify patterns and suggest improvements
"""

from typing import Dict, Any, List, Optional
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import openai
from backend.config.settings import settings
from ai.learning.learning_engine import LearningEngine


class FeedbackProcessor:
    def __init__(self, learning_engine: Optional[LearningEngine] = None):
        self.learning_engine = learning_engine or LearningEngine()
        openai.api_key = settings.OPENAI_API_KEY

    def get_feedback_data(self) -> List[Dict[str, Any]]:
        """Get all interactions with feedback"""
        interactions = self.learning_engine.get_interactions()
        return [i for i in interactions if i.get("feedback")]

    def analyze_feedback_patterns(self) -> Dict[str, Any]:
        """Analyze feedback data for common patterns and themes"""
        feedback_data = self.get_feedback_data()

        if not feedback_data:
            return {"message": "No feedback data available for analysis"}

        # Basic text analysis
        feedback_texts = [item["feedback"] for item in feedback_data if item["feedback"]]

        # Common keywords/themes
        keywords = self._extract_keywords(feedback_texts)

        # Error patterns
        error_patterns = self._analyze_error_patterns(feedback_data)

        # Success rates over time
        success_trends = self._analyze_success_trends(feedback_data)

        # Query type analysis
        query_types = self._analyze_query_types(feedback_data)

        return {
            "total_feedback": len(feedback_data),
            "common_keywords": keywords,
            "error_patterns": error_patterns,
            "success_trends": success_trends,
            "query_type_analysis": query_types,
            "analysis_timestamp": datetime.now().isoformat()
        }

    def _extract_keywords(self, feedback_texts: List[str]) -> Dict[str, int]:
        """Extract common keywords from feedback"""
        all_words = []
        for text in feedback_texts:
            # Simple tokenization (could be improved with NLP)
            words = re.findall(r'\b\w+\b', text.lower())
            # Remove common stop words
            stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'}
            words = [w for w in words if w not in stop_words and len(w) > 2]
            all_words.extend(words)

        return dict(Counter(all_words).most_common(20))

    def _analyze_error_patterns(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze patterns in errors and feedback"""
        errors = []
        feedback_themes = defaultdict(int)

        for item in feedback_data:
            if item.get("error"):
                errors.append(item["error"])

            feedback = item.get("feedback", "").lower()
            # Categorize feedback themes
            if "wrong" in feedback or "incorrect" in feedback:
                feedback_themes["incorrect_sql"] += 1
            elif "slow" in feedback or "performance" in feedback:
                feedback_themes["performance"] += 1
            elif "missing" in feedback or "not found" in feedback:
                feedback_themes["missing_data"] += 1
            elif "format" in feedback or "display" in feedback:
                feedback_themes["formatting"] += 1
            else:
                feedback_themes["other"] += 1

        return {
            "common_errors": dict(Counter(errors).most_common(5)),
            "feedback_themes": dict(feedback_themes)
        }

    def _analyze_success_trends(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze success rates over time"""
        # Group by date
        daily_stats = defaultdict(lambda: {"total": 0, "success": 0})

        for item in feedback_data:
            date = datetime.fromisoformat(item["timestamp"]).date()
            daily_stats[date]["total"] += 1
            if item.get("success", False):
                daily_stats[date]["success"] += 1

        trends = {}
        for date, stats in sorted(daily_stats.items()):
            success_rate = stats["success"] / stats["total"] if stats["total"] > 0 else 0
            trends[str(date)] = {
                "total_queries": stats["total"],
                "success_rate": round(success_rate, 2)
            }

        return trends

    def _analyze_query_types(self, feedback_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze types of queries being processed"""
        query_keywords = {
            "select": ["show", "list", "get", "find", "display"],
            "insert": ["add", "create", "insert", "new"],
            "update": ["update", "change", "modify", "edit"],
            "delete": ["delete", "remove", "erase"],
            "join": ["combine", "join", "merge", "link"],
            "aggregate": ["count", "sum", "average", "total", "group"]
        }

        type_counts = defaultdict(int)

        for item in feedback_data:
            query = item.get("natural_query", "").lower()
            for query_type, keywords in query_keywords.items():
                if any(keyword in query for keyword in keywords):
                    type_counts[query_type] += 1

        return dict(type_counts)

    def generate_improvement_suggestions(self, analysis: Optional[Dict[str, Any]] = None) -> List[str]:
        """Generate improvement suggestions based on analysis"""
        if analysis is None:
            analysis = self.analyze_feedback_patterns()

        suggestions = []

        # Based on error patterns
        error_patterns = analysis.get("error_patterns", {})
        common_errors = error_patterns.get("common_errors", {})

        if "Invalid JSON response" in common_errors:
            suggestions.append("Improve prompt engineering to ensure consistent JSON responses from OpenAI")

        feedback_themes = error_patterns.get("feedback_themes", {})
        if feedback_themes.get("incorrect_sql", 0) > feedback_themes.get("other", 0):
            suggestions.append("Review and enhance SQL generation prompts for better accuracy")

        # Based on success trends
        success_trends = analysis.get("success_trends", {})
        recent_dates = sorted(success_trends.keys())[-7:]  # Last 7 days
        recent_rates = [success_trends[date]["success_rate"] for date in recent_dates if date in success_trends]

        if recent_rates and sum(recent_rates) / len(recent_rates) < 0.7:
            suggestions.append("Investigate recent decline in success rates - check for prompt degradation or API changes")

        # Based on query types
        query_types = analysis.get("query_type_analysis", {})
        if query_types.get("join", 0) > 10:  # Arbitrary threshold
            suggestions.append("Add specific handling for complex JOIN queries in the prompt")

        # General suggestions
        total_feedback = analysis.get("total_feedback", 0)
        if total_feedback > 50:
            suggestions.append("Consider implementing A/B testing for different prompt versions")

        if not suggestions:
            suggestions.append("System performing well - continue monitoring feedback patterns")

        return suggestions

    def get_ai_insights(self, analysis: Optional[Dict[str, Any]] = None) -> str:
        """Use OpenAI to generate deeper insights from the analysis"""
        if analysis is None:
            analysis = self.analyze_feedback_patterns()

        prompt = f"""
Based on the following analysis of user feedback and system performance data, provide insights and recommendations for improving the natural language to SQL conversion system:

Analysis Data:
{json.dumps(analysis, indent=2)}

Please provide:
1. Key insights from the data
2. Potential root causes for issues
3. Specific recommendations for prompt improvements
4. Suggestions for system enhancements
5. Metrics to monitor going forward

Focus on actionable improvements that can enhance accuracy and user satisfaction.
"""

        try:
            client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.AI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,  # Lower temperature for more focused analysis
                max_tokens=1000
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"Error generating AI insights: {str(e)}"

    def export_report(self, include_ai_insights: bool = True) -> Dict[str, Any]:
        """Generate a complete feedback analysis report"""
        analysis = self.analyze_feedback_patterns()
        suggestions = self.generate_improvement_suggestions(analysis)

        report = {
            "analysis": analysis,
            "suggestions": suggestions,
            "generated_at": datetime.now().isoformat()
        }

        if include_ai_insights:
            report["ai_insights"] = self.get_ai_insights(analysis)

        return report


# Export a singleton instance
feedback_processor = FeedbackProcessor()
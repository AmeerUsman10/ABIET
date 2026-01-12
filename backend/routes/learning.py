"""
Learning System Routes
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any
from ai.learning.learning_engine import LearningEngine
from ai.feedback_processor import FeedbackProcessor

logger = logging.getLogger(__name__)
router = APIRouter()

class FeedbackRequest(BaseModel):
    interaction_index: int
    feedback: str

class FeedbackResponse(BaseModel):
    status: str
    message: str

class HistoryResponse(BaseModel):
    status: str
    history: List

class AnalysisResponse(BaseModel):
    status: str
    analysis: Dict[str, Any]
    suggestions: List[str]

learning_engine = LearningEngine()
feedback_processor = FeedbackProcessor(learning_engine)

@router.get("/")
async def learning_root():
    try:
        logger.info("Learning root endpoint accessed")
        return {"message": "Learning system endpoint - to be implemented"}
    except Exception as e:
        logger.error(f"Error in learning root: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred.")

@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(request: FeedbackRequest):
    try:
        logger.info(f"Submitting feedback for interaction {request.interaction_index}")
        learning_engine.add_feedback_to_interaction(request.interaction_index, request.feedback)
        logger.info("Feedback submitted successfully")
        return FeedbackResponse(status="success", message="Feedback recorded")
    except Exception as exc:
        logger.error(f"Error submitting feedback: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to record feedback. Please try again.")

@router.get("/history", response_model=HistoryResponse)
async def get_history(limit: int = 10):
    try:
        logger.info(f"Fetching interaction history with limit {limit}")
        interactions = learning_engine.get_interactions(limit)
        logger.info("History fetched successfully")
        return HistoryResponse(status="success", history=interactions)
    except Exception as exc:
        logger.error(f"Error fetching history: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to retrieve interaction history. Please try again.")

@router.get("/analysis", response_model=AnalysisResponse)
async def get_feedback_analysis():
    try:
        logger.info("Generating feedback analysis")
        analysis = feedback_processor.analyze_feedback_patterns()
        suggestions = feedback_processor.generate_improvement_suggestions(analysis)
        logger.info("Analysis generated successfully")
        return AnalysisResponse(status="success", analysis=analysis, suggestions=suggestions)
    except Exception as exc:
        logger.error(f"Error generating analysis: {str(exc)}")
        raise HTTPException(status_code=500, detail="Failed to generate feedback analysis. Please try again.")

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import List, Dict, Any
import logging

from app.services.agent_service import process_query
from app.dependencies import rate_limit_dependency

logger = logging.getLogger(__name__)

router = APIRouter()

class AgentAskRequest(BaseModel):
    question: str

class AgentAskResponse(BaseModel):
    answer: str
    steps: List[Dict[str, Any]]

@router.post("/agent/ask", response_model=AgentAskResponse, dependencies=[Depends(rate_limit_dependency)])
def ask_agent(payload: AgentAskRequest):
    if not payload.question.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be empty."
        )
        
    try:
        result = process_query(payload.question)
        return result
    except ValueError as e:
        logger.error(f"Agent service configuration error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Configuration error: {str(e)}"
        )
    except RuntimeError as e:
        logger.error(f"Agent service runtime failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"OpenRouter API failure: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected agent failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {str(e)}"
        )

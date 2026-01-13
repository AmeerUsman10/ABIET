from backend.routes.auth import get_current_user
from backend.models import User
"""backend.routes.db
-------------------
Provides a generic endpoint to execute raw SQL against a selected database.
Supported ``db_type`` values: ``mssql`` and ``oracle``.
The endpoint expects a JSON payload:
```json
{ "db_type": "mssql", "query": "SELECT 1 AS test" }
```
It returns the rows as a list of dictionaries or an error message.
"""

import logging
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from backend.config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class DBQuery(BaseModel):
    db_type: str = Field(..., description="Database type: 'mssql' or 'oracle'")
    query: str = Field(..., description="SQL query to execute")

class DBQueryResponse(BaseModel):
    status: str
    rows: List[Dict] | None = None

def _get_engine(db_type: str):
    if db_type == "mssql":
        url = settings.MSSQL_DATABASE_URL
    elif db_type == "oracle":
        url = settings.ORACLE_DATABASE_URL
    else:
        raise ValueError("Unsupported db_type. Use 'mssql' or 'oracle'.")
    if not url:
        raise ValueError(f"Database URL for {db_type} is not configured.")
    return create_engine(url)

@router.post("/execute", response_model=DBQueryResponse)
async def execute_query(payload: DBQuery, current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Executing query for user {current_user.username} on {payload.db_type}")
        
        engine = _get_engine(payload.db_type)
        
        with engine.connect() as conn:
            result = conn.execute(text(payload.query))
            # Convert ResultProxy to list of dicts
            rows = [dict(row) for row in result]
            
        logger.info(f"Query executed successfully for user {current_user.username}")
        return DBQueryResponse(status="success", rows=rows)
    
    except ValueError as e:
        logger.warning(f"Invalid request from user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="A database error occurred. Please check your query and try again.")
    except Exception as e:
        logger.error(f"Unexpected error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again later.")

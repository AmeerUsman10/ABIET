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
    query: str = Field(..., description="SQL query to execute")
    connection: DBConnection = Field(None, description="Database connection details (optional)")

class DBConnection(BaseModel):
    type: str = Field(..., description="Database type: 'mssql', 'postgresql', or 'oracle'")
    host: str = Field(..., description="Database host")
    port: int = Field(..., description="Database port")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")

class TestConnectionResponse(BaseModel):
    success: bool
    message: str

def _get_engine(db_type: str, connection: DBConnection = None):
    if connection:
        # Use provided connection details
        if db_type == "mssql":
            url = f"mssql+pyodbc://{connection.username}:{connection.password}@{connection.host}:{connection.port}/{connection.database}?driver=ODBC+Driver+17+for+SQL+Server"
        elif db_type == "postgresql":
            url = f"postgresql://{connection.username}:{connection.password}@{connection.host}:{connection.port}/{connection.database}"
        elif db_type == "oracle":
            url = f"oracle://{connection.username}:{connection.password}@{connection.host}:{connection.port}/{connection.database}"
        else:
            raise ValueError("Unsupported db_type.")
    else:
        # Use configured URLs
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
        logger.info(f"Executing query for user {current_user.username}")
        
        db_type = payload.connection.type if payload.connection else "mssql"  # Default fallback
        engine = _get_engine(db_type, payload.connection)
        
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

@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(connection: DBConnection, current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Testing connection for user {current_user.username} to {connection.type}")
        
        engine = _get_engine(connection.type, connection)
        
        # Try to connect and execute a simple query
        with engine.connect() as conn:
            if connection.type == "mssql":
                conn.execute(text("SELECT 1"))
            elif connection.type == "postgresql":
                conn.execute(text("SELECT 1"))
            elif connection.type == "oracle":
                conn.execute(text("SELECT 1 FROM dual"))
        
        logger.info(f"Connection test successful for user {current_user.username}")
        return TestConnectionResponse(success=True, message="Connection successful!")
    
    except Exception as e:
        logger.error(f"Connection test failed for user {current_user.username}: {str(e)}")
        return TestConnectionResponse(success=False, message=f"Connection failed: {str(e)}")

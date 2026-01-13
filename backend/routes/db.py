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

class DBConnection(BaseModel):
    db_type: str = Field(..., description="Database type: 'mssql', 'postgresql', or 'oracle'")
    host: str = Field(..., description="Database host")
    port: int = Field(..., description="Database port")
    database: str = Field(..., description="Database name")
    username: str = Field(..., description="Database username")
    password: str = Field(..., description="Database password")

class DBQuery(BaseModel):
    db_type: str = Field(..., description="Database type: 'mssql', 'postgresql', or 'oracle'")
    query: str = Field(..., description="SQL query to execute")
    connection: DBConnection = Field(None, description="Database connection details (optional, uses static config if not provided)")

class DBQueryResponse(BaseModel):
    status: str
    rows: List[Dict] | None = None

def _get_engine(db_type: str, connection_data: DBConnection = None):
    if connection_data:
        # Dynamic connection
        if db_type == "mssql":
            url = f"mssql+pyodbc://{connection_data.username}:{connection_data.password}@{connection_data.host}:{connection_data.port}/{connection_data.database}?driver=ODBC+Driver+17+for+SQL+Server"
        elif db_type == "postgresql":
            url = f"postgresql://{connection_data.username}:{connection_data.password}@{connection_data.host}:{connection_data.port}/{connection_data.database}"
        elif db_type == "oracle":
            url = f"oracle+cx_oracle://{connection_data.username}:{connection_data.password}@{connection_data.host}:{connection_data.port}/{connection_data.database}"
        else:
            raise ValueError("Unsupported db_type. Use 'mssql', 'postgresql', or 'oracle'.")
    else:
        # Static connection from settings
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
        
        engine = _get_engine(payload.db_type, payload.connection)
        
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

@router.post("/connect")
async def connect_db(payload: DBConnection, current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Testing connection for user {current_user.username} to {payload.db_type}")
        
        engine = _get_engine(payload.db_type, payload)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            
        logger.info(f"Connection test successful for user {current_user.username}")
        return {"status": "success", "message": "Connection established successfully"}
    
    except ValueError as e:
        logger.warning(f"Invalid connection request from user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database connection error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to connect to database. Please check your connection details.")
    except Exception as e:
        logger.error(f"Unexpected connection error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again later.")

@router.post("/test")
async def test_db_connection(payload: DBConnection, current_user: User = Depends(get_current_user)):
    try:
        logger.info(f"Testing connection for user {current_user.username} to {payload.db_type}")
        
        engine = _get_engine(payload.db_type, payload)
        
        # Test connection
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            
        logger.info(f"Connection test successful for user {current_user.username}")
        return {"status": "success", "message": "Connection test successful"}
    
    except ValueError as e:
        logger.warning(f"Invalid connection test request from user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except SQLAlchemyError as e:
        logger.error(f"Database connection test error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="Connection test failed. Please check your connection details.")
    except Exception as e:
        logger.error(f"Unexpected connection test error for user {current_user.username}: {str(e)}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred. Please try again later.")

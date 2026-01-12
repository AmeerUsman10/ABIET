from backend.routes.auth import get_current_user, User
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

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from backend.config.settings import settings

router = APIRouter()

class DBQuery(BaseModel):
    db_type: str = Field(..., description="Database type: 'mssql' or 'oracle'")
    query: str = Field(..., description="SQL query to execute")

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

@router.post("/execute")
async def execute_query(payload: DBQuery, current_user: User = Depends(get_current_user)):
    try:
        engine = _get_engine(payload.db_type)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    try:
        with engine.connect() as conn:
            result = conn.execute(text(payload.query))
            # Convert ResultProxy to list of dicts
            rows = [dict(row) for row in result]
            return {"status": "success", "rows": rows}
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

"""
Saved database connections: CRUD, connection tests, schema browsing, demo database.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.deps import get_current_user, get_owned_connection
from backend.models import DatabaseConnection, User
from backend.schemas import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionTest,
    ConnectionTestResult,
    ConnectionUpdate,
    DbTypeOut,
    clean_options,
)
from backend.security import encrypt_secret
from backend.services.assistant import get_schema
from backend.services.connectors import (
    DB_TYPES,
    ConnectionSpec,
    ConnectorError,
    build_url,
    dispose_engine,
    test_connection,
)
from backend.services.demo import DEMO_FILE_NAME, ensure_demo_database

logger = logging.getLogger(__name__)
router = APIRouter()

DEMO_CONNECTION_NAME = "Demo - Sales"
_CONNECTION_FIELDS = ("db_type", "host", "port", "database", "username", "options", "read_only")


def to_out(conn: DatabaseConnection) -> ConnectionOut:
    return ConnectionOut(
        id=conn.id,
        name=conn.name,
        db_type=conn.db_type,
        db_label=DB_TYPES[conn.db_type].label if conn.db_type in DB_TYPES else conn.db_type,
        host=conn.host,
        port=conn.port,
        database=conn.database,
        username=conn.username,
        has_password=bool(conn.password_encrypted),
        options=conn.options or {},
        read_only=conn.read_only,
        is_demo=conn.is_demo,
        table_count=len(conn.schema_cache["tables"]) if conn.schema_cache else None,
        schema_cached_at=conn.schema_cached_at,
        created_at=conn.created_at,
        updated_at=conn.updated_at,
    )


def _validate(spec: ConnectionSpec) -> None:
    """Reject settings that can never work (without connecting)."""
    try:
        build_url(spec)
    except ConnectorError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _name_taken(db: Session, user: User, name: str, exclude_id: int | None = None) -> bool:
    stmt = select(DatabaseConnection.id).where(DatabaseConnection.owner_id == user.id, DatabaseConnection.name == name)
    if exclude_id is not None:
        stmt = stmt.where(DatabaseConnection.id != exclude_id)
    return db.scalar(stmt) is not None


@router.get("/types", response_model=list[DbTypeOut])
def list_types():
    return [
        DbTypeOut(
            key=t.key,
            label=t.label,
            default_port=t.default_port,
            requires_host=t.requires_host,
            options=list(t.options),
        )
        for t in DB_TYPES.values()
    ]


@router.get("", response_model=list[ConnectionOut])
def list_connections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conns = db.scalars(
        select(DatabaseConnection).where(DatabaseConnection.owner_id == user.id).order_by(DatabaseConnection.name)
    )
    return [to_out(c) for c in conns]


@router.post("", response_model=ConnectionOut, status_code=status.HTTP_201_CREATED)
def create_connection(payload: ConnectionCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    name = payload.name.strip()
    if _name_taken(db, user, name):
        raise HTTPException(status_code=409, detail=f"You already have a connection named '{name}'")
    options = clean_options(payload.db_type, payload.options)
    spec = ConnectionSpec(
        db_type=payload.db_type,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password=payload.password,
        options=options,
        read_only=payload.read_only,
    )
    _validate(spec)
    conn = DatabaseConnection(
        owner_id=user.id,
        name=name,
        db_type=payload.db_type,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password_encrypted=encrypt_secret(payload.password),
        options=options,
        read_only=payload.read_only,
    )
    db.add(conn)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"You already have a connection named '{name}'") from None
    logger.info("User %s created connection %s (%s)", user.username, conn.id, conn.db_type)
    return to_out(conn)


@router.post("/demo", response_model=ConnectionOut)
def create_demo_connection(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add (or return) the sample sales database for this user."""
    ensure_demo_database()
    existing = db.scalar(
        select(DatabaseConnection).where(DatabaseConnection.owner_id == user.id, DatabaseConnection.is_demo.is_(True))
    )
    if existing:
        return to_out(existing)
    name = DEMO_CONNECTION_NAME
    suffix = 2
    while _name_taken(db, user, name):
        name = f"{DEMO_CONNECTION_NAME} {suffix}"
        suffix += 1
    conn = DatabaseConnection(
        owner_id=user.id,
        name=name,
        db_type="sqlite",
        database=DEMO_FILE_NAME,
        options={"sample_values": True},
        read_only=True,
        is_demo=True,
    )
    db.add(conn)
    db.commit()
    return to_out(conn)


@router.post("/test", response_model=ConnectionTestResult)
def test_unsaved_connection(
    payload: ConnectionTest, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    password = payload.password
    if password is None and payload.connection_id is not None:
        saved = get_owned_connection(db, user, payload.connection_id)
        password = ConnectionSpec.from_model(saved).password
    spec = ConnectionSpec(
        db_type=payload.db_type,
        host=payload.host,
        port=payload.port,
        database=payload.database,
        username=payload.username,
        password=password,
        options=clean_options(payload.db_type, payload.options),
        read_only=payload.read_only,
    )
    try:
        return ConnectionTestResult(**test_connection(spec))
    except ConnectorError as exc:
        return ConnectionTestResult(ok=False, message=str(exc))


@router.get("/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return to_out(get_owned_connection(db, user, connection_id))


@router.put("/{connection_id}", response_model=ConnectionOut)
def update_connection(
    connection_id: int,
    payload: ConnectionUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = get_owned_connection(db, user, connection_id)
    changes = payload.model_dump(exclude_unset=True)
    if conn.is_demo and set(changes) - {"name"}:
        raise HTTPException(status_code=400, detail="Only the name of the demo connection can be changed")

    before = {f: getattr(conn, f) for f in _CONNECTION_FIELDS}
    before_password = conn.password_encrypted
    if "name" in changes and changes["name"] is not None:
        name = changes["name"].strip()
        if _name_taken(db, user, name, exclude_id=conn.id):
            raise HTTPException(status_code=409, detail=f"You already have a connection named '{name}'")
        conn.name = name
    for field in ("db_type", "host", "port", "database", "username", "read_only"):
        if field in changes:
            value = changes[field]
            if isinstance(value, str):
                value = value.strip() or None
            if field in ("db_type", "read_only") and value is None:
                continue
            setattr(conn, field, value)
    if "options" in changes and changes["options"] is not None:
        conn.options = clean_options(conn.db_type, changes["options"])
    elif "db_type" in changes:
        conn.options = clean_options(conn.db_type, conn.options)
    if payload.clear_password:
        conn.password_encrypted = None
    elif payload.password is not None:
        conn.password_encrypted = encrypt_secret(payload.password)

    _validate(ConnectionSpec.from_model(conn))
    if before != {f: getattr(conn, f) for f in _CONNECTION_FIELDS} or before_password != conn.password_encrypted:
        conn.schema_cache = None
        conn.schema_cached_at = None
        dispose_engine(conn.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A connection with that name already exists") from None
    return to_out(conn)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_connection(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned_connection(db, user, connection_id)
    dispose_engine(conn.id)
    db.delete(conn)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_saved_connection(connection_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conn = get_owned_connection(db, user, connection_id)
    if conn.is_demo:
        ensure_demo_database()
    try:
        return ConnectionTestResult(**test_connection(ConnectionSpec.from_model(conn)))
    except ConnectorError as exc:
        return ConnectionTestResult(ok=False, message=str(exc))


@router.get("/{connection_id}/schema")
def connection_schema(
    connection_id: int,
    refresh: bool = Query(False, description="Re-read the schema from the database"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    conn = get_owned_connection(db, user, connection_id)
    if conn.is_demo:
        ensure_demo_database()
    return get_schema(db, conn, refresh=refresh)

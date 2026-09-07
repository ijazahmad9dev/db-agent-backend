import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import Connection, TableSelection
from db_agent.security.credentials import encrypt_config, decrypt_config
from db_agent.adapters.factory import get_adapter
from db_agent.schemas.connection import (
    ConnectionCreate,
    ConnectionOut,
    ConnectionTestResult,
    TableListOut,
    TableSelectionIn, 
    TableSelectionOut,
)
from db_agent.introspection.ddl_vectorstore import index_ddl

router = APIRouter(prefix="/connections")
settings = get_settings()


@router.post("", response_model=ConnectionOut)
def create_connection(payload: ConnectionCreate, db: Session = Depends(get_db)):
    if payload.source_type == "csv":
        raise HTTPException(
            status_code=400,
            detail="CSV connections require file upload — use POST /connections/csv instead",
        )

    adapter = get_adapter(payload.source_type, payload.config)
    if not adapter.test_connection():
        raise HTTPException(status_code=400, detail="Could not connect with the provided config")

    connection = Connection(
        name=payload.name,
        source_type=payload.source_type,
        encrypted_config=encrypt_config(payload.config),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.post("/csv", response_model=ConnectionOut)
def create_csv_connection(
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="At least one CSV file is required")

    connection_id = str(uuid.uuid4())
    upload_dir = os.path.join(settings.upload_dir, connection_id)
    os.makedirs(upload_dir, exist_ok=True)

    file_entries = []
    for upload in files:
        if not upload.filename.lower().endswith(".csv"):
            raise HTTPException(status_code=400, detail=f"{upload.filename} is not a CSV file")
        table_name = os.path.splitext(upload.filename)[0]
        dest_path = os.path.join(upload_dir, upload.filename)
        with open(dest_path, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        file_entries.append({"table_name": table_name, "file_path": dest_path})

    config = {"files": file_entries}
    adapter = get_adapter("csv", config)
    if not adapter.test_connection():
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Uploaded CSV(s) could not be read")

    connection = Connection(
        id=connection_id,
        name=name,
        source_type="csv",
        encrypted_config=encrypt_config(config),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


@router.get("", response_model=list[ConnectionOut])
def list_connections(db: Session = Depends(get_db)):
    return db.query(Connection).filter(Connection.is_active == True).all()  # noqa: E712


@router.get("/{connection_id}", response_model=ConnectionOut)
def get_connection(connection_id: str, db: Session = Depends(get_db)):
    connection = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_connection(connection_id: str, db: Session = Depends(get_db)):
    connection = _get_connection_or_404(connection_id, db)
    config = decrypt_config(connection.encrypted_config)
    adapter = get_adapter(connection.source_type, config)

    if adapter.test_connection():
        return ConnectionTestResult(success=True, message="Connection is healthy")
    return ConnectionTestResult(success=False, message="Connection failed")


@router.get("/{connection_id}/tables", response_model=TableListOut)
def list_tables(connection_id: str, db: Session = Depends(get_db)):
    connection = _get_connection_or_404(connection_id, db)
    config = decrypt_config(connection.encrypted_config)
    adapter = get_adapter(connection.source_type, config)

    try:
        tables = adapter.list_tables()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list tables: {exc}")
    return TableListOut(tables=tables)


@router.delete("/{connection_id}")
def delete_connection(connection_id: str, db: Session = Depends(get_db)):
    connection = _get_connection_or_404(connection_id, db)
    connection.is_active = False
    db.commit()
    return {"status": "deactivated"}


def _get_connection_or_404(connection_id: str, db: Session) -> Connection:
    connection = db.get(Connection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection

@router.post("/{connection_id}/tables/select", response_model=TableSelectionOut)
def select_tables(connection_id: str, payload: TableSelectionIn, db: Session = Depends(get_db)):
    connection = _get_connection_or_404(connection_id, db)
    config = decrypt_config(connection.encrypted_config)
    adapter = get_adapter(connection.source_type, config)

    valid_tables = set(adapter.list_tables())
    invalid = set(payload.table_names) - valid_tables
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown tables: {sorted(invalid)}")

    db.query(TableSelection).filter(TableSelection.connection_id == connection_id).delete()
    for name in payload.table_names:
        db.add(TableSelection(connection_id=connection_id, table_name=name, is_selected=True))
    db.commit()

    # DDL is deterministic (unlike semantic descriptions) — safe to index automatically on selection,
    # no separate "draft" step needed like the semantic layer has.
    schema = adapter.get_schema(payload.table_names)
    index_ddl(connection_id, schema)

    return TableSelectionOut(table_names=payload.table_names)


@router.get("/{connection_id}/tables/selected", response_model=TableSelectionOut)
def get_selected_tables(connection_id: str, db: Session = Depends(get_db)):
    rows = db.query(TableSelection).filter(
        TableSelection.connection_id == connection_id, TableSelection.is_selected == True  # noqa: E712
    ).all()
    return TableSelectionOut(table_names=[r.table_name for r in rows])
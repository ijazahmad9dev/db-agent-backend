import os
import shutil
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

from db_agent.core.config import get_settings
from db_agent.db.session import get_db
from db_agent.db.models import Connection, TableSelection, User
from db_agent.security.credentials import encrypt_config, decrypt_config
from db_agent.adapters.factory import get_adapter
from db_agent.schemas.connection import (
    ConnectionCreate, ConnectionOut, ConnectionTestResult, GSheetsConnectionCreate, TableListOut,
    TableSelectionIn, TableSelectionOut,
)
from db_agent.introspection.ddl_vectorstore import index_ddl, delete_connection_ddl
from db_agent.semantic.loader import delete_semantic_layer
from db_agent.semantic.vectorstore import delete_connection_vectors
from db_agent.auth.dependencies import get_current_user
from db_agent.adapters.config_resolver import resolve_adapter_config, GoogleSheetsNotConnectedError

from db_agent.adapters.gsheets_adapter import extract_spreadsheet_id

router = APIRouter(prefix="/connections")
settings = get_settings()


def _get_owned_connection_or_404(connection_id: str, current_user: User, db: Session) -> Connection:
    connection = (
        db.query(Connection)
        .filter(Connection.id == connection_id, Connection.user_id == current_user.id)
        .first()
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Connection not found")
    return connection


@router.post("", response_model=ConnectionOut)
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload.source_type == "csv":
        raise HTTPException(status_code=400, detail="CSV connections require file upload — use POST /connections/csv instead")

    adapter = get_adapter(payload.source_type, payload.config)
    if not adapter.test_connection():
        raise HTTPException(status_code=400, detail="Could not connect with the provided config")

    connection = Connection(
        user_id=current_user.id,
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
    current_user: User = Depends(get_current_user),
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
        _normalize_to_utf8(dest_path)
        file_entries.append({"table_name": table_name, "file_path": dest_path})

    config = {"files": file_entries}
    adapter = get_adapter("csv", config)
    if not adapter.test_connection():
        shutil.rmtree(upload_dir, ignore_errors=True)
        raise HTTPException(status_code=400, detail="Uploaded CSV(s) could not be read")

    connection = Connection(
        id=connection_id,
        user_id=current_user.id,
        name=name,
        source_type="csv",
        encrypted_config=encrypt_config(config),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection


def _normalize_to_utf8(path: str) -> None:
    from charset_normalizer import from_path
    result = from_path(path).best()
    if result is None or result.encoding is None:
        return
    if result.encoding.lower() in ("utf-8", "ascii"):
        return
    text = str(result)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@router.get("", response_model=list[ConnectionOut])
def list_connections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return db.query(Connection).filter(
        Connection.user_id == current_user.id, Connection.is_active == True  # noqa: E712
    ).all()


@router.get("/{connection_id}", response_model=ConnectionOut)
def get_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _get_owned_connection_or_404(connection_id, current_user, db)

@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
def test_connection(
    connection_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection_or_404(connection_id, current_user, db)
    try:
        config = resolve_adapter_config(connection, current_user)
    except GoogleSheetsNotConnectedError as e:
        raise HTTPException(status_code=428, detail=str(e))
    adapter = get_adapter(connection.source_type, config)
    if adapter.test_connection():
        return ConnectionTestResult(success=True, message="Connection is healthy")
    return ConnectionTestResult(success=False, message="Connection failed")


@router.get("/{connection_id}/tables", response_model=TableListOut)
def list_tables(
    connection_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection_or_404(connection_id, current_user, db)
    try:
        config = resolve_adapter_config(connection, current_user)
    except GoogleSheetsNotConnectedError as e:
        raise HTTPException(status_code=428, detail=str(e))
    adapter = get_adapter(connection.source_type, config)
    try:
        tables = adapter.list_tables()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Failed to list tables: {exc}")
    return TableListOut(tables=tables)


@router.post("/{connection_id}/tables/select", response_model=TableSelectionOut)
def select_tables(
    connection_id: str, payload: TableSelectionIn,
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection_or_404(connection_id, current_user, db)
    try:
        config = resolve_adapter_config(connection, current_user)
    except GoogleSheetsNotConnectedError as e:
        raise HTTPException(status_code=428, detail=str(e))
    adapter = get_adapter(connection.source_type, config)

    valid_tables = set(adapter.list_tables())
    invalid = set(payload.table_names) - valid_tables
    if invalid:
        raise HTTPException(status_code=400, detail=f"Unknown tables: {sorted(invalid)}")

    db.query(TableSelection).filter(TableSelection.connection_id == connection_id).delete()
    for name in payload.table_names:
        db.add(TableSelection(connection_id=connection_id, table_name=name, is_selected=True))
    db.commit()

    schema = adapter.get_schema(payload.table_names)
    index_ddl(connection_id, schema)
    return TableSelectionOut(table_names=payload.table_names)


@router.get("/{connection_id}/tables/selected", response_model=TableSelectionOut)
def get_selected_tables(
    connection_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _get_owned_connection_or_404(connection_id, current_user, db)
    rows = db.query(TableSelection).filter(
        TableSelection.connection_id == connection_id, TableSelection.is_selected == True  # noqa: E712
    ).all()
    return TableSelectionOut(table_names=[r.table_name for r in rows])


@router.delete("/{connection_id}")
def delete_connection(
    connection_id: str,
    hard: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = _get_owned_connection_or_404(connection_id, current_user, db)

    if not hard:
        connection.is_active = False
        db.commit()
        return {"status": "deactivated"}

    upload_dir = os.path.join(settings.upload_dir, connection_id)
    shutil.rmtree(upload_dir, ignore_errors=True)
    delete_semantic_layer(connection_id)
    delete_connection_vectors(connection_id)
    delete_connection_ddl(connection_id)

    db.delete(connection)
    db.commit()
    return {"status": "deleted"}


@router.post("/gsheets", response_model=ConnectionOut)
def create_gsheets_connection(
    payload: GSheetsConnectionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    spreadsheet_id = extract_spreadsheet_id(payload.sheet_url)

    public_config = {"spreadsheet_id": spreadsheet_id, "auth_mode": "public", "api_key": settings.google_api_key}
    public_adapter = get_adapter("gsheets", public_config)
    if public_adapter.test_connection():
        connection = Connection(
            user_id=current_user.id, name=payload.name, source_type="gsheets",
            encrypted_config=encrypt_config(public_config),
        )
        db.add(connection)
        db.commit()
        db.refresh(connection)
        return connection

    if not current_user.google_sheets_scope_granted:
        # Only reachable for sessions from before this change. New logins always
        # carry Sheets scope, so this is a one-time re-auth prompt, not the normal path.
        raise HTTPException(
            status_code=428,
            detail="Sign out and sign back in with Google to grant Sheets access, then try again.",
        )

    token_data = decrypt_config(current_user.google_refresh_token_encrypted)
    oauth_config = {
        "spreadsheet_id": spreadsheet_id, "auth_mode": "oauth",
        "refresh_token": token_data["refresh_token"],
        "client_id": settings.google_oauth_client_id, "client_secret": settings.google_oauth_client_secret,
    }
    oauth_adapter = get_adapter("gsheets", oauth_config)
    if not oauth_adapter.test_connection():
        raise HTTPException(status_code=403, detail="This sheet isn't shared with your Google account.")

    stored_config = {"spreadsheet_id": spreadsheet_id, "auth_mode": "oauth"}
    connection = Connection(
        user_id=current_user.id, name=payload.name, source_type="gsheets",
        encrypted_config=encrypt_config(stored_config),
    )
    db.add(connection)
    db.commit()
    db.refresh(connection)
    return connection
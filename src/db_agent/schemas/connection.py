from pydantic import BaseModel, ConfigDict


class ConnectionCreate(BaseModel):
    name: str
    source_type: str  # "postgres" | "mysql" | "csv" | "gsheets"
    config: dict       # raw config — host/user/password, or file_path, or spreadsheet_id etc.


class ConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    source_type: str
    is_active: bool
    # deliberately no `config` or `encrypted_config` field here


class ConnectionTestResult(BaseModel):
    success: bool
    message: str


class TableListOut(BaseModel):
    tables: list[str]

class TableSelectionIn(BaseModel):
    table_names: list[str]


class TableSelectionOut(BaseModel):
    table_names: list[str]

class GSheetsConnectionCreate(BaseModel):
    name: str
    sheet_url: str
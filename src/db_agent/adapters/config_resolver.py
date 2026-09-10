from db_agent.db.models import Connection, User
from db_agent.security.credentials import decrypt_config
from db_agent.core.config import get_settings

settings = get_settings()


class GoogleSheetsNotConnectedError(Exception):
    """Raised when a connection needs the owner's Sheets OAuth grant, but they haven't completed it."""


def resolve_adapter_config(connection: Connection, owner: User) -> dict:
    config = decrypt_config(connection.encrypted_config)
    if connection.source_type == "gsheets" and config.get("auth_mode") == "oauth":
        if not owner.google_refresh_token_encrypted:
            raise GoogleSheetsNotConnectedError(
                "Google Sheets access not connected for this account"
            )
        token_data = decrypt_config(owner.google_refresh_token_encrypted)
        config["refresh_token"] = token_data["refresh_token"]
        config["client_id"] = settings.google_oauth_client_id
        config["client_secret"] = settings.google_oauth_client_secret
    return config
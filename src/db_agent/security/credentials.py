import json
from cryptography.fernet import Fernet

from db_agent.core.config import get_settings

settings = get_settings()
_fernet = Fernet(settings.credential_encryption_key.encode())


def encrypt_config(config: dict) -> str:
    payload = json.dumps(config).encode()
    return _fernet.encrypt(payload).decode()


def decrypt_config(encrypted: str) -> dict:
    payload = _fernet.decrypt(encrypted.encode())
    return json.loads(payload)
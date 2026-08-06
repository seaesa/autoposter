from cryptography.fernet import Fernet

from app.core.config import settings


def _fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode("utf-8"))


def encrypt_token(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")

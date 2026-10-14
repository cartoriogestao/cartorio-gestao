from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass

PBKDF2_ITERATIONS = 310_000


@dataclass(frozen=True)
class PasswordRecord:
    salt_hex: str
    hash_hex: str


def hash_password(password: str) -> PasswordRecord:
    if not password:
        raise ValueError("A senha não pode ficar em branco.")
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return PasswordRecord(salt.hex(), digest.hex())


def verify_password(password: str, salt_hex: str, hash_hex: str) -> bool:
    try:
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return hmac.compare_digest(digest, expected)


def validate_password_strength(
    password: str,
    min_length: int = 6,
    require_upper: bool = False,
    require_lower: bool = False,
    require_digit: bool = False,
) -> tuple[bool, str]:
    min_length = max(1, int(min_length or 1))
    if len(password) < min_length:
        return False, f"A senha deve ter pelo menos {min_length} caracteres."
    if require_upper and not any(c.isupper() for c in password):
        return False, "A senha deve conter pelo menos uma letra maiúscula."
    if require_lower and not any(c.islower() for c in password):
        return False, "A senha deve conter pelo menos uma letra minúscula."
    if require_digit and not any(c.isdigit() for c in password):
        return False, "A senha deve conter pelo menos um número."
    return True, "OK"


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def new_secret_key() -> str:
    return secrets.token_hex(32)

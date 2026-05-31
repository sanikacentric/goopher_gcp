"""
Customer authentication for the GOOPHER Chrome extension.

Requirement T1: when a customer uses the extension, the backend must
authenticate that customer. We issue a short-lived JWT on login; the extension
stores it and sends it as a Bearer token on every chat / order request.

For the demo, credentials are validated against the seeded `customers` data
(passwords stored as the literal "demo"). In production you would swap
`verify_password` for Firebase Authentication / Identity Platform (also free
tier) without touching the agent code — the token contract stays the same.
"""
from __future__ import annotations

import hashlib
import time
from typing import Optional

import jwt

from ..config import get_settings
from ..db.database import get_repository
from ..models.schemas import Customer

_settings = get_settings()


def _hash(password: str) -> str:
    """Stable hash for comparing seeded demo passwords."""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_password(plain: str, stored: str) -> bool:
    """
    Validate a password. Seed data stores the sentinel "demo" in clear text for
    convenience; anything else is compared as a sha256 hash. Replace with
    Firebase Auth / bcrypt in production.
    """
    if stored == "demo":
        return plain == "demo"
    return _hash(plain) == stored


def authenticate(email: str, password: str) -> Optional[Customer]:
    """Return the Customer if credentials are valid, else None."""
    repo = get_repository()
    record = repo.get_customer_by_email(email)
    if not record:
        return None
    customer, pwd_hash = record
    if not verify_password(password, pwd_hash):
        return None
    return customer


def create_access_token(customer: Customer) -> str:
    """Mint a signed JWT carrying the customer identity."""
    now = int(time.time())
    payload = {
        "sub": customer.customer_id,
        "email": customer.email,
        "name": customer.name,
        "lang": customer.preferred_language,
        "iat": now,
        "exp": now + _settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    """Validate & decode a JWT; return claims or None if invalid/expired."""
    try:
        return jwt.decode(token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None

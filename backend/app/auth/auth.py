"""
Customer authentication for the GOOPHER Chrome extension.

Requirement T1: when a customer uses the extension, the backend must
authenticate that customer. We issue a short-lived JWT on login; the extension
stores it and sends it as a Bearer token on every chat / order request.

SINGLE-USER LOCKDOWN: the LLM endpoint is private. A login is accepted ONLY if
BOTH hold:
  1. the email is on the allowlist (settings.allowed_emails), AND
  2. the password equals the master password (settings.master_password),
     compared in constant time.
The master password MUST be supplied via env / Secret Manager. If it is left at
its sentinel value, the service is FAIL-CLOSED — every login is rejected — so a
misconfiguration can never leave the endpoint open. The seeded per-customer
demo passwords are intentionally ignored.
"""
from __future__ import annotations

import hmac
import time
from typing import Optional

import jwt

from ..config import get_settings
from ..db.database import get_repository
from ..models.schemas import Customer

_settings = get_settings()

# Sentinel that means "no real password configured" -> reject all logins.
_UNSET_PASSWORD = "CHANGE_ME_set_via_env"


def _allowed_emails() -> set[str]:
    """Lower-cased set of emails permitted to authenticate."""
    return {e.strip().lower() for e in _settings.allowed_emails.split(",") if e.strip()}


def verify_password(plain: str) -> bool:
    """
    Validate the master password in constant time.

    Fail-closed: if the master password isn't configured (still the sentinel),
    or the supplied password is empty, authentication is refused.
    """
    expected = _settings.master_password
    if not expected or expected == _UNSET_PASSWORD:
        return False
    if not plain:
        return False
    return hmac.compare_digest(plain, expected)


def authenticate(email: str, password: str) -> Optional[Customer]:
    """
    Return the Customer only if the email is allowlisted AND the master password
    is correct. Returns None (login rejected) otherwise.
    """
    email_norm = (email or "").strip().lower()

    # 1) Allowlist check — only approved email(s) may even attempt login.
    if email_norm not in _allowed_emails():
        return None

    # 2) Master password check (constant-time, fail-closed).
    if not verify_password(password):
        return None

    # 3) Load the customer record for identity/profile (must exist in the DB).
    repo = get_repository()
    record = repo.get_customer_by_email(email_norm)
    if not record:
        return None
    customer, _ = record
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

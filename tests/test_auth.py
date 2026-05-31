"""Unit tests for customer authentication (Req T1)."""
from backend.app.auth.auth import (
    authenticate,
    create_access_token,
    decode_token,
)


def test_authenticate_valid():
    cust = authenticate("demo@goopher.app", "demo")
    assert cust is not None
    assert cust.customer_id == "CUST-1001"


def test_authenticate_invalid_password():
    assert authenticate("demo@goopher.app", "wrong") is None


def test_authenticate_unknown_user():
    assert authenticate("nobody@example.com", "demo") is None


def test_token_roundtrip():
    cust = authenticate("demo@goopher.app", "demo")
    token = create_access_token(cust)
    claims = decode_token(token)
    assert claims["sub"] == "CUST-1001"
    assert claims["email"] == "demo@goopher.app"


def test_decode_bad_token():
    assert decode_token("not.a.valid.token") is None

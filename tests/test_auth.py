"""
Unit tests for the single-user-lockdown authentication (Req T1).

conftest sets ALLOWED_EMAILS=demo@goopher.app and MASTER_PASSWORD=
test-master-password, so only that email + that password may authenticate.
"""
from backend.app.auth.auth import (
    authenticate,
    create_access_token,
    decode_token,
)

GOOD_EMAIL = "demo@goopher.app"
GOOD_PASSWORD = "test-master-password"


def test_authenticate_valid():
    cust = authenticate(GOOD_EMAIL, GOOD_PASSWORD)
    assert cust is not None
    assert cust.customer_id == "CUST-1001"


def test_authenticate_email_is_case_insensitive():
    # Allowlist match should not depend on casing/whitespace.
    assert authenticate("  Demo@Goopher.App  ", GOOD_PASSWORD) is not None


def test_authenticate_wrong_password_rejected():
    assert authenticate(GOOD_EMAIL, "wrong") is None


def test_authenticate_old_demo_password_rejected():
    # The seeded "demo" password must NOT work anymore.
    assert authenticate(GOOD_EMAIL, "demo") is None


def test_authenticate_non_allowlisted_email_rejected():
    # Even with the correct master password, a non-allowlisted email is denied.
    assert authenticate("maria@example.com", GOOD_PASSWORD) is None
    assert authenticate("attacker@evil.com", GOOD_PASSWORD) is None


def test_authenticate_empty_password_rejected():
    assert authenticate(GOOD_EMAIL, "") is None


def test_token_roundtrip():
    cust = authenticate(GOOD_EMAIL, GOOD_PASSWORD)
    token = create_access_token(cust)
    claims = decode_token(token)
    assert claims["sub"] == "CUST-1001"
    assert claims["email"] == GOOD_EMAIL


def test_decode_bad_token():
    assert decode_token("not.a.valid.token") is None

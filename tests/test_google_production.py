"""Focused tests for ProductionGoogleVerifier (Phase 1, Google Sign-In).

No DB, no network: the JWKS client is stubbed; RSA round-trip tests need the
`cryptography` package and skip cleanly where it is absent.
"""
import types
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app import config as config_module
from app.services import google as google_svc

AUD = "test-client-id.apps.googleusercontent.com"
ISS = "https://accounts.google.com"


@pytest.fixture()
def verifier(monkeypatch):
    monkeypatch.setattr(config_module.settings, "GOOGLE_CLIENT_ID", AUD)
    return google_svc.ProductionGoogleVerifier()


def _stub_jwks(monkeypatch, key):
    fake = types.SimpleNamespace(
        get_signing_key_from_jwt=lambda token: types.SimpleNamespace(key=key)
    )
    monkeypatch.setattr(google_svc, "_jwks_client", fake)


def test_malformed_token_is_401(verifier):
    with pytest.raises(HTTPException) as e:
        verifier.verify("not-a-jwt")
    assert e.value.status_code == 401


def test_empty_token_is_401(verifier):
    for bad in ("", None):
        with pytest.raises(HTTPException) as e:
            verifier.verify(bad)
        assert e.value.status_code == 401


def test_decode_wiring_audience_issuer_algorithm(verifier, monkeypatch):
    """The verifier must pass aud/iss/RS256/required-claims to jwt.decode."""
    _stub_jwks(monkeypatch, key="unused")
    seen = {}

    def fake_decode(token, key, algorithms=None, audience=None, issuer=None, options=None):
        seen.update(algorithms=algorithms, audience=audience, issuer=issuer, options=options)
        return {"sub": "google-sub-123"}

    monkeypatch.setattr(jwt, "decode", fake_decode)
    assert verifier.verify("header.payload.sig") == "google-sub-123"
    assert seen["algorithms"] == ["RS256"]
    assert seen["audience"] == AUD
    assert set(seen["issuer"]) == {"accounts.google.com", "https://accounts.google.com"}
    for claim in ("exp", "iss", "aud", "sub"):
        assert claim in seen["options"]["require"]


def _rsa_keypair():
    crypto = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.rsa")
    return crypto.generate_private_key(public_exponent=65537, key_size=2048)


def _rsa_token(key, **claims):
    now = datetime.now(timezone.utc)
    payload = {"iss": ISS, "aud": AUD, "sub": "google-sub-1",
               "exp": now + timedelta(minutes=5), "iat": now}
    payload.update(claims)
    return jwt.encode(payload, key, algorithm="RS256", headers={"kid": "t1"})


def test_rsa_valid_token_returns_sub(verifier, monkeypatch):
    key = _rsa_keypair()
    _stub_jwks(monkeypatch, key.public_key())
    assert verifier.verify(_rsa_token(key)) == "google-sub-1"


def test_rsa_expired_is_401(verifier, monkeypatch):
    key = _rsa_keypair()
    _stub_jwks(monkeypatch, key.public_key())
    token = _rsa_token(key, exp=datetime.now(timezone.utc) - timedelta(minutes=5))
    with pytest.raises(HTTPException) as e:
        verifier.verify(token)
    assert e.value.status_code == 401


def test_rsa_wrong_audience_is_401(verifier, monkeypatch):
    key = _rsa_keypair()
    _stub_jwks(monkeypatch, key.public_key())
    with pytest.raises(HTTPException) as e:
        verifier.verify(_rsa_token(key, aud="other-client"))
    assert e.value.status_code == 401


def test_rsa_wrong_issuer_is_401(verifier, monkeypatch):
    key = _rsa_keypair()
    _stub_jwks(monkeypatch, key.public_key())
    with pytest.raises(HTTPException) as e:
        verifier.verify(_rsa_token(key, iss="https://evil.example.com"))
    assert e.value.status_code == 401


def test_rsa_tampered_signature_is_401(verifier, monkeypatch):
    key = _rsa_keypair()
    _stub_jwks(monkeypatch, key.public_key())
    other = _rsa_keypair()
    _stub_jwks(monkeypatch, other.public_key())
    with pytest.raises(HTTPException) as e:
        verifier.verify(_rsa_token(key))
    assert e.value.status_code == 401

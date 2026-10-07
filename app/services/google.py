"""RESTAMP Phase 4 — Google identity verification abstraction.

Approved rules:
- Google identities live ONLY in auth_identities (never duplicated to users).
- An unknown Google identity must NOT auto-create a user (404, no side effects).
- A known identity (provider='google' row exists) may authenticate/link.

Real verification requires RESTAMP_GOOGLE_CLIENT_ID plus a production verifier
(not configured in this phase). DevGoogleVerifier accepts ONLY synthetic
"dev:<subject>" tokens when RESTAMP_GOOGLE_DEV_MODE=1, so tests and local
development can exercise the flow honestly without pretending real Google auth works.
"""
from fastapi import HTTPException, status

from ..config import settings


class GoogleVerifier:
    def verify(self, id_token: str) -> str:
        """Return the Google subject (stable provider_identifier) for a valid token."""
        raise NotImplementedError


class DevGoogleVerifier(GoogleVerifier):
    def verify(self, id_token: str) -> str:
        if not settings.GOOGLE_DEV_MODE:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail="Google authentication is not configured",
            )
        if not id_token.startswith("dev:") or len(id_token) <= 4:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential"
            )
        return id_token[4:]


class ProductionGoogleVerifier(GoogleVerifier):
    """Placeholder for a real Google ID-token verifier (needs client ID + JWKS).

    Deliberately unimplemented: wiring a fake "always valid" verifier would be
    dishonest. Connect a real provider here in a later phase.
    """

    def verify(self, id_token: str) -> str:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google authentication is not configured",
        )


def get_verifier() -> GoogleVerifier:
    if settings.GOOGLE_CLIENT_ID:
        return ProductionGoogleVerifier()
    return DevGoogleVerifier()

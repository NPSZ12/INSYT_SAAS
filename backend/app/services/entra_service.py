import os
from functools import lru_cache
from typing import Any, Dict

import requests
from fastapi import HTTPException
from jose import JWTError, jwk, jwt


ENTRA_DISCOVERY_TIMEOUT_SECONDS = 15
ENTRA_GRAPH_TIMEOUT_SECONDS = 30


def _required_env(name: str) -> str:
    value = str(os.getenv(name) or "").strip()

    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}"
        )

    return value


def _entra_tenant_id() -> str:
    return _required_env("ENTRA_TENANT_ID")


def _entra_client_id() -> str:
    return _required_env("ENTRA_CLIENT_ID")


@lru_cache(maxsize=1)
def get_entra_openid_configuration() -> Dict[str, Any]:
    tenant_id = _entra_tenant_id()

    response = requests.get(
        (
            "https://login.microsoftonline.com/"
            f"{tenant_id}/v2.0/.well-known/openid-configuration"
        ),
        timeout=ENTRA_DISCOVERY_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    data = response.json()

    issuer = str(data.get("issuer") or "").strip()
    jwks_uri = str(data.get("jwks_uri") or "").strip()

    if not issuer or not jwks_uri:
        raise RuntimeError(
            "Microsoft Entra OpenID configuration is incomplete."
        )

    return data


@lru_cache(maxsize=1)
def get_entra_jwks() -> Dict[str, Any]:
    configuration = get_entra_openid_configuration()
    jwks_uri = str(configuration["jwks_uri"])

    response = requests.get(
        jwks_uri,
        timeout=ENTRA_DISCOVERY_TIMEOUT_SECONDS,
    )

    response.raise_for_status()

    data = response.json()

    keys = data.get("keys")

    if not isinstance(keys, list) or not keys:
        raise RuntimeError(
            "Microsoft Entra signing keys are unavailable."
        )

    return data


def _find_signing_key(
    token: str,
) -> Dict[str, Any]:
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid Microsoft Entra identity token.",
        ) from error

    key_id = str(header.get("kid") or "").strip()
    algorithm = str(header.get("alg") or "").strip()

    if not key_id:
        raise HTTPException(
            status_code=401,
            detail="Microsoft Entra token is missing a signing key identifier.",
        )

    if algorithm != "RS256":
        raise HTTPException(
            status_code=401,
            detail="Unsupported Microsoft Entra token signing algorithm.",
        )

    keys = get_entra_jwks().get("keys") or []

    for candidate in keys:
        if str(candidate.get("kid") or "") == key_id:
            return candidate

    # Microsoft rotates signing keys. Refresh once before failing.
    get_entra_jwks.cache_clear()

    keys = get_entra_jwks().get("keys") or []

    for candidate in keys:
        if str(candidate.get("kid") or "") == key_id:
            return candidate

    raise HTTPException(
        status_code=401,
        detail="Unable to locate Microsoft Entra token signing key.",
    )


def verify_entra_id_token(
    token: str,
) -> Dict[str, Any]:
    token = str(token or "").strip()

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Missing Microsoft Entra identity token.",
        )

    configuration = get_entra_openid_configuration()
    issuer = str(configuration["issuer"])
    client_id = _entra_client_id()
    tenant_id = _entra_tenant_id()

    signing_key_data = _find_signing_key(token)

    try:
        signing_key = jwk.construct(
            signing_key_data,
            algorithm="RS256",
        )

        claims = jwt.decode(
            token,
            signing_key.to_pem(),
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer,
            options={
                "verify_aud": True,
                "verify_exp": True,
                "verify_iss": True,
                "verify_signature": True,
            },
        )
    except JWTError as error:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired Microsoft Entra identity token.",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=401,
            detail="Unable to validate Microsoft Entra identity token.",
        ) from error

    token_tenant_id = str(claims.get("tid") or "").strip()

    if not token_tenant_id:
        raise HTTPException(
            status_code=401,
            detail="Microsoft Entra token is missing tenant identity.",
        )

    if token_tenant_id.lower() != tenant_id.lower():
        raise HTTPException(
            status_code=401,
            detail="Microsoft Entra token was issued by an unauthorized tenant.",
        )

    subject = str(
        claims.get("oid")
        or claims.get("sub")
        or ""
    ).strip()

    if not subject:
        raise HTTPException(
            status_code=401,
            detail="Microsoft Entra token is missing user identity.",
        )

    return claims


def extract_verified_entra_email(
    claims: Dict[str, Any],
) -> str:
    email = str(
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("upn")
        or ""
    ).strip().lower()

    if not email:
        emails = claims.get("emails")

        if isinstance(emails, list) and emails:
            email = str(emails[0] or "").strip().lower()

    if not email:
        raise HTTPException(
            status_code=401,
            detail="Verified Microsoft Entra identity does not contain an email address.",
        )

    return email


def get_graph_token():
    tenant_id = os.getenv("ENTRA_TENANT_ID")
    client_id = os.getenv("ENTRA_CLIENT_ID")
    client_secret = os.getenv("ENTRA_CLIENT_SECRET")

    response = requests.post(
        f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://graph.microsoft.com/.default",
            "grant_type": "client_credentials",
        },
        timeout=30,
    )

    response.raise_for_status()

    return response.json()["access_token"]


def invite_external_user(
    email: str,
    display_name: str,
):
    token = get_graph_token()

    response = requests.post(
        "https://graph.microsoft.com/v1.0/invitations",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={
            "invitedUserEmailAddress": email,
            "inviteRedirectUrl": "https://www.insyt360.com/login",
            "invitedUserDisplayName": display_name,
            "sendInvitationMessage": True,
        },
        timeout=30,
    )

    if response.status_code in [200, 201]:
        return response.json()

    return None
import os
import requests


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
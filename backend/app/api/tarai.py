"""Authenticated, read-only TARai Discovery privilege suggestions."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from app.database.connection import get_db
from app.services.security import get_current_user
from app.services.authorization import (
    PERMISSION_REVIEW,
    PERMISSION_MANAGE_PROTOCOL,
    require_permission,
    require_scoped_project_access,
)
from app.services.ai.tarai_protocol import (
    TARaiProtocolError,
    resolve_privilege_fields,
)
from app.services.ai.tarai_analyzer import (
    analyze_privilege,
    tarai_enabled,
    TARaiDisabledError,
    TARaiConfigurationError,
    TARaiResponseError,
)
from app.services.ai.tarai_criteria import (
    TARaiCriteriaApprovalError,
)
from app.services.ai.tarai_approval import (
    approve_criteria,
    verify_approved_criteria,
)
from app.api.review import load_review_document_by_doc_id
from app.api.workspace_protocols import (
    get_workspace_protocol,
    get_live_source_container_client,
    build_project_path,
)

router = APIRouter(
    prefix="/api/discovery/tarai",
    tags=["tarai"],
)

SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")

CRITERIA_FILENAME = "TARai_Privilege_Criteria.txt"


class SuggestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: str = Field(min_length=1, max_length=150)
    project: str = Field(min_length=1, max_length=150)
    doc_id: str = Field(min_length=1, max_length=250)


def require_valid_identifiers(payload: SuggestRequest) -> None:
    for value in (
        payload.client,
        payload.project,
        payload.doc_id,
    ):
        if not SAFE_IDENTIFIER.fullmatch(value):
            raise HTTPException(
                status_code=400,
                detail="Invalid Discovery document identifier.",
            )


def read_project_criteria_bytes(
    client: str,
    project: str,
) -> bytes:
    """Read the existing project's exact criteria bytes."""

    path = build_project_path(
        "discovery",
        client,
        project,
        "source/protocol",
        CRITERIA_FILENAME,
    )

    container = get_live_source_container_client("discovery")
    blob = container.get_blob_client(path)

    if not blob.exists():
        raise HTTPException(
            status_code=409,
            detail="Project privilege criteria are missing.",
        )

    properties = blob.get_blob_properties()

    if properties.size > 10000:
        raise HTTPException(
            status_code=409,
            detail="Project privilege criteria exceed the size limit.",
        )

    content = blob.download_blob().readall()

    if not isinstance(content, bytes) or not content or len(content) > 10000:
        raise HTTPException(
            status_code=409,
            detail="Project privilege criteria are invalid.",
        )

    return content


def load_approved_privilege_criteria(
    client: str,
    project: str,
    db,
) -> str:
    """Fail closed unless the exact file has trusted audit approval."""

    content = read_project_criteria_bytes(client, project)

    try:
        return verify_approved_criteria(
            db=db,
            client=client,
            project=project,
            criteria_bytes=content,
        )
    except TARaiCriteriaApprovalError as exc:
        raise HTTPException(
            status_code=409,
            detail="TARai privilege criteria lack valid approval.",
        ) from exc


def require_exact_document_identity(
    document: dict,
    client: str,
    project: str,
    requested_doc_id: str,
) -> None:
    """Fail closed before AI when identity or provenance is uncertain."""

    if document.get("workspace") != "discovery":
        raise HTTPException(
            status_code=409,
            detail="Document workspace identity mismatch.",
        )

    if document.get("project_id") != project:
        raise HTTPException(
            status_code=409,
            detail="Document project identity mismatch.",
        )

    if document.get("doc_id") != requested_doc_id:
        raise HTTPException(
            status_code=409,
            detail="Document ID does not exactly match the request.",
        )

    if document.get("native_storage_source") != "live_source":
        raise HTTPException(
            status_code=409,
            detail="Document provenance is not supported by TARai.",
        )

    base = build_project_path(
        "discovery",
        client,
        project,
    ).rstrip("/")

    native_prefix = base + "/source/native/"
    text_prefix = base + "/source/text/"

    native_blob = str(document.get("native_blob") or "")
    text_blob = str(document.get("text_blob") or "")

    if not native_blob.startswith(native_prefix):
        raise HTTPException(
            status_code=409,
            detail="Document native storage identity mismatch.",
        )

    if not text_blob.startswith(text_prefix):
        raise HTTPException(
            status_code=409,
            detail="Document text storage identity mismatch.",
        )

class ApproveCriteriaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client: str = Field(min_length=1, max_length=150)
    project: str = Field(min_length=1, max_length=150)


@router.post("/privilege/criteria/approve")
def approve_privilege_criteria(
    payload: ApproveCriteriaRequest,
    request: Request,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    for value in (payload.client, payload.project):
        if not SAFE_IDENTIFIER.fullmatch(value):
            raise HTTPException(
                status_code=400,
                detail="Invalid Discovery project identifier.",
            )

    require_scoped_project_access(
        current_user,
        "discovery",
        payload.client,
        payload.project,
    )

    require_permission(
        current_user,
        PERMISSION_MANAGE_PROTOCOL,
    )

    criteria_bytes = read_project_criteria_bytes(
        payload.client,
        payload.project,
    )

    try:
        digest = approve_criteria(
            db=db,
            actor=current_user,
            client=payload.client,
            project=payload.project,
            criteria_bytes=criteria_bytes,
            request=request,
        )
    except TARaiCriteriaApprovalError as exc:
        raise HTTPException(
            status_code=409,
            detail="Project privilege criteria cannot be approved.",
        ) from exc

    return {
        "workspace": "discovery",
        "client": payload.client,
        "project": payload.project,
        "status": "approved",
        "sha256": digest,
    }


@router.post("/privilege/suggest")
def suggest_privilege(
    payload: SuggestRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
):
    require_valid_identifiers(payload)

    # Authorization must happen before any document or protocol read.
    require_scoped_project_access(
        current_user,
        "discovery",
        payload.client,
        payload.project,
    )

    require_permission(current_user, PERMISSION_REVIEW)

    if not tarai_enabled():
        raise HTTPException(
            status_code=503,
            detail="TARai AI suggestions are not enabled.",
        )

    protocol = get_workspace_protocol(
        workspace="discovery",
        project_id=payload.project,
        client=payload.client,
        current_user=current_user,
    )

    if not protocol.get("has_protocol"):
        raise HTTPException(
            status_code=409,
            detail="Discovery protocol is missing.",
        )

    fields = (
        protocol.get("protocol", {}).get("fields")
        or protocol.get("fields")
        or []
    )

    try:
        mapping = resolve_privilege_fields(fields)
    except TARaiProtocolError:
        raise HTTPException(
            status_code=409,
            detail="Discovery privilege coding configuration is invalid.",
        )

    criteria = load_approved_privilege_criteria(
        payload.client,
        payload.project,
        db,
    )

    # No browser-controlled blob path is accepted.
    document = load_review_document_by_doc_id(
        workspace="discovery",
        client=payload.client,
        project=payload.project,
        doc_id=payload.doc_id,
    )

    require_exact_document_identity(
        document,
        payload.client,
        payload.project,
        payload.doc_id,
    )

    if document.get("text_truncated"):
        raise HTTPException(
            status_code=422,
            detail="Complete extracted document text is required.",
        )

    text = document.get("text") or ""

    if not text.strip():
        raise HTTPException(
            status_code=422,
            detail="Document has no usable extracted text.",
        )

    if len(text) > 50000:
        raise HTTPException(
            status_code=422,
            detail="Document exceeds the initial TARai analysis limit.",
        )

    try:
        suggestion = analyze_privilege(
            workspace="discovery",
            document_text=text,
            privilege_criteria=criteria,
        )
    except TARaiDisabledError:
        raise HTTPException(
            status_code=503,
            detail="TARai AI suggestions are disabled.",
        )
    except TARaiConfigurationError:
        raise HTTPException(
            status_code=503,
            detail="TARai AI provider is unavailable.",
        )
    except TARaiResponseError:
        raise HTTPException(
            status_code=502,
            detail="TARai could not validate the AI suggestion.",
        )
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="TARai AI analysis failed.",
        )

    return {
        "workspace": "discovery",
        "client": payload.client,
        "project": payload.project,
        "doc_id": document.get("doc_id", payload.doc_id),
        "suggestion": suggestion.model_dump(),
        "coding_mapping": mapping,
        "saved_to_review": False,
        "requires_reviewer_approval": True,
    }
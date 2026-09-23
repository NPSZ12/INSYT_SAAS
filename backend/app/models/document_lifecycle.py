from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from app.database.connection import Base


class DocumentLifecycle(Base):
    __tablename__ = "document_lifecycle"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Project identity
    workspace = Column(String(32), nullable=False)
    client = Column(String(255), nullable=False)
    project = Column(String(255), nullable=False)

    # INSYT document identity
    doc_id = Column(String(64), nullable=False)

    source_job_id = Column(String(64), nullable=True)
    tracked_job_id = Column(String(64), nullable=True)

    file_id = Column(String(128), nullable=True)
    parent_file_id = Column(String(128), nullable=True)
    family_id = Column(String(128), nullable=True)

    # File identity / display
    original_filename = Column(Text, nullable=True)
    extension = Column(String(32), nullable=True)
    source_type = Column(String(64), nullable=True)

    source_bytes = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    page_count = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    # Duplicate / canonical relationships
    content_hash = Column(String(128), nullable=True)
    canonical_doc_id = Column(String(64), nullable=True)

    is_duplicate = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    preserve_occurrence = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    is_denisted = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    # Storage locations
    native_staged_blob_path = Column(Text, nullable=True)
    text_staged_blob_path = Column(Text, nullable=True)
    text_staged_bytes = Column(
        BigInteger,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    native_live_blob_path = Column(Text, nullable=True)
    text_live_blob_path = Column(Text, nullable=True)

    # Lifecycle state
    ingestion_status = Column(
        String(32),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )

    ocr_status = Column(
        String(32),
        nullable=True,
    )

    detection_status = Column(
        String(32),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )

    promotion_status = Column(
        String(32),
        nullable=False,
        default="PENDING",
        server_default=text("'PENDING'"),
    )

    review_status = Column(
        String(32),
        nullable=True,
    )

    detection_mode = Column(
        String(32),
        nullable=True,
    )

    # Search / coding
    coding = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    source_metadata = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    detection_metadata = Column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "workspace",
            "client",
            "project",
            "doc_id",
            name="uq_document_lifecycle_project_doc",
        ),

        Index(
            "ix_document_lifecycle_detection_status",
            "workspace",
            "client",
            "project",
            "detection_status",
            "doc_id",
        ),

        Index(
            "ix_document_lifecycle_promotion_status",
            "workspace",
            "client",
            "project",
            "promotion_status",
            "doc_id",
        ),

        Index(
            "ix_document_lifecycle_review_status",
            "workspace",
            "client",
            "project",
            "review_status",
            "doc_id",
        ),

        Index(
            "ix_document_lifecycle_source_job",
            "workspace",
            "client",
            "project",
            "source_job_id",
        ),

        Index(
            "ix_document_lifecycle_family",
            "workspace",
            "client",
            "project",
            "family_id",
        ),

        Index(
            "ix_document_lifecycle_extension",
            "workspace",
            "client",
            "project",
            "extension",
            "doc_id",
        ),
        Index(
            "ix_document_lifecycle_content_hash",
            "workspace",
            "client",
            "project",
            "content_hash",
        ),
        Index(
            "ix_document_lifecycle_canonical_doc",
            "workspace",
            "client",
            "project",
            "canonical_doc_id",
        ),
        Index(
            "ix_document_lifecycle_detection_ready",
            "workspace",
            "client",
            "project",
            "doc_id",
            postgresql_where=text(
                "detection_status = 'READY' "
                "AND is_denisted = false"
            ),
        ),
    )

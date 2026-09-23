"""add document lifecycle index

Revision ID: d6bd72728e16
Revises: 685cb69dacae
Create Date: 2026-09-23 10:24:41.503385
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d6bd72728e16"
down_revision: Union[str, Sequence[str], None] = "685cb69dacae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the INSYT document lifecycle control-plane index."""

    op.create_table(
        "document_lifecycle",

        sa.Column(
            "id",
            sa.BigInteger(),
            autoincrement=True,
            nullable=False,
        ),

        # Project identity
        sa.Column("workspace", sa.String(length=32), nullable=False),
        sa.Column("client", sa.String(length=255), nullable=False),
        sa.Column("project", sa.String(length=255), nullable=False),

        # INSYT document identity
        sa.Column("doc_id", sa.String(length=64), nullable=False),

        sa.Column("source_job_id", sa.String(length=64), nullable=True),
        sa.Column("tracked_job_id", sa.String(length=64), nullable=True),

        sa.Column("file_id", sa.String(length=128), nullable=True),
        sa.Column("parent_file_id", sa.String(length=128), nullable=True),
        sa.Column("family_id", sa.String(length=128), nullable=True),

        # File identity / display
        sa.Column("original_filename", sa.Text(), nullable=True),
        sa.Column("extension", sa.String(length=32), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=True),

        sa.Column(
            "source_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        sa.Column(
            "page_count",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        # Duplicate / canonical relationships
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("canonical_doc_id", sa.String(length=64), nullable=True),

        sa.Column(
            "is_duplicate",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        sa.Column(
            "preserve_occurrence",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        sa.Column(
            "is_denisted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),

        # Storage locations
        sa.Column("native_staged_blob_path", sa.Text(), nullable=True),
        sa.Column("text_staged_blob_path", sa.Text(), nullable=True),

        sa.Column(
            "text_staged_bytes",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),

        sa.Column("native_live_blob_path", sa.Text(), nullable=True),
        sa.Column("text_live_blob_path", sa.Text(), nullable=True),

        # Lifecycle state
        sa.Column(
            "ingestion_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),

        sa.Column(
            "ocr_status",
            sa.String(length=32),
            nullable=True,
        ),

        sa.Column(
            "detection_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),

        sa.Column(
            "promotion_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'PENDING'"),
        ),

        sa.Column(
            "review_status",
            sa.String(length=32),
            nullable=True,
        ),

        sa.Column(
            "detection_mode",
            sa.String(length=32),
            nullable=True,
        ),

        # Flexible searchable/project metadata.
        sa.Column(
            "coding",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column(
            "source_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column(
            "detection_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),

        sa.PrimaryKeyConstraint(
            "id",
            name="pk_document_lifecycle",
        ),

        sa.UniqueConstraint(
            "workspace",
            "client",
            "project",
            "doc_id",
            name="uq_document_lifecycle_project_doc",
        ),
    )

    # ------------------------------------------------------------------
    # Core population/pagination indexes.
    # These support millions of rows without loading a project population
    # into application memory.
    # ------------------------------------------------------------------

    op.create_index(
        "ix_document_lifecycle_detection_status",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "detection_status",
            "doc_id",
        ],
        unique=False,
    )

    # Smaller partial index specifically for the hot Detection Ready query.
    op.create_index(
        "ix_document_lifecycle_detection_ready",
        "document_lifecycle",
        ["workspace", "client", "project", "doc_id"],
        unique=False,
        postgresql_where=sa.text(
            "detection_status = 'READY' "
            "AND is_denisted = false"
        ),
    )

    op.create_index(
        "ix_document_lifecycle_promotion_status",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "promotion_status",
            "doc_id",
        ],
        unique=False,
    )

    op.create_index(
        "ix_document_lifecycle_review_status",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "review_status",
            "doc_id",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Provenance / reconciliation indexes.
    # ------------------------------------------------------------------

    op.create_index(
        "ix_document_lifecycle_source_job",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "source_job_id",
        ],
        unique=False,
    )

    op.create_index(
        "ix_document_lifecycle_family",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "family_id",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Duplicate/canonical-content indexes.
    # ------------------------------------------------------------------

    op.create_index(
        "ix_document_lifecycle_content_hash",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "content_hash",
        ],
        unique=False,
    )

    op.create_index(
        "ix_document_lifecycle_canonical_doc",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "canonical_doc_id",
        ],
        unique=False,
    )

    # ------------------------------------------------------------------
    # Files pane structured filter.
    # Filename free-text search is intentionally NOT indexed here yet;
    # it will get PostgreSQL trigram indexing separately.
    # ------------------------------------------------------------------

    op.create_index(
        "ix_document_lifecycle_extension",
        "document_lifecycle",
        [
            "workspace",
            "client",
            "project",
            "extension",
            "doc_id",
        ],
        unique=False,
    )


def downgrade() -> None:
    """Remove the INSYT document lifecycle control-plane index."""

    op.drop_index(
        "ix_document_lifecycle_extension",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_canonical_doc",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_content_hash",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_family",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_source_job",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_review_status",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_promotion_status",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_detection_ready",
        table_name="document_lifecycle",
    )

    op.drop_index(
        "ix_document_lifecycle_detection_status",
        table_name="document_lifecycle",
    )

    op.drop_table("document_lifecycle")

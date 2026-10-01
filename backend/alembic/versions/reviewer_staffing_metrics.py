"""add reviewer staffing metrics

Revision ID: reviewer_staffing_metrics
Revises: d6bd72728e16
Create Date: 2026-10-01
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "reviewer_staffing_metrics"
down_revision: Union[str, Sequence[str], None] = "d6bd72728e16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "staffing_groups",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "performance_score",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "performance_band",
            sa.String(),
            nullable=False,
            server_default="Unrated",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "performance_rating_source",
            sa.String(),
            nullable=False,
            server_default="metrics",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "performance_rating_updated_at",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "users",
        "performance_rating_updated_at",
    )

    op.drop_column(
        "users",
        "performance_rating_source",
    )

    op.drop_column(
        "users",
        "performance_band",
    )

    op.drop_column(
        "users",
        "performance_score",
    )

    op.drop_column(
        "users",
        "staffing_groups",
    )
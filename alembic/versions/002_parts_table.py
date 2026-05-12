"""Add parts table (structural segmenter output).

Revision ID: 002
Revises: 001
Create Date: 2026-05-12 10:00:00.000000

The `parts` table stores the high-level structural segmentation of each
episode (interview / host_talk / news / jingle / commercial / unknown).
It is produced by `analysis.structural_segmenter.segment_into_parts` and
populated by `PipelineOrchestrator._step_structural_segment`.
"""

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("host_labels", sa.JSON(), nullable=False),
        sa.Column("guest_labels", sa.JSON(), nullable=False),
        sa.Column("unknown_labels", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_parts_episode", "parts", ["episode_id"])
    op.create_index(
        "idx_parts_episode_idx", "parts", ["episode_id", "idx"], unique=True
    )
    op.create_index("idx_parts_type", "parts", ["type"])


def downgrade() -> None:
    op.drop_index("idx_parts_type", table_name="parts")
    op.drop_index("idx_parts_episode_idx", table_name="parts")
    op.drop_index("idx_parts_episode", table_name="parts")
    op.drop_table("parts")

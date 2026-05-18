"""Add speaker_analyses and qa_pairs columns to parts table.

Revision ID: 003
Revises: 002
Create Date: 2026-05-17

Populated by the new `enrich_parts` pipeline step which runs
SpeakerPartAnalyzer (stance + hate scoring) and NamedQAExtractor
(Q&A pair extraction) per structural part.
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("parts", sa.Column("speaker_analyses", sa.JSON(), nullable=True))
    op.add_column("parts", sa.Column("qa_pairs", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("parts", "qa_pairs")
    op.drop_column("parts", "speaker_analyses")

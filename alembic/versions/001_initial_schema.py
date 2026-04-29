"""Initial schema with all tables.

Revision ID: 001
Revises:
Create Date: 2026-04-29 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Upgrade database schema."""

    # Create stations table
    op.create_table(
        "stations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("stream_url", sa.String(500), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Create episodes table
    op.create_table(
        "episodes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("station_id", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration", sa.Float(), nullable=False),
        sa.Column("audio_path", sa.String(500), nullable=False),
        sa.Column("language", sa.String(10), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["stations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_episode_station_recorded", "episodes", ["station_id", "recorded_at"])

    # Create segments table
    op.create_table(
        "segments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("start", sa.Float(), nullable=False),
        sa.Column("end", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_segment_episode_type", "segments", ["episode_id", "type"])

    # Create topics table
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("name_he", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("summary_he", sa.Text(), nullable=False),
        sa.Column("summary_en", sa.Text(), nullable=False),
        sa.Column("is_main", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_topic_segment_category", "topics", ["segment_id", "category"])

    # Create guests table
    op.create_table(
        "guests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name_he", sa.String(255), nullable=False),
        sa.Column("name_en", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("affiliation", sa.String(255), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name_en"),
    )
    op.create_index("idx_guest_name_en", "guests", ["name_en"])

    # Create guest_appearances table
    op.create_table(
        "guest_appearances",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("guest_id", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["guest_id"], ["guests.id"]),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_guest_appearance_segment",
        "guest_appearances",
        ["segment_id", "guest_id"],
    )

    # Create sentiment_results table
    op.create_table(
        "sentiment_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("segment_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("speaker_label", sa.String(50), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("tone", sa.String(50), nullable=False),
        sa.Column("quotes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["segments.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sentiment_topic", "sentiment_results", ["topic_id"])
    op.create_index("idx_sentiment_speaker", "sentiment_results", ["speaker_label"])

    # Create pipeline_runs table
    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("episode_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("status", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["episode_id"], ["episodes.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_pipeline_run_episode_step",
        "pipeline_runs",
        ["episode_id", "step"],
    )


def downgrade() -> None:
    """Downgrade database schema."""

    op.drop_index("idx_pipeline_run_episode_step")
    op.drop_table("pipeline_runs")

    op.drop_index("idx_sentiment_speaker")
    op.drop_index("idx_sentiment_topic")
    op.drop_table("sentiment_results")

    op.drop_index("idx_guest_appearance_segment")
    op.drop_table("guest_appearances")

    op.drop_index("idx_guest_name_en")
    op.drop_table("guests")

    op.drop_index("idx_topic_segment_category")
    op.drop_table("topics")

    op.drop_index("idx_segment_episode_type")
    op.drop_table("segments")

    op.drop_index("idx_episode_station_recorded")
    op.drop_table("episodes")

    op.drop_table("stations")

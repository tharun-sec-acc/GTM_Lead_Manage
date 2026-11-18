"""Unified AI-Powered Meeting Management (Microsoft Teams + Google Meet).

Revision ID: 0015_unified_meetings
Revises: 0014_update_product_names
"""

from alembic import op
import sqlalchemy as sa

revision = "0015_unified_meetings"
down_revision = "0014_update_product_names"
branch_labels = None
depends_on = None


def upgrade():
    # 1. meetings table
    op.create_table(
        "meetings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_meeting_id", sa.String(255), nullable=True),
        sa.Column("organizer_email", sa.String(320), nullable=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meeting_type", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("join_url", sa.Text(), nullable=False),
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("status", sa.String(32), nullable=False, server_default="scheduled"),
        sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meetings_external_meeting_id", "meetings", ["external_meeting_id"])
    op.create_index("ix_meetings_lead_id", "meetings", ["lead_id"])
    op.create_index("ix_meetings_status", "meetings", ["status"])

    # 2. meeting_participants table
    op.create_table(
        "meeting_participants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_participant_id", sa.String(255), nullable=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("participant_role", sa.String(64), nullable=False, server_default="attendee"),
        sa.Column("join_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leave_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_participants_meeting_id", "meeting_participants", ["meeting_id"])

    # 3. meeting_recordings table
    op.create_table(
        "meeting_recordings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_recording_id", sa.String(255), nullable=True),
        sa.Column("external_file_id", sa.String(255), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="video/mp4"),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("source_location", sa.String(500), nullable=True),
        sa.Column("s3_bucket", sa.String(255), nullable=True),
        sa.Column("s3_key", sa.String(500), nullable=True),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_recordings_meeting_id", "meeting_recordings", ["meeting_id"])

    # 4. meeting_transcripts table
    op.create_table(
        "meeting_transcripts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_transcript_id", sa.String(255), nullable=True),
        sa.Column("language", sa.String(16), nullable=False, server_default="en"),
        sa.Column("source", sa.String(64), nullable=False, server_default="provider"),
        sa.Column("s3_bucket", sa.String(255), nullable=True),
        sa.Column("s3_key", sa.String(500), nullable=True),
        sa.Column("raw_content", sa.Text(), nullable=True),
        sa.Column("processing_status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_transcripts_meeting_id", "meeting_transcripts", ["meeting_id"])

    # 5. meeting_transcript_entries table
    op.create_table(
        "meeting_transcript_entries",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("transcript_id", sa.String(36), sa.ForeignKey("meeting_transcripts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("speaker_id", sa.String(255), nullable=True),
        sa.Column("speaker_name", sa.String(255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_timestamp", sa.String(64), nullable=True),
        sa.Column("end_timestamp", sa.String(64), nullable=True),
        sa.Column("original_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_transcript_entries_transcript_id", "meeting_transcript_entries", ["transcript_id"])

    # 6. meeting_analyses table
    op.create_table(
        "meeting_analyses",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("analysis_version", sa.String(32), nullable=False, server_default="v1"),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("customer_requirements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("customer_pain_points", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("technical_requirements", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("objections", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("buying_signals", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("decisions", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("next_steps", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("meeting_minutes", sa.Text(), nullable=False),
        sa.Column("followup_draft_subject", sa.String(500), nullable=True),
        sa.Column("followup_draft_body", sa.Text(), nullable=True),
        sa.Column("recommended_sales_stage", sa.String(64), nullable=True),
        sa.Column("recommended_next_action", sa.Text(), nullable=True),
        sa.Column("structured_analysis", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("analysis_status", sa.String(32), nullable=False, server_default="completed"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.85"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_analyses_meeting_id", "meeting_analyses", ["meeting_id"], unique=True)

    # 7. meeting_action_items table
    op.create_table(
        "meeting_action_items",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner", sa.String(255), nullable=True),
        sa.Column("due_date", sa.String(64), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default="medium"),
        sa.Column("status", sa.String(32), nullable=False, server_default="open"),
        sa.Column("source_timestamp", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_meeting_action_items_meeting_id", "meeting_action_items", ["meeting_id"])
    op.create_index("ix_meeting_action_items_lead_id", "meeting_action_items", ["lead_id"])


def downgrade():
    op.drop_table("meeting_action_items")
    op.drop_table("meeting_analyses")
    op.drop_table("meeting_transcript_entries")
    op.drop_table("meeting_transcripts")
    op.drop_table("meeting_recordings")
    op.drop_table("meeting_participants")
    op.drop_table("meetings")

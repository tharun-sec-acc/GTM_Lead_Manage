"""Public Customer Booking System with Google Meet, Google Calendar, and Microsoft Outlook.

Revision ID: 0017_public_booking_system
Revises: 0016_advanced_research_engine
"""

from alembic import op
import sqlalchemy as sa

revision = "0017_public_booking_system"
down_revision = "0016_advanced_research_engine"
branch_labels = None
depends_on = None


def upgrade():
    # 1. booking_profiles
    op.create_table(
        "booking_profiles",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36), nullable=True),
        sa.Column("public_slug", sa.String(100), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("company_name", sa.String(255), nullable=False, server_default="DENSO"),
        sa.Column("meeting_title", sa.String(255), nullable=False, server_default="DENSO Solutions Discovery Call"),
        sa.Column("meeting_description", sa.Text(), nullable=True),
        sa.Column("default_provider", sa.String(32), nullable=False, server_default="google_meet"),
        sa.Column("duration_minutes", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("buffer_before_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("buffer_after_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("minimum_notice_minutes", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("booking_horizon_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("max_meetings_per_day", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Kolkata"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_booking_profiles_public_slug", "booking_profiles", ["public_slug"], unique=True)

    # 2. booking_availabilities
    op.create_table(
        "booking_availabilities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_profile_id", sa.String(36), sa.ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.String(8), nullable=False, server_default="09:00"),
        sa.Column("end_time", sa.String(8), nullable=False, server_default="17:00"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.UniqueConstraint("booking_profile_id", "weekday", name="uq_profile_weekday"),
    )
    op.create_index("ix_booking_availabilities_booking_profile_id", "booking_availabilities", ["booking_profile_id"])

    # 3. bookings
    op.create_table(
        "bookings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_profile_id", sa.String(36), sa.ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meeting_id", sa.String(36), sa.ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lead_id", sa.String(36), sa.ForeignKey("leads.id", ondelete="SET NULL"), nullable=True),
        sa.Column("contact_id", sa.String(36), sa.ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(32), nullable=False, server_default="google_meet"),
        sa.Column("customer_name", sa.String(255), nullable=False),
        sa.Column("customer_email", sa.String(320), nullable=False),
        sa.Column("customer_company", sa.String(255), nullable=True),
        sa.Column("customer_phone", sa.String(64), nullable=True),
        sa.Column("meeting_purpose", sa.Text(), nullable=True),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("google_calendar_event_id", sa.String(255), nullable=True),
        sa.Column("google_meet_uri", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="confirmed"),
        sa.Column("cancellation_token_hash", sa.String(64), nullable=False),
        sa.Column("reschedule_token_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_bookings_booking_profile_id", "bookings", ["booking_profile_id"])
    op.create_index("ix_bookings_meeting_id", "bookings", ["meeting_id"])
    op.create_index("ix_bookings_lead_id", "bookings", ["lead_id"])
    op.create_index("ix_bookings_customer_email", "bookings", ["customer_email"])
    op.create_index("ix_bookings_start_time", "bookings", ["start_time"])
    op.create_index("ix_bookings_status", "bookings", ["status"])
    op.create_index("ix_bookings_cancellation_token_hash", "bookings", ["cancellation_token_hash"], unique=True)
    op.create_index("ix_bookings_reschedule_token_hash", "bookings", ["reschedule_token_hash"], unique=True)
    op.create_index("ix_bookings_idempotency_key", "bookings", ["idempotency_key"], unique=True)
    op.create_index("ix_bookings_google_calendar_event_id", "bookings", ["google_calendar_event_id"])

    # 4. booking_reservations
    op.create_table(
        "booking_reservations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_profile_id", sa.String(36), sa.ForeignKey("booking_profiles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reservation_token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_booking_reservations_booking_profile_id", "booking_reservations", ["booking_profile_id"])
    op.create_index("ix_booking_reservations_start_time", "booking_reservations", ["start_time"])
    op.create_index("ix_booking_reservations_reservation_token_hash", "booking_reservations", ["reservation_token_hash"], unique=True)
    op.create_index("ix_booking_reservations_expires_at", "booking_reservations", ["expires_at"])
    op.create_index("ix_booking_reservations_status", "booking_reservations", ["status"])

    # 5. booking_event_logs
    op.create_table(
        "booking_event_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("booking_id", sa.String(36), sa.ForeignKey("bookings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("event_type", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False, server_default="google_meet"),
        sa.Column("provider_event_id", sa.String(255), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_booking_event_logs_booking_id", "booking_event_logs", ["booking_id"])
    op.create_index("ix_booking_event_logs_event_type", "booking_event_logs", ["event_type"])


def downgrade():
    op.drop_table("booking_event_logs")
    op.drop_table("booking_reservations")
    op.drop_table("bookings")
    op.drop_table("booking_availabilities")
    op.drop_table("booking_profiles")

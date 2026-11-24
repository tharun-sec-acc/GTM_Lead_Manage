from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, false
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def new_id() -> str:
    return str(uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class ZohoOAuthState(Base):
    __tablename__ = "zoho_oauth_states"

    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    accounts_domain: Mapped[str] = mapped_column(String(255), default="https://accounts.zoho.in")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ZohoConnection(Base):
    __tablename__ = "zoho_connections"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    org_id: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    org_name: Mapped[str] = mapped_column(String(255))
    user_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    user_zuid: Mapped[str | None] = mapped_column(String(100), nullable=True)
    accounts_domain: Mapped[str] = mapped_column(String(255), default="https://accounts.zoho.in")
    api_domain: Mapped[str] = mapped_column(String(255), default="https://www.zohoapis.in")
    crm_api_version: Mapped[str] = mapped_column(String(10), default="v8")
    
    # Encrypted OAuth tokens
    refresh_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    access_token_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    access_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sync_direction: Mapped[str] = mapped_column(String(20), default="bidirectional")  # bidirectional, outbound, inbound
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ZohoFieldMapping(Base):
    __tablename__ = "zoho_field_mappings"
    __table_args__ = (
        UniqueConstraint("zoho_module", "gtm_field", name="uq_zoho_module_gtm_field"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    zoho_module: Mapped[str] = mapped_column(String(50), index=True)  # Accounts, Contacts, Leads, Deals, Tasks, Events, Notes
    gtm_field: Mapped[str] = mapped_column(String(100))
    zoho_field: Mapped[str] = mapped_column(String(100))
    field_type: Mapped[str] = mapped_column(String(50), default="string")
    sync_direction: Mapped[str] = mapped_column(String(20), default="bidirectional")  # bidirectional, gtm_to_zoho, zoho_to_gtm
    conflict_policy: Mapped[str] = mapped_column(String(30), default="crm_wins")     # crm_wins, gtm_wins, newest_wins
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ZohoRecordMapping(Base):
    __tablename__ = "zoho_record_mappings"
    __table_args__ = (
        UniqueConstraint("gtm_entity_type", "gtm_entity_id", name="uq_zoho_gtm_entity"),
        UniqueConstraint("zoho_module", "zoho_record_id", name="uq_zoho_module_record_id"),
        Index("ix_zoho_record_mappings_gtm_entity", "gtm_entity_type", "gtm_entity_id"),
        Index("ix_zoho_record_mappings_zoho_record", "zoho_module", "zoho_record_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    gtm_entity_type: Mapped[str] = mapped_column(String(50))  # lead, contact, product_opportunity, meeting, sales_task, research_job
    gtm_entity_id: Mapped[str] = mapped_column(String(36))
    zoho_module: Mapped[str] = mapped_column(String(50))      # Accounts, Contacts, Leads, Deals, Events, Tasks, Notes
    zoho_record_id: Mapped[str] = mapped_column(String(100))
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sync_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    sync_status: Mapped[str] = mapped_column(String(20), default="synced")  # synced, pending, failed, conflict
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ZohoSyncJob(Base):
    __tablename__ = "zoho_sync_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_type: Mapped[str] = mapped_column(String(30))  # outbound_sync, inbound_sync, reconcile, booking_sync, meeting_sync
    status: Mapped[str] = mapped_column(String(20), default="running")  # running, completed, failed, partial
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ZohoSyncLog(Base):
    __tablename__ = "zoho_sync_logs"
    __table_args__ = (
        Index("ix_zoho_sync_logs_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    job_id: Mapped[str | None] = mapped_column(ForeignKey("zoho_sync_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    zoho_module: Mapped[str] = mapped_column(String(50))
    zoho_record_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    action: Mapped[str] = mapped_column(String(50))  # create, update, upsert, pull, delete, conflict
    status: Mapped[str] = mapped_column(String(20))  # success, failure, skipped, conflict
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ZohoSyncConflict(Base):
    __tablename__ = "zoho_sync_conflicts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    record_mapping_id: Mapped[str | None] = mapped_column(ForeignKey("zoho_record_mappings.id", ondelete="SET NULL"), nullable=True)
    gtm_entity_type: Mapped[str] = mapped_column(String(50))
    gtm_entity_id: Mapped[str] = mapped_column(String(36))
    zoho_module: Mapped[str] = mapped_column(String(50))
    zoho_record_id: Mapped[str] = mapped_column(String(100))
    field_name: Mapped[str] = mapped_column(String(100))
    gtm_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    zoho_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[str] = mapped_column(String(20), default="unresolved")  # unresolved, resolved_gtm, resolved_zoho, ignored
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

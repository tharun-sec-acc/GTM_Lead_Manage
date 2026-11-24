from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.auth.models import (
    Organization,
    User,
    OrganizationMember,
    OrganizationInvitation,
    PasswordResetToken,
    EmailVerificationToken,
    RevokedToken,
    AuditLog,
    OAuthConnection,
)


def new_id():
    return str(uuid4())


def now():
    return datetime.now(timezone.utc)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    headers: Mapped[list] = mapped_column(JSON)
    sheet_headers: Mapped[dict | None] = mapped_column(JSON)
    mapping: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    error: Mapped[str | None] = mapped_column(Text)
    product_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Lead(Base):
    __tablename__ = "leads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    company_name: Mapped[str] = mapped_column(String(500))
    company_key: Mapped[str] = mapped_column(String(500), index=True)
    domain: Mapped[str | None] = mapped_column(String(253))
    industry: Mapped[str | None] = mapped_column(String(255))
    designation: Mapped[str | None] = mapped_column(String(500))
    location: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    revenue: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(Text)
    remarks: Mapped[str | None] = mapped_column(Text)
    key_person_info: Mapped[str | None] = mapped_column(Text)
    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ImportRow(Base):
    __tablename__ = "import_rows"
    __table_args__ = (UniqueConstraint("batch_id", "sheet_name", "row_number", name="uq_batch_sheet_row"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"))
    sheet_name: Mapped[str] = mapped_column(String(255), default="", server_default="")
    row_number: Mapped[int] = mapped_column(Integer)
    original: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(Text)
    lead_id: Mapped[str | None] = mapped_column(ForeignKey("leads.id"))


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("lead_id", "apollo_id", name="uq_contact_apollo"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    apollo_id: Mapped[str | None] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(500))
    email: Mapped[str | None] = mapped_column(String(320))
    department: Mapped[str | None] = mapped_column(String(255))
    seniority: Mapped[str | None] = mapped_column(String(100))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(String(500))
    is_key_decision_maker: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_status: Mapped[str] = mapped_column(String(30), default="unverified")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(50), default="Apollo")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApolloSearchResult(Base):
    __tablename__ = "apollo_search_results"
    __table_args__ = (UniqueConstraint("lead_id", "apollo_id", name="uq_apollo_search_lead_person"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    apollo_id: Mapped[str] = mapped_column(String(100))
    name: Mapped[str | None] = mapped_column(String(500))
    title: Mapped[str | None] = mapped_column(String(500))
    department: Mapped[str | None] = mapped_column(String(255))
    seniority: Mapped[str | None] = mapped_column(String(100))
    organization_name: Mapped[str | None] = mapped_column(String(500))
    organization_domain: Mapped[str | None] = mapped_column(String(253))
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    has_email: Mapped[bool | None] = mapped_column(Boolean)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    mode: Mapped[str] = mapped_column(String(20))
    delays: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    sequence_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    product_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (UniqueConstraint("campaign_id", "recipient", name="uq_campaign_recipient"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    campaign_id: Mapped[str] = mapped_column(ForeignKey("campaigns.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    contact_id: Mapped[str | None] = mapped_column(ForeignKey("contacts.id"))
    recipient: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(20), default="active")
    reply_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    unsubscribe_token: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailMessage(Base):
    __tablename__ = "email_messages"
    __table_args__ = (UniqueConstraint("enrollment_id", "step_number", name="uq_enrollment_step"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    enrollment_id: Mapped[str] = mapped_column(ForeignKey("enrollments.id"))
    step_number: Mapped[int] = mapped_column(Integer)
    manual_reply: Mapped[bool] = mapped_column(Boolean, default=False)
    reply_to_id: Mapped[str | None] = mapped_column(String(36))
    subject: Mapped[str] = mapped_column(String(998), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="draft")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    message_id: Mapped[str] = mapped_column(String(255), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    open_token: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailEvent(Base):
    __tablename__ = "email_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email_id: Mapped[str] = mapped_column(ForeignKey("email_messages.id"))
    event_type: Mapped[str] = mapped_column(String(30))
    detail: Mapped[str | None] = mapped_column(Text)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailReply(Base):
    __tablename__ = "email_replies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    mailbox_uid: Mapped[str] = mapped_column(String(128), unique=True)
    incoming_message_id: Mapped[str | None] = mapped_column(String(998))
    enrollment_id: Mapped[str | None] = mapped_column(ForeignKey("enrollments.id"))
    original_email_id: Mapped[str | None] = mapped_column(ForeignKey("email_messages.id"))
    sender: Mapped[str | None] = mapped_column(String(320))
    subject: Mapped[str | None] = mapped_column(Text)
    body: Mapped[str] = mapped_column(Text)
    classification: Mapped[str | None] = mapped_column(String(50))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Suppression(Base):
    __tablename__ = "suppressions"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    reason: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MailboxState(Base):
    __tablename__ = "mailbox_state"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid_validity: Mapped[str | None] = mapped_column(String(40))
    account: Mapped[str | None] = mapped_column(String(320))
    last_uid: Mapped[int] = mapped_column(Integer, default=0)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)


class TrackingLink(Base):
    __tablename__ = "tracking_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    email_id: Mapped[str] = mapped_column(ForeignKey("email_messages.id"))
    token: Mapped[str] = mapped_column(String(128), unique=True)
    destination: Mapped[str] = mapped_column(Text)


class SalesTask(Base):
    __tablename__ = "sales_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    reply_id: Mapped[str] = mapped_column(ForeignKey("email_replies.id"), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoogleOAuthState(Base):
    __tablename__ = "google_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    verifier_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    booking_requested: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoogleOAuthCredential(Base):
    __tablename__ = "google_oauth_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    organizer_email: Mapped[str] = mapped_column(String(320))
    refresh_token_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class MicrosoftOAuthState(Base):
    __tablename__ = "microsoft_oauth_states"
    state_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    browser_hash: Mapped[str] = mapped_column(String(64))
    auth_flow_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MicrosoftOAuthCredential(Base):
    __tablename__ = "microsoft_oauth_credentials"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(36))
    organizer_email: Mapped[str] = mapped_column(String(320))
    token_cache_encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    scopes: Mapped[list] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(String(500))
    logo_url: Mapped[str | None] = mapped_column(Text)
    primary_color: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default="active")
    product_context: Mapped[str | None] = mapped_column(Text)
    value_proposition: Mapped[str | None] = mapped_column(Text)
    target_industries: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProductLead(Base):
    __tablename__ = "product_leads"
    __table_args__ = (UniqueConstraint("product_id", "lead_id", name="uq_product_lead"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"))
    stage: Mapped[str] = mapped_column(String(50), default="prospect")
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    status: Mapped[str] = mapped_column(String(20), default="active")
    owner_id: Mapped[str | None] = mapped_column(String(36))
    sales_notes: Mapped[str | None] = mapped_column(Text)
    associated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ProductOpportunity(Base):
    __tablename__ = "product_opportunities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    product_lead_id: Mapped[str] = mapped_column(ForeignKey("product_leads.id"))
    research_job_id: Mapped[str | None] = mapped_column(ForeignKey("research_jobs.id"), nullable=True)
    opportunity_summary: Mapped[str | None] = mapped_column(Text)
    pain_points: Mapped[list] = mapped_column(JSON, default=list)
    use_cases: Mapped[list] = mapped_column(JSON, default=list)
    relevance_score: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_fact_ids: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailTemplate(Base):
    __tablename__ = "email_templates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    parent_template_id: Mapped[str | None] = mapped_column(ForeignKey("email_templates.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(50), default="custom")
    subject_template: Mapped[str] = mapped_column(String(998), default="")
    body_template: Mapped[str] = mapped_column(Text, default="")
    variables: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailTemplateVersion(Base):
    __tablename__ = "email_template_versions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(ForeignKey("email_templates.id"))
    version: Mapped[int] = mapped_column(Integer)
    subject_template: Mapped[str] = mapped_column(String(998), default="")
    body_template: Mapped[str] = mapped_column(Text, default="")
    variables: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class EmailAttachment(Base):
    __tablename__ = "email_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("email_messages.id"), nullable=True)
    upload_session_id: Mapped[str] = mapped_column(String(36), default=new_id)
    filename_safe: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(127))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_key: Mapped[str] = mapped_column(String(500))
    upload_status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ResearchFactOverride(Base):
    __tablename__ = "research_fact_overrides"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    fact_id: Mapped[str] = mapped_column(ForeignKey("research_facts.id"), index=True)
    product_id: Mapped[str | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    override_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by_note: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


# Public Booking Models
from app.booking.models import (  # noqa: E402
    BookingProfile,
    BookingAvailability,
    Booking,
    BookingReservation,
    BookingEventLog,
)

# Unified Meeting Intelligence Models
from app.meetings.models import (  # noqa: E402
    Meeting,
    MeetingParticipant,
    MeetingRecording,
    MeetingTranscript,
    MeetingTranscriptEntry,
    MeetingAnalysis,
    MeetingActionItem,
)

# Zoho CRM Integration Models
from app.zoho.models import (  # noqa: E402
    ZohoConnection,
    ZohoOAuthState,
    ZohoFieldMapping,
    ZohoRecordMapping,
    ZohoSyncJob,
    ZohoSyncLog,
    ZohoSyncConflict,
)

# Automotive Market Intelligence & Opportunity Detection Models
from app.market_intelligence.models import (  # noqa: E402
    MarketSource,
    MarketSourceRun,
    MarketArticle,
    MarketArticleVersion,
    MarketCompany,
    MarketEvent,
    ProductCatalog,
    ProductMatchRule,
    OpportunitySignal,
    MarketAlert,
    CompanyWatchlist,
    MarketFeedback,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://prospecting:prospecting@db:5432/prospecting"
    redis_url: str = "redis://redis:6379/0"
    apollo_api_key: str = ""
    gmail_address: str = ""
    gmail_app_password: str = ""
    mail_send_enabled: bool = False
    mail_unsubscribe_enabled: bool = True
    tracking_enabled: bool = False
    public_base_url: str = ""
    daily_send_limit: int = 50
    aws_region: str = ""
    aws_s3_bucket: str = "gtmprospecting-meeting-artifacts"
    aws_s3_upload_enabled: bool = False
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    bedrock_model_id: str = ""
    company_intelligence_enabled: bool = False
    research_browser_enabled: bool = False
    research_browser_wait_ms: int = 10000
    research_search_provider: str = ""
    research_search_api_key: str = ""
    research_discovery_enabled: bool = True
    research_discovery_max_candidates: int = 30
    research_discovery_max_domains: int = 12
    research_discovery_max_candidates_per_domain: int = 4
    research_discovery_min_score: float = 0.45
    research_discovery_max_bytes: int = 4_000_000
    research_discovery_deadline_seconds: int = 90
    research_discovery_wikipedia_enabled: bool = True
    research_discovery_sec_enabled: bool = True
    research_discovery_gleif_enabled: bool = True
    research_max_concurrent_agents: int = 3
    research_max_pages_per_company: int = 25
    research_max_crawl_depth: int = 3
    research_request_timeout: int = 20
    research_max_duration_seconds: int = 180
    research_cache_ttl_hours: int = 24
    research_max_retries: int = 2
    research_max_content_size: int = 3_000_000
    research_max_total_content_size: int = 15_000_000
    research_daily_budget: int = 100
    research_daily_bedrock_calls: int = 500
    research_daily_source_bytes: int = 50_000_000
    microsoft_tenant_id: str = ""
    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""
    microsoft_redirect_uri: str = "http://localhost:8000/microsoft/oauth/callback"
    microsoft_organizer_email: str = ""
    microsoft_token_encryption_key: str = ""
    microsoft_graph_base_url: str = "https://graph.microsoft.com/v1.0"
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/google/oauth/callback"
    google_workspace_organizer_email: str = ""
    google_token_encryption_key: str = ""
    google_calendar_enabled: bool = True
    google_meet_enabled: bool = True
    google_drive_enabled: bool = True
    google_workspace_events_enabled: bool = False
    meeting_timezone: str = "UTC"
    meeting_duration_minutes: int = 30
    meeting_workday_start_hour: int = 9
    meeting_workday_end_hour: int = 17
    meeting_booking_window_days: int = 30
    zoho_client_id: str = ""
    zoho_client_secret: str = ""
    zoho_redirect_uri: str = "http://localhost:8000/zoho/oauth/callback"
    zoho_accounts_domain: str = "https://accounts.zoho.in"
    zoho_api_domain: str = "https://www.zohoapis.in"
    zoho_crm_api_version: str = "v8"
    zoho_token_encryption_key: str = ""
    zoho_sync_enabled: bool = True

    # Multi-Tenant SaaS & Auth Settings
    jwt_secret_key: str = "gtm-production-super-secret-key-change-in-env-minimum-32-chars-2026"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 120
    jwt_refresh_token_expire_days: int = 14
    cors_allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000,http://0.0.0.0:3000,http://[::1]:3000"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None
    default_org_name: str = "Default Organization"
    default_org_slug: str = "default-org"
    auth_enabled: bool = True
    auth_allow_anonymous_fallback: bool = True  # Allows legacy tests to fallback to default tenant seamlessly

    # Billing & Subscription Foundation
    billing_default_plan_code: str = "growth"
    billing_currency: str = "INR"
    # Kill switch: when false, metered limits are reported but never enforced.
    billing_enforce_limits: bool = True

    # Advertising & Lead Capture (Release 3)
    advertising_enabled: bool = True
    advertising_sync_enabled: bool = True
    meta_app_id: str = ""
    meta_app_secret: str = ""
    meta_webhook_verify_token: str = ""
    meta_graph_version: str = "v21.0"
    google_ads_client_id: str = ""
    google_ads_client_secret: str = ""
    google_ads_developer_token: str = ""
    google_ads_login_customer_id: str = ""
    google_ads_api_version: str = "v19"
    google_lead_form_key: str = ""

    # Omnichannel inbox (Release 4)
    # Kill switch: no email/WhatsApp/SMS message leaves the system unless true.
    conversation_send_enabled: bool = False
    sms_inbound_webhook_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

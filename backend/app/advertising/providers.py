"""Read-only provider clients for the advertising connectors.

Nothing in this module writes to a provider. Campaign creation, pausing,
budget changes and any other spend-affecting call stay out of scope until the
approval workflow and spend safeguards exist.

When a provider is not configured the client raises :class:`ProviderNotConfigured`
instead of returning invented data, so the UI can report the external
requirement honestly.
"""

import logging
from datetime import date, datetime

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

META_DEFAULT_VERSION = "v21.0"
GOOGLE_DEFAULT_VERSION = "v19"


class ProviderNotConfigured(RuntimeError):
    """The provider needs credentials or app approval that are not configured."""


class ProviderError(RuntimeError):
    """The provider rejected the request or could not be reached."""


def meta_app_configured() -> bool:
    return bool(settings.meta_app_id and settings.meta_app_secret)


def google_app_configured() -> bool:
    return bool(
        settings.google_ads_developer_token
        and settings.google_ads_client_id
        and settings.google_ads_client_secret
    )


def _parse_timestamp(value) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("+0000", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _money_to_cents(value) -> int:
    try:
        return int(round(float(value) * 100))
    except (TypeError, ValueError):
        return 0


class MetaAdsClient:
    """Meta Marketing API reader (campaigns, daily insights, lead details)."""

    def __init__(self, access_token: str | None, *, version: str | None = None, timeout: float = 20.0):
        self.access_token = access_token or ""
        self.version = version or settings.meta_graph_version or META_DEFAULT_VERSION
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.access_token)

    def _get(self, path: str, params: dict) -> dict:
        if not self.configured:
            raise ProviderNotConfigured(
                "Meta access token is missing. Reconnect the ad account with a provider-approved token."
            )
        url = f"https://graph.facebook.com/{self.version}/{path.lstrip('/')}"
        query = {"access_token": self.access_token, **params}
        try:
            response = httpx.get(url, params=query, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Meta request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(self._error_message(response))
        return response.json()

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error") or {}
            message = error.get("message") or payload
        except ValueError:
            message = response.text[:300]
        return f"Meta API error {response.status_code}: {message}"

    def fetch_campaigns(self, account_id: str) -> list[dict]:
        account = account_id if account_id.startswith("act_") else f"act_{account_id}"
        payload = self._get(
            f"{account}/campaigns",
            {
                "fields": "id,name,status,objective,daily_budget,start_time",
                "limit": 200,
            },
        )
        rows = []
        for item in payload.get("data", []):
            rows.append(
                {
                    "external_id": str(item.get("id")),
                    "name": item.get("name") or str(item.get("id")),
                    "status": item.get("status"),
                    "objective": item.get("objective"),
                    "daily_budget_cents": int(item["daily_budget"]) if item.get("daily_budget") else None,
                    "started_at": _parse_timestamp(item.get("start_time")),
                    "raw": item,
                }
            )
        return rows

    def fetch_daily_insights(
        self, account_id: str, since: date, until: date
    ) -> list[dict]:
        account = account_id if account_id.startswith("act_") else f"act_{account_id}"
        payload = self._get(
            f"{account}/insights",
            {
                "level": "campaign",
                "time_increment": 1,
                "fields": "campaign_id,campaign_name,spend,impressions,clicks,actions,date_start",
                "time_range": f'{{"since":"{since.isoformat()}","until":"{until.isoformat()}"}}',
                "limit": 500,
            },
        )
        rows = []
        for item in payload.get("data", []):
            leads = 0
            for action in item.get("actions") or []:
                if action.get("action_type") in ("lead", "onsite_conversion.lead_grouped"):
                    try:
                        leads += int(float(action.get("value") or 0))
                    except (TypeError, ValueError):
                        continue
            rows.append(
                {
                    "campaign_external_id": str(item.get("campaign_id")),
                    "campaign_name": item.get("campaign_name"),
                    "metric_date": item.get("date_start"),
                    "spend_cents": _money_to_cents(item.get("spend")),
                    "impressions": int(item.get("impressions") or 0),
                    "clicks": int(item.get("clicks") or 0),
                    "leads": leads,
                }
            )
        return rows

    def fetch_lead(self, leadgen_id: str) -> dict:
        payload = self._get(leadgen_id, {"fields": "id,created_time,field_data,form_id,ad_id,adset_id,campaign_id"})
        return payload


class GoogleAdsClient:
    """Google Ads API reader using the official search endpoint."""

    def __init__(
        self,
        access_token: str | None,
        *,
        developer_token: str | None = None,
        login_customer_id: str | None = None,
        version: str | None = None,
        timeout: float = 25.0,
    ):
        self.access_token = access_token or ""
        self.developer_token = developer_token if developer_token is not None else settings.google_ads_developer_token
        self.login_customer_id = login_customer_id or settings.google_ads_login_customer_id or None
        self.version = version or settings.google_ads_api_version or GOOGLE_DEFAULT_VERSION
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.access_token and self.developer_token)

    def fetch_campaigns(self, customer_id: str) -> list[dict]:
        if not self.configured:
            raise ProviderNotConfigured(
                "Google Ads needs an access token and a developer token with approved API access."
            )
        customer = str(customer_id).replace("-", "")
        url = f"https://googleads.googleapis.com/{self.version}/customers/{customer}/googleAds:search"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "developer-token": self.developer_token,
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            headers["login-customer-id"] = str(self.login_customer_id).replace("-", "")
        query = (
            "SELECT campaign.id, campaign.name, campaign.status, campaign.advertising_channel_type, "
            "campaign_budget.amount_micros, campaign.start_date, metrics.cost_micros, "
            "metrics.impressions, metrics.clicks, metrics.conversions "
            "FROM campaign"
        )
        try:
            response = httpx.post(url, headers=headers, json={"query": query}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise ProviderError(f"Google Ads request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                f"Google Ads API error {response.status_code}: {response.text[:300]}"
            )
        payload = response.json()
        rows = []
        for result in payload.get("results", []):
            campaign = result.get("campaign") or {}
            metrics = result.get("metrics") or {}
            budget = result.get("campaignBudget") or {}
            micros = budget.get("amountMicros")
            rows.append(
                {
                    "external_id": str(campaign.get("id")),
                    "name": campaign.get("name") or str(campaign.get("id")),
                    "status": campaign.get("status"),
                    "objective": campaign.get("advertisingChannelType"),
                    "daily_budget_cents": int(int(micros) / 10_000) if micros else None,
                    "started_at": _parse_timestamp(campaign.get("startDate")),
                    "raw": result,
                    "metrics": {
                        "spend_cents": int(int(metrics.get("costMicros") or 0) / 10_000),
                        "impressions": int(metrics.get("impressions") or 0),
                        "clicks": int(metrics.get("clicks") or 0),
                        "conversions": int(float(metrics.get("conversions") or 0)),
                    },
                }
            )
        return rows

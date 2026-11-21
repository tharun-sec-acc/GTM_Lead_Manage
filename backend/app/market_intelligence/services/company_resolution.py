import logging
import re
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.models import Lead
from app.market_intelligence.models import MarketCompany, now

logger = logging.getLogger(__name__)


def normalize_company_name(name: str) -> str:
    """Normalizes company name for fuzzy matching (strips Ltd, Pvt, Inc, punctuation, spaces)."""
    cleaned = name.lower()
    cleaned = re.sub(r"\b(private|pvt|limited|ltd|inc|corp|corporation|group|india|motors|solutions)\b", "", cleaned)
    cleaned = re.sub(r"[^\w\s]", "", cleaned)
    return " ".join(cleaned.split())


class CompanyResolutionService:
    def resolve_or_create_company(
        self,
        session: Session,
        company_name: str,
        domain: Optional[str] = None,
        industry: str = "Automotive",
        business_segment: Optional[str] = None,
        location: Optional[str] = None,
        parent_company: Optional[str] = None,
    ) -> MarketCompany:
        """
        Resolves a company mentioned in market news against existing GTMProspecting Leads
        or registers it as a newly discovered prospect requiring human review.
        """
        norm_name = normalize_company_name(company_name)
        clean_domain = domain.strip().lower() if domain else None

        # 1. Check if MarketCompany already recorded
        query = select(MarketCompany)
        if clean_domain:
            existing_mc = session.scalar(query.where(MarketCompany.domain == clean_domain))
            if existing_mc:
                return existing_mc

        existing_mc = session.scalar(query.where(MarketCompany.normalized_name == norm_name))
        if existing_mc:
            return existing_mc

        # 2. Match against existing CRM Leads
        matched_lead: Optional[Lead] = None
        match_confidence = 1.0

        if clean_domain:
            matched_lead = session.scalar(select(Lead).where(func.lower(Lead.domain) == clean_domain))

        if not matched_lead:
            # Match by normalized name
            leads = session.scalars(select(Lead)).all()
            for l in leads:
                if normalize_company_name(l.company_name) == norm_name:
                    matched_lead = l
                    match_confidence = 0.90
                    break

        is_new = matched_lead is None
        approval_status = "matched_existing" if matched_lead else "pending_review"

        company = MarketCompany(
            company_name=company_name,
            normalized_name=norm_name,
            domain=clean_domain or (matched_lead.domain if matched_lead else None),
            industry=industry or (matched_lead.industry if matched_lead else "Automotive"),
            business_segment=business_segment,
            location=location or (matched_lead.location if matched_lead else None),
            parent_company=parent_company,
            is_new=is_new,
            gtm_lead_id=matched_lead.id if matched_lead else None,
            match_confidence=match_confidence,
            approval_status=approval_status,
        )
        session.add(company)
        session.flush()

        logger.info(
            "Resolved company '%s' (is_new=%s, lead_id=%s, status=%s)",
            company_name,
            is_new,
            matched_lead.id if matched_lead else "None",
            approval_status,
        )
        return company

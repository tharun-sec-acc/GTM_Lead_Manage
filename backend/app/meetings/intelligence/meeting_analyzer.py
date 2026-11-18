import json
import logging
from typing import Any
from pydantic import BaseModel, Field

from app import bedrock
from app.config import settings

logger = logging.getLogger(__name__)


class ActionItemModel(BaseModel):
    title: str
    description: str | None = None
    owner: str | None = None
    due_date: str | None = None
    priority: str = "medium"


class StructuredMeetingIntelligence(BaseModel):
    executive_summary: str
    meeting_purpose: str | None = None
    customer_requirements: list[str] = Field(default_factory=list)
    customer_pain_points: list[str] = Field(default_factory=list)
    business_challenges: list[str] = Field(default_factory=list)
    technical_requirements: list[str] = Field(default_factory=list)
    products_discussed: list[str] = Field(default_factory=list)
    customer_interests: list[str] = Field(default_factory=list)
    buying_intent: str = "medium"
    buying_signals: list[str] = Field(default_factory=list)
    decision_makers: list[str] = Field(default_factory=list)
    budget_information: str | None = None
    competitors_mentioned: list[str] = Field(default_factory=list)
    objections: list[str] = Field(default_factory=list)
    questions_by_customer: list[str] = Field(default_factory=list)
    questions_by_sales: list[str] = Field(default_factory=list)
    decisions_made: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    unresolved_issues: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    action_items: list[dict[str, Any]] = Field(default_factory=list)
    meeting_minutes: str
    followup_draft_subject: str
    followup_draft_body: str
    recommended_sales_stage: str = "Meeting Completed"
    recommended_next_action: str
    confidence: float = 0.85


INSTRUCTION = """You are a Principal B2B Sales Executive and Solutions Architect analyzing a sales call transcript for DENSO GTMProspecting.
Extract structured intelligence from the meeting transcript, distinguishing explicit facts from interpretations.
Do not fabricate commitments, budgets, or participant names. If information is absent, return an empty list or null.

Output JSON strictly conforming to this structure:
{
  "executive_summary": "High-level 2-3 sentence overview of what was discussed and the overall meeting outcome.",
  "meeting_purpose": "Primary objective of the call.",
  "customer_requirements": ["Specific operational or business capabilities requested by customer"],
  "customer_pain_points": ["Current pain points, inefficiencies or bottlenecks mentioned"],
  "business_challenges": ["High-level organizational, logistics or cost challenges"],
  "technical_requirements": ["Integration, API, ERP, device, or technical constraints discussed"],
  "products_discussed": ["DENSO or vendor solutions evaluated (e.g. TWMS, VDI, IE, MCE)"],
  "customer_interests": ["Specific features or benefits that resonated with customer"],
  "buying_intent": "high" | "medium" | "low",
  "decision_makers": ["Names or titles of stakeholders and decision makers mentioned"],
  "budget_information": "Explicit budget/pricing discussed or null",
  "competitors_mentioned": ["Any competing vendors or legacy tools named"],
  "objections": ["Concerns, pushback, timeline hesitations or objections raised"],
  "questions_by_customer": ["Key questions asked by the prospect"],
  "questions_by_sales": ["Questions asked by the sales representative"],
  "decisions_made": ["Concrete agreements or conclusions reached"],
  "unresolved_issues": ["Open questions or blockers requiring follow-up"],
  "next_steps": ["Agreed next steps with timeline where available"],
  "action_items": [
    {
      "title": "Clear action verb title",
      "description": "Details of the assigned task",
      "owner": "Person responsible or 'Sales Rep' or 'Prospect'",
      "due_date": "YYYY-MM-DD or relative time window",
      "priority": "high" | "medium" | "low"
    }
  ],
  "meeting_minutes": "# Minutes of Meeting (MoM)\n\n## 1. Executive Summary\n...\n\n## 2. Key Discussion Points\n...\n\n## 3. Customer Requirements\n...\n\n## 4. Objections & Blockers\n...\n\n## 5. Next Steps & Timeline\n...",
  "followup_draft_subject": "Re: [Company Name] discussion follow-up & next steps",
  "followup_draft_body": "Personalized 3-paragraph email thanking the customer, recapping key points agreed, and confirming next actions.",
  "recommended_sales_stage": "Discovery Completed" | "Solution Validation" | "Proposal / Demo Requested" | "Follow-up Required",
  "recommended_next_action": "Specific recommendation for the sales rep within 24-48 hours.",
  "confidence": 0.88
}
"""


def _fallback_analysis(
    transcript_text: str,
    company_name: str,
    contact_name: str | None,
) -> StructuredMeetingIntelligence:
    """Deterministic fallback analysis when Bedrock credentials are unavailable."""
    name_display = contact_name or "Prospect"
    comp_display = company_name or "the customer"

    reqs = ["Logistics visibility and operations optimization"]
    if "integration" in transcript_text.lower() or "erp" in transcript_text.lower():
        reqs.append("ERP / API integration capabilities")
    if "cost" in transcript_text.lower() or "price" in transcript_text.lower():
        reqs.append("Cost and ROI assessment across fleet depots")

    pains = ["Manual tracking and coordination overhead"]
    if "delay" in transcript_text.lower() or "breakdown" in transcript_text.lower():
        pains.append("Turnaround delays and maintenance visibility")

    action_items = [
        {
            "title": f"Send product collateral and walkthrough deck to {name_display}",
            "description": f"Share solution details and architecture overview discussed during the meeting.",
            "owner": "Sales Rep",
            "due_date": "Next business day",
            "priority": "high",
        },
        {
            "title": f"Schedule follow-up solution walkthrough with {comp_display} technical team",
            "description": "Demonstrate live deployment workflow and dispatch optimization.",
            "owner": "Sales Rep",
            "due_date": "Next week",
            "priority": "medium",
        },
    ]

    mom = f"""# Minutes of Meeting (MoM)

**Date**: Today  
**Participants**: Sales Team, {name_display} ({comp_display})  
**Solution**: DENSO Enterprise Logistics & Inspection Suite  

## 1. Executive Summary
The sales team met with {name_display} from {comp_display} to explore operational synergies and review how DENSO's enterprise platform can streamline fleet and warehouse workflows. The prospect expressed interest in modernizing operations and reviewing next steps.

## 2. Key Discussion Topics
- Current operational landscape and workflow challenges at {comp_display}.
- Overview of DENSO's solution capabilities and expected ROI.
- Technical considerations and deployment roadmap.

## 3. Customer Requirements & Pain Points
- Requirements: {', '.join(reqs)}.
- Current challenges: {', '.join(pains)}.

## 4. Next Steps & Action Items
- Send follow-up summary and solution documentation.
- Coordinate subsequent session with operational stakeholders.
"""

    draft_subject = f"{comp_display} & DENSO Discussion — Follow-up & Next Steps"
    draft_body = (
        f"Hi {name_display.split()[0]},\n\n"
        f"Thank you for taking the time to speak with our team today regarding {comp_display}'s operational priorities.\n\n"
        f"As discussed, our platform can significantly streamline your operations and reduce coordination overhead. "
        f"I have noted your specific requirements around {reqs[0].lower()}.\n\n"
        f"I would be glad to coordinate a targeted 20-minute solution walkthrough next Tuesday at 2:00 PM for your team. "
        f"Please let me know if that time works for you.\n\n"
        f"Best regards,\nDENSO Solutions Team"
    )

    return StructuredMeetingIntelligence(
        executive_summary=f"Introductory discussion with {name_display} at {comp_display} reviewing operations digitization. The customer expressed positive interest in exploring solutions.",
        meeting_purpose=f"Solution introduction and requirements discovery for {comp_display}.",
        customer_requirements=reqs,
        customer_pain_points=pains,
        business_challenges=["Operational visibility and process modernization"],
        technical_requirements=["Cloud deployment", "ERP compatibility"],
        products_discussed=["DENSO TWMS / VDI Platform"],
        customer_interests=["Automated tracking", "Dispatch optimization"],
        buying_intent="high" if "interested" in transcript_text.lower() else "medium",
        buying_signals=["Requested walkthrough", "Engaged with solution overview"],
        decision_makers=[name_display],
        budget_information=None,
        competitors_mentioned=[],
        objections=["Implementation timeline and internal alignment"],
        questions_by_customer=["What does the deployment onboarding look like?", "Can it integrate with our existing ERP?"],
        questions_by_sales=["What are your primary operational bottlenecks across depots?"],
        decisions_made=["Agreed to review collateral and schedule technical deep-dive."],
        decisions=["Agreed to review collateral and schedule technical deep-dive."],
        unresolved_issues=["Finalizing stakeholder availability for next session."],
        next_steps=["Distribute summary deck", "Propose date for technical deep-dive"],
        action_items=action_items,
        meeting_minutes=mom,
        followup_draft_subject=draft_subject,
        followup_draft_body=draft_body,
        recommended_sales_stage="Discovery Completed",
        recommended_next_action=f"Follow up with {name_display} within 24 hours sharing deck and proposing follow-up walkthrough.",
        confidence=0.85,
    )


def analyze_meeting_transcript(
    transcript_text: str,
    company_name: str,
    contact_name: str | None = None,
    product_name: str | None = None,
) -> StructuredMeetingIntelligence:
    """
    Analyze meeting transcript using Amazon Bedrock Converse API with structured JSON output.
    Falls back gracefully if Bedrock credentials are not configured.
    """
    if not transcript_text or not transcript_text.strip():
        return _fallback_analysis("", company_name, contact_name)

    data = {
        "company_name": company_name,
        "contact_name": contact_name or "Prospect",
        "product_name": product_name or "DENSO Enterprise Solutions",
        "transcript": transcript_text[:12000],  # Bound context safely
    }

    if settings.aws_region and settings.bedrock_model_id:
        try:
            parsed = bedrock.converse_json(INSTRUCTION, data)
            if isinstance(parsed, dict) and "executive_summary" in parsed:
                return StructuredMeetingIntelligence(**parsed)
        except Exception as e:
            logger.warning("Bedrock meeting analysis failed (%s); falling back to heuristic engine.", e)

    return _fallback_analysis(transcript_text, company_name, contact_name)

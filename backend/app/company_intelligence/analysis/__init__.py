"""Analysis and sales intelligence engines for Company Research."""

from app.company_intelligence.analysis.engine import generate_strategic_analysis
from app.company_intelligence.analysis.product_fit import evaluate_product_opportunities
from app.company_intelligence.analysis.summary_and_diff import (
    detect_research_changes,
    generate_one_page_summary,
)

__all__ = [
    "generate_strategic_analysis",
    "evaluate_product_opportunities",
    "generate_one_page_summary",
    "detect_research_changes",
]

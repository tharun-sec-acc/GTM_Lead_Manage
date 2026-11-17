from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.config import settings
from app.company_intelligence.models import ResearchBudget


class BudgetExceeded(RuntimeError):
    pass


def reserve_daily_job(session) -> None:
    _reserve(session, "jobs", max(1, settings.research_daily_budget))


def reserve_daily_bedrock_call(session) -> None:
    _reserve(session, "bedrock_calls", max(1, settings.research_daily_bedrock_calls))


def reserve_source_bytes(session, amount: int) -> None:
    _reserve(session, "source_bytes", max(0, settings.research_daily_source_bytes), amount)


def release_source_bytes(session, amount: int) -> None:
    if amount <= 0:
        return
    day = datetime.now(timezone.utc).date().isoformat()
    field = ResearchBudget.source_bytes
    session.execute(update(ResearchBudget).where(
        ResearchBudget.day == day,
        field >= amount,
    ).values(source_bytes=field - amount))


def _reserve(session, column: str, limit: int, amount: int = 1) -> None:
    day = datetime.now(timezone.utc).date().isoformat()
    dialect = session.get_bind().dialect.name
    insert_stmt = pg_insert if dialect == "postgresql" else sqlite_insert if dialect == "sqlite" else None
    if insert_stmt:
        session.execute(insert_stmt(ResearchBudget).values(
            day=day, jobs=0, bedrock_calls=0, source_bytes=0
        ).on_conflict_do_nothing())
    elif session.get(ResearchBudget, day) is None:
        session.add(ResearchBudget(day=day, jobs=0, bedrock_calls=0, source_bytes=0))
        session.flush()
    field = getattr(ResearchBudget, column)
    result = session.execute(update(ResearchBudget).where(
        ResearchBudget.day == day,
        field + amount <= limit,
    ).values({column: field + amount}))
    if result.rowcount != 1:
        raise BudgetExceeded(f"The daily company research {column.replace('_', ' ')} budget is exhausted.")

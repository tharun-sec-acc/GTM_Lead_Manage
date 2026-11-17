from pydantic import BaseModel, Field


class EvidenceFact(BaseModel):
    field_name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    source_id: str = Field(min_length=1, max_length=36)
    quote: str = Field(min_length=10, max_length=2000)
    unit: str | None = Field(default=None, max_length=80)
    currency: str | None = Field(default=None, max_length=20)
    reporting_period: str | None = Field(default=None, max_length=100)
    entity_scope: str | None = Field(default=None, max_length=300)


class AgentResult(BaseModel):
    facts: list[EvidenceFact] = Field(default_factory=list, max_length=40)
    not_available: str | None = Field(default=None, max_length=1000)


class SynthesisResult(BaseModel):
    summary: str
    sections: list[dict]

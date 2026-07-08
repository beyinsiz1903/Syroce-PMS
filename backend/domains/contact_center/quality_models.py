from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ScorecardQuestion(BaseModel):
    id: str
    text: str
    max_points: int = 10
    weight: float = 1.0


class ScorecardSection(BaseModel):
    section_name: str
    weight: float = 1.0
    questions: list[ScorecardQuestion]


class ScorecardConfigCreate(BaseModel):
    name: str
    sections: list[ScorecardSection]


class ScorecardConfigResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    is_active: bool = True
    sections: list[ScorecardSection]
    created_at: datetime
    updated_at: datetime


class CallEvaluationCreate(BaseModel):
    scorecard_id: str
    scores: dict[str, int]  # question_id -> points
    comments: str | None = None
    coaching_notes: str | None = None


class CallEvaluationResponse(BaseModel):
    id: str
    tenant_id: str
    call_id: str
    scorecard_id: str
    agent_id: str
    evaluator_id: str
    scores: dict[str, int]
    total_score: float
    comments: str | None = None
    coaching_notes: str | None = None
    created_at: datetime

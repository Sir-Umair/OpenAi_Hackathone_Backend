from datetime import datetime
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, description="Absolute local path available to the API")
    target_stack: str = "Next.js + FastAPI"


class Finding(BaseModel):
    severity: str
    category: str
    message: str
    file: str | None = None


class RoadmapStep(BaseModel):
    phase: str
    action: str
    rationale: str


class ProjectReport(BaseModel):
    id: str
    name: str
    path: str
    status: str = "complete"
    created_at: datetime
    languages: dict[str, int]
    findings: list[Finding]
    roadmap: list[RoadmapStep]
    summary: str

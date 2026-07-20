from datetime import datetime
from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, description="Absolute local path available to the API")
    target_stack: str = "Next.js + FastAPI"


class GitHubAnalyzeRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    repository_url: str = Field(min_length=1, description="Public HTTPS GitHub repository URL")
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


class MigrationRecommendation(BaseModel):
    current_technology: str
    reason: str
    recommended_targets: list[str]


class ConvertProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    path: str = Field(min_length=1, description="Absolute local path available to the API")
    source_paths: list[str] = Field(min_length=1, description="Project-relative files or directories to convert")
    target_stack: str = Field(min_length=1, max_length=120)
    output_directory: str | None = Field(default=None, description="Optional separate directory for generated files")


class GeneratedFile(BaseModel):
    path: str
    content: str


class ConversionReport(BaseModel):
    id: str
    name: str
    project_path: str
    target_stack: str
    output_directory: str
    generated_files: list[GeneratedFile]
    findings: list[Finding]
    summary: str


class ProjectReport(BaseModel):
    id: str
    name: str
    path: str
    source_type: str = "local_folder"
    repository_url: str | None = None
    status: str = "complete"
    created_at: datetime
    languages: dict[str, int]
    findings: list[Finding]
    roadmap: list[RoadmapStep]
    recommendations: list[MigrationRecommendation] = []
    summary: str

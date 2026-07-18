from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import AnalyzeRequest, ProjectReport
from .services import default_roadmap, new_id, claude_roadmap, persist_report
from .workflow import analysis_workflow

app = FastAPI(title="O2N Engine API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Add this endpoint
@app.get("/")
def root():
    return {
        "message": "O2N Engine Backend Running",
        "status": "success",
        "docs": "/docs",
        "health": "/health"
    }

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/v1/projects/analyze", response_model=ProjectReport)
def analyze_project(request: AnalyzeRequest):
    root = Path(request.path).resolve()

    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail="The provided project path does not exist or is not a folder.",
        )

    project_id = new_id()

    state = analysis_workflow.invoke(
        {
            "project_id": project_id,
            "path": str(root),
            "target_stack": request.target_stack,
            "files": [],
            "languages": {},
            "findings": [],
        }
    )

    languages = state["languages"]

    report = ProjectReport(
        id=project_id,
        name=request.name,
        path=str(root),
        created_at=datetime.now(timezone.utc),
        languages=languages,
        findings=state["findings"],
        roadmap=claude_roadmap(
            languages,
            state["findings"],
            request.target_stack,
            settings.anthropic_api_key,
        ),
        summary=f"Scanned {len(state['files'])} source files across {len(languages)} language(s).",
    )

    persist_report(
        report.model_dump(mode="json"),
        settings.mongodb_uri,
        settings.mongodb_database,
    )

    return report
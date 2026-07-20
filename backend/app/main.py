from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .models import AnalyzeRequest, ConversionReport, ConvertProjectRequest, GitHubAnalyzeRequest, ProjectReport
from .services import (
    CONVERSION_TARGETS,
    ConversionError,
    RepositoryError,
    claude_conversion,
    claude_roadmap,
    clone_public_github_repository,
    migration_recommendations,
    new_id,
    persist_report,
    selected_source_files,
    semgrep_findings,
    tree_sitter_inventory,
    write_conversion,
)
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


@app.get("/api/v1/conversion-targets")
def conversion_targets():
    """Return target-stack presets for a frontend dropdown; custom values remain supported."""
    return {"targets": CONVERSION_TARGETS, "custom_target_supported": True}


def build_project_report(
    name: str,
    root: Path,
    target_stack: str,
    project_id: str,
    source_type: str,
    repository_url: str | None = None,
) -> ProjectReport:
    state = analysis_workflow.invoke(
        {
            "project_id": project_id,
            "path": str(root),
            "target_stack": target_stack,
            "files": [],
            "languages": {},
            "findings": [],
        }
    )

    languages = state["languages"]

    report = ProjectReport(
        id=project_id,
        name=name,
        path=str(root),
        source_type=source_type,
        repository_url=repository_url,
        created_at=datetime.now(timezone.utc),
        languages=languages,
        findings=state["findings"],
        recommendations=migration_recommendations(state["files"]),
        roadmap=claude_roadmap(
            languages,
            state["findings"],
            target_stack,
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


@app.post("/api/v1/projects/analyze", response_model=ProjectReport)
def analyze_project(request: AnalyzeRequest):
    root = Path(request.path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail="The provided project path does not exist or is not a folder.",
        )
    return build_project_report(
        name=request.name,
        root=root,
        target_stack=request.target_stack,
        project_id=new_id(),
        source_type="local_folder",
    )


@app.post("/api/v1/projects/analyze/github", response_model=ProjectReport)
def analyze_github_project(request: GitHubAnalyzeRequest):
    """Clone a public GitHub repository and analyze its checked-out source code."""
    project_id = new_id()
    try:
        root = clone_public_github_repository(
            request.repository_url,
            settings.repository_workspace,
            project_id,
        )
    except RepositoryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return build_project_report(
        name=request.name,
        root=root,
        target_stack=request.target_stack,
        project_id=project_id,
        source_type="github_repository",
        repository_url=request.repository_url,
    )


@app.post("/api/v1/projects/convert", response_model=ConversionReport)
def convert_project(request: ConvertProjectRequest):
    """Convert selected files to a separate generated folder; never mutate the source project."""
    root = Path(request.path).resolve()
    if not root.is_dir():
        raise HTTPException(status_code=400, detail="The provided project path does not exist or is not a folder.")

    conversion_id = new_id()
    output_directory = (
        Path(request.output_directory).expanduser().resolve()
        if request.output_directory
        else root.parent / f"{root.name}_converted_{conversion_id[:8]}"
    )
    try:
        output_directory.relative_to(root)
        raise HTTPException(status_code=400, detail="Output directory must be outside the source project.")
    except ValueError:
        pass

    try:
        source_files = selected_source_files(root, request.source_paths)
        generated_files = claude_conversion(root, source_files, request.target_stack, settings.anthropic_api_key)
        write_conversion(output_directory, generated_files)
    except ConversionError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    generated_paths = [output_directory / file.path for file in generated_files]
    findings = tree_sitter_inventory(generated_paths) + semgrep_findings(output_directory)
    return ConversionReport(
        id=conversion_id,
        name=request.name,
        project_path=str(root),
        target_stack=request.target_stack,
        output_directory=str(output_directory),
        generated_files=generated_files,
        findings=findings,
        summary=f"Generated {len(generated_files)} file(s) from {len(source_files)} selected source file(s).",
    )
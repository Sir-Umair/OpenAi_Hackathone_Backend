import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
    extract_zip_securely,
    find_project_root,
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


import asyncio
import logging
import time

logger = logging.getLogger(__name__)

async def analyze_project(
    project_directory: Path,
    name: str,
    target_stack: str,
    project_id: str,
    source_type: str,
    repository_url: str | None = None,
) -> ProjectReport:
    """Core analysis pipeline shared across all endpoints."""
    logger.info(f"Analysis started for project {project_id} from {source_type}")
    start_time = time.time()

    def run_workflow():
        return analysis_workflow.invoke(
            {
                "project_id": project_id,
                "path": str(project_directory),
                "target_stack": target_stack,
                "files": [],
                "languages": {},
                "findings": [],
            }
        )

    state = await asyncio.to_thread(run_workflow)
    languages = state["languages"]

    report = ProjectReport(
        id=project_id,
        name=name,
        path=str(project_directory),
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

    await asyncio.to_thread(
        persist_report,
        report.model_dump(mode="json"),
        settings.mongodb_uri,
        settings.mongodb_database,
    )

    logger.info(f"Analysis completed for project {project_id} in {time.time() - start_time:.2f}s")
    return report


@app.post("/api/v1/projects/analyze", response_model=ProjectReport)
async def analyze_local_project(request: AnalyzeRequest):
    root = Path(request.path).expanduser().resolve()
    if not root.is_dir():
        raise HTTPException(
            status_code=400,
            detail="The provided project path does not exist or is not a folder.",
        )
    return await analyze_project(
        project_directory=root,
        name=request.name,
        target_stack=request.target_stack,
        project_id=new_id(),
        source_type="local_folder",
    )


@app.post("/api/v1/projects/analyze/github", response_model=ProjectReport)
async def analyze_github_project(request: GitHubAnalyzeRequest):
    """Clone a public GitHub repository and analyze its checked-out source code."""
    project_id = new_id()
    try:
        root = await asyncio.to_thread(
            clone_public_github_repository,
            request.repository_url,
            settings.repository_workspace,
            project_id,
        )
    except RepositoryError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    
    return await analyze_project(
        project_directory=root,
        name=request.name,
        target_stack=request.target_stack,
        project_id=project_id,
        source_type="github_repository",
        repository_url=request.repository_url,
    )


@app.post("/api/v1/projects/analyze/upload", response_model=ProjectReport)
async def analyze_uploaded_project(
    name: str = Form(...),
    target_stack: str = Form("Next.js + FastAPI"),
    file: UploadFile = File(...)
):
    """Receive a ZIP file upload, extract it securely to a temporary workspace, and analyze it."""
    if not file.filename.endswith(".zip") and file.content_type not in ["application/zip", "application/x-zip-compressed"]:
        raise HTTPException(status_code=400, detail="Uploaded file must be a ZIP archive.")

    project_id = new_id()
    logger.info(f"Upload started for project {project_id}")
    
    # We will stream the file to a temporary location to enforce size limits safely
    total_size = 0
    
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            temp_path = Path(tmpdir)
            zip_file_path = temp_path / "uploaded.zip"
            
            with open(zip_file_path, "wb") as buffer:
                while chunk := await file.read(1024 * 1024):  # 1MB chunks
                    total_size += len(chunk)
                    if total_size > settings.max_upload_size_bytes:
                        raise HTTPException(status_code=413, detail=f"File exceeds maximum allowed size of {settings.max_upload_size_bytes} bytes.")
                    buffer.write(chunk)
            
            logger.info(f"ZIP validation started for project {project_id} ({total_size} bytes)")
            
            try:
                await asyncio.to_thread(extract_zip_securely, zip_file_path, temp_path)
            except ValueError as error:
                logger.error(f"ZIP extraction failed: {error}")
                raise HTTPException(status_code=400, detail=str(error))
                
            project_root = find_project_root(temp_path)
            
            report = await analyze_project(
                project_directory=project_root,
                name=name,
                target_stack=target_stack,
                project_id=project_id,
                source_type="zip_upload",
            )
            
            logger.info(f"Temporary files automatically deleted for project {project_id}")
            return report
            
    except HTTPException:
        raise
    except Exception as error:
        logger.exception(f"Failed to process uploaded ZIP for project {project_id}")
        raise HTTPException(status_code=500, detail=f"Failed to process uploaded ZIP: {error}")


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
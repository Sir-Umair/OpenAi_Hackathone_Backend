from __future__ import annotations

import io
import json
import logging
import shutil
import subprocess
import time
import zipfile
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

logger = logging.getLogger(__name__)

from .models import Finding, GeneratedFile, MigrationRecommendation, RoadmapStep

LANGUAGE_SUFFIXES = {
    ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".py": "Python", ".java": "Java", ".cs": "C#", ".php": "PHP", ".rb": "Ruby",
    ".go": "Go", ".c": "C", ".cpp": "C++", ".h": "C/C++",
}
IGNORED_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv", "vendor"}
CONVERSION_TARGETS = [
    "Next.js + FastAPI",
    "React + Node.js/Express",
    "React + Django",
    "Vue + FastAPI",
    "Angular + Spring Boot",
    "Laravel",
    "Django",
    "FastAPI",
    "Node.js/Express",
    ".NET Web API",
    "Java Spring Boot",
]


class ConversionError(ValueError):
    """Raised when a conversion cannot be generated safely."""


class RepositoryError(ValueError):
    """Raised when a GitHub repository cannot be cloned safely."""

def source_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in LANGUAGE_SUFFIXES and not any(x in IGNORED_DIRS for x in p.parts)]

def detect_languages(files: list[Path]) -> dict[str, int]:
    return dict(Counter(LANGUAGE_SUFFIXES[p.suffix.lower()] for p in files))


def migration_recommendations(files: list[Path]) -> list[MigrationRecommendation]:
    """Suggest modern targets only for detected legacy technologies or patterns."""
    suffixes = {file.suffix.lower() for file in files}
    recommendations: list[MigrationRecommendation] = []
    if ".php" in suffixes:
        recommendations.append(MigrationRecommendation(
            current_technology="PHP",
            reason="PHP source files were detected; modern API boundaries can simplify an incremental migration.",
            recommended_targets=["FastAPI", "Laravel", "Node.js/Express"],
        ))
    javascript_files = [file for file in files if file.suffix.lower() in {".js", ".jsx"}]
    if any("jquery" in file.read_text(encoding="utf-8", errors="ignore").lower() or "$(" in file.read_text(encoding="utf-8", errors="ignore") for file in javascript_files[:100]):
        recommendations.append(MigrationRecommendation(
            current_technology="jQuery",
            reason="jQuery-style DOM manipulation was detected in JavaScript files.",
            recommended_targets=["React", "Next.js", "Vue"],
        ))
    python_files = [file for file in files if file.suffix.lower() == ".py"]
    if any("xrange(" in file.read_text(encoding="utf-8", errors="ignore") or "raw_input(" in file.read_text(encoding="utf-8", errors="ignore") for file in python_files[:100]):
        recommendations.append(MigrationRecommendation(
            current_technology="Python 2 patterns",
            reason="Python 2-only APIs were detected.",
            recommended_targets=["Python 3 + FastAPI", "Python 3 + Django"],
        ))
    return recommendations

def tree_sitter_inventory(files: list[Path]) -> list[Finding]:
    """Use Tree-sitter syntax parsing where the optional language pack is present.
    Returns an empty list when the parser is unavailable — no dummy findings surfaced to the user."""
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser("python")
        invalid = [p for p in files if p.suffix == ".py" and parser.parse(p.read_bytes()).root_node.has_error]
        return [Finding(severity="medium", category="syntax", message="Tree-sitter found a syntax error", file=str(p)) for p in invalid]
    except Exception:
        logger.info("Tree-sitter language pack unavailable; skipping semantic parsing.")
        return []

def semgrep_findings(root: Path) -> list[Finding]:
    """Run Semgrep security rules against the project root. Returns an empty list if Semgrep is
    not installed or times out — the caller should not surface a dummy finding to the user."""
    try:
        completed = subprocess.run(
            ["semgrep", "scan", "--config=auto", "--json", str(root)],
            capture_output=True, text=True, timeout=120,
        )
        payload = json.loads(completed.stdout or "{}")
        return [
            Finding(
                severity=item.get("extra", {}).get("severity", "info").lower(),
                category="security",
                message=item.get("extra", {}).get("message", "Semgrep finding"),
                file=item.get("path"),
            )
            for item in payload.get("results", [])
        ]
    except FileNotFoundError:
        logger.info("Semgrep is not installed; skipping security scan.")
        return []
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        logger.warning("Semgrep scan failed: %s", exc)
        return []

def default_roadmap(languages: dict[str, int], target: str) -> list[RoadmapStep]:
    source = ", ".join(languages) or "the existing application"
    return [
        RoadmapStep(phase="1. Baseline", action="Add tests and capture current behavior", rationale="Protect business logic before changing the migration surface."),
        RoadmapStep(phase="2. Architecture", action=f"Define incremental boundaries toward {target}", rationale=f"Move {source} in independently verifiable slices."),
        RoadmapStep(phase="3. Modernize", action="Refactor highest-risk modules behind adapters", rationale="Reduces blast radius and supports rollback."),
        RoadmapStep(phase="4. Validate", action="Run tests, Semgrep, and manual review on generated diffs", rationale="AI-proposed changes require deterministic verification."),
    ]

def claude_roadmap(languages: dict[str, int], findings: list[Finding], target: str, api_key: str | None) -> list[RoadmapStep]:
    """Ask Claude for a concise plan, while retaining a deterministic offline fallback."""
    fallback = default_roadmap(languages, target)
    if not api_key:
        return fallback
    prompt = {
        "current_languages": languages,
        "findings": [item.model_dump() for item in findings[:15]],
        "target_stack": target,
        "instruction": "Return JSON only: an array of up to 5 objects with phase, action, rationale. Favor safe incremental modernization.",
    }
    try:
        from anthropic import Anthropic
        message = Anthropic(api_key=api_key).messages.create(
            model="claude-3-5-sonnet-20241022", max_tokens=900,
            messages=[{"role": "user", "content": json.dumps(prompt)}],
        )
        content = message.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
        return [RoadmapStep.model_validate(item) for item in json.loads(content)]
    except Exception:
        return fallback


def selected_source_files(root: Path, source_paths: list[str]) -> list[Path]:
    """Resolve user-selected project-relative files without permitting path traversal."""
    selected: list[Path] = []
    for source_path in source_paths:
        candidate = (root / source_path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ConversionError(f"Source path escapes the project directory: {source_path}") from error
        if not candidate.exists():
            raise ConversionError(f"Source path does not exist: {source_path}")
        files = source_files(candidate) if candidate.is_dir() else [candidate]
        selected.extend(file for file in files if file.suffix.lower() in LANGUAGE_SUFFIXES)
    return list(dict.fromkeys(selected))


# Stack-specific guidance injected into every conversion prompt so Claude produces
# idiomatic, runnable code rather than a generic rewrite.
_STACK_HINTS: dict[str, str] = {
    "Next.js + FastAPI": (
        "Frontend: use Next.js 14 App Router conventions — pages go in app/<route>/page.tsx, "
        "shared components in components/, API calls via fetch or axios from client components. "
        "Backend: use FastAPI with Pydantic v2 models, APIRouter, and dependency injection; "
        "routes go in routers/<domain>.py and are registered in main.py via app.include_router()."
    ),
    "React + Node.js/Express": (
        "Frontend: functional React components with hooks; files in src/components/ and src/pages/. "
        "Backend: Express 4 with async/await, routes in routes/<domain>.js, middleware in middleware/."
    ),
    "React + Django": (
        "Frontend: functional React components, files in frontend/src/. "
        "Backend: Django 4 with Django REST Framework; serializers in serializers.py, views in views.py, "
        "URLs registered in urls.py."
    ),
    "Vue + FastAPI": (
        "Frontend: Vue 3 Composition API with <script setup>; single-file components in src/components/. "
        "Backend: FastAPI with Pydantic v2, APIRouter, routes in routers/."
    ),
    "Angular + Spring Boot": (
        "Frontend: Angular 17 standalone components using signals; files in src/app/. "
        "Backend: Spring Boot 3 with @RestController, @Service, and @Repository layers."
    ),
    "Django": (
        "Django 4 monolith: models in models.py, views in views.py, serializers in serializers.py "
        "(DRF), URLs in urls.py. Use class-based views where appropriate."
    ),
    "FastAPI": (
        "FastAPI with Pydantic v2; routes grouped in routers/<domain>.py, registered in main.py. "
        "Use async def for I/O-bound handlers and Depends() for shared dependencies."
    ),
    "Laravel": (
        "Laravel 10: controllers in app/Http/Controllers/, models in app/Models/, "
        "routes in routes/api.php, validation via Form Requests."
    ),
    "Node.js/Express": (
        "Express 4 with ESM; routes in routes/, middleware in middleware/, "
        "controllers in controllers/, async/await throughout."
    ),
    ".NET Web API": (
        ".NET 8 minimal API or controller-based Web API; "
        "controllers in Controllers/, models in Models/, DTOs in DTOs/."
    ),
    "Java Spring Boot": (
        "Spring Boot 3 with @RestController, @Service, @Repository; "
        "entities in model/, DTOs in dto/, repositories extending JpaRepository."
    ),
}

_SYSTEM_PROMPT = (
    "You are an expert code modernization engine. "
    "Your sole task is to convert legacy source files to a new technology stack. "
    "Rules you MUST follow:\n"
    "1. Output ONLY a valid JSON array — no markdown fences, no prose, no explanations.\n"
    "2. Each element must have exactly two keys: \"path\" (relative, no '..', no leading slash) "
    "and \"content\" (the full converted file content as a string).\n"
    "3. Use idiomatic conventions of the target stack (correct file names, folder structure, "
    "imports, and patterns).\n"
    "4. Preserve all business logic from the source while adapting it to the target stack.\n"
    "5. Generate only the files required for this conversion slice — do not invent extra files."
)


def claude_conversion(root: Path, files: list[Path], target_stack: str, api_key: str | None) -> list[GeneratedFile]:
    """Generate a bounded file conversion and validate every returned output path."""
    if not api_key:
        raise ConversionError("ANTHROPIC_API_KEY is required to generate converted code.")
    if not files:
        raise ConversionError("No supported source files were selected for conversion.")
    if len(files) > 20:
        raise ConversionError("Select at most 20 source files per conversion request.")

    source = [
        {
            "path": str(file.relative_to(root)).replace("\\", "/"),
            "content": file.read_text(encoding="utf-8", errors="ignore")[:12000],
        }
        for file in files
    ]

    stack_hint = _STACK_HINTS.get(target_stack, "")
    user_content = json.dumps({
        "target_stack": target_stack,
        "stack_conventions": stack_hint,
        "source_files": source,
        "instruction": (
            f"Convert the source files above to {target_stack}. "
            f"Follow the stack conventions exactly. "
            "Return a JSON array where each object has 'path' and 'content'. "
            "Paths must be relative, must not contain '..', and must not be absolute."
        ),
    })

    try:
        from anthropic import Anthropic
        message = Anthropic(api_key=api_key).messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=8000,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_content}],
        )
        raw = message.content[0].text.strip()
        # Strip any accidental markdown fences Claude may still emit
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0].strip()
        generated = [GeneratedFile.model_validate(item) for item in json.loads(raw)]
    except Exception as error:
        logger.exception("Claude conversion error: %s", error)
        raise ConversionError(f"AI conversion error: {error}") from error

    if not generated:
        raise ConversionError("The AI conversion did not return any files.")
    for gfile in generated:
        output_path = Path(gfile.path)
        if output_path.is_absolute() or ".." in output_path.parts:
            raise ConversionError(f"The AI returned an unsafe output path: {gfile.path}")
    return generated


def write_conversion(output_directory: Path, files: list[GeneratedFile]) -> None:
    """Write generated files only to a new output directory."""
    if output_directory.exists():
        raise ConversionError("Output directory already exists; choose a new empty location.")
    output_directory.mkdir(parents=True)
    for file in files:
        destination = output_directory / file.path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(file.content, encoding="utf-8")


def clone_public_github_repository(repository_url: str, workspace: str, project_id: str) -> Path:
    """Clone a public GitHub repository into the backend-managed workspace."""
    parsed = urlparse(repository_url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() not in {"github.com", "www.github.com"}
        or len(path_parts) != 2
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RepositoryError("Use a public HTTPS GitHub URL such as https://github.com/owner/repository.")

    repository_name = path_parts[1].removesuffix(".git")
    if not repository_name:
        raise RepositoryError("GitHub repository URL is invalid.")
    destination = Path(workspace).resolve() / f"{repository_name}_{project_id[:8]}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        from git import Repo
        Repo.clone_from(repository_url, destination, depth=1)
    except Exception as error:
        logger.exception("Failed to clone repository")
        shutil.rmtree(destination, ignore_errors=True)
        raise RepositoryError("GitHub repository could not be cloned. Confirm it is public and the URL is correct.") from error
    return destination

def persist_report(report: dict, uri: str, database: str) -> None:
    """Store reports in MongoDB if it is configured and reachable."""
    try:
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=1500)
        client.admin.command("ping")
        client[database].projects.replace_one({"id": report["id"]}, report, upsert=True)
        client.close()
    except Exception:
        pass

def store_embeddings(project_id: str, files: list[Path], chroma_path: str) -> None:
    """Persist lightweight semantic search documents in Chroma when optional services are available."""
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer
        client = chromadb.PersistentClient(path=chroma_path)
        collection = client.get_or_create_collection("code_chunks")
        docs = [p.read_text(encoding="utf-8", errors="ignore")[:4000] for p in files[:100]]
        if docs:
            vectors = SentenceTransformer("all-MiniLM-L6-v2").encode(docs).tolist()
            collection.upsert(ids=[f"{project_id}:{n}" for n in range(len(docs))], documents=docs, embeddings=vectors, metadatas=[{"project_id": project_id, "path": str(p)} for p in files[:100]])
    except Exception:
        pass

def new_id() -> str:
    return str(uuid4())

def extract_zip_securely(file_path: Path, extract_to: Path) -> None:
    """Extract a ZIP file securely, preventing Zip Slip path traversal."""
    extract_to = extract_to.resolve()
    logger.info(f"Extraction started to {extract_to}")
    start_time = time.time()
    try:
        with zipfile.ZipFile(file_path, 'r') as zf:
            infolist = zf.infolist()
            if not infolist:
                raise ValueError("Uploaded ZIP archive is empty.")
            
            for member in infolist:
                # Resolve the intended absolute path of the extracted file
                target_path = (extract_to / member.filename).resolve()
                # Ensure it falls strictly within the target directory
                if extract_to not in target_path.parents and target_path != extract_to:
                    raise ValueError(f"Zip slip vulnerability detected in file: {member.filename}")
            
            zf.extractall(extract_to)
    except zipfile.BadZipFile as e:
        raise ValueError("Uploaded file is not a valid ZIP archive or is corrupted.") from e
        
    logger.info(f"Extraction completed in {time.time() - start_time:.2f}s")


def find_project_root(extracted_dir: Path) -> Path:
    """
    Intelligently locate the project root.
    If the ZIP contains a single top-level folder, assume that's the root.
    Otherwise, the extraction directory itself is the root.
    """
    contents = list(extracted_dir.iterdir())
    # If there is exactly one item and it is a directory, it's a wrapper folder
    if len(contents) == 1 and contents[0].is_dir():
        root = contents[0]
        logger.info(f"Project root detected inside wrapper folder: {root.name}")
        return root
    
    logger.info(f"Project root detected at extraction root")
    return extracted_dir

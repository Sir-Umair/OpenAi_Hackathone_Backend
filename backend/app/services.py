from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path
from uuid import uuid4

from .models import Finding, RoadmapStep

LANGUAGE_SUFFIXES = {
    ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".py": "Python", ".java": "Java", ".cs": "C#", ".php": "PHP", ".rb": "Ruby",
    ".go": "Go", ".c": "C", ".cpp": "C++", ".h": "C/C++",
}
IGNORED_DIRS = {"node_modules", ".git", ".next", "dist", "build", ".venv", "vendor"}

def source_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in LANGUAGE_SUFFIXES and not any(x in IGNORED_DIRS for x in p.parts)]

def detect_languages(files: list[Path]) -> dict[str, int]:
    return dict(Counter(LANGUAGE_SUFFIXES[p.suffix.lower()] for p in files))

def tree_sitter_inventory(files: list[Path]) -> list[Finding]:
    """Use Tree-sitter syntax parsing where the optional language pack is present."""
    try:
        from tree_sitter_language_pack import get_parser
        parser = get_parser("python")
        invalid = [p for p in files if p.suffix == ".py" and parser.parse(p.read_bytes()).root_node.has_error]
        return [Finding(severity="medium", category="syntax", message="Tree-sitter found a syntax error", file=str(p)) for p in invalid]
    except Exception:
        return [Finding(severity="info", category="parser", message="Tree-sitter parser unavailable; semantic parsing was skipped")]

def semgrep_findings(root: Path) -> list[Finding]:
    try:
        completed = subprocess.run(["semgrep", "scan", "--config=auto", "--json", str(root)], capture_output=True, text=True, timeout=120)
        payload = json.loads(completed.stdout or "{}")
        return [Finding(severity=item.get("extra", {}).get("severity", "info").lower(), category="security", message=item.get("extra", {}).get("message", "Semgrep finding"), file=item.get("path")) for item in payload.get("results", [])]
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return [Finding(severity="info", category="security", message="Semgrep is not available; install it to run security rules")]

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
            model="claude-sonnet-4-20250514", max_tokens=900,
            messages=[{"role": "user", "content": json.dumps(prompt)}],
        )
        content = message.content[0].text.strip().removeprefix("```json").removesuffix("```").strip()
        return [RoadmapStep.model_validate(item) for item in json.loads(content)]
    except Exception:
        return fallback

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

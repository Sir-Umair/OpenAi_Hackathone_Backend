from typing import TypedDict
from pathlib import Path
from langgraph.graph import END, START, StateGraph

from .config import settings
from .services import detect_languages, semgrep_findings, source_files, store_embeddings, tree_sitter_inventory

class AnalysisState(TypedDict):
    project_id: str
    path: str
    target_stack: str
    files: list[Path]
    languages: dict[str, int]
    findings: list

def collect(state: AnalysisState):
    root = Path(state["path"])
    return {"files": source_files(root)}

def analyze(state: AnalysisState):
    return {"languages": detect_languages(state["files"]), "findings": tree_sitter_inventory(state["files"]) + semgrep_findings(Path(state["path"]))}

def embed(state: AnalysisState):
    store_embeddings(state["project_id"], state["files"], settings.chroma_path)
    return {}

graph = StateGraph(AnalysisState)
graph.add_node("collect", collect)
graph.add_node("analyze", analyze)
graph.add_node("embed", embed)
graph.add_edge(START, "collect")
graph.add_edge("collect", "analyze")
graph.add_edge("analyze", "embed")
graph.add_edge("embed", END)
analysis_workflow = graph.compile()

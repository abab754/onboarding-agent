"""MCP resources — passive context the LLM can read without calling a tool."""

import json

from onboarding_agent.server import mcp, get_current_repo_path
from onboarding_agent.tools.ingest import ingest_repo
from onboarding_agent.tools.analysis import get_overview
from onboarding_agent.tools.search import get_architecture


@mcp.resource("repo://overview")
def resource_overview() -> str:
    """High-level project summary: languages, frameworks, entry points, and structure."""
    if not get_current_repo_path():
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = get_overview(get_current_repo_path())
    return json.dumps(result, indent=2)


@mcp.resource("repo://structure")
def resource_structure() -> str:
    """File tree of the project."""
    if not get_current_repo_path():
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = ingest_repo(get_current_repo_path())
    return json.dumps(result, indent=2)


@mcp.resource("repo://dependencies")
def resource_dependencies() -> str:
    """Dependency/import graph showing how files and modules connect."""
    if not get_current_repo_path():
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = get_architecture(get_current_repo_path())
    return json.dumps(result, indent=2)

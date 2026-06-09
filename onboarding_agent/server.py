"""MCP server instance and global state."""

from pathlib import Path

from mcp.server.fastmcp import FastMCP

from onboarding_agent.knowledge_graph import KnowledgeGraph

mcp = FastMCP("onboarding-agent")

# Global state — tracks the currently analyzed repo and its knowledge graph.
_graph: KnowledgeGraph | None = None
_current_repo_path: str | None = None


def get_current_repo_path() -> str | None:
    """Return the currently active repo path."""
    return _current_repo_path


def set_current_repo_path(path: str) -> None:
    """Set the currently active repo path."""
    global _current_repo_path
    _current_repo_path = path


def get_or_create_graph(repo_path: str) -> KnowledgeGraph:
    """Get the current graph or create one backed by a file in the target repo."""
    global _graph, _current_repo_path
    storage = Path(repo_path) / ".onboarding_agent" / "graph.json"
    if _graph is None or _graph.storage_path != storage:
        _graph = KnowledgeGraph(str(storage))
        _current_repo_path = str(Path(repo_path).resolve())
    return _graph

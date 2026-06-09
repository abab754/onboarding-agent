"""Tools for building and querying the knowledge graph."""

from pathlib import Path

from onboarding_agent.server import mcp, get_or_create_graph
from onboarding_agent.constants import EXTENSION_TO_LANGUAGE
from onboarding_agent.helpers import extract_python_symbols
from onboarding_agent.tools.ingest import ingest_repo


def _populate_graph(graph, tree: dict, root_path: str, current_path: str) -> None:
    """Recursively walk the file tree and add entities + relationships to the graph."""
    for name, info in tree.items():
        if not isinstance(info, dict):
            continue

        full_path = f"{current_path}/{name}"

        if info.get("type") == "directory":
            graph.add_entity(full_path, "module", name, {"path": full_path})
            graph.add_relationship(current_path, full_path, "contains")

            children = info.get("children")
            if isinstance(children, dict):
                _populate_graph(graph, children, root_path, full_path)

        elif info.get("type") == "file":
            ext = Path(name).suffix.lower()
            language = EXTENSION_TO_LANGUAGE.get(ext, "Unknown")

            graph.add_entity(full_path, "file", name, {
                "path": full_path,
                "size": info.get("size", 0),
                "language": language,
            })
            graph.add_relationship(current_path, full_path, "contains")

            if ext == ".py":
                try:
                    content = Path(full_path).read_text(encoding="utf-8")
                    symbols = extract_python_symbols(content)

                    for func_name in symbols["functions"]:
                        func_id = f"{full_path}::{func_name}"
                        graph.add_entity(func_id, "function", func_name, {"file": full_path})
                        graph.add_relationship(full_path, func_id, "contains")

                    for class_name in symbols["classes"]:
                        class_id = f"{full_path}::{class_name}"
                        graph.add_entity(class_id, "class", class_name, {"file": full_path})
                        graph.add_relationship(full_path, class_id, "contains")

                    for imp in symbols["imports"]:
                        if imp.startswith("from "):
                            module = imp.split()[1]
                        else:
                            module = imp.split()[1].split(",")[0]
                        graph.add_relationship(full_path, module, "imports")

                except Exception:
                    pass


@mcp.tool()
def build_knowledge_graph(repo_path: str) -> dict:
    """Analyze a repository and build a knowledge graph of its entities and relationships.

    Extracts files, functions, classes, modules, and their relationships (contains,
    imports). The graph is saved to .onboarding_agent/graph.json inside the repo.

    Args:
        repo_path: Absolute path to a local repository directory.

    Returns:
        A dict with graph statistics (entity counts, relationship counts by type).
    """
    repo = ingest_repo(repo_path)
    if "error" in repo:
        return repo

    graph = get_or_create_graph(repo["root_path"])
    graph.clear()

    root = repo["root_path"]
    graph.add_entity(root, "module", repo["repo_name"], {"path": root})

    _populate_graph(graph, repo["tree"], root, root)
    graph.save()

    return {
        "status": "success",
        "repo": repo["repo_name"],
        **graph.stats(),
    }


@mcp.tool()
def query_entities(repo_path: str, entity_type: str | None = None, name_contains: str | None = None) -> dict:
    """Search the knowledge graph for entities by type and/or name.

    Args:
        repo_path: Absolute path to the repo (to locate the graph).
        entity_type: Filter by type — "file", "function", "class", or "module".
        name_contains: Filter by substring match on entity name.

    Returns:
        A dict with matching entities and the total count.
    """
    graph = get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    results = graph.find_entities(entity_type=entity_type, name_contains=name_contains)
    return {"count": len(results), "entities": results}


@mcp.tool()
def query_relationships(
    repo_path: str,
    source: str | None = None,
    target: str | None = None,
    rel_type: str | None = None,
) -> dict:
    """Search the knowledge graph for relationships between entities.

    Args:
        repo_path: Absolute path to the repo (to locate the graph).
        source: Filter by source entity id.
        target: Filter by target entity id.
        rel_type: Filter by relationship type — "contains", "imports", etc.

    Returns:
        A dict with matching relationships and the total count.
    """
    graph = get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    results = graph.find_relationships(source=source, target=target, rel_type=rel_type)
    return {"count": len(results), "relationships": results}

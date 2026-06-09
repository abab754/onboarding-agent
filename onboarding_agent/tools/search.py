"""Tools for searching code, viewing architecture, and answering questions."""

from onboarding_agent.server import mcp, get_or_create_graph
from onboarding_agent.tools.ingest import read_file
from onboarding_agent.tools.analysis import get_overview
from onboarding_agent.tools.graph import build_knowledge_graph


@mcp.tool()
def find_relevant_code(repo_path: str, query: str) -> dict:
    """Given a topic or question, find the most relevant files, functions, and classes in the codebase.

    Searches entity names, file paths, and import statements in the knowledge graph.
    Returns matching entities ranked by relevance, plus the content of the top matching files.

    Args:
        repo_path: Absolute path to the repo.
        query: A topic, keyword, or question (e.g., "authentication", "database", "error handling").

    Returns:
        A dict with matching entities grouped by type and content of top file matches.
    """
    graph = get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    query_lower = query.lower()
    query_terms = query_lower.split()

    scored: list[tuple[float, dict]] = []
    for entity in graph.entities.values():
        score = 0.0
        name_lower = entity["name"].lower()
        id_lower = entity["id"].lower()
        meta_str = str(entity.get("metadata", {})).lower()

        for term in query_terms:
            if term in name_lower:
                score += 3.0
            if term in id_lower:
                score += 1.0
            if term in meta_str:
                score += 0.5

        if entity["type"] == "file" and score > 0:
            score += 1.0

        if score > 0:
            scored.append((score, entity))

    for rel in graph.relationships:
        if rel["type"] == "imports":
            target_lower = rel["target"].lower()
            for term in query_terms:
                if term in target_lower:
                    source_entity = graph.get_entity(rel["source"])
                    if source_entity:
                        scored.append((2.0, source_entity))

    seen: set[str] = set()
    unique_scored: list[tuple[float, dict]] = []
    for score, entity in sorted(scored, key=lambda x: -x[0]):
        if entity["id"] not in seen:
            seen.add(entity["id"])
            unique_scored.append((score, entity))

    results: dict[str, list[dict]] = {"files": [], "functions": [], "classes": [], "modules": []}
    for score, entity in unique_scored[:20]:
        entry = {**entity, "relevance_score": score}
        bucket = entity["type"] + "s" if entity["type"] + "s" in results else "files"
        results.get(bucket, results["files"]).append(entry)

    file_contents: list[dict] = []
    for score, entity in unique_scored[:5]:
        if entity["type"] == "file":
            path = entity.get("metadata", {}).get("path", entity["id"])
            content = read_file(path)
            if "error" not in content:
                file_contents.append({
                    "file": path,
                    "content": content["content"],
                })

    return {
        "query": query,
        "total_matches": len(unique_scored),
        "results": results,
        "top_file_contents": file_contents,
    }


@mcp.tool()
def get_architecture(repo_path: str) -> dict:
    """Return the architectural view of the codebase: how modules and files connect via imports.

    Args:
        repo_path: Absolute path to the repo.

    Returns:
        A dict with the import graph, module structure, and key architectural observations.
    """
    graph = get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    import_rels = graph.find_relationships(rel_type="imports")
    import_graph: dict[str, list[str]] = {}
    for rel in import_rels:
        source = rel["source"]
        target = rel["target"]
        if source not in import_graph:
            import_graph[source] = []
        import_graph[source].append(target)

    contains_rels = graph.find_relationships(rel_type="contains")
    module_structure: dict[str, list[str]] = {}
    for rel in contains_rels:
        source_entity = graph.get_entity(rel["source"])
        target_entity = graph.get_entity(rel["target"])
        if source_entity and source_entity["type"] == "module" and target_entity:
            if rel["source"] not in module_structure:
                module_structure[rel["source"]] = []
            module_structure[rel["source"]].append({
                "id": rel["target"],
                "name": target_entity["name"],
                "type": target_entity["type"],
            })

    import_counts: dict[str, int] = {}
    for targets in import_graph.values():
        for target in targets:
            import_counts[target] = import_counts.get(target, 0) + 1
    most_imported = sorted(import_counts.items(), key=lambda x: -x[1])[:10]

    most_importing = sorted(
        [(f, len(targets)) for f, targets in import_graph.items()],
        key=lambda x: -x[1],
    )[:10]

    return {
        "import_graph": import_graph,
        "module_structure": module_structure,
        "most_depended_on": [{"module": m, "imported_by_count": c} for m, c in most_imported],
        "highest_coupling": [{"file": f, "import_count": c} for f, c in most_importing],
        "stats": graph.stats(),
    }


@mcp.tool()
def ask(repo_path: str, question: str) -> dict:
    """Answer a freeform question about the codebase by gathering relevant context.

    Combines the knowledge graph, file contents, and project overview into a context
    bundle that the LLM can use to answer any onboarding question.

    Args:
        repo_path: Absolute path to the repo.
        question: Any question about the codebase (e.g., "how is auth handled?", "what does server.py do?").

    Returns:
        A dict with the question, relevant context gathered from the graph, and project overview.
    """
    graph = get_or_create_graph(repo_path)

    if not graph.entities:
        build_result = build_knowledge_graph(repo_path)
        if "error" in build_result:
            return build_result

    overview = get_overview(repo_path)
    relevant = find_relevant_code(repo_path, question)

    connections: list[dict] = []
    if relevant.get("top_file_contents"):
        for fc in relevant["top_file_contents"][:3]:
            file_path = fc["file"]
            neighbors = graph.get_neighbors(file_path)
            if neighbors["entity"]:
                connections.append({
                    "file": file_path,
                    "imports": [r["target"] for r in neighbors["outgoing"] if r["type"] == "imports"],
                    "contains": [r["target"] for r in neighbors["outgoing"] if r["type"] == "contains"],
                })

    return {
        "question": question,
        "project_overview": {
            "name": overview.get("repo_name"),
            "languages": overview.get("languages"),
            "frameworks": overview.get("frameworks_and_tools"),
            "entry_points": overview.get("entry_points"),
        },
        "relevant_code": {
            "total_matches": relevant.get("total_matches", 0),
            "results": relevant.get("results", {}),
            "file_contents": relevant.get("top_file_contents", []),
        },
        "connections": connections,
        "graph_stats": graph.stats(),
    }

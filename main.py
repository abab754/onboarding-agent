import json
from collections import Counter
from pathlib import Path

from git import Repo, InvalidGitRepositoryError
from mcp.server.fastmcp import FastMCP

from knowledge_graph import KnowledgeGraph

# FastMCP is the high-level API from the MCP SDK.
# It handles all the protocol plumbing (JSON-RPC, capability negotiation, etc.)
# so you just focus on defining tools, resources, and prompts.
mcp = FastMCP("onboarding-agent")

# Directories we never want to crawl — these are noise, not project structure.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"}


def build_file_tree(root: Path, max_depth: int = 5) -> dict:
    """Recursively walk a directory and return a nested dict representing the file tree.

    Each directory is a dict with "type": "directory" and "children": {...}.
    Each file is a dict with "type": "file" and "size": <bytes>.
    """
    tree: dict = {}

    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return {"error": "permission denied"}

    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue

        if entry.is_dir():
            if max_depth <= 0:
                tree[entry.name] = {"type": "directory", "children": "...truncated"}
            else:
                tree[entry.name] = {
                    "type": "directory",
                    "children": build_file_tree(entry, max_depth - 1),
                }
        elif entry.is_file():
            tree[entry.name] = {
                "type": "file",
                "size": entry.stat().st_size,
            }

    return tree


@mcp.tool()
def ingest_repo(repo_path: str) -> dict:
    """Ingest a local repository and return its file tree structure.

    Args:
        repo_path: Absolute path to a local repository directory.

    Returns:
        A dict with the repo name, root path, file tree, and summary stats.
    """
    global _current_repo_path
    root = Path(repo_path).expanduser().resolve()

    if not root.exists():
        return {"error": f"Path does not exist: {root}"}
    if not root.is_dir():
        return {"error": f"Path is not a directory: {root}"}

    _current_repo_path = str(root)
    tree = build_file_tree(root)

    # Count files and directories for a quick summary
    file_count = 0
    dir_count = 0

    def count(node: dict) -> None:
        nonlocal file_count, dir_count
        for value in node.values():
            if not isinstance(value, dict):
                continue
            if value.get("type") == "file":
                file_count += 1
            elif value.get("type") == "directory":
                dir_count += 1
                children = value.get("children")
                if isinstance(children, dict):
                    count(children)

    count(tree)

    return {
        "repo_name": root.name,
        "root_path": str(root),
        "summary": {
            "total_files": file_count,
            "total_directories": dir_count,
        },
        "tree": tree,
    }


@mcp.tool()
def read_file(filepath: str) -> dict:
    """Reads a file path and returns its content with additional metadata.

    Args:
        filepath: Absolute path to a local file.

    Returns:
    A dict with the filename, size, extension and its content.
    """
    path = Path(filepath)
    if not path.exists():
        return {"error": f"File not found at {filepath}"}
    if not path.is_file():
        return {"error": f"{filepath} is not a file"}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return {
                "file_name": path.name,
                "size": path.stat().st_size,
                "extension": path.suffix,
                "content": f.read(),
            }
    except Exception as e:
        return {"error": f"reading file: {str(e)}"}

# Maps file extensions to language names.
EXTENSION_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".jsx": "JavaScript (React)", ".tsx": "TypeScript (React)",
    ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".cpp": "C++", ".c": "C", ".cs": "C#", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".php": "PHP",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sh": "Shell", ".sql": "SQL", ".r": "R",
}

# Config files that reveal which frameworks/tools the project uses.
CONFIG_SIGNALS = {
    "pyproject.toml": "Python (uv/pip)", "setup.py": "Python (setuptools)",
    "requirements.txt": "Python (pip)", "Pipfile": "Python (pipenv)",
    "package.json": "Node.js", "tsconfig.json": "TypeScript",
    "Cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)", "Gemfile": "Ruby",
    "Makefile": "Make", "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose", "docker-compose.yaml": "Docker Compose",
    ".eslintrc.json": "ESLint", ".prettierrc": "Prettier",
}

ENTRY_POINT_NAMES = {
    "main.py", "app.py", "manage.py", "server.py", "cli.py",
    "index.js", "index.ts", "main.go", "main.rs", "App.java",
}


def collect_extensions(tree: dict) -> dict[str, int]:
    """Walk the file tree and count occurrences of each file extension."""
    counts: dict[str, int] = {}
    for name, info in tree.items():
        if not isinstance(info, dict):
            continue
        if info.get("type") == "file":
            ext = Path(name).suffix.lower()
            if ext:
                counts[ext] = counts.get(ext, 0) + 1
        elif info.get("type") == "directory":
            children = info.get("children")
            if isinstance(children, dict):
                for ext, n in collect_extensions(children).items():
                    counts[ext] = counts.get(ext, 0) + n
    return counts


def find_config_files(tree: dict) -> list[str]:
    """Return names of known config/framework files found at the repo root."""
    return [name for name in tree if name in CONFIG_SIGNALS]


def find_entry_points(tree: dict, root_path: str) -> list[str]:
    """Find likely entry point files in the tree (searches recursively)."""
    found: list[str] = []
    for name, info in tree.items():
        if not isinstance(info, dict):
            continue
        if info.get("type") == "file" and name in ENTRY_POINT_NAMES:
            found.append(f"{root_path}/{name}")
        elif info.get("type") == "directory":
            children = info.get("children")
            if isinstance(children, dict):
                found.extend(find_entry_points(children, f"{root_path}/{name}"))
    return found


@mcp.tool()
def get_overview(repo_path: str) -> dict:
    """Return a high-level overview of a repository: languages, frameworks, entry points, and structure.

    Args:
        repo_path: Absolute path to a local repository directory.

    Returns:
        A dict with detected languages, frameworks/tools, entry points, top-level structure, and file stats.
    """
    repo = ingest_repo(repo_path)
    if "error" in repo:
        return repo

    tree = repo["tree"]
    root = repo["root_path"]

    # Detect languages from file extensions
    ext_counts = collect_extensions(tree)
    languages = {
        EXTENSION_TO_LANGUAGE[ext]: count
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])
        if ext in EXTENSION_TO_LANGUAGE
    }

    # Detect frameworks/tools from config files
    config_files = find_config_files(tree)
    frameworks = [CONFIG_SIGNALS[f] for f in config_files]

    # Find entry points
    entry_points = find_entry_points(tree, root)

    # Top-level directory names give a quick sense of project layout
    top_level_dirs = [
        name for name, info in tree.items()
        if isinstance(info, dict) and info.get("type") == "directory"
    ]

    return {
        "repo_name": repo["repo_name"],
        "root_path": root,
        "languages": languages,
        "frameworks_and_tools": frameworks,
        "config_files": config_files,
        "entry_points": entry_points,
        "top_level_directories": top_level_dirs,
        "summary": repo["summary"],
    }

def extract_python_symbols(content: str) -> dict:
    """Extract imports, function names, and class names from Python source code.

    Uses simple line-based parsing rather than AST — faster, works on files
    with syntax errors, and good enough for an overview.
    """
    imports: list[str] = []
    functions: list[str] = []
    classes: list[str] = []

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
        elif stripped.startswith("def "):
            # Extract function name: "def foo(..." -> "foo"
            name = stripped[4:].split("(")[0].strip()
            functions.append(name)
        elif stripped.startswith("class "):
            # Extract class name: "class Foo(..." or "class Foo:" -> "Foo"
            name = stripped[6:].split("(")[0].split(":")[0].strip()
            classes.append(name)

    return {"imports": imports, "functions": functions, "classes": classes}


@mcp.tool()
def explain_file(file_path: str, repo_path: str | None = None) -> dict:
    """Return the contents of a file along with structural metadata to help understand it.

    Extracts imports, function/class definitions, and context about where the file
    sits in the project. The LLM client uses this to explain the file to the user.

    Args:
        file_path: Absolute path to the file to explain.
        repo_path: Optional repo root path. If provided, shows the file's relative location.

    Returns:
        A dict with file metadata, extracted symbols, and the file content.
    """
    result = read_file(file_path)
    if "error" in result:
        return result

    path = Path(file_path)
    content = result["content"]

    # Extract symbols for Python files
    symbols = {}
    if path.suffix == ".py":
        symbols = extract_python_symbols(content)

    language = EXTENSION_TO_LANGUAGE.get(path.suffix.lower(), "Unknown")

    response: dict = {
        "file_name": result["file_name"],
        "language": language,
        "size": result["size"],
        "line_count": content.count("\n") + 1,
        "content": content,
    }

    if symbols:
        response["symbols"] = symbols

    # If repo_path is provided, show where this file lives relative to the root
    if repo_path:
        try:
            response["relative_path"] = str(path.relative_to(Path(repo_path).resolve()))
        except ValueError:
            pass

    return response


@mcp.tool()
def explain_module(module_path: str, repo_path: str | None = None) -> dict:
    """Return an overview of a directory/module: its files, purpose, and key components.

    Args:
        module_path: Absolute path to the directory to explain.
        repo_path: Optional repo root path for relative path context.

    Returns:
        A dict with the module's files, detected languages, key symbols per file, and any README content.
    """
    root = Path(module_path).resolve()

    if not root.exists():
        return {"error": f"Path does not exist: {root}"}
    if not root.is_dir():
        return {"error": f"Path is not a directory: {root}"}

    files_info: list[dict] = []

    try:
        entries = sorted(root.iterdir(), key=lambda e: (e.is_file(), e.name))
    except PermissionError:
        return {"error": "permission denied"}

    readme_content = None

    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue

        if entry.is_dir():
            # Just note subdirectories, don't recurse deep
            child_count = sum(1 for _ in entry.iterdir() if _.name not in SKIP_DIRS)
            files_info.append({
                "name": entry.name,
                "type": "directory",
                "item_count": child_count,
            })
        elif entry.is_file():
            info: dict = {
                "name": entry.name,
                "type": "file",
                "size": entry.stat().st_size,
                "language": EXTENSION_TO_LANGUAGE.get(entry.suffix.lower(), "Unknown"),
            }

            # Extract symbols from Python files
            if entry.suffix == ".py":
                try:
                    content = entry.read_text(encoding="utf-8")
                    symbols = extract_python_symbols(content)
                    info["functions"] = symbols["functions"]
                    info["classes"] = symbols["classes"]
                except Exception:
                    pass

            # Capture README content for module-level docs
            if entry.name.lower().startswith("readme"):
                try:
                    readme_content = entry.read_text(encoding="utf-8")
                except Exception:
                    pass

            files_info.append(info)

    response: dict = {
        "module_name": root.name,
        "path": str(root),
        "files": files_info,
    }

    if repo_path:
        try:
            response["relative_path"] = str(root.relative_to(Path(repo_path).resolve()))
        except ValueError:
            pass

    if readme_content:
        response["readme"] = readme_content

    return response


# Global state — tracks the currently analyzed repo and its knowledge graph.
_graph: KnowledgeGraph | None = None
_current_repo_path: str | None = None


def _get_or_create_graph(repo_path: str) -> KnowledgeGraph:
    """Get the current graph or create one backed by a file in the target repo."""
    global _graph, _current_repo_path
    storage = Path(repo_path) / ".onboarding_agent" / "graph.json"
    if _graph is None or _graph.storage_path != storage:
        _graph = KnowledgeGraph(str(storage))
        _current_repo_path = str(Path(repo_path).resolve())
    return _graph


def _populate_graph(graph: KnowledgeGraph, tree: dict, root_path: str, current_path: str) -> None:
    """Recursively walk the file tree and add entities + relationships to the graph."""
    for name, info in tree.items():
        if not isinstance(info, dict):
            continue

        full_path = f"{current_path}/{name}"

        if info.get("type") == "directory":
            graph.add_entity(full_path, "module", name, {"path": full_path})
            # Module is contained by its parent
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

            # For Python files, extract functions/classes and add them as entities
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

                    # Track import relationships
                    for imp in symbols["imports"]:
                        # Normalize "from X import Y" and "import X" to module name
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

    graph = _get_or_create_graph(repo["root_path"])
    graph.clear()

    # Add the repo root as a top-level module entity
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
    graph = _get_or_create_graph(repo_path)
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
    graph = _get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    results = graph.find_relationships(source=source, target=target, rel_type=rel_type)
    return {"count": len(results), "relationships": results}


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
    graph = _get_or_create_graph(repo_path)
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

        # Boost files over individual symbols — they provide more context
        if entity["type"] == "file" and score > 0:
            score += 1.0

        if score > 0:
            scored.append((score, entity))

    # Also search import relationships — if a file imports something matching the query,
    # that file is probably relevant
    for rel in graph.relationships:
        if rel["type"] == "imports":
            target_lower = rel["target"].lower()
            for term in query_terms:
                if term in target_lower:
                    source_entity = graph.get_entity(rel["source"])
                    if source_entity:
                        scored.append((2.0, source_entity))

    # Deduplicate and sort by score
    seen: set[str] = set()
    unique_scored: list[tuple[float, dict]] = []
    for score, entity in sorted(scored, key=lambda x: -x[0]):
        if entity["id"] not in seen:
            seen.add(entity["id"])
            unique_scored.append((score, entity))

    # Group results by type
    results: dict[str, list[dict]] = {"files": [], "functions": [], "classes": [], "modules": []}
    for score, entity in unique_scored[:20]:
        entry = {**entity, "relevance_score": score}
        bucket = entity["type"] + "s" if entity["type"] + "s" in results else "files"
        results.get(bucket, results["files"]).append(entry)

    # Read content of top file matches so the LLM has something to work with
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
    graph = _get_or_create_graph(repo_path)
    if not graph.entities:
        return {"error": "No knowledge graph found. Run build_knowledge_graph first."}

    # Build the import graph: which files import what
    import_rels = graph.find_relationships(rel_type="imports")
    import_graph: dict[str, list[str]] = {}
    for rel in import_rels:
        source = rel["source"]
        target = rel["target"]
        if source not in import_graph:
            import_graph[source] = []
        import_graph[source].append(target)

    # Build the containment tree: modules -> files
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

    # Find the most-imported modules (dependencies many files rely on)
    import_counts: dict[str, int] = {}
    for targets in import_graph.values():
        for target in targets:
            import_counts[target] = import_counts.get(target, 0) + 1
    most_imported = sorted(import_counts.items(), key=lambda x: -x[1])[:10]

    # Find files with the most imports (high coupling)
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
    graph = _get_or_create_graph(repo_path)

    # If no graph exists yet, build one automatically
    if not graph.entities:
        build_result = build_knowledge_graph(repo_path)
        if "error" in build_result:
            return build_result

    # Gather context from multiple sources
    overview = get_overview(repo_path)
    relevant = find_relevant_code(repo_path, question)

    # Get the relationships for the most relevant files to show connections
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


# ---------------------------------------------------------------------------
# Git History Tools
# ---------------------------------------------------------------------------


@mcp.tool()
def get_git_history(repo_path: str, max_commits: int = 30) -> dict:
    """Return recent git commit history for the repo.

    Args:
        repo_path: Absolute path to the repo.
        max_commits: Number of recent commits to return (default 30).

    Returns:
        A dict with recent commits and contributor summary.
    """
    try:
        repo = Repo(repo_path)
    except InvalidGitRepositoryError:
        return {"error": f"Not a git repository: {repo_path}"}

    commits = []
    author_counts: Counter[str] = Counter()

    for commit in repo.iter_commits(max_count=max_commits):
        author = f"{commit.author.name} <{commit.author.email}>"
        author_counts[author] += 1
        commits.append({
            "hash": commit.hexsha[:8],
            "message": commit.message.strip().split("\n")[0],
            "author": commit.author.name,
            "date": commit.committed_datetime.isoformat(),
            "files_changed": len(commit.stats.files),
        })

    return {
        "total_commits_shown": len(commits),
        "commits": commits,
        "contributors": [
            {"name": name, "commit_count": count}
            for name, count in author_counts.most_common()
        ],
    }


@mcp.tool()
def get_hot_files(repo_path: str, max_commits: int = 100, top_n: int = 15) -> dict:
    """Find the most frequently changed files in the repo — these are often the most important to understand.

    Args:
        repo_path: Absolute path to the repo.
        max_commits: How many recent commits to analyze (default 100).
        top_n: How many top files to return (default 15).

    Returns:
        A dict with the most-changed files and their change counts.
    """
    try:
        repo = Repo(repo_path)
    except InvalidGitRepositoryError:
        return {"error": f"Not a git repository: {repo_path}"}

    file_counts: Counter[str] = Counter()

    for commit in repo.iter_commits(max_count=max_commits):
        for file_path in commit.stats.files:
            file_counts[file_path] += 1

    hot_files = [
        {"file": f, "change_count": count}
        for f, count in file_counts.most_common(top_n)
    ]

    return {
        "commits_analyzed": min(max_commits, sum(1 for _ in repo.iter_commits(max_count=max_commits))),
        "hot_files": hot_files,
    }


@mcp.tool()
def get_file_contributors(repo_path: str, file_path: str) -> dict:
    """Find who has contributed to a specific file — tells a new dev who to ask about it.

    Args:
        repo_path: Absolute path to the repo.
        file_path: Path to the file, relative to the repo root.

    Returns:
        A dict with contributors to this file and their commit counts.
    """
    try:
        repo = Repo(repo_path)
    except InvalidGitRepositoryError:
        return {"error": f"Not a git repository: {repo_path}"}

    author_counts: Counter[str] = Counter()
    recent_commits: list[dict] = []

    for commit in repo.iter_commits(paths=file_path, max_count=50):
        author_counts[commit.author.name] += 1
        if len(recent_commits) < 10:
            recent_commits.append({
                "hash": commit.hexsha[:8],
                "message": commit.message.strip().split("\n")[0],
                "author": commit.author.name,
                "date": commit.committed_datetime.isoformat(),
            })

    if not author_counts:
        return {"error": f"No git history found for: {file_path}"}

    return {
        "file": file_path,
        "contributors": [
            {"name": name, "commit_count": count}
            for name, count in author_counts.most_common()
        ],
        "recent_commits": recent_commits,
    }


# ---------------------------------------------------------------------------
# MCP Resources
# ---------------------------------------------------------------------------
# Resources are passive context the LLM can read without calling a tool.
# They use the currently active repo (set when any tool is called with a repo_path).
# The LLM or client reads them via simple URIs like repo://overview.


@mcp.resource("repo://overview")
def resource_overview() -> str:
    """High-level project summary: languages, frameworks, entry points, and structure."""
    if not _current_repo_path:
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = get_overview(_current_repo_path)
    return json.dumps(result, indent=2)


@mcp.resource("repo://structure")
def resource_structure() -> str:
    """File tree of the project."""
    if not _current_repo_path:
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = ingest_repo(_current_repo_path)
    return json.dumps(result, indent=2)


@mcp.resource("repo://dependencies")
def resource_dependencies() -> str:
    """Dependency/import graph showing how files and modules connect."""
    if not _current_repo_path:
        return json.dumps({"error": "No repo loaded. Call ingest_repo or build_knowledge_graph first."})
    result = get_architecture(_current_repo_path)
    return json.dumps(result, indent=2)


# ---------------------------------------------------------------------------
# MCP Prompts
# ---------------------------------------------------------------------------
# Prompts are reusable prompt templates that tell the LLM how to use the tools
# and format responses. Clients show these as actions the user can trigger
# (e.g., a button or slash command in Claude Desktop).


@mcp.prompt()
def onboard(repo_path: str) -> str:
    """Full onboarding walkthrough for a codebase."""
    return f"""You are an expert senior engineer onboarding a new team member to a codebase.

Use the following tools to analyze the repo at: {repo_path}

1. First, call `build_knowledge_graph` with repo_path="{repo_path}" to index the codebase.
2. Then call `get_overview` with repo_path="{repo_path}" for the high-level summary.
3. Then call `get_architecture` with repo_path="{repo_path}" to understand how components connect.

4. Then call `get_git_history` with repo_path="{repo_path}" to see recent activity.
5. Then call `get_hot_files` with repo_path="{repo_path}" to find the most important files.

Once you have all this context, provide a comprehensive onboarding guide that covers:
- What the project does (purpose and goals)
- Tech stack and key dependencies
- Project structure and what each top-level directory/file is for
- Architecture: how the main components connect
- Entry points: where the code starts executing
- Key files a new developer should read first (use the hot files data to prioritize)
- Recent activity: what's been worked on lately and who the key contributors are

Write in a friendly, clear tone. Use headers and bullet points. Be specific — reference actual file names and functions from the analysis."""


@mcp.prompt()
def explain_this_file(file_path: str, repo_path: str) -> str:
    """Get a detailed explanation of what a specific file does and how it fits in the project."""
    return f"""You are an expert engineer explaining code to a teammate.

Use the following tools to analyze this file:

1. Call `explain_file` with file_path="{file_path}" and repo_path="{repo_path}".
2. Call `get_overview` with repo_path="{repo_path}" for project context.
3. If the file imports other modules, call `query_relationships` with source="{file_path}" and rel_type="imports" to understand its dependencies.

Then explain:
- What this file does in plain English
- How it fits into the overall project architecture
- Key functions/classes and what they do
- What other parts of the codebase depend on or are related to this file
- Any patterns or conventions used in this file

Be specific and reference actual code from the file."""


@mcp.prompt()
def find_code_for(topic: str, repo_path: str) -> str:
    """Find and explain code related to a specific topic or feature."""
    return f"""You are an expert engineer helping a teammate find relevant code.

Use the following tools:

1. Call `find_relevant_code` with repo_path="{repo_path}" and query="{topic}".
2. For the top results, call `explain_file` on the most relevant files to get details.
3. Call `query_relationships` to understand how the relevant files connect.

Then provide:
- Which files are most relevant to "{topic}" and why
- Key functions/classes that handle this feature
- How the relevant pieces connect to each other
- A suggested reading order for understanding this part of the codebase"""


@mcp.prompt()
def ask_question(question: str, repo_path: str) -> str:
    """Answer any freeform question about the codebase."""
    return f"""You are a senior engineer who knows this codebase inside out.

Call `ask` with repo_path="{repo_path}" and question="{question}".

Use the returned context to answer the question thoroughly. Be specific — reference actual
file names, function names, and code from the analysis. If the question requires deeper
investigation, use `explain_file` or `find_relevant_code` to gather more detail.

Answer in a clear, helpful tone as if explaining to a new team member."""


if __name__ == "__main__":
    mcp.run()

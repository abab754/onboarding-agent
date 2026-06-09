"""Tools for analyzing files and modules."""

from pathlib import Path

from onboarding_agent.server import mcp
from onboarding_agent.constants import SKIP_DIRS, EXTENSION_TO_LANGUAGE, CONFIG_SIGNALS
from onboarding_agent.helpers import (
    extract_python_symbols,
    collect_extensions,
    find_config_files,
    find_entry_points,
)
from onboarding_agent.tools.ingest import ingest_repo, read_file


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

    ext_counts = collect_extensions(tree)
    languages = {
        EXTENSION_TO_LANGUAGE[ext]: count
        for ext, count in sorted(ext_counts.items(), key=lambda x: -x[1])
        if ext in EXTENSION_TO_LANGUAGE
    }

    config_files = find_config_files(tree)
    frameworks = [CONFIG_SIGNALS[f] for f in config_files]
    entry_points = find_entry_points(tree, root)

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

            if entry.suffix == ".py":
                try:
                    content = entry.read_text(encoding="utf-8")
                    symbols = extract_python_symbols(content)
                    info["functions"] = symbols["functions"]
                    info["classes"] = symbols["classes"]
                except Exception:
                    pass

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

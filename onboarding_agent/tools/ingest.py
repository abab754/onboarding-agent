"""Tools for ingesting and reading repository files."""

from pathlib import Path

from onboarding_agent.server import mcp, set_current_repo_path
from onboarding_agent.helpers import build_file_tree


@mcp.tool()
def ingest_repo(repo_path: str) -> dict:
    """Ingest a local repository and return its file tree structure.

    Args:
        repo_path: Absolute path to a local repository directory.

    Returns:
        A dict with the repo name, root path, file tree, and summary stats.
    """
    root = Path(repo_path).expanduser().resolve()

    if not root.exists():
        return {"error": f"Path does not exist: {root}"}
    if not root.is_dir():
        return {"error": f"Path is not a directory: {root}"}

    set_current_repo_path(str(root))
    tree = build_file_tree(root)

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

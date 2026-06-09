"""Shared helper functions used across multiple tools."""

from pathlib import Path

from onboarding_agent.constants import SKIP_DIRS, EXTENSION_TO_LANGUAGE, CONFIG_SIGNALS, ENTRY_POINT_NAMES


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
            name = stripped[4:].split("(")[0].strip()
            functions.append(name)
        elif stripped.startswith("class "):
            name = stripped[6:].split("(")[0].split(":")[0].strip()
            classes.append(name)

    return {"imports": imports, "functions": functions, "classes": classes}


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

from pathlib import Path

from mcp.server.fastmcp import FastMCP

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
    root = Path(repo_path).expanduser().resolve()

    if not root.exists():
        return {"error": f"Path does not exist: {root}"}
    if not root.is_dir():
        return {"error": f"Path is not a directory: {root}"}

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


if __name__ == "__main__":
    mcp.run()

# Directories we never want to crawl — these are noise, not project structure.
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".tox", ".mypy_cache"}

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

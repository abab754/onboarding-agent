"""Tools for analyzing git history — commits, hot files, and contributors."""

from collections import Counter

from git import Repo, InvalidGitRepositoryError

from onboarding_agent.server import mcp


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

"""MCP prompts — reusable prompt templates that guide the LLM's behavior."""

from onboarding_agent.server import mcp


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

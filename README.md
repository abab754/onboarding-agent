# onboarding-agent

An MCP server that onboards you to any codebase. Point it at a repo, and it builds a knowledge graph of the project — files, functions, classes, imports, and their relationships. Then ask questions like you're talking to a senior engineer who knows the project inside out.

## What it does

- **Ingests any local repo** — crawls the file tree, detects languages and frameworks
- **Builds a knowledge graph** — maps files, functions, classes, modules, and how they connect via imports
- **Answers onboarding questions** — "where does auth happen?", "what does this file do?", "who should I ask about the database?"
- **Analyzes git history** — finds the most-changed files (often the most important), recent activity, and contributors per file
- **Works 100% locally** — no API keys, no cloud, no data leaves your machine

## Install

Requires Python 3.12+.

```bash
# From PyPI (recommended)
uv pip install onboarding-agent

# Or run directly without installing
uvx onboarding-agent

# Or clone and install locally
git clone https://github.com/abab754/onboarding-agent.git
cd onboarding-agent
uv sync
```

## Connect to an MCP client

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "onboarding-agent": {
      "command": "uvx",
      "args": ["onboarding-agent"]
    }
  }
}
```

### Claude Code

Add a `.mcp.json` file to your project root (or the repo you want to onboard to):

```json
{
  "mcpServers": {
    "onboarding-agent": {
      "command": "uvx",
      "args": ["onboarding-agent"]
    }
  }
}
```

Then restart Claude Code.

### Any MCP-compatible client

The server uses stdio transport. Any MCP client can connect by running `onboarding-agent` (after pip install) or `uvx onboarding-agent`.

### Local development

If you cloned the repo and want to run from source:

```json
{
  "mcpServers": {
    "onboarding-agent": {
      "command": "uv",
      "args": ["--directory", "/path/to/onboarding-agent", "run", "main.py"]
    }
  }
}
```

## Usage examples

Once connected, just talk to your AI assistant naturally:

**Full onboarding:**
> "Onboard me to the repo at /Users/me/projects/my-app"

**Understand a file:**
> "Explain what /Users/me/projects/my-app/src/auth.py does"

**Find relevant code:**
> "Where does database configuration happen in /Users/me/projects/my-app?"

**Check project activity:**
> "Who are the main contributors to /Users/me/projects/my-app and what files change the most?"

**Freeform questions:**
> "How is error handling done in this project?"

## Tools

| Tool | Description |
|---|---|
| `ingest_repo` | Crawl a repo and return the file tree |
| `read_file` | Read a file's contents with metadata |
| `get_overview` | High-level summary: languages, frameworks, entry points |
| `explain_file` | File contents + imports, functions, classes |
| `explain_module` | Directory overview with per-file symbols |
| `build_knowledge_graph` | Index the repo into a queryable knowledge graph |
| `query_entities` | Search the graph for files, functions, classes, modules |
| `query_relationships` | Find how entities connect (imports, contains) |
| `find_relevant_code` | Search by topic and get ranked results |
| `get_architecture` | Import graph, module structure, coupling analysis |
| `ask` | Freeform Q&A — gathers context automatically |
| `get_git_history` | Recent commits and contributor summary |
| `get_hot_files` | Most frequently changed files |
| `get_file_contributors` | Who has worked on a specific file |

## Resources

| URI | Description |
|---|---|
| `repo://overview` | Project summary (after a repo is loaded) |
| `repo://structure` | File tree |
| `repo://dependencies` | Import/dependency graph |

## Prompts

| Prompt | Description |
|---|---|
| `onboard` | Full onboarding walkthrough |
| `explain_this_file` | Deep dive into a specific file |
| `find_code_for` | Find code related to a topic |
| `ask_question` | Freeform question answering |

## How it works

1. You point the server at a repo path
2. It crawls the file tree, skipping noise directories (`.git`, `node_modules`, etc.)
3. For Python files, it extracts functions, classes, and import statements
4. Everything gets stored in a knowledge graph (saved to `.onboarding_agent/graph.json` in the repo)
5. When you ask a question, it searches the graph, reads relevant files, and bundles the context for the LLM to answer

The knowledge graph persists between sessions, so re-analysis is only needed when the code changes.

## Development

```bash
git clone https://github.com/YOUR_USERNAME/onboarding-agent.git
cd onboarding-agent
uv sync

# Run the server
uv run main.py

# Test with MCP Inspector
npx @modelcontextprotocol/inspector uv run main.py
```

## Project structure

```
onboarding_agent/
├── server.py              # FastMCP instance and global state
├── constants.py           # Language maps, config signals, skip dirs
├── helpers.py             # File tree building, Python symbol extraction
├── knowledge_graph.py     # KnowledgeGraph class with JSON persistence
├── resources.py           # MCP resources (repo://overview, etc.)
├── prompts.py             # MCP prompt templates
└── tools/
    ├── ingest.py          # ingest_repo, read_file
    ├── analysis.py        # get_overview, explain_file, explain_module
    ├── graph.py           # build_knowledge_graph, query_entities, query_relationships
    ├── search.py          # find_relevant_code, get_architecture, ask
    └── git_history.py     # get_git_history, get_hot_files, get_file_contributors
```

## License

MIT

"""Entry point for the onboarding-agent MCP server."""

from onboarding_agent.server import mcp

# Import all tool/resource/prompt modules so they register with the mcp instance.
import onboarding_agent.tools.ingest  # noqa: F401
import onboarding_agent.tools.analysis  # noqa: F401
import onboarding_agent.tools.graph  # noqa: F401
import onboarding_agent.tools.search  # noqa: F401
import onboarding_agent.tools.git_history  # noqa: F401
import onboarding_agent.resources  # noqa: F401
import onboarding_agent.prompts  # noqa: F401

if __name__ == "__main__":
    mcp.run()

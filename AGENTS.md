# Osiris: instructions for AI agents

The goal: build Osiris into the best fitness and fitness-competition app out there.

1. Read [`docs/agents/KNOWLEDGE_GRAPH.md`](docs/agents/KNOWLEDGE_GRAPH.md) first. It maps every feature to its backend, shared, UI, test and doc files, with recipes, invariants and gotchas.
2. Follow [`CLAUDE.md`](CLAUDE.md) for commands, conventions and the Definition of Done. It applies to every agent, not only Claude.
3. Tools: MCP servers are defined in [`.mcp.json`](.mcp.json) (Supabase, Render, Playwright, REA). Register them in your own agent's config. Tokens come from environment variables (`RENDER_API_KEY`) and never go into tracked files.
4. The worktree is shared with other agents. Work in your own `git worktree`, stage explicit paths, and remember that a push to `master` deploys production.

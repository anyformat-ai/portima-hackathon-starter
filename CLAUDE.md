@AGENTS.md

## Claude Code specifics

- The anyformat MCP server is configured in `.mcp.json`. It needs `ANYFORMAT_API_KEY` exported in
  the shell that starts Claude Code. Check it with `claude mcp list`.
- For the anyformat skill (workflow API reference): `npx @anyformat/skill --project`, then restart.
- Prefer `uv run af.py ...` over ad-hoc API calls: it keeps results in the shape the scorer reads.

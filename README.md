# elasticsearch-mcp

Read-only [MCP](https://modelcontextprotocol.io) server for Elasticsearch that works in any MCP client: Claude Code, Codex, Cursor, OpenCode, Gemini CLI, VS Code, Claude Desktop and the rest. It's a standard stdio server: the client launches one command, `elasticsearch-mcp`, and passes settings as environment variables. It calls the Elasticsearch REST API directly, so it works with Elasticsearch 7, 8, 9 and Elastic Cloud.

| Tool | Calls |
|---|---|
| `list_indices(pattern="*")` | `GET _cat/indices/{pattern}` |
| `get_mappings(index)` | `GET {index}/_mapping` |
| `search(index, body)` | `POST {index}/_search`: Query DSL, aggregations |
| `esql(query)` | `POST _query`: ES\|QL, Elasticsearch 8.11+ |
| `get_shards(index="*")` | `GET _cat/shards/{index}` |
| `cluster_health()` | `GET _cluster/health` |

It also ships one MCP prompt, `elasticsearch(question)`. Clients that support MCP prompts, such as Claude Code and VS Code, list it as a slash command. In every client you can also just ask about your data, and the agent calls the tools.

No tool writes, so the server can't change data, whatever the credentials allow.

## Settings

| Variable | Meaning |
|---|---|
| `ES_URL` | Cluster URL. Default `http://localhost:9200` |
| `ES_API_KEY` | Preferred. The `encoded` value from `POST _security/api_key` |
| `ES_USERNAME`, `ES_PASSWORD` | Basic auth, used when `ES_API_KEY` is empty |
| `ES_CA_CERT` | CA bundle path for self-signed TLS, e.g. `http_ca.crt` |

Keep them in this folder's `.env` (the commands below load it with `--env-file`), or put them in the client's own env setting instead.

## Add it to your agent

Every client runs the same command. Replace `/path/to/elasticsearch-mcp` with this folder's path:

```
uv run --directory /path/to/elasticsearch-mcp --env-file .env elasticsearch-mcp
```

### Claude Code

```bash
claude mcp add --scope user elasticsearch -- uv run --directory /path/to/elasticsearch-mcp --env-file .env elasticsearch-mcp
```

### Codex

```bash
codex mcp add elasticsearch -- uv run --directory /path/to/elasticsearch-mcp --env-file .env elasticsearch-mcp
```

### VS Code

```bash
code --add-mcp '{"name":"elasticsearch","command":"uv","args":["run","--directory","/path/to/elasticsearch-mcp","--env-file",".env","elasticsearch-mcp"]}'
```

If `code` opens Cursor (Cursor can install its own `code` command), run VS Code's CLI by its full path: `"/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"`.

### Cursor, Gemini CLI, Claude Desktop and most other clients

Add this to `~/.cursor/mcp.json`, `~/.gemini/settings.json` or `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "elasticsearch": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/elasticsearch-mcp", "--env-file", ".env", "elasticsearch-mcp"]
    }
  }
}
```

### OpenCode

Add this to `~/.config/opencode/opencode.json`:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "elasticsearch": {
      "type": "local",
      "command": ["uv", "run", "--directory", "/path/to/elasticsearch-mcp", "--env-file", ".env", "elasticsearch-mcp"]
    }
  }
}
```

### Another machine

Any machine with [uv](https://docs.astral.sh/uv/) can run it straight from GitHub, without a checkout. Use `uvx --from git+https://github.com/aniketshukla1/elasticsearch-mcp elasticsearch-mcp` as the command, and pass the settings through the client's env: `env` in JSON configs, `environment` in OpenCode, `--env KEY=value` for `codex mcp add`, `-e KEY=value` for `claude mcp add`. For example:

```bash
claude mcp add --scope user -e ES_URL=https://your-cluster:9200 -e ES_API_KEY=your-key elasticsearch -- uvx --from git+https://github.com/aniketshukla1/elasticsearch-mcp elasticsearch-mcp
```

## Run it locally with Docker

1. Create `.env`:
   ```
   ES_URL=http://localhost:9200
   ES_USERNAME=elastic
   ES_PASSWORD=<pick one>
   ```
2. `docker compose up -d --wait` starts Elasticsearch 9.5.5 on `127.0.0.1:9200`.
3. `uv run --env-file .env test_e2e.py` seeds the `mcp-demo-products` index and checks every tool and the prompt, once with a read-only API key and once with the password.
4. Add the server to your agent (above), then ask: "Which products in mcp-demo-products are in stock?"

## Read-only API key for real clusters

A least-privilege key that covers all six tools (the same role `test_e2e.py` uses):

```
POST /_security/api_key
{
  "name": "mcp-read-only",
  "role_descriptors": {
    "mcp_read_only": {
      "cluster": ["monitor"],
      "indices": [{ "names": ["*"], "privileges": ["read", "view_index_metadata", "monitor"] }]
    }
  }
}
```

Narrow `names` to the indices the agent should see.

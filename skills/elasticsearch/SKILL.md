---
name: elasticsearch
description: "Read-only access to an Elasticsearch cluster from the shell: list indices, read field mappings, run Query DSL searches, aggregations and ES|QL queries, and check cluster health and shards. Use it whenever the user asks about data, logs, metrics or documents stored in Elasticsearch, Elastic Cloud or an ELK stack, such as counts, top-N, trends, a specific document or what an index contains, even if they only name an index or a pattern like logs-*. If elasticsearch MCP tools are available in the session, use those instead."
license: MIT
compatibility: Needs network access to the cluster, plus uv (preferred) or curl.
---

# Elasticsearch (read-only)

Answer questions from an Elasticsearch cluster by running read-only commands in a shell. These are the same operations the `elasticsearch` MCP server offers, so if its tools (`list_indices`, `get_mappings`, `search`, `esql`, `get_shards`, `cluster_health`) are already available, call them instead.

## Commands

Run each command with uv. The first run downloads the tool; later runs start instantly.

```bash
uvx --from git+https://github.com/aniketshukla1/elasticsearch-mcp elasticsearch-mcp <command> [args]
```

If `elasticsearch-mcp` is already on PATH (installed with `uv tool install git+https://github.com/aniketshukla1/elasticsearch-mcp`), run it directly. Every command prints Elasticsearch's JSON on stdout. On failure it prints Elasticsearch's own error on stderr and exits with 1, so read the reason and fix the query instead of retrying the same one.

| Command | Returns |
|---|---|
| `cluster-health` | Status (green, yellow or red), node and shard counts |
| `list-indices [PATTERN]` | Indices matching a pattern such as `logs-*`, with health, doc count and size |
| `get-mappings INDEX` | Field names and types |
| `search INDEX [BODY]` | Query DSL search. BODY is the full `_search` JSON, or `-` to read it from stdin |
| `esql QUERY` | ES\|QL result as columns and rows (Elasticsearch 8.11+). `-` reads the query from stdin |
| `get-shards [PATTERN]` | Shard state, docs, size and node |

## Connection settings

The commands read these environment variables:

- `ES_URL`: the cluster URL, default `http://localhost:9200`
- `ES_API_KEY`, or `ES_USERNAME` and `ES_PASSWORD`
- `ES_CA_CERT`: a CA bundle path, only for self-signed TLS

If the user keeps them in a `.env` file, load it with `uvx --env-file /path/to/.env --from ...`. If nothing is set and the cluster needs auth, ask the user where the credentials live. Never print a credential or paste one into a command the user will see.

## Answering a question

1. With no specific question, run `cluster-health` and `list-indices`, then summarise health, index count and the largest indices.
2. Find the index with `list-indices` and a pattern taken from the question, such as `*order*`.
3. Read `get-mappings` before writing a query. Field types decide the query: `match` works on `text` fields, terms aggregations and exact filters need `keyword` fields (often `<field>.keyword`), and date ranges need a `date` field.
4. For counts, group-bys, top-N and trends, use `esql` with a `LIMIT`. For full-text matches or fetching documents, use `search` with a small `size` and `_source` filtering. Results land in your context, so keep them small.
5. Give the answer with its numbers, and show the query you ran so the user can rerun it.

```bash
uvx --from git+https://github.com/aniketshukla1/elasticsearch-mcp elasticsearch-mcp esql 'FROM logs-* | WHERE level == "error" | STATS errors = COUNT(*) BY host.name | SORT errors DESC | LIMIT 5'

echo '{"size": 3, "query": {"match": {"message": "timeout"}}, "_source": ["@timestamp", "message"]}' \
  | uvx --from git+https://github.com/aniketshukla1/elasticsearch-mcp elasticsearch-mcp search 'logs-*' -
```

## Without uv: curl

The same read-only calls work with curl. Send only GET requests, plus POST to `_search` and `_query`. Never send PUT, DELETE or any other POST: this skill must not change data, and unlike the CLI, curl can't stop a write.

```bash
curl -s -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/_cluster/health"
curl -s -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/_cat/indices/logs-*?format=json&h=index,health,docs.count,store.size"
curl -s -H "Authorization: ApiKey $ES_API_KEY" "$ES_URL/logs-*/_mapping"
curl -s -H "Authorization: ApiKey $ES_API_KEY" -H "Content-Type: application/json" "$ES_URL/logs-*/_search" -d '{"size": 3, "query": {"match": {"message": "timeout"}}}'
curl -s -H "Authorization: ApiKey $ES_API_KEY" -H "Content-Type: application/json" "$ES_URL/_query?format=json" -d '{"query": "FROM logs-* | STATS n = COUNT(*)"}'
```

With a username and password, replace the `Authorization` header with `-u "$ES_USERNAME:$ES_PASSWORD"`.

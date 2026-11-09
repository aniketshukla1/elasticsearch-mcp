"""Read-only Elasticsearch MCP server (stdio).

Talks to the Elasticsearch REST API directly, so one build works with ES 7, 8, 9 and Elastic Cloud.
Config comes from the environment:
  ES_URL                     default http://localhost:9200
  ES_API_KEY                 preferred auth: the `encoded` value from POST /_security/api_key
  ES_USERNAME, ES_PASSWORD   basic auth, used when ES_API_KEY is unset
  ES_CA_CERT                 CA bundle path, for clusters with self-signed TLS
"""

import os
from urllib.parse import quote

import httpx2
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")

headers, auth = {}, None
if api_key := os.environ.get("ES_API_KEY"):
    headers["Authorization"] = f"ApiKey {api_key}"
elif username := os.environ.get("ES_USERNAME"):
    auth = (username, os.environ.get("ES_PASSWORD", ""))

es = httpx2.AsyncClient(
    base_url=ES_URL,
    headers=headers,
    auth=auth,
    verify=os.environ.get("ES_CA_CERT") or True,
    timeout=30,
)

mcp = MCPServer(
    "elasticsearch",
    instructions=(
        "Read-only access to an Elasticsearch cluster. Find indices with list_indices, read field names "
        "and types with get_mappings, then query with search (Query DSL) or esql (ES|QL)."
    ),
)
# Every tool only reads. Results are Elasticsearch's own compact JSON, passed through as one text block.
read_only_tool = mcp.tool(
    annotations=ToolAnnotations(readOnlyHint=True), structured_output=False
)


async def _es(method: str, path: str, **kwargs) -> str:
    """Call Elasticsearch and return the response body; turn failures into errors the model can act on."""
    try:
        r = await es.request(method, path, **kwargs)
    except httpx2.TransportError as e:
        raise ToolError(f"Cannot reach Elasticsearch at {ES_URL}: {e}") from e
    if r.is_error:
        raise ToolError(f"Elasticsearch returned HTTP {r.status_code}: {r.text[:4000]}")
    # ponytail: success bodies are not truncated; add a size cap if a client chokes on large results.
    return r.text


def _target(index: str) -> str:
    """Encode a model-supplied index name for the URL path, keeping list (,), wildcard (*) and remote-cluster (:) syntax."""
    return quote(index, safe=",*:")


@read_only_tool
async def list_indices(pattern: str = "*") -> str:
    """List indices matching a pattern such as "logs-*" or "a,b", with health, status, doc count and size."""
    params = {
        "format": "json",
        "h": "index,health,status,docs.count,store.size",
        "s": "index",
    }
    return await _es("GET", f"/_cat/indices/{_target(pattern)}", params=params)


@read_only_tool
async def get_mappings(index: str) -> str:
    """Get the field names and types of an index or pattern. Read them before writing a search or ES|QL query."""
    return await _es("GET", f"/{_target(index)}/_mapping")


@read_only_tool
async def search(index: str, body: dict | None = None) -> str:
    """Run a Query DSL search. `body` is the full _search request body, for example
    {"query": {"match": {"title": "shoes"}}, "size": 5}. Aggregations, sort and _source filtering work as
    usual; omit `body` to get the first 10 documents."""
    return await _es("POST", f"/{_target(index)}/_search", json=body)


@read_only_tool
async def esql(query: str) -> str:
    """Run an ES|QL query (Elasticsearch 8.11+), for example
    'FROM logs-* | STATS errors = COUNT(*) BY host.name | SORT errors DESC | LIMIT 10'. Returns columns and rows."""
    return await _es(
        "POST", "/_query", params={"format": "json"}, json={"query": query}
    )


@read_only_tool
async def get_shards(index: str = "*") -> str:
    """Show shards for indices matching a pattern: primary or replica, state, docs, size and node."""
    params = {"format": "json", "h": "index,shard,prirep,state,docs,store,node"}
    return await _es("GET", f"/_cat/shards/{_target(index)}", params=params)


@read_only_tool
async def cluster_health() -> str:
    """Cluster health: status (green, yellow or red), node count and shard counts."""
    return await _es("GET", "/_cluster/health")


@mcp.prompt()
def elasticsearch(question: str = "") -> str:
    """Answer a question from your Elasticsearch data, or give a cluster overview when no question is given."""
    if not question:
        return "Give me an overview of my Elasticsearch cluster: health, then the largest indices by document count."
    return (
        f"Answer this from my Elasticsearch data: {question}\n\n"
        "Use the elasticsearch tools. Find the index with list_indices, read its fields with get_mappings, "
        "then query with esql for counts, group-bys and top-N, or with search for full-text matches and documents. "
        "Keep results small (LIMIT or size) and show the query you ran."
    )


def main() -> None:
    """Console entry point (`elasticsearch-mcp`): serve over stdio, which every MCP client can launch."""
    mcp.run()


if __name__ == "__main__":
    main()

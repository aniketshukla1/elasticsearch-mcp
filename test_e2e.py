"""End-to-end check: Elasticsearch <- elasticsearch-mcp <- MCP client over stdio.

Seeds the demo index `mcp-demo-products` (left in place so you can query it from Claude), creates a
1-hour read-only API key, then calls every tool once with that key and once with basic auth.

    docker compose up -d --wait
    uv run --env-file .env test_e2e.py
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import httpx2
from mcp import Client, StdioServerParameters

ES_URL = os.environ.get("ES_URL", "http://localhost:9200")
BASIC_AUTH = {
    "ES_URL": ES_URL,
    "ES_USERNAME": os.environ["ES_USERNAME"],
    "ES_PASSWORD": os.environ["ES_PASSWORD"],
}
INDEX = "mcp-demo-products"
PRODUCTS = [
    {
        "name": "Trail running shoes",
        "category": "shoes",
        "price": 129.0,
        "in_stock": True,
    },
    {
        "name": "Road running shoes",
        "category": "shoes",
        "price": 99.0,
        "in_stock": False,
    },
    {
        "name": "Waterproof hiking jacket",
        "category": "jackets",
        "price": 249.0,
        "in_stock": True,
    },
    {
        "name": "Insulated down jacket",
        "category": "jackets",
        "price": 299.0,
        "in_stock": True,
    },
    {"name": "Merino wool socks", "category": "socks", "price": 19.0, "in_stock": True},
]
# Least privilege for all six tools; the README recommends the same role for real clusters.
READ_ONLY_ROLE = {
    "cluster": ["monitor"],
    "indices": [
        {"names": ["*"], "privileges": ["read", "view_index_metadata", "monitor"]}
    ],
}
TOOLS = {
    "list_indices",
    "get_mappings",
    "search",
    "esql",
    "get_shards",
    "cluster_health",
}


def seed() -> str:
    """Index the demo docs (fixed ids, so re-runs overwrite them) and return a read-only API key."""
    with httpx2.Client(
        base_url=ES_URL, auth=(BASIC_AUTH["ES_USERNAME"], BASIC_AUTH["ES_PASSWORD"])
    ) as es:
        for doc_id, doc in enumerate(PRODUCTS, 1):
            es.put(f"/{INDEX}/_doc/{doc_id}", json=doc).raise_for_status()
        es.post(f"/{INDEX}/_refresh").raise_for_status()
        key = es.post(
            "/_security/api_key",
            json={
                "name": "mcp-e2e",
                "expiration": "1h",
                "role_descriptors": {"mcp_read_only": READ_ONLY_ROLE},
            },
        )
        key.raise_for_status()
        return key.json()["encoded"]


async def check(env: dict) -> None:
    # Launch the installed console script, the same entry point every MCP client runs.
    server = StdioServerParameters(
        command=str(Path(sys.executable).with_name("elasticsearch-mcp")), env=env
    )
    async with Client(server) as client:
        assert {t.name for t in (await client.list_tools()).tools} == TOOLS
        assert [p.name for p in (await client.list_prompts()).prompts] == [
            "elasticsearch"
        ]
        prompt = await client.get_prompt(
            "elasticsearch", {"question": "how many socks?"}
        )
        assert "how many socks?" in prompt.messages[0].content.text, prompt

        async def call(tool: str, **args):
            result = await client.call_tool(tool, args)
            assert not result.is_error, f"{tool}: {result.content}"
            return json.loads(result.content[0].text)

        assert (await call("cluster_health"))["status"] in ("green", "yellow")
        [row] = await call("list_indices", pattern=INDEX)
        assert row["docs.count"] == str(len(PRODUCTS)), row
        assert (
            "price"
            in (await call("get_mappings", index=INDEX))[INDEX]["mappings"][
                "properties"
            ]
        )
        hits = (
            await call(
                "search", index=INDEX, body={"query": {"match": {"name": "shoes"}}}
            )
        )["hits"]
        assert hits["total"]["value"] == 2, hits
        aggs = await call(
            "search",
            index=INDEX,
            body={"size": 0, "aggs": {"by": {"terms": {"field": "category.keyword"}}}},
        )
        buckets = {
            b["key"]: b["doc_count"] for b in aggs["aggregations"]["by"]["buckets"]
        }
        assert buckets == {"shoes": 2, "jackets": 2, "socks": 1}, buckets
        rows = (
            await call(
                "esql",
                query=f"FROM {INDEX} | WHERE in_stock == true | STATS n = COUNT(*)",
            )
        )["values"]
        assert rows == [[4]], rows
        primaries = [
            s for s in await call("get_shards", index=INDEX) if s["prirep"] == "p"
        ]
        assert primaries and all(s["state"] == "STARTED" for s in primaries), primaries

        missing = await client.call_tool("search", {"index": "mcp-no-such-index"})
        assert (
            missing.is_error and "index_not_found_exception" in missing.content[0].text
        ), missing.content


def test_e2e() -> None:
    api_key = seed()
    for env in ({"ES_URL": ES_URL, "ES_API_KEY": api_key}, BASIC_AUTH):
        asyncio.run(check(env))


if __name__ == "__main__":
    test_e2e()
    print(f"e2e OK: {len(TOOLS)} tools x 2 auth modes against {ES_URL}")

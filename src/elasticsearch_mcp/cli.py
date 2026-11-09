"""The `elasticsearch-mcp` command.

With no arguments it serves MCP over stdio, which is what MCP clients launch. With a command it runs one of
the same read-only tools and prints Elasticsearch's JSON: that is how the Agent Skill works where MCP isn't
allowed.
"""

import argparse
import asyncio
import json
import sys

from mcp.server.mcpserver.exceptions import ToolError

from . import server


def _stdin_or(value: str) -> str:
    """Let long queries and bodies come from stdin ("-"), which avoids shell-quoting trouble."""
    return sys.stdin.read() if value == "-" else value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="elasticsearch-mcp",
        description="Read-only Elasticsearch access. With no command, serves MCP over stdio. Settings come "
        "from ES_URL, ES_API_KEY (or ES_USERNAME and ES_PASSWORD) and ES_CA_CERT.",
    )
    commands = parser.add_subparsers(title="commands", metavar="COMMAND")

    def add(name: str, text: str, run) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=text, description=text)
        sub.set_defaults(run=run)
        return sub

    add(
        "cluster-health",
        "Cluster status (green, yellow or red), node and shard counts.",
        lambda a: server.cluster_health(),
    )
    add(
        "list-indices",
        "Indices matching a pattern, with health, status, doc count and size.",
        lambda a: server.list_indices(a.pattern),
    ).add_argument("pattern", nargs="?", default="*")
    add(
        "get-mappings",
        "Field names and types of an index or pattern.",
        lambda a: server.get_mappings(a.index),
    ).add_argument("index")
    search = add(
        "search",
        "Query DSL search: aggregations, sort and _source filtering work as usual.",
        lambda a: server.search(
            a.index, json.loads(_stdin_or(a.body)) if a.body else None
        ),
    )
    search.add_argument("index")
    search.add_argument(
        "body",
        nargs="?",
        help='full _search body as JSON, or "-" to read it from stdin',
    )
    add(
        "esql",
        "ES|QL query (Elasticsearch 8.11+), returned as columns and rows.",
        lambda a: server.esql(_stdin_or(a.query)),
    ).add_argument("query", help='the query, or "-" to read it from stdin')
    add(
        "get-shards",
        "Shards for indices matching a pattern: primary or replica, state, docs, size and node.",
        lambda a: server.get_shards(a.pattern),
    ).add_argument("pattern", nargs="?", default="*")
    return parser


async def _call(args: argparse.Namespace) -> str:
    try:
        return await args.run(args)
    finally:
        await server.es.aclose()


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if not hasattr(args, "run"):
        server.mcp.run()  # no command: the stdio server that MCP clients launch
        return
    try:
        print(asyncio.run(_call(args)))
    except ToolError as e:
        sys.exit(str(e))
    except json.JSONDecodeError as e:
        sys.exit(f"search body is not valid JSON: {e}")

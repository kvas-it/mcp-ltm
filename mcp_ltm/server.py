"""MCP server exposing long-term memory tools."""

import json
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from .config import Config
from .storage import MemoryStorage, InvalidMemoryId

# Default paths - can be overridden via environment variables
DEFAULT_BASE_PATH = Path.home() / ".local" / "share" / "mcp-ltm"
DEFAULT_MEMORY_PATH = DEFAULT_BASE_PATH / "memories"
DEFAULT_CONFIG_PATH = DEFAULT_BASE_PATH / "config.yaml"

server = Server("mcp-ltm")
storage: MemoryStorage | None = None
config: Config | None = None


def get_config() -> Config:
    global config
    if config is None:
        config_path = Path(os.environ.get("MCP_LTM_CONFIG", DEFAULT_CONFIG_PATH))
        config = Config(config_path)
    return config


def get_storage() -> MemoryStorage:
    global storage
    if storage is None:
        memory_path = Path(os.environ.get("MCP_LTM_PATH", DEFAULT_MEMORY_PATH))
        storage = MemoryStorage(memory_path, get_config())
    return storage


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="store_memory",
            description="Store a new long-term memory with tags for later retrieval.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title for the memory (3-8 words). Becomes the filename.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for retrieval. Use existing tags when possible (check with get_tags first).",
                    },
                    "summary": {
                        "type": "string",
                        "description": "1-2 sentence summary of the memory.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Full content in markdown. Can link to other memories using [text](memory_id.md).",
                    },
                    "links": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of related memories to link to.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Path to source document (full path or origin:path format). Auto-contracts using configured origins.",
                    },
                },
                "required": ["title", "tags", "summary", "content"],
            },
        ),
        Tool(
            name="query_memories",
            description="Search memories by tags. Returns memories with highest tag overlap.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to search for. Results ranked by overlap count.",
                    },
                    "required_tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags that must ALL be present (filter, not scoring).",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return (default 10).",
                    },
                    "include_content": {
                        "type": "boolean",
                        "description": "Include full content in results (default false).",
                    },
                },
                "required": ["tags"],
            },
        ),
        Tool(
            name="get_memory",
            description="Retrieve a specific memory by ID. Updates access stats.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Memory ID (the slug/filename without .md).",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="get_tags",
            description="Get all tags with usage counts. Use to discover existing tags before storing.",
            inputSchema={
                "type": "object",
                "properties": {
                    "include_examples": {
                        "type": "boolean",
                        "description": "Include example summaries for each tag (default false).",
                    },
                    "examples_per_tag": {
                        "type": "integer",
                        "description": "Number of example summaries per tag (default 2).",
                    },
                },
            },
        ),
        Tool(
            name="get_related_tags",
            description="Find tags that frequently co-occur with given tags. Useful for query expansion.",
            inputSchema={
                "type": "object",
                "properties": {
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags to find related tags for.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum related tags to return (default 10).",
                    },
                },
                "required": ["tags"],
            },
        ),
        Tool(
            name="update_memory",
            description="Update an existing memory's content, tags, links, or source.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Memory ID to update.",
                    },
                    "title": {
                        "type": "string",
                        "description": "New title (doesn't change the ID/filename).",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New tags (replaces existing).",
                    },
                    "summary": {
                        "type": "string",
                        "description": "New summary.",
                    },
                    "content": {
                        "type": "string",
                        "description": "New content.",
                    },
                    "links": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "New links (replaces existing).",
                    },
                    "source": {
                        "type": "string",
                        "description": "New source path.",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="delete_memory",
            description="Delete a memory permanently.",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Memory ID to delete.",
                    },
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="get_stale_memories",
            description="Find memories that might be candidates for pruning or consolidation.",
            inputSchema={
                "type": "object",
                "properties": {
                    "older_than_days": {
                        "type": "integer",
                        "description": "Only memories older than this many days.",
                    },
                    "min_access_count": {
                        "type": "integer",
                        "description": "Only memories accessed fewer than this many times.",
                    },
                },
            },
        ),
        Tool(
            name="list_origins",
            description="List configured origin directories. Origins allow short paths like 'hwif:research/file.md' instead of full paths.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="add_origin",
            description="Add or update an origin directory mapping.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Origin name (e.g., 'hwif', 'notes').",
                    },
                    "path": {
                        "type": "string",
                        "description": "Full path to the origin directory.",
                    },
                },
                "required": ["name", "path"],
            },
        ),
        Tool(
            name="remove_origin",
            description="Remove an origin directory mapping.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Origin name to remove.",
                    },
                },
                "required": ["name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    store = get_storage()
    cfg = get_config()

    if name == "store_memory":
        memory_id, suggested_links = store.store(
            title=arguments["title"],
            tags=arguments["tags"],
            summary=arguments["summary"],
            content=arguments["content"],
            links=arguments.get("links"),
            source=arguments.get("source"),
        )
        result = {"id": memory_id, "suggested_links": suggested_links}

    elif name == "query_memories":
        result = store.query(
            tags=arguments["tags"],
            required_tags=arguments.get("required_tags"),
            limit=arguments.get("limit", 10),
            include_content=arguments.get("include_content", False),
        )

    elif name == "get_memory":
        try:
            memory = store.get(arguments["id"])
        except InvalidMemoryId as e:
            result = {"error": str(e)}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        if memory is None:
            result = {"error": f"Memory not found: {arguments['id']}"}
        else:
            result = {
                "id": memory.id,
                "title": memory.title,
                "tags": memory.tags,
                "summary": memory.summary,
                "content": memory.content,
                "created_at": memory.created_at.isoformat(),
                "accessed_at": memory.accessed_at.isoformat(),
                "access_count": memory.access_count,
                "links": memory.links,
            }
            # Expand source path for the response
            if memory.source:
                expanded, warning = cfg.expand_path(memory.source)
                result["source"] = expanded
                if warning:
                    result["source_warning"] = warning

    elif name == "get_tags":
        result = store.get_tags(
            include_examples=arguments.get("include_examples", False),
            examples_per_tag=arguments.get("examples_per_tag", 2),
        )

    elif name == "get_related_tags":
        result = store.get_related_tags(
            tags=arguments["tags"],
            limit=arguments.get("limit", 10),
        )

    elif name == "update_memory":
        try:
            memory = store.update(
                memory_id=arguments["id"],
                title=arguments.get("title"),
                tags=arguments.get("tags"),
                summary=arguments.get("summary"),
                content=arguments.get("content"),
                links=arguments.get("links"),
                source=arguments.get("source"),
            )
        except InvalidMemoryId as e:
            result = {"error": str(e)}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        if memory is None:
            result = {"error": f"Memory not found: {arguments['id']}"}
        else:
            result = {"id": memory.id, "updated": True}

    elif name == "delete_memory":
        try:
            success = store.delete(arguments["id"])
        except InvalidMemoryId as e:
            result = {"error": str(e)}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
        result = {"deleted": success}

    elif name == "get_stale_memories":
        result = store.get_stale_memories(
            older_than_days=arguments.get("older_than_days"),
            min_access_count=arguments.get("min_access_count"),
        )

    elif name == "list_origins":
        result = {"origins": cfg.origins}

    elif name == "add_origin":
        cfg.add_origin(arguments["name"], arguments["path"])
        # Contract any existing sources that match the new origin
        updated = store.contract_sources_for_origin(
            arguments["name"], cfg.origins[arguments["name"]]
        )
        result = {
            "added": arguments["name"],
            "path": cfg.origins[arguments["name"]],
            "sources_contracted": len(updated),
            "updated_memories": updated if updated else None,
        }

    elif name == "remove_origin":
        existed = cfg.remove_origin(arguments["name"])
        result = {"removed": existed, "name": arguments["name"]}

    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def run():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main():
    import asyncio
    asyncio.run(run())


if __name__ == "__main__":
    main()

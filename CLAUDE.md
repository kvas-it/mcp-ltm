# mcp-ltm

Long-term memory MCP server for AI assistants. Stores memories as browsable markdown files with SQLite index for fast tag-based retrieval.

## Structure

```
mcp_ltm/
  config.py   - Origin management (path contraction/expansion)
  storage.py  - SQLite index + markdown file storage
  server.py   - MCP server with 11 tools
```

## Development

```bash
pip install -e .        # Install in editable mode
python test_storage.py  # Run tests
mcp-ltm                 # Start server (for testing)
```

## Code Review

Use `codex review --uncommitted` to get AI review of changes before committing.
Must be run from this directory so codex can see the repo context.

## Configuration

**Environment variables:**
- `MCP_LTM_PATH` - Memory storage directory (default: `~/.local/share/mcp-ltm/memories/`)
- `MCP_LTM_CONFIG` - Config file path (default: `~/.local/share/mcp-ltm/config.yaml`)

**Config file** (`~/.local/share/mcp-ltm/config.yaml`):
```yaml
origins:
  myproject: /path/to/project
  notes: /path/to/notes
```

## Tools

### Memory Operations
- `store_memory` - Create memory with title, tags, summary, content, optional source/links
- `query_memories` - Search by tags (ranked by overlap), filter by required_tags
- `get_memory` - Retrieve by ID (updates access stats)
- `update_memory` - Modify existing memory
- `delete_memory` - Remove memory
- `get_stale_memories` - Find pruning candidates (old, rarely accessed)

### Tag Operations
- `get_tags` - List all tags with counts and example summaries
- `get_related_tags` - Find co-occurring tags for query expansion

### Origin Management
- `list_origins` - Show configured origins
- `add_origin` - Register origin (auto-contracts existing matching sources)
- `remove_origin` - Delete origin mapping

## Usage with Claude Code

Add to `~/.claude.json`:

```json
{
  "mcpServers": {
    "ltm": {
      "command": "mcp-ltm"
    }
  }
}
```

Or with custom paths:

```json
{
  "mcpServers": {
    "ltm": {
      "command": "mcp-ltm",
      "env": {
        "MCP_LTM_PATH": "/custom/path/to/memories",
        "MCP_LTM_CONFIG": "/custom/path/to/config.yaml"
      }
    }
  }
}
```

## Key Design Decisions

1. **Hybrid storage**: SQLite for fast queries, markdown files for human browsing
2. **Tag-based retrieval**: Simple, interpretable, no embeddings needed
3. **Origin system**: Short portable paths (`project:path/file.md`) that expand to full paths
4. **Two-tier memory**: Pure memories (self-contained) and reference memories (point to external docs)
5. **Access tracking**: Timestamps and counts for staleness detection
6. **Write ordering**: Markdown first, then DB - orphaned files are less harmful than
   DB entries without files (which would make `get()` return None for visible memories)
7. **Link validation**: Links to nonexistent memories are silently filtered out
8. **Memory ID validation**: IDs must match `^[\w-]+$` to prevent path traversal

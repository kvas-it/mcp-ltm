# mcp-ltm: Long-Term Memory for LLMs

An MCP server that provides persistent long-term memory for AI assistants. Memories are stored as browsable markdown files with a SQLite index for fast tag-based retrieval.

## Features

- **Tag-based retrieval**: Store and query memories using tags, ranked by overlap
- **Human-browsable**: Memories stored as markdown files with YAML frontmatter
- **Tag co-occurrence**: Discover related tags based on how often they appear together
- **Memory linking**: Create wiki-style links between related memories
- **Source references**: Link memories to external documents with origin-based path management
- **Access tracking**: Track when and how often memories are accessed for pruning

## Installation

```bash
pip install -e .
```

## Configuration

Add to your Claude Code MCP settings (`~/.claude.json`):

```json
{
  "mcpServers": {
    "ltm": {
      "command": "mcp-ltm",
      "env": {
        "MCP_LTM_PATH": "/path/to/memories",
        "MCP_LTM_CONFIG": "/path/to/config.yaml"
      }
    }
  }
}
```

Default paths (if env vars not set):
- Memories: `~/.local/share/mcp-ltm/memories/`
- Config: `~/.local/share/mcp-ltm/config.yaml`

## Tools

### Memory Operations

- **store_memory** - Create memory with title, tags, summary, content, optional source/links
- **query_memories** - Search by tags (ranked by overlap), filter by required_tags
- **get_memory** - Retrieve by ID (updates access stats)
- **update_memory** - Modify existing memory
- **delete_memory** - Remove memory
- **get_stale_memories** - Find old, rarely-accessed memories for pruning

### Tag Operations

- **get_tags** - List all tags with usage counts and example summaries
- **get_related_tags** - Find tags that frequently co-occur (for query expansion)

### Origin Management

- **list_origins** - Show configured origin directories
- **add_origin** - Register origin (auto-contracts existing matching sources)
- **remove_origin** - Delete origin mapping

## Origins: Managing Source Paths

Origins let you use short paths like `myproject:docs/file.md` instead of full absolute paths.

**Config file** (`~/.local/share/mcp-ltm/config.yaml`):
```yaml
origins:
  myproject: /home/user/projects/myproject
  notes: /home/user/notes
```

When storing a memory with a source:
- Full paths matching an origin are automatically contracted
- When retrieving, paths are expanded back to full paths
- Makes memories portable and readable

## Storage Format

Each memory is a markdown file with YAML frontmatter:

```markdown
---
id: example-memory-title
title: Example Memory Title
tags: [python, debugging, testing]
summary: Brief description of what this memory contains.
source: myproject:docs/example.md
created_at: 2026-01-15T10:30:00Z
accessed_at: 2026-01-20T14:00:00Z
access_count: 3
links: [related-memory-id]
---

# Example Memory Title

Full content here. Can link to [other memories](related-memory-id.md).
```

The SQLite index (`index.db`) stores metadata for fast querying but can be rebuilt from the markdown files if needed.

## Tag Conventions

Tags are normalized: lowercase, spaces become hyphens, punctuation stripped (except colons for namespacing).

Suggested prefixes:
- `type:` - Memory type (decision, insight, preference, fact, reference)
- `project:` - Project name
- `topic:` - Subject area

## Usage Patterns

### Pure Memory
Self-contained insight with no external reference:
```python
store_memory(
    title="Python Dict Merge Operator",
    tags=["python", "syntax"],
    summary="Python 3.9+ supports d1 | d2 to merge dicts.",
    content="Use `d1 | d2` to merge dictionaries..."
)
```

### Reference Memory
Summary pointing to detailed external document:
```python
store_memory(
    title="Project Architecture Overview",
    tags=["project:foo", "architecture"],
    summary="Key architectural decisions for the Foo project.",
    content="Main insight: use event sourcing for audit trail...",
    source="/path/to/architecture.md"
)
```

## License

MIT License - see [LICENSE](LICENSE) for details.

"""Storage layer: SQLite index + markdown files."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from .config import Config


# Valid memory ID: word characters (letters, digits, underscores) and hyphens
# Uses \w to match Unicode letters for backwards compatibility with slugify
MEMORY_ID_PATTERN = re.compile(r"^[\w-]+$")


class InvalidMemoryId(ValueError):
    """Raised when a memory ID contains invalid characters."""

    pass


@dataclass
class Memory:
    id: str
    title: str
    tags: list[str]
    summary: str
    content: str
    created_at: datetime
    accessed_at: datetime
    access_count: int
    links: list[str]
    source: str | None = None  # origin:path or full path to source document


def slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    text = text.lower()
    text = re.sub(r"[''`]", "", text)  # remove apostrophes
    text = re.sub(r"[^\w\s-]", " ", text)  # replace punctuation with space
    text = re.sub(r"[-\s]+", "-", text)  # collapse spaces/hyphens
    text = text.strip("-")
    return text


def normalize_tag(tag: str) -> str:
    """Normalize a tag: lowercase, hyphens for spaces, strip punctuation."""
    tag = tag.lower().strip()
    tag = re.sub(r"[^\w\s:-]", "", tag)  # keep colons for namespacing
    tag = re.sub(r"\s+", "-", tag)
    return tag


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from markdown content."""
    if not content.startswith("---"):
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        return {}, content

    frontmatter = yaml.safe_load(parts[1]) or {}
    body = parts[2].lstrip("\n")
    return frontmatter, body


def render_frontmatter(metadata: dict) -> str:
    """Render metadata as YAML frontmatter."""
    return "---\n" + yaml.dump(metadata, default_flow_style=False, sort_keys=False) + "---\n\n"


class MemoryStorage:
    def __init__(self, base_path: Path, config: Config | None = None):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_path / "index.db"
        self.config = config
        self._init_db()

    def _init_db(self):
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    summary TEXT,
                    source TEXT,
                    created_at TEXT,
                    accessed_at TEXT,
                    access_count INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS memory_tags (
                    memory_id TEXT,
                    tag TEXT,
                    PRIMARY KEY (memory_id, tag),
                    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS memory_links (
                    from_id TEXT,
                    to_id TEXT,
                    PRIMARY KEY (from_id, to_id),
                    FOREIGN KEY (from_id) REFERENCES memories(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS tag_cooccurrence (
                    tag1 TEXT,
                    tag2 TEXT,
                    count INTEGER DEFAULT 1,
                    PRIMARY KEY (tag1, tag2)
                );

                CREATE INDEX IF NOT EXISTS idx_tags ON memory_tags(tag);
                CREATE INDEX IF NOT EXISTS idx_cooccurrence ON tag_cooccurrence(tag1);
            """)
            # Add source column if missing (migration for existing DBs)
            try:
                conn.execute("ALTER TABLE memories ADD COLUMN source TEXT")
            except sqlite3.OperationalError:
                pass  # Column already exists

    def _contract_source(self, source: str | None) -> str | None:
        """Contract a source path using origins if available."""
        if source is None:
            return None
        if self.config is None:
            return source
        return self.config.contract_path(source)

    def _expand_source(self, source: str | None) -> tuple[str | None, str | None]:
        """Expand a source path. Returns (path, warning)."""
        if source is None:
            return None, None
        if self.config is None:
            return source, None
        return self.config.expand_path(source)

    def _generate_id(self, title: str) -> str:
        """Generate a unique ID from title."""
        base_slug = slugify(title)
        if not base_slug:
            base_slug = "memory"

        slug = base_slug
        counter = 1
        while (self.base_path / f"{slug}.md").exists():
            counter += 1
            slug = f"{base_slug}-{counter}"
        return slug

    def _resolve_memory_path(self, memory_id: str) -> Path:
        """Resolve memory ID to file path, validating against path traversal.

        Raises InvalidMemoryId if the ID contains invalid characters.
        """
        if not MEMORY_ID_PATTERN.match(memory_id):
            raise InvalidMemoryId(
                f"Invalid memory ID: {memory_id!r}. "
                "Must contain only letters, digits, hyphens, and underscores."
            )
        return self.base_path / f"{memory_id}.md"

    def _update_cooccurrence(self, conn: sqlite3.Connection, tags: list[str], delta: int = 1):
        """Update tag co-occurrence counts."""
        for i, tag1 in enumerate(tags):
            for tag2 in tags[i + 1:]:
                t1, t2 = sorted([tag1, tag2])
                if delta > 0:
                    conn.execute("""
                        INSERT INTO tag_cooccurrence (tag1, tag2, count)
                        VALUES (?, ?, ?)
                        ON CONFLICT(tag1, tag2) DO UPDATE SET count = count + ?
                    """, (t1, t2, delta, delta))
                else:
                    conn.execute("""
                        UPDATE tag_cooccurrence SET count = count + ?
                        WHERE tag1 = ? AND tag2 = ?
                    """, (delta, t1, t2))

    def _write_markdown(self, memory: Memory):
        """Write memory to markdown file."""
        metadata = {
            "id": memory.id,
            "title": memory.title,
            "tags": memory.tags,
            "summary": memory.summary,
            "created_at": memory.created_at.isoformat(),
            "accessed_at": memory.accessed_at.isoformat(),
            "access_count": memory.access_count,
            "links": memory.links,
        }
        if memory.source:
            metadata["source"] = memory.source

        content = render_frontmatter(metadata)
        content += f"# {memory.title}\n\n"
        content += memory.content

        file_path = self.base_path / f"{memory.id}.md"
        file_path.write_text(content)

    def _read_markdown(self, memory_id: str) -> Memory | None:
        """Read memory from markdown file."""
        file_path = self._resolve_memory_path(memory_id)
        if not file_path.exists():
            return None

        content = file_path.read_text()
        frontmatter, body = parse_frontmatter(content)

        # Remove the H1 title from body if present
        body = re.sub(r"^#\s+.*\n+", "", body)

        return Memory(
            id=frontmatter.get("id", memory_id),
            title=frontmatter.get("title", ""),
            tags=frontmatter.get("tags", []),
            summary=frontmatter.get("summary", ""),
            content=body.strip(),
            created_at=datetime.fromisoformat(frontmatter.get("created_at", datetime.now(timezone.utc).isoformat())),
            accessed_at=datetime.fromisoformat(frontmatter.get("accessed_at", datetime.now(timezone.utc).isoformat())),
            access_count=frontmatter.get("access_count", 0),
            links=frontmatter.get("links", []),
            source=frontmatter.get("source"),
        )

    def store(
        self,
        title: str,
        tags: list[str],
        summary: str,
        content: str,
        links: list[str] | None = None,
        source: str | None = None,
    ) -> tuple[str, list[str]]:
        """Store a new memory. Returns (id, suggested_links)."""
        now = datetime.now(timezone.utc)
        memory_id = self._generate_id(title)
        normalized_tags = [normalize_tag(t) for t in tags]
        links = links or []
        contracted_source = self._contract_source(source)

        memory = Memory(
            id=memory_id,
            title=title,
            tags=normalized_tags,
            summary=summary,
            content=content,
            created_at=now,
            accessed_at=now,
            access_count=0,
            links=links,
            source=contracted_source,
        )

        # Write markdown file
        self._write_markdown(memory)

        # Update SQLite index
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO memories (id, title, summary, source, created_at, accessed_at, access_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (memory_id, title, summary, contracted_source, now.isoformat(), now.isoformat(), 0))

            for tag in normalized_tags:
                conn.execute("INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)", (memory_id, tag))

            for link in links:
                conn.execute("INSERT OR IGNORE INTO memory_links (from_id, to_id) VALUES (?, ?)", (memory_id, link))

            self._update_cooccurrence(conn, normalized_tags)

            # Find suggested links (memories with highest tag overlap)
            if normalized_tags:
                placeholders = ",".join("?" * len(normalized_tags))
                suggested = conn.execute(f"""
                    SELECT memory_id, COUNT(*) as overlap
                    FROM memory_tags
                    WHERE tag IN ({placeholders}) AND memory_id != ?
                    GROUP BY memory_id
                    ORDER BY overlap DESC
                    LIMIT 5
                """, (*normalized_tags, memory_id)).fetchall()
                suggested_links = [row[0] for row in suggested]
            else:
                suggested_links = []

        return memory_id, suggested_links

    def query(
        self,
        tags: list[str],
        required_tags: list[str] | None = None,
        limit: int = 10,
        include_content: bool = False,
    ) -> list[dict]:
        """Query memories by tags. Returns list of memory dicts."""
        normalized_tags = [normalize_tag(t) for t in tags]
        required_tags = [normalize_tag(t) for t in (required_tags or [])]

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            if not normalized_tags and not required_tags:
                # No tags specified, return recent memories
                rows = conn.execute("""
                    SELECT m.*, GROUP_CONCAT(mt.tag) as tags_str
                    FROM memories m
                    LEFT JOIN memory_tags mt ON m.id = mt.memory_id
                    GROUP BY m.id
                    ORDER BY m.created_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            else:
                all_tags = list(set(normalized_tags + required_tags))
                placeholders = ",".join("?" * len(all_tags))

                query = f"""
                    SELECT m.*,
                           COUNT(DISTINCT mt.tag) as tag_overlap,
                           GROUP_CONCAT(DISTINCT mt.tag) as tags_str
                    FROM memories m
                    JOIN memory_tags mt ON m.id = mt.memory_id
                    WHERE mt.tag IN ({placeholders})
                """
                params = list(all_tags)

                if required_tags:
                    # Subquery to ensure all required tags are present
                    req_placeholders = ",".join("?" * len(required_tags))
                    query += f"""
                        AND m.id IN (
                            SELECT memory_id FROM memory_tags
                            WHERE tag IN ({req_placeholders})
                            GROUP BY memory_id
                            HAVING COUNT(DISTINCT tag) = ?
                        )
                    """
                    params.extend(required_tags)
                    params.append(len(required_tags))

                query += """
                    GROUP BY m.id
                    ORDER BY tag_overlap DESC, m.accessed_at DESC
                    LIMIT ?
                """
                params.append(limit)

                rows = conn.execute(query, params).fetchall()

            results = []
            for row in rows:
                memory_dict = {
                    "id": row["id"],
                    "title": row["title"],
                    "summary": row["summary"],
                    "tags": row["tags_str"].split(",") if row["tags_str"] else [],
                    "created_at": row["created_at"],
                }

                # Expand source path
                if row["source"]:
                    expanded, warning = self._expand_source(row["source"])
                    memory_dict["source"] = expanded
                    if warning:
                        memory_dict["source_warning"] = warning

                if include_content:
                    memory = self._read_markdown(row["id"])
                    if memory:
                        memory_dict["content"] = memory.content
                        memory_dict["links"] = memory.links

                results.append(memory_dict)

            return results

    def get(self, memory_id: str) -> Memory | None:
        """Get a memory by ID, updating access stats."""
        memory = self._read_markdown(memory_id)
        if not memory:
            return None

        now = datetime.now(timezone.utc)
        memory.accessed_at = now
        memory.access_count += 1

        # Update markdown file
        self._write_markdown(memory)

        # Update SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memories
                SET accessed_at = ?, access_count = access_count + 1
                WHERE id = ?
            """, (now.isoformat(), memory_id))

        return memory

    def update(
        self,
        memory_id: str,
        title: str | None = None,
        tags: list[str] | None = None,
        summary: str | None = None,
        content: str | None = None,
        links: list[str] | None = None,
        source: str | None = None,
    ) -> Memory | None:
        """Update an existing memory."""
        memory = self._read_markdown(memory_id)
        if not memory:
            return None

        old_tags = memory.tags

        if title is not None:
            memory.title = title
        if tags is not None:
            memory.tags = [normalize_tag(t) for t in tags]
        if summary is not None:
            memory.summary = summary
        if content is not None:
            memory.content = content
        if links is not None:
            memory.links = links
        if source is not None:
            memory.source = self._contract_source(source)

        memory.accessed_at = datetime.now(timezone.utc)

        # Write updated markdown
        self._write_markdown(memory)

        # Update SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE memories
                SET title = ?, summary = ?, source = ?, accessed_at = ?
                WHERE id = ?
            """, (memory.title, memory.summary, memory.source, memory.accessed_at.isoformat(), memory_id))

            if tags is not None:
                # Update tags
                conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
                for tag in memory.tags:
                    conn.execute("INSERT INTO memory_tags (memory_id, tag) VALUES (?, ?)", (memory_id, tag))

                # Update co-occurrence
                self._update_cooccurrence(conn, old_tags, delta=-1)
                self._update_cooccurrence(conn, memory.tags, delta=1)

            if links is not None:
                conn.execute("DELETE FROM memory_links WHERE from_id = ?", (memory_id,))
                for link in memory.links:
                    conn.execute("INSERT OR IGNORE INTO memory_links (from_id, to_id) VALUES (?, ?)", (memory_id, link))

        return memory

    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        file_path = self._resolve_memory_path(memory_id)
        if not file_path.exists():
            return False

        memory = self._read_markdown(memory_id)

        # Delete file
        file_path.unlink()

        # Delete from SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
            conn.execute("DELETE FROM memory_tags WHERE memory_id = ?", (memory_id,))
            conn.execute("DELETE FROM memory_links WHERE from_id = ? OR to_id = ?", (memory_id, memory_id))

            if memory:
                self._update_cooccurrence(conn, memory.tags, delta=-1)

        return True

    def get_tags(self, include_examples: bool = False, examples_per_tag: int = 2) -> list[dict]:
        """Get all tags with counts and optional examples."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            tags = conn.execute("""
                SELECT tag, COUNT(*) as count
                FROM memory_tags
                GROUP BY tag
                ORDER BY count DESC
            """).fetchall()

            results = []
            for row in tags:
                tag_dict = {"tag": row["tag"], "count": row["count"]}

                if include_examples:
                    examples = conn.execute("""
                        SELECT m.summary
                        FROM memories m
                        JOIN memory_tags mt ON m.id = mt.memory_id
                        WHERE mt.tag = ?
                        ORDER BY m.accessed_at DESC
                        LIMIT ?
                    """, (row["tag"], examples_per_tag)).fetchall()
                    tag_dict["examples"] = [e["summary"] for e in examples]

                results.append(tag_dict)

            return results

    def get_related_tags(self, tags: list[str], limit: int = 10) -> list[dict]:
        """Get tags that frequently co-occur with the given tags."""
        normalized_tags = [normalize_tag(t) for t in tags]

        with sqlite3.connect(self.db_path) as conn:
            # Find tags that co-occur with any of the input tags
            placeholders = ",".join("?" * len(normalized_tags))

            rows = conn.execute(f"""
                SELECT
                    CASE WHEN tag1 IN ({placeholders}) THEN tag2 ELSE tag1 END as related_tag,
                    SUM(count) as score
                FROM tag_cooccurrence
                WHERE tag1 IN ({placeholders}) OR tag2 IN ({placeholders})
                GROUP BY related_tag
                HAVING related_tag NOT IN ({placeholders})
                ORDER BY score DESC
                LIMIT ?
            """, (*normalized_tags, *normalized_tags, *normalized_tags, *normalized_tags, limit)).fetchall()

            return [{"tag": row[0], "score": row[1]} for row in rows]

    def get_stale_memories(
        self,
        older_than_days: int | None = None,
        min_access_count: int | None = None,
    ) -> list[dict]:
        """Get memories that might be candidates for pruning."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row

            conditions = []
            params = []

            if older_than_days is not None:
                cutoff = datetime.now(timezone.utc).isoformat()[:10]  # Date only
                conditions.append("DATE(created_at) < DATE(?, ?)")
                params.extend([cutoff, f"-{older_than_days} days"])

            if min_access_count is not None:
                conditions.append("access_count < ?")
                params.append(min_access_count)

            where_clause = " AND ".join(conditions) if conditions else "1=1"

            rows = conn.execute(f"""
                SELECT id, title, summary, created_at, accessed_at, access_count
                FROM memories
                WHERE {where_clause}
                ORDER BY access_count ASC, created_at ASC
            """, params).fetchall()

            return [dict(row) for row in rows]

    def contract_sources_for_origin(self, origin_name: str, origin_path: str) -> list[str]:
        """Contract existing full-path sources to use a newly added origin.

        Returns list of memory IDs that were updated.
        """
        origin_path = str(Path(origin_path).resolve())
        prefix = origin_path + "/"
        updated_ids = []

        with sqlite3.connect(self.db_path) as conn:
            # Find memories with sources that match this origin
            rows = conn.execute(
                "SELECT id, source FROM memories WHERE source IS NOT NULL"
            ).fetchall()

            for memory_id, source in rows:
                if source and source.startswith(prefix):
                    # Contract the path
                    relative = source[len(prefix):]
                    new_source = f"{origin_name}:{relative}"

                    # Update SQLite
                    conn.execute(
                        "UPDATE memories SET source = ? WHERE id = ?",
                        (new_source, memory_id)
                    )

                    # Update markdown file
                    memory = self._read_markdown(memory_id)
                    if memory:
                        memory.source = new_source
                        self._write_markdown(memory)

                    updated_ids.append(memory_id)

        return updated_ids

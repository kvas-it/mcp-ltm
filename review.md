# Code Review

## Findings (ordered by severity)

1) Path traversal allows reading/updating/deleting files outside the memory directory
- Files/lines: `mcp_ltm/storage.py:189`, `mcp_ltm/storage.py:366`, `mcp_ltm/storage.py:389`, `mcp_ltm/storage.py:449`
- `memory_id` is taken directly from tool input and used to build file paths. A caller can pass `../some/other/file` and the code will read or unlink arbitrary `*.md` files outside `base_path`.
- Fix: validate `memory_id` against a strict slug regex (e.g., `^[a-z0-9-]+$`) or resolve the path and ensure it stays within `base_path` before any file I/O.

2) Duplicate tags can raise IntegrityError and desync markdown/db
- Files/lines: `mcp_ltm/storage.py:253`, `mcp_ltm/storage.py:434`
- `memory_tags` has a `(memory_id, tag)` primary key. If `tags` contains duplicates, `INSERT` will fail and you already wrote the markdown file. This can leave an orphaned file and a partially updated DB.
- Fix: dedupe tags on input and/or use `INSERT OR IGNORE`. If you allow duplicates, also update co-occurrence logic to match the DB representation.

3) `get_related_tags` fails on empty input
- Files/lines: `mcp_ltm/storage.py:502`
- If `tags=[]`, `placeholders` becomes an empty string and the SQL is invalid (`IN ()`). The tool schema requires `tags`, but empty lists are still possible at runtime.
- Fix: early-return `[]` when `normalized_tags` is empty.

4) Co-occurrence counts can go negative and never removed
- Files/lines: `mcp_ltm/storage.py:150`
- When tags are removed, the counter is decremented but rows are never deleted when count reaches 0 (or below). This can skew `get_related_tags` and accumulate junk rows.
- Fix: clamp at zero or delete rows when count <= 0.

5) Foreign key constraints are declared but not enforced
- Files/lines: `mcp_ltm/storage.py:77`
- SQLite does not enforce foreign keys unless `PRAGMA foreign_keys=ON` is set per connection. This makes `memory_links` and `memory_tags` integrity entirely manual.
- Fix: enable foreign keys on each connection (or use a connection factory).

## Improvements (non-blocking)

- Consider wrapping `store`/`update` in a single transaction and only writing the markdown file after the DB write succeeds (or the reverse with rollback). This reduces the chance of DB/markdown divergence on failures.
- Normalize/validate `links` to ensure they refer to existing memory IDs and are slug-safe, or explicitly document that they are best-effort.

## Tests to Add

- Path traversal attempts for `get`, `update`, `delete` (should be rejected).
- Duplicate tags in `store`/`update` (should not error and should produce consistent tag lists).
- `get_related_tags([])` should return `[]` without SQL errors.
- Tag removal updates should not leave negative or zero-count co-occurrence rows.


# mcp-ltm Code Review TODO

Based on Codex review in `review.md`.

## Security Fixes (Critical)

- [x] **Fix path traversal vulnerability**
  - Added `_resolve_memory_path()` helper that validates memory_id against `^[a-z0-9-]+$`
  - Added `InvalidMemoryId` exception, caught in server.py for clean error messages
  - Test added: `test_path_traversal_rejected()`

## Data Integrity Fixes

- [x] **Dedupe tags to prevent IntegrityError**
  - Used `dict.fromkeys()` to dedupe after normalization in both `store()` and `update()`
  - Test added: `test_duplicate_tags_deduped()`

- [x] **Handle empty input in get_related_tags**
  - Early-return `[]` when `normalized_tags` is empty
  - Also filters out empty strings after normalization
  - Test added: `test_get_related_tags_empty_input()`

- [x] **Clean up zero/negative co-occurrence counts**
  - Delete rows with `count <= 0` after decrementing
  - Test added: `test_cooccurrence_cleanup()`

- [x] **Enable foreign key enforcement**
  - Added `_connect()` helper that runs `PRAGMA foreign_keys=ON`
  - All DB connections now use the helper

## Tests to Add

- [x] Test path traversal rejection for `get`, `update`, `delete`
- [x] Test duplicate tags handling in `store`/`update`
- [x] Test `get_related_tags([])` returns `[]` without error
- [x] Test tag removal doesn't leave zero/negative co-occurrence rows

## Non-blocking Improvements

- [x] **Document write ordering decision**
  - Markdown is written first, then DB - orphaned files are less harmful than
    DB entries without files (which would make get() return None for visible memories)
  - Added comments explaining this trade-off

- [x] **Validate links refer to existing memory IDs**
  - Added `_memory_exists()` and `_validate_links()` helpers
  - Invalid/nonexistent links are silently filtered out
  - Test added: `test_link_validation()`

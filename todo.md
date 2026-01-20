# mcp-ltm Code Review TODO

Based on Codex review in `review.md`.

## Security Fixes (Critical)

- [x] **Fix path traversal vulnerability**
  - Added `_resolve_memory_path()` helper that validates memory_id against `^[a-z0-9-]+$`
  - Added `InvalidMemoryId` exception, caught in server.py for clean error messages
  - Test added: `test_path_traversal_rejected()`

## Data Integrity Fixes

- [ ] **Dedupe tags to prevent IntegrityError**
  - Location: `storage.py:253`, `storage.py:434`
  - Issue: Duplicate tags in input cause INSERT failure after markdown already written
  - Fix: Dedupe tags on input and/or use `INSERT OR IGNORE`

- [ ] **Handle empty input in get_related_tags**
  - Location: `storage.py:502`
  - Issue: Empty `tags=[]` produces invalid SQL `IN ()`
  - Fix: Early-return `[]` when `normalized_tags` is empty

- [ ] **Clean up zero/negative co-occurrence counts**
  - Location: `storage.py:150`
  - Issue: Rows never deleted when count reaches 0, can go negative
  - Fix: Delete rows when count <= 0

- [ ] **Enable foreign key enforcement**
  - Location: `storage.py:77`
  - Issue: SQLite FKs not enforced without `PRAGMA foreign_keys=ON`
  - Fix: Set pragma on each connection

## Tests to Add

- [x] Test path traversal rejection for `get`, `update`, `delete`
- [ ] Test duplicate tags handling in `store`/`update`
- [ ] Test `get_related_tags([])` returns `[]` without error
- [ ] Test tag removal doesn't leave zero/negative co-occurrence rows

## Non-blocking Improvements (defer)

- [ ] Wrap store/update in transaction, write markdown after DB succeeds
- [ ] Validate links refer to existing memory IDs

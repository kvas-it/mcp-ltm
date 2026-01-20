"""Quick test of the storage layer."""

import tempfile
from pathlib import Path

from mcp_ltm.config import Config
from mcp_ltm.storage import MemoryStorage, slugify, normalize_tag, InvalidMemoryId


def test_slugify():
    assert slugify("Hello World") == "hello-world"
    assert slugify("Pytest's -x Flag: Stop!") == "pytests-x-flag-stop"
    assert slugify("  Multiple   Spaces  ") == "multiple-spaces"


def test_normalize_tag():
    assert normalize_tag("Hello World") == "hello-world"
    assert normalize_tag("type:Decision") == "type:decision"
    assert normalize_tag("  python  ") == "python"


def test_store_and_retrieve():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        # Store a memory
        memory_id, suggested = storage.store(
            title="Pytest Stop on First Failure",
            tags=["python", "testing", "pytest"],
            summary="The -x flag stops pytest on first failure.",
            content="Use `pytest -x` to stop on first failure. Useful for debugging.",
        )

        assert memory_id == "pytest-stop-on-first-failure"
        assert (Path(tmpdir) / f"{memory_id}.md").exists()

        # Query by tags
        results = storage.query(tags=["python", "testing"])
        assert len(results) == 1
        assert results[0]["id"] == memory_id

        # Get full memory
        memory = storage.get(memory_id)
        assert memory is not None
        assert memory.title == "Pytest Stop on First Failure"
        assert memory.access_count == 1

        # Get tags
        tags = storage.get_tags()
        assert len(tags) == 3
        tag_names = [t["tag"] for t in tags]
        assert "python" in tag_names


def test_tag_cooccurrence():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        # Store memories with overlapping tags
        storage.store(
            title="Memory One",
            tags=["python", "testing"],
            summary="First memory",
            content="Content one",
        )
        storage.store(
            title="Memory Two",
            tags=["python", "debugging"],
            summary="Second memory",
            content="Content two",
        )

        # Check co-occurrence
        related = storage.get_related_tags(["python"])
        related_tags = [r["tag"] for r in related]
        assert "testing" in related_tags
        assert "debugging" in related_tags


def test_required_tags():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        storage.store(
            title="Python Testing",
            tags=["python", "testing", "type:insight"],
            summary="About testing",
            content="Content",
        )
        storage.store(
            title="Python Debugging",
            tags=["python", "debugging", "type:decision"],
            summary="About debugging",
            content="Content",
        )

        # Query with required tag
        results = storage.query(tags=["python"], required_tags=["type:insight"])
        assert len(results) == 1
        assert results[0]["title"] == "Python Testing"


def test_links():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        id1, _ = storage.store(
            title="First Memory",
            tags=["topic-a"],
            summary="First",
            content="Content one",
        )
        id2, suggested = storage.store(
            title="Second Memory",
            tags=["topic-a"],
            summary="Second",
            content="Content two, related to [first](first-memory.md).",
            links=[id1],
        )

        # suggested_links should include the first memory
        assert id1 in suggested

        # Verify link is stored
        memory = storage.get(id2)
        assert id1 in memory.links


def test_source_without_config():
    """Test source field without origin configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        memory_id, _ = storage.store(
            title="Memory With Source",
            tags=["test"],
            summary="Test memory",
            content="Content",
            source="/absolute/path/to/file.md",
        )

        memory = storage.get(memory_id)
        assert memory.source == "/absolute/path/to/file.md"


def test_config_origins():
    """Test config origin management."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config = Config(config_path)

        # Initially empty
        assert config.origins == {}

        # Add an origin
        config.add_origin("hwif", "/Users/test/Documents/hwif")
        assert "hwif" in config.origins
        assert config.origins["hwif"] == "/Users/test/Documents/hwif"

        # Contract path
        contracted = config.contract_path("/Users/test/Documents/hwif/research/file.md")
        assert contracted == "hwif:research/file.md"

        # Expand path
        expanded, warning = config.expand_path("hwif:research/file.md")
        assert expanded == "/Users/test/Documents/hwif/research/file.md"
        assert warning is None

        # Unknown origin
        expanded, warning = config.expand_path("unknown:file.md")
        assert expanded == "unknown:file.md"
        assert warning is not None

        # Remove origin
        config.remove_origin("hwif")
        assert "hwif" not in config.origins

        # Config persists
        config2 = Config(config_path)
        assert "hwif" not in config2.origins


def test_source_with_config():
    """Test source field with origin configuration."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Set up config
        config_path = Path(tmpdir) / "config.yaml"
        config = Config(config_path)
        config.add_origin("project", "/Users/test/project")

        # Set up storage with config
        memory_path = Path(tmpdir) / "memories"
        storage = MemoryStorage(memory_path, config)

        # Store with full path - should contract
        memory_id, _ = storage.store(
            title="Memory With Source",
            tags=["test"],
            summary="Test memory",
            content="Content",
            source="/Users/test/project/docs/file.md",
        )

        # Read the markdown file to check stored format
        md_path = memory_path / f"{memory_id}.md"
        content = md_path.read_text()
        assert "source: project:docs/file.md" in content

        # Query should return expanded path
        results = storage.query(tags=["test"])
        assert results[0].get("source") == "/Users/test/project/docs/file.md"


def test_update_source():
    """Test updating the source field."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        memory_id, _ = storage.store(
            title="Memory",
            tags=["test"],
            summary="Test",
            content="Content",
        )

        # Initially no source
        memory = storage.get(memory_id)
        assert memory.source is None

        # Update with source
        storage.update(memory_id, source="/path/to/source.md")

        memory = storage.get(memory_id)
        assert memory.source == "/path/to/source.md"


def test_duplicate_tags_deduped():
    """Test that duplicate tags are deduped without error."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        # Store with duplicate tags (including ones that normalize to same value)
        memory_id, _ = storage.store(
            title="Test Memory",
            tags=["Python", "python", "PYTHON", "testing", "testing"],
            summary="Test",
            content="Content",
        )

        # Should succeed and have deduped tags
        memory = storage.get(memory_id)
        assert memory is not None
        assert memory.tags == ["python", "testing"]

        # Update with duplicate tags
        storage.update(memory_id, tags=["New", "new", "NEW", "tag"])
        memory = storage.get(memory_id)
        assert memory.tags == ["new", "tag"]


def test_path_traversal_rejected():
    """Test that path traversal attempts are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = MemoryStorage(Path(tmpdir))

        # Store a valid memory first
        storage.store(
            title="Valid Memory",
            tags=["test"],
            summary="Test",
            content="Content",
        )

        # Path traversal attempts should raise InvalidMemoryId
        # These contain characters not in [\w-]: slashes, dots, spaces, etc.
        traversal_ids = [
            "../etc/passwd",
            "..%2F..%2Fetc/passwd",
            "foo/../../../etc/passwd",
            "has spaces",
            "has.dot",
            "has/slash",
        ]

        for bad_id in traversal_ids:
            try:
                storage.get(bad_id)
                assert False, f"Should have raised InvalidMemoryId for {bad_id!r}"
            except InvalidMemoryId:
                pass

            try:
                storage.update(bad_id, content="hacked")
                assert False, f"Should have raised InvalidMemoryId for {bad_id!r}"
            except InvalidMemoryId:
                pass

            try:
                storage.delete(bad_id)
                assert False, f"Should have raised InvalidMemoryId for {bad_id!r}"
            except InvalidMemoryId:
                pass

        # Valid IDs should work (backwards compat with slugify)
        # These return None (not found) but don't raise InvalidMemoryId
        valid_ids = [
            "valid_with_underscore",
            "UPPERCASE",  # \w includes uppercase
            "café",  # Unicode letters allowed
            "日本語",  # Non-latin scripts
        ]
        for valid_id in valid_ids:
            assert storage.get(valid_id) is None
            assert storage.update(valid_id, content="test") is None
            assert storage.delete(valid_id) is False


def test_retroactive_origin_contraction():
    """Test that adding an origin contracts existing full-path sources."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.yaml"
        config = Config(config_path)
        memory_path = Path(tmpdir) / "memories"
        storage = MemoryStorage(memory_path, config)

        # Store memories with full paths (no origin configured yet)
        storage.store(
            title="Memory One",
            tags=["test"],
            summary="First",
            content="Content",
            source="/Users/test/project/docs/file1.md",
        )
        storage.store(
            title="Memory Two",
            tags=["test"],
            summary="Second",
            content="Content",
            source="/Users/test/project/research/file2.md",
        )
        storage.store(
            title="Memory Three",
            tags=["test"],
            summary="Third - different path",
            content="Content",
            source="/Users/test/other/file3.md",
        )

        # Now add an origin
        config.add_origin("project", "/Users/test/project")
        updated = storage.contract_sources_for_origin("project", "/Users/test/project")

        # Should have updated the first two, not the third
        assert len(updated) == 2
        assert "memory-one" in updated
        assert "memory-two" in updated
        assert "memory-three" not in updated

        # Check the stored format
        md1 = (memory_path / "memory-one.md").read_text()
        assert "source: project:docs/file1.md" in md1

        md2 = (memory_path / "memory-two.md").read_text()
        assert "source: project:research/file2.md" in md2

        # Third one should be unchanged
        md3 = (memory_path / "memory-three.md").read_text()
        assert "source: /Users/test/other/file3.md" in md3


if __name__ == "__main__":
    test_slugify()
    test_normalize_tag()
    test_store_and_retrieve()
    test_tag_cooccurrence()
    test_required_tags()
    test_links()
    test_source_without_config()
    test_config_origins()
    test_source_with_config()
    test_update_source()
    test_duplicate_tags_deduped()
    test_path_traversal_rejected()
    test_retroactive_origin_contraction()
    print("All tests passed!")

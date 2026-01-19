"""Configuration management for mcp-ltm."""

from pathlib import Path

import yaml


def default_config() -> dict:
    """Return a fresh default config (deep copy to avoid mutation issues)."""
    return {"origins": {}}


class Config:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path)
        self._data = self._load()

    def _load(self) -> dict:
        """Load config from file, creating with defaults if missing."""
        if not self.config_path.exists():
            return default_config()

        with open(self.config_path) as f:
            data = yaml.safe_load(f) or {}

        # Merge with defaults
        result = default_config()
        result.update(data)
        return result

    def save(self):
        """Save config to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self._data, f, default_flow_style=False, sort_keys=False)

    @property
    def origins(self) -> dict[str, str]:
        """Get origins mapping (name -> path)."""
        return self._data.get("origins", {})

    def add_origin(self, name: str, path: str) -> None:
        """Add or update an origin."""
        if "origins" not in self._data:
            self._data["origins"] = {}
        self._data["origins"][name] = str(Path(path).expanduser().resolve())
        self.save()

    def remove_origin(self, name: str) -> bool:
        """Remove an origin. Returns True if it existed."""
        if name in self._data.get("origins", {}):
            del self._data["origins"][name]
            self.save()
            return True
        return False

    def contract_path(self, full_path: str) -> str:
        """Convert a full path to origin:relative format if possible.

        Returns the shortest representation (prefers origins over full paths).
        """
        full_path = str(Path(full_path).expanduser().resolve())

        best_origin = None
        best_relative = None

        for name, origin_path in self.origins.items():
            origin_path = str(Path(origin_path).resolve())
            if full_path.startswith(origin_path + "/"):
                relative = full_path[len(origin_path) + 1:]
                if best_relative is None or len(relative) < len(best_relative):
                    best_origin = name
                    best_relative = relative

        if best_origin:
            return f"{best_origin}:{best_relative}"
        return full_path

    def expand_path(self, path: str) -> tuple[str, str | None]:
        """Expand an origin:relative path to full path.

        Returns (expanded_path, warning) where warning is set if origin not found.
        """
        if ":" not in path or path.startswith("/"):
            # Already a full path or no origin prefix
            return path, None

        # Check if it looks like a Windows path (C:\...)
        if len(path) > 1 and path[1] == ":" and path[0].isalpha():
            return path, None

        origin_name, relative = path.split(":", 1)

        if origin_name not in self.origins:
            return path, f"Unknown origin '{origin_name}'. Use list_origins to see available origins."

        origin_path = self.origins[origin_name]
        return str(Path(origin_path) / relative), None

"""Reads a `.env` file: one KEY=VALUE per line, `#` starts a comment line."""

from pathlib import Path


def read_env_file(path: Path | None) -> dict[str, str]:
    """The file's values, or nothing if there's no file. Quotes around values are dropped."""
    if path is None or not path.exists():
        return {}
    values = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values

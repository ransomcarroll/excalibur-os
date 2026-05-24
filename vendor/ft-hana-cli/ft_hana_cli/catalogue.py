"""Semantic catalogue loader."""

from pathlib import Path
from typing import List, Optional


def _objects_dir() -> Path:
    return Path(__file__).resolve().parent / "catalogue" / "objects"


def _context_dir() -> Path:
    return Path(__file__).resolve().parent / "catalogue" / "context"


def _filename_for(table: str) -> str:
    return table.replace(" ", "_") + ".md"


def _title_of(path: Path) -> str:
    """First H1 in the markdown file; falls back to the filename stem."""
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("# "):
                    return stripped[2:].strip()
    except OSError:
        pass
    return path.stem.replace("_", " ")


def get_profile(table: str) -> Optional[str]:
    """Return the markdown profile for `table`, or None."""
    path = _objects_dir() / _filename_for(table)
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def list_profiles() -> List[str]:
    """List HANA objects that have catalogue profiles.

    Names come from each file's H1 so the displayed name matches the actual
    HANA object name (which may itself contain underscores).
    """
    d = _objects_dir()
    if not d.is_dir():
        return []
    return [_title_of(p) for p in sorted(d.glob("*.md"))]


def has_profile(table: str) -> bool:
    return (_objects_dir() / _filename_for(table)).is_file()


def get_context(name: str) -> Optional[str]:
    path = _context_dir() / f"{name}.md"
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def list_contexts() -> List[str]:
    d = _context_dir()
    if not d.is_dir():
        return []
    return [p.stem for p in sorted(d.glob("*.md"))]

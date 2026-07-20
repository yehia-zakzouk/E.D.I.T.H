from pathlib import Path


def should_ignore(path: Path, ignored: set[str]) -> bool:
    """
    Returns True if the path should be skipped.
    """
    return any(part in ignored for part in path.parts)
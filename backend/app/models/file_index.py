from dataclasses import dataclass, field
from pathlib import Path

from app.models.file_analysis import FileAnalysis

@dataclass
class FileIndex:

    path: Path

    size: int

    lines: int

    hash: str

    analysis: FileAnalysis | None = None
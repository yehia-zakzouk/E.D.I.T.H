from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from app.models.file_analysis import FileAnalysis

@dataclass
class FileIndex:

    path: Path

    size: int

    lines: int

    hash: str

    last_modified: float

    id: Optional[int] = None

    language: Optional[str] = None

    analysis: Optional[FileAnalysis] = None

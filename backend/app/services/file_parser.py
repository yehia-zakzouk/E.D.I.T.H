from pathlib import Path
import hashlib

from app.core.config import config
from app.models.file_index import FileIndex


class FileParser:

    def parse(self, file: Path) -> FileIndex:

        text = file.read_text(
            encoding=config.parser.encoding,
            errors=config.parser.errors,
        )

        file_hash = hashlib.sha256(
            text.encode("utf-8")
        ).hexdigest()

        return FileIndex(
            path=file,
            size=file.stat().st_size,
            lines=len(text.splitlines()),
            hash=file_hash,
            last_modified=file.stat().st_mtime,
            language=file.suffix.lower().lstrip('.') or None
        )

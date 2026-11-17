from os import PathLike
from typing import Any

class FileType:
    tags: Any

def File(filething: str | PathLike[str]) -> FileType | None: ...

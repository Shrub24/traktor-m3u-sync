from os import PathLike
from typing import Any

class MutagenError(Exception): ...

class FileType:
    info: Any
    tags: Any

def File(filething: str | PathLike[str]) -> FileType | None: ...

from pathlib import Path

from .models.collection import Nml

class TraktorCollection:
    nml: Nml

    def __init__(self, path: Path) -> None: ...
    def save(self) -> None: ...

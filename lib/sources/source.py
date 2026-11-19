from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self


@dataclass(frozen=True)
class Source(ABC):
    @classmethod
    @abstractmethod
    def from_path(cls, path: Path) -> Self | None:
        pass

    @classmethod
    def discover(cls, paths: Sequence[Path]) -> Sequence[Self]:
        """Sources for each path: a file is one source; a directory's direct
        children (files or folders) are one source each. Hidden entries
        (.gitkeep, .DS_Store, ...) are skipped."""
        discovered = []
        for path in paths:
            candidates = [path] if path.is_file() else sorted(path.iterdir()) if path.is_dir() else []
            for candidate in candidates:
                if candidate.name.startswith('.'):
                    continue
                result = cls.from_path(candidate)
                if result:
                    discovered.append(result)
        return discovered

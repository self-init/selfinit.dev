from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Self

from ..build_environment import BuildEnvironment
from .source import Source


@dataclass(frozen=True)
class ContentSource(Source):
    """A post or page on disk: either a lone .md file, or a folder holding
    exactly one .md file plus its assets (images etc.), which are copied
    next to the rendered page so relative links keep working."""
    path: Path
    md_file: Path
    assets: Sequence[Path]      # relative to `path` (empty for a lone file)

    @property
    def is_bundle(self) -> bool:
        return self.path.is_dir()

    @classmethod
    def from_path(cls, path: Path) -> Self | None:
        pretty = BuildEnvironment.pretty_path
        if path.is_dir():
            md_files = sorted(path.glob("*.md"))
            if len(md_files) != 1:
                found = ", ".join(str(pretty(f)) for f in md_files) or "none"
                BuildEnvironment.emit_error(
                    f"{pretty(path)}: page/post folders must contain exactly one .md file (found: {found})."
                )
                return None
            md_file = md_files[0]
            assets = sorted(
                file.relative_to(path) for file in path.rglob("*")
                if file.is_file() and file != md_file
                and not any(part.startswith('.') for part in file.relative_to(path).parts)
            )
            return cls(path=path, md_file=md_file, assets=tuple(assets))
        if path.suffix == ".md":
            return cls(path=path, md_file=path, assets=())
        BuildEnvironment.emit_warning(f"{pretty(path)}: not a .md file or a post/page folder. Skipping.")
        return None

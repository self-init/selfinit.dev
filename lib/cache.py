"""The generated-image cache (site.json "cache", default .cache/).

Social cards and thumbnails are cached by a hash of everything that goes
into them, so unchanged images aren't redrawn on every build. Each build
marks the cache files it uses (by touching them); after a successful build,
files it didn't use, such as images from an older design or a deleted post,
are removed, so the cache doesn't grow forever.
"""
import hashlib
import os
import time
from pathlib import Path

SUBFOLDERS = ('cards', 'thumbs')


def code_version(*files: Path) -> str:
    """A short hash of source files, for cache keys: editing the drawing code
    then redraws everything it made."""
    return hashlib.sha256(b''.join(f.read_bytes() for f in files)).hexdigest()[:16]


def use(path: Path):
    """Mark a cache file as used by this build."""
    try:
        os.utime(path)
    except OSError:
        pass


def prune(cache_dir: Path, since: float) -> int:
    """Delete cache files not used since `since` (the build's start time).
    Files another build used meanwhile are newer, so they're kept."""
    removed = 0
    for sub in SUBFOLDERS:
        folder = cache_dir / sub
        if not folder.is_dir():
            continue
        for f in folder.iterdir():
            try:
                if f.is_file() and f.stat().st_mtime < since:
                    f.unlink()
                    removed += 1
            except OSError:
                pass   # in use or already gone: try again next build
    return removed


def now() -> float:
    # A little slack, so a filesystem with coarse timestamps can't make a
    # file used at the very start of the build look older than the build.
    return time.time() - 2

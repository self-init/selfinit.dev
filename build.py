#!/usr/bin/env python
"""Build the site described by site.json into its output folder.

    python build.py [--config site.json] [--drafts] [--output DIR]

Problems are collected across the whole build and listed together. If there
are any errors, the existing output is left untouched and the exit status
is 1, so CI fails and the dev server keeps serving the last good build.
"""
import argparse
import shutil
import sys
import tempfile
from pathlib import Path

from lib import cache
from lib.build_environment import BuildEnvironment
from lib.config import load_config
from lib.render import Renderer
from lib.site import Site

ROOT = Path(__file__).resolve().parent


def build(config_path: Path, include_drafts=False, output: Path | None = None) -> bool:
    """Build the site; returns True on success."""
    BuildEnvironment.reset(ROOT)
    started = cache.now()

    config = load_config(config_path)
    if config is None:
        return _finish(False)

    site = Site.load(config, include_drafts=include_drafts)
    if BuildEnvironment.has_errors():
        return _finish(False)

    # Render into a fresh temporary sibling folder (unique per build, so two
    # builds at once, e.g. the dev server and a manual build, can't collide),
    # then swap it in with renames, so a failed build never leaves a
    # half-written or emptied output folder.
    out_dir = (output or config.output_dir).resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(prefix=f'{out_dir.name}.tmp-', dir=out_dir.parent))
    try:
        Renderer(site, tmp_dir).run()
        if BuildEnvironment.has_errors():
            return _finish(False)
        _swap_in(tmp_dir, out_dir)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
    cache.prune(config.cache_dir, started)   # drop images this build didn't use

    drafts = f", {site.drafts_skipped} draft(s) skipped" if site.drafts_skipped else ""
    print(
        f"Built {len(site.posts)} post(s), {len(site.pages)} page(s), {len(site.tags)} tag(s) "
        f"and {len(site.series)} series into {BuildEnvironment.pretty_path(out_dir)}/{drafts}."
    )
    return _finish(True)


def _swap_in(new_dir: Path, out_dir: Path):
    """Replace out_dir with new_dir using renames (each is atomic)."""
    old_dir = Path(tempfile.mkdtemp(prefix=f'{out_dir.name}.old-', dir=out_dir.parent))
    old_dir.rmdir()
    for _ in range(3):  # another build may swap in between our two renames
        if out_dir.exists():
            out_dir.rename(old_dir)
        try:
            new_dir.rename(out_dir)
            break
        except OSError:
            if old_dir.exists():
                shutil.rmtree(old_dir, ignore_errors=True)
    shutil.rmtree(old_dir, ignore_errors=True)


def _finish(ok: bool) -> bool:
    w, e = len(BuildEnvironment.warnings), len(BuildEnvironment.errors)
    if not ok:
        print(f"Build failed: {e} error(s), {w} warning(s). Output was not changed.")
    elif w:
        print(f"{w} warning(s).")
    return ok


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--config', type=Path, default=ROOT / 'site.json', help='site config (default: site.json)')
    parser.add_argument('--drafts', action='store_true', help='include posts/pages marked draft: true')
    parser.add_argument('--output', type=Path, help="output folder (default: the config's 'output')")
    args = parser.parse_args()
    sys.exit(0 if build(args.config, args.drafts, args.output) else 1)


if __name__ == '__main__':
    main()

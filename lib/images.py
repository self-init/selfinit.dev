"""Image helpers shared by the Markdown renderer and generated images."""
import hashlib
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageOps, UnidentifiedImageError

from .cache import code_version, use

_NUMBER_RE = re.compile(r'^\s*([0-9.]+)\s*(px)?\s*$')


def image_size(path: Path) -> tuple[int, int] | None:
    """(width, height) in pixels, or None if it can't be determined.
    Raster images are read with Pillow (header only); SVGs from their
    width/height attributes or viewBox."""
    try:
        stat = path.stat()
    except OSError:
        return None
    return _image_size(path.resolve(), stat.st_mtime_ns)


@lru_cache(maxsize=None)
def _image_size(path: Path, _mtime: int) -> tuple[int, int] | None:
    if path.suffix.lower() == '.svg':
        return _svg_size(path)
    try:
        with Image.open(path) as image:
            return image.size
    except (UnidentifiedImageError, OSError):
        return None


def _svg_size(path: Path) -> tuple[int, int] | None:
    try:
        root = ElementTree.parse(path).getroot()
    except (ElementTree.ParseError, OSError):
        return None
    width, height = (_svg_length(root.get(a)) for a in ('width', 'height'))
    if width and height:
        return round(width), round(height)
    view_box = (root.get('viewBox') or '').replace(',', ' ').split()
    if len(view_box) == 4:
        try:
            w, h = float(view_box[2]), float(view_box[3])
        except ValueError:
            return None
        if w > 0 and h > 0:
            return round(w), round(h)
    return None


def _svg_length(value: str | None) -> float | None:
    """'640', '640px' -> 640.0. Percentages and other units -> None."""
    match = _NUMBER_RE.match(value or '')
    return float(match.group(1)) if match else None


# --- Thumbnails --------------------------------------------------------------

THUMB_SIZE = (180, 120)          # largest displayed size beside posts (3:2)
THUMB_SCALE = 2                  # stored at 2x for sharp high-DPI screens
THUMB_LARGE_WIDTH = 780          # full-width version for phones (3:2)
_CODE_VERSION = code_version(Path(__file__))   # editing this file redraws cached thumbnails


def write_thumbnail(source: Path, target: Path, cache_dir: Path,
                    size: tuple[int, int] = (THUMB_SIZE[0] * THUMB_SCALE, THUMB_SIZE[1] * THUMB_SCALE)) -> bool:
    """Make a 3:2 WebP thumbnail of `source` at `target` (cached by the
    source's content). Photos and screenshots (fully opaque) are
    centre-cropped to fill it; graphics with transparency (logos, cut-out
    product shots) are scaled to fit whole, so nothing important is cut
    off. Animated images use their first frame. Returns False if the image
    can't be read."""
    data = source.read_bytes()
    key = hashlib.sha256(data + f'{size}{_CODE_VERSION}'.encode()).hexdigest()[:32]
    cached = cache_dir / 'thumbs' / f'{key}.webp'
    if not cached.is_file():
        try:
            with Image.open(source) as image:
                image.seek(0)
                frame = image.convert('RGBA')
        except (UnidentifiedImageError, OSError, EOFError):
            return False
        if frame.getchannel('A').getextrema()[0] < 255:      # has transparency
            fitted = ImageOps.contain(frame, size, Image.Resampling.LANCZOS)
            thumb = Image.new('RGBA', size, (0, 0, 0, 0))
            thumb.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
        else:
            thumb = ImageOps.fit(frame, size, Image.Resampling.LANCZOS)
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_name(f'{cached.stem}.{os.getpid()}.tmp.webp')  # unique per build process
        thumb.save(tmp, 'WEBP', quality=82, method=6)
        tmp.replace(cached)
    use(cached)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, target)
    return True

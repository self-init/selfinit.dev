"""Open Graph "social cards": 1200x630 PNGs shown when a link to the site is
shared (LinkedIn, Discord, Slack, Mastodon, X, ...).

Dark variant of the site style: a near-black background, the site's blue
gradient band along the top, the logo (site.json icons.logo) in a faint
shade, cropped by the right edge like the header logo, and IBM Plex Mono for
the text (as on the site).

Cards are cached in <cache>/cards/ by a hash of everything drawn on them,
so unchanged cards aren't redrawn on every build.
"""

import hashlib
import json
import os
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .build_environment import BuildEnvironment
from .cache import code_version, use
from .svgpath import Shape, draw_shape, load_shape

WIDTH, HEIGHT = 1200, 630
SCALE = 2  # draw at 2x, then downsample for smooth edges
# Cached images are keyed on this code (and lib/svgpath.py), so any change
# to the drawing or layout here redraws them on the next build.
_CODE_VERSION = code_version(Path(__file__), Path(__file__).parent / "svgpath.py")

FONT_FILES = {
    "title": "IBMPlexMono-Bold.ttf",
    "medium": "IBMPlexMono-Medium.ttf",
    "regular": "IBMPlexMono-Regular.ttf",
}

BG_TOP, BG_BOTTOM = (29, 32, 37), (15, 17, 20)
BAND_TOP, BAND_BOTTOM = (63, 127, 200), (18, 61, 112)  # the site's --grad-accent
LOGO = (35, 41, 50)  # the faint logo behind the text
TITLE = (243, 245, 247)
KICKER = (159, 176, 195)
ACCENT = (127, 176, 232)  # light site blue, readable on dark
MUTED = (154, 163, 173)

PAD_X = 80

# The logo on cards (and, scaled by height, on placeholder thumbnails): its
# centre's distance from the right edge, its centre's height, and its size.
LOGO_FROM_RIGHT, LOGO_CENTER_Y, LOGO_SIZE = 190, 450, 700
TEXT_WIDTH = 900


@dataclass(frozen=True)
class Card:
    kicker: str  # small line at the top (the site title)
    title: str
    accent_line: str = ""  # e.g. "Hecate OS · Part 2 of 2"
    detail_line: str = ""  # e.g. "October 28, 2026 · 6 min read"
    domain: str = ""
    large: bool = False  # the site card: a big title, centred, no kicker


def write_card(
    card: Card, target: Path, fonts_dir: Path, cache_dir: Path, logo: Path | None = None
) -> bool:
    """Render (or reuse from cache) the card as a PNG at `target`."""
    fonts = {key: fonts_dir / name for key, name in FONT_FILES.items()}
    missing = [
        str(BuildEnvironment.pretty_path(p)) for p in fonts.values() if not p.is_file()
    ]
    if missing:
        BuildEnvironment.emit_error(
            f"social cards need these font files: {', '.join(missing)} "
            f'(or set "social_cards": false in site.json).'
        )
        return False

    key = hashlib.sha256(
        json.dumps(
            {
                "card": asdict(card),
                "version": _CODE_VERSION,
                "fonts": {k: p.stat().st_mtime_ns for k, p in fonts.items()},
                "logo": _file_hash(logo),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()[:32]
    cached = cache_dir / "cards" / f"{key}.png"
    if not cached.is_file():
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_name(
            f"{cached.stem}.{os.getpid()}.tmp.png"
        )  # unique per build process
        _draw(card, fonts, _shape(logo)).save(tmp, optimize=True)
        tmp.replace(cached)
    use(cached)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, target)
    return True


PLACEHOLDER_LOGO = (50, 59, 72)  # a little brighter than on cards: tiles are small


def _file_hash(path: Path | None) -> str:
    return (
        hashlib.sha256(path.read_bytes()).hexdigest() if path and path.is_file() else ""
    )


def _shape(logo: Path | None) -> Shape | None:
    if logo is None:
        return None
    shape = load_shape(logo)
    if shape is None:
        BuildEnvironment.emit_warning(
            f"{BuildEnvironment.pretty_path(logo)}: no <path> shapes to draw on social cards "
            f"and thumbnails (they're drawn without the logo)."
        )
    return shape


def write_placeholder(
    target: Path, size: tuple[int, int], cache_dir: Path, logo: Path | None = None
):
    """Thumbnail for posts without an image: the card background, blue band
    and logo (cropped at the right, like the header logo), as WebP."""
    key = hashlib.sha256(
        f"placeholder{size}{_CODE_VERSION}{_file_hash(logo)}".encode()
    ).hexdigest()[:32]
    cached = cache_dir / "thumbs" / f"{key}.webp"
    if not cached.is_file():
        w, h = size[0] * SCALE, size[1] * SCALE
        image = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(image)
        _vertical_gradient(draw, (0, 0, w, h), BG_TOP, BG_BOTTOM)
        shape = _shape(logo)
        if shape:
            # Placed as on the cards, scaled to the tile's height.
            k = h / HEIGHT
            draw_shape(
                image,
                shape,
                (round(w - LOGO_FROM_RIGHT * k), round(LOGO_CENTER_Y * k)),
                round(LOGO_SIZE * k),
                PLACEHOLDER_LOGO,
            )
        _vertical_gradient(
            draw, (0, 0, w, max(2 * SCALE, round(h * 0.03))), BAND_TOP, BAND_BOTTOM
        )
        image = image.resize(size, Image.Resampling.LANCZOS)
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_name(f"{cached.stem}.{os.getpid()}.tmp.webp")
        image.save(tmp, "WEBP", quality=85, method=6)
        tmp.replace(cached)
    use(cached)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cached, target)


def _draw(card: Card, fonts: dict[str, Path], logo: Shape | None) -> Image.Image:
    s = SCALE
    image = Image.new("RGB", (WIDTH * s, HEIGHT * s))
    draw = ImageDraw.Draw(image)

    _vertical_gradient(draw, (0, 0, WIDTH * s, HEIGHT * s), BG_TOP, BG_BOTTOM)
    if logo:
        # Large and cropped by the right and bottom edges; the top of the
        # logo (the keep's battlements) stays clear of the band.
        draw_shape(
            image,
            logo,
            ((WIDTH - LOGO_FROM_RIGHT) * s, LOGO_CENTER_Y * s),
            LOGO_SIZE * s,
            LOGO,
        )
    _vertical_gradient(draw, (0, 0, WIDTH * s, 12 * s), BAND_TOP, BAND_BOTTOM)

    def font(kind, size):
        return ImageFont.truetype(str(fonts[kind]), size * s)

    full_width = (WIDTH - 2 * PAD_X) * s
    if card.large:
        _draw_large(card, draw, font)
        return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)

    # Top: site title.
    kicker_font = font("medium", 30)
    draw.text(
        (PAD_X * s, 64 * s),
        _fit(card.kicker, kicker_font, full_width),
        font=kicker_font,
        fill=KICKER,
    )

    # Bottom: series / date lines on the left, domain on the right. Lines
    # too long for the space are cut short with an ellipsis.
    bottom = HEIGHT - 72
    detail_font, accent_font, domain_font = (
        font("regular", 28),
        font("medium", 30),
        font("medium", 28),
    )
    domain_width = domain_font.getlength(card.domain) + 40 * s if card.domain else 0
    if card.detail_line:
        # Up to two lines when there's no accent line; otherwise one. The
        # bottom line leaves room for the domain.
        width = full_width - domain_width
        lines = _wrap(card.detail_line, detail_font, width)
        if card.accent_line or len(lines) == 1:
            lines = [_fit(card.detail_line, detail_font, width)]
        elif len(lines) > 2:
            lines = _ellipsize(lines[:2], detail_font, width)
        for line in reversed(lines):
            draw.text(
                (PAD_X * s, bottom * s), line, font=detail_font, fill=MUTED, anchor="ls"
            )
            bottom -= 40
        bottom -= 6
    if card.accent_line:
        line = _fit(
            card.accent_line,
            accent_font,
            full_width - (0 if card.detail_line else domain_width),
        )
        draw.text(
            (PAD_X * s, bottom * s), line, font=accent_font, fill=ACCENT, anchor="ls"
        )
        bottom -= 46
    if card.domain:
        draw.text(
            ((WIDTH - PAD_X) * s, (HEIGHT - 72) * s),
            card.domain,
            font=domain_font,
            fill=MUTED,
            anchor="rs",
        )

    # Title: the largest size (76 -> 44px) that fits in 4 lines, vertically
    # centred between the top line and the bottom lines.
    top, bottom_limit = 130, bottom - 30
    for size in range(76, 43, -4):
        title_font = font("title", size)
        lines = _wrap(card.title, title_font, TEXT_WIDTH * s)
        line_height = round(size * 1.14)
        if len(lines) <= 4 and len(lines) * line_height <= bottom_limit - top:
            break
    else:
        lines = _ellipsize(lines[:4], title_font, TEXT_WIDTH * s)
    block = len(lines) * line_height
    y = top + max(0, (bottom_limit - top - block) // 2)
    for line in lines:
        draw.text(
            (PAD_X * s, (y + size) * s), line, font=title_font, fill=TITLE, anchor="ls"
        )
        y += line_height

    return image.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS)


def _draw_large(card: Card, draw, font):
    """The site card's text: a big one-line title, centred vertically, and
    the domain at the bottom right as on post cards."""
    s = SCALE
    width = TEXT_WIDTH * s
    for size in range(132, 63, -8):  # largest size that fits on one line
        title_font = font("title", size)
        if title_font.getlength(card.title) <= width:
            break
    title = _fit(card.title, title_font, width)
    # Centre the letters themselves (not the line box) in the space below
    # the band: the ink's top and bottom relative to the baseline.
    _, ink_top, _, ink_bottom = title_font.getbbox(title, anchor="ls")
    middle = (12 + HEIGHT) / 2 * s
    baseline = middle - (ink_top + ink_bottom) / 2
    draw.text((PAD_X * s, baseline), title, font=title_font, fill=TITLE, anchor="ls")

    if card.domain:
        domain_font = font("medium", 28)
        draw.text(((WIDTH - PAD_X) * s, (HEIGHT - 72) * s), card.domain,
                  font=domain_font, fill=MUTED, anchor="rs")


def _vertical_gradient(draw, box, top, bottom):
    x0, y0, x1, y1 = box
    height = max(1, y1 - y0 - 1)
    for y in range(y0, y1):
        t = (y - y0) / height
        draw.line(
            [(x0, y), (x1, y)],
            fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)),
        )


def _wrap(text: str, font, width: float) -> list[str]:
    """Greedy word wrap; words wider than a line are split by character."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if font.getlength(candidate) <= width:
            current = candidate
            continue
        if current:
            lines.append(current)
        while font.getlength(word) > width:
            cut = max(
                1,
                next(
                    i
                    for i in range(len(word), 0, -1)
                    if font.getlength(word[:i]) <= width
                ),
            )
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines or [""]


def _ellipsize(lines: list[str], font, width: float) -> list[str]:
    last = lines[-1]
    while last and font.getlength(last + "…") > width:
        last = last[:-1].rstrip()
    return lines[:-1] + [last + "…"]


def _fit(text: str, font, width: float) -> str:
    """One line of text, cut short with an ellipsis if wider than `width`."""
    return text if font.getlength(text) <= width else _ellipsize([text], font, width)[0]

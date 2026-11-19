"""Draw a simple SVG logo with Pillow (which can't render SVG itself).

Reads the viewBox and every <path d="..."> of the file, flattens the paths
into polygons and fills them into a mask (even-odd, so cut-outs work).
Supports the path commands logos made of lines, arcs and curves use:
M L H V A C Q Z, absolute and relative. Fills, strokes, transforms and
other shapes (<circle>, <rect>, ...) are ignored: draw the logo as paths.
"""
import math
import re
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, ImageChops, ImageDraw

_TOKEN = re.compile(r'[MmLlHhVvAaCcQqZz]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
CURVE_STEPS = 24     # line segments per curve
ARC_STEP = math.radians(3)


@dataclass(frozen=True)
class Shape:
    viewbox: tuple[float, float, float, float]      # min-x, min-y, width, height
    polygons: tuple[tuple[tuple[float, float], ...], ...]


def load_shape(svg: Path) -> Shape | None:
    """The logo's outline, or None if the file has no usable paths."""
    try:
        root = ElementTree.parse(svg).getroot()
    except (ElementTree.ParseError, OSError):
        return None
    numbers = [float(n) for n in re.split(r'[\s,]+', root.get('viewBox', '').strip()) if n]
    if len(numbers) != 4:
        return None
    polygons = []
    for element in root.iter():
        if element.tag.rsplit('}', 1)[-1] == 'path' and element.get('d'):
            polygons.extend(_flatten(element.get('d')))
    polygons = [p for p in polygons if len(p) >= 3]
    return Shape(tuple(numbers), tuple(polygons)) if polygons else None


def render_mask(shape: Shape, height: int) -> Image.Image:
    """The shape filled white on black, `height` pixels tall."""
    min_x, min_y, vw, vh = shape.viewbox
    scale = height / vh
    mask = Image.new('L', (max(1, round(vw * scale)), height), 0)
    for polygon in shape.polygons:
        layer = Image.new('L', mask.size, 0)
        ImageDraw.Draw(layer).polygon([((x - min_x) * scale, (y - min_y) * scale) for x, y in polygon], fill=255)
        mask = ImageChops.difference(mask, layer)   # even-odd: overlaps cancel
    return mask


def draw_shape(image: Image.Image, shape: Shape, center: tuple[int, int], height: int, color):
    """Fill the shape onto `image`, centred at `center` (may run off the edges)."""
    mask = render_mask(shape, height)
    x = round(center[0] - mask.width / 2)
    y = round(center[1] - mask.height / 2)
    image.paste(Image.new('RGB', mask.size, color), (x, y), mask)


def _flatten(d: str) -> list[list[tuple[float, float]]]:
    tokens = _TOKEN.findall(d)
    polygons, current = [], []
    x = y = start_x = start_y = 0.0
    i, command = 0, None

    def number():
        nonlocal i
        value = float(tokens[i])
        i += 1
        return value

    while i < len(tokens):
        if tokens[i].isalpha():
            command = tokens[i]
            i += 1
        elif command is None:
            break
        rel = command.islower()
        op = command.upper()
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if op == 'Z':
            if current:
                polygons.append(current)
            current = []
            x, y = start_x, start_y
            continue
        if op == 'M':
            if current:
                polygons.append(current)
            x, y = ox + number(), oy + number()
            start_x, start_y = x, y
            current = [(x, y)]
            command = 'l' if rel else 'L'   # further pairs are line-tos
        elif op == 'L':
            x, y = ox + number(), oy + number()
            current.append((x, y))
        elif op == 'H':
            x = ox + number()
            current.append((x, y))
        elif op == 'V':
            y = oy + number()
            current.append((x, y))
        elif op == 'C':
            x1, y1, x2, y2 = ox + number(), oy + number(), ox + number(), oy + number()
            ex, ey = ox + number(), oy + number()
            for k in range(1, CURVE_STEPS + 1):
                t = k / CURVE_STEPS
                u = 1 - t
                current.append((u**3 * x + 3 * u * u * t * x1 + 3 * u * t * t * x2 + t**3 * ex,
                                u**3 * y + 3 * u * u * t * y1 + 3 * u * t * t * y2 + t**3 * ey))
            x, y = ex, ey
        elif op == 'Q':
            x1, y1, ex, ey = ox + number(), oy + number(), ox + number(), oy + number()
            for k in range(1, CURVE_STEPS + 1):
                t = k / CURVE_STEPS
                u = 1 - t
                current.append((u * u * x + 2 * u * t * x1 + t * t * ex, u * u * y + 2 * u * t * y1 + t * t * ey))
            x, y = ex, ey
        elif op == 'A':
            rx, ry, rotation = number(), number(), number()
            large, sweep = number() != 0, number() != 0
            ex, ey = ox + number(), oy + number()
            current.extend(_arc(x, y, rx, ry, rotation, large, sweep, ex, ey))
            x, y = ex, ey
        else:
            break   # unsupported command: stop rather than draw something wrong
    if current:
        polygons.append(current)
    return polygons


def _arc(x1, y1, rx, ry, rotation, large, sweep, x2, y2):
    """Points along an SVG elliptical arc (SVG spec, appendix B.2.4)."""
    if rx == 0 or ry == 0 or (x1, y1) == (x2, y2):
        return [(x2, y2)]
    rx, ry = abs(rx), abs(ry)
    phi = math.radians(rotation)
    cos_phi, sin_phi = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    x1p = cos_phi * dx + sin_phi * dy
    y1p = -sin_phi * dx + cos_phi * dy
    scale = x1p**2 / rx**2 + y1p**2 / ry**2
    if scale > 1:                       # radii too small: scale them up
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx**2 * ry**2 - rx**2 * y1p**2 - ry**2 * x1p**2
    den = rx**2 * y1p**2 + ry**2 * x1p**2
    factor = math.sqrt(max(0.0, num / den)) * (-1 if large == sweep else 1)
    cxp, cyp = factor * rx * y1p / ry, -factor * ry * x1p / rx
    cx = cos_phi * cxp - sin_phi * cyp + (x1 + x2) / 2
    cy = sin_phi * cxp + cos_phi * cyp + (y1 + y2) / 2

    def angle(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a

    theta1 = angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    delta = angle((x1p - cxp) / rx, (y1p - cyp) / ry, (-x1p - cxp) / rx, (-y1p - cyp) / ry)
    if not sweep and delta > 0:
        delta -= 2 * math.pi
    elif sweep and delta < 0:
        delta += 2 * math.pi
    steps = max(2, math.ceil(abs(delta) / ARC_STEP))
    points = []
    for k in range(1, steps + 1):
        t = theta1 + delta * k / steps
        px, py = rx * math.cos(t), ry * math.sin(t)
        points.append((cos_phi * px - sin_phi * py + cx, sin_phi * px + cos_phi * py + cy))
    return points

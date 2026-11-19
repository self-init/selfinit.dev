"""Shared parsing for Markdown content (posts and pages)."""
import re

import frontmatter
import yaml

from ..build_environment import BuildEnvironment
from ..fields import get_str
from ..sources.content_source import ContentSource

H1_RE = re.compile(r'^#\s+(.+?)\s*#*\s*$', re.MULTILINE)


def load_markdown(src: ContentSource) -> frontmatter.Post | None:
    try:
        return frontmatter.load(src.md_file)
    except (yaml.YAMLError, UnicodeDecodeError, ValueError) as e:
        BuildEnvironment.emit_error(f"{BuildEnvironment.pretty_path(src.md_file)}: could not read frontmatter: {e}")
        return None


def strip_title_heading(content: str, title: str) -> str:
    """Templates always show the title, so drop a `# Heading` that just
    repeats it. A first heading that differs from the title is kept."""
    h1 = H1_RE.search(content)
    if h1 and h1.group(1) == title:
        return content[:h1.start()] + content[h1.end():]
    return content


def og_image(meta, src: ContentSource, where: str) -> str | None:
    """Optional `og_image:` frontmatter: an image (relative to the post, e.g.
    ./preview.png, or an absolute https URL) to use for social previews
    instead of the generated card."""
    value = get_str(meta, 'og_image', where, default=None)
    if value is None or value.startswith(('http://', 'https://')):
        return value
    base = src.path if src.is_bundle else src.md_file.parent
    if not (base / value).is_file():
        BuildEnvironment.emit_error(f"{where}: og_image '{value}' not found.")
        return None
    return value.removeprefix('./')


def thumbnail(meta, src: ContentSource, where: str) -> str | bool | None:
    """Optional `thumbnail:` frontmatter for post lists: an image next to the
    post (e.g. ./diagram.png), or `false` for no thumbnail. Unset: the
    post's first image is used."""
    value = meta.get('thumbnail')
    if value is None or value is False:
        return value
    if not isinstance(value, str) or not value.strip():
        BuildEnvironment.emit_error(f"{where}: 'thumbnail' must be an image path next to the post, or false.")
        return None
    base = src.path if src.is_bundle else src.md_file.parent
    if not (base / value).is_file():
        BuildEnvironment.emit_error(f"{where}: thumbnail '{value}' not found.")
        return None
    return value.strip().removeprefix('./')
